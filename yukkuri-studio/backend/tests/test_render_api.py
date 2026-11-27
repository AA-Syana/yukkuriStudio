"""MP4書き出しのAPI(ジョブ・状態・ダウンロード・所有者チェック)。実際にFFmpegを動かすので、
FFmpeg・日本語フォントが無い環境では読み飛ばす。"""
import shutil
import subprocess

import pytest
from helpers import dialogues, job, parse, project_character

from app.core.config import settings
from app.fonts import find_font

pytestmark = pytest.mark.skipif(
    shutil.which(settings.ffmpeg_path) is None or shutil.which("ffprobe") is None or find_font() is None,
    reason="FFmpeg または日本語フォントが無い環境",
)

TEXT = "[霊夢]\nこんにちは\n[魔理沙]\nやあ\n"


def _setup(client, project, script, voices=True, layout=True):
    for name in ("霊夢", "魔理沙"):
        c = project_character(client, project["id"], name)
        res = client.post(f"/api/characters/{c['id']}/generate-image", json={"expression": None})
        assert job(client, res.json()["id"])["status"] == "succeeded"
    ds = parse(client, script["id"], TEXT)["dialogues"]
    if voices:
        for d in ds:
            res = client.post(f"/api/dialogues/{d['id']}/regenerate")
            assert job(client, res.json()["id"])["status"] == "succeeded"
    if layout:
        assert client.post(f"/api/scripts/{script['id']}/layout", json={}).status_code == 200
    return ds


def _render(client, project, **body):
    res = client.post(f"/api/projects/{project['id']}/render", json={"height": 480, **body})
    assert res.status_code == 202, res.text
    return job(client, res.json()["id"])


def _status(client, project):
    return client.get(f"/api/projects/{project['id']}/render-status").json()


def test_render_produces_a_downloadable_mp4_matching_the_timeline(client, project, script, tmp_path):
    _setup(client, project, script)
    done = _render(client, project)
    assert done["status"] == "succeeded" and done["progress"] == 100, done

    last = _status(client, project)["last_success"]
    assert last["script_id"] == script["id"] and last["size_bytes"] > 1000 and (last["width"], last["height"]) == (854, 480)
    assert last["warnings"] == []

    res = client.get(f"/api/projects/{project['id']}/download")
    assert res.status_code == 200 and res.headers["content-type"] == "video/mp4" and res.content[4:8] == b"ftyp"
    assert ".mp4" in res.headers["content-disposition"]
    mp4 = tmp_path / "out.mp4"
    mp4.write_bytes(res.content)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                         capture_output=True, text=True, check=True).stdout
    total_ms = client.get(f"/api/scripts/{script['id']}/timeline").json()["total_ms"]
    assert abs(float(out) * 1000 - total_ms) < 300  # 書き出した長さが、タイムラインの長さと一致する


def test_render_warns_about_silent_dialogues(client, project, script):
    _setup(client, project, script, voices=False)
    assert _render(client, project)["status"] == "succeeded"
    assert any("無音" in w for w in _status(client, project)["last_success"]["warnings"])


def test_render_status_before_and_between_renders(client, project, script):
    _setup(client, project, script)
    assert _status(client, project) == {"job": None, "last_success": None}
    first = _render(client, project)
    second = _render(client, project, include_original_audio=False)
    status = _status(client, project)
    assert status["job"]["id"] == second["id"] and status["last_success"]["job_id"] == second["id"]
    assert first["id"] != second["id"]
    assert client.get(f"/api/projects/{project['id']}/download").status_code == 200


def test_render_needs_a_placed_timeline(client, project, script):
    _setup(client, project, script, layout=False)
    res = client.post(f"/api/projects/{project['id']}/render", json={})
    assert res.status_code == 422 and "タイミング" in res.json()["detail"]


def test_render_validates_options(client, project, script):
    _setup(client, project, script)
    url = f"/api/projects/{project['id']}/render"
    assert client.post(url, json={"height": 999}).status_code == 422
    assert client.post(url, json={"original_volume": 5}).status_code == 422
    assert client.post(url, json={"script_id": "nope"}).status_code == 404


def test_render_reports_missing_ffmpeg(client, project, script, monkeypatch):
    _setup(client, project, script)
    monkeypatch.setattr(settings, "ffmpeg_path", "no-such-ffmpeg-binary")
    res = client.post(f"/api/projects/{project['id']}/render", json={})
    assert res.status_code == 503 and "FFmpeg" in res.json()["detail"]


def test_download_before_any_render_is_404(client, project, script):
    _setup(client, project, script)
    assert client.get(f"/api/projects/{project['id']}/download").status_code == 404


def test_render_uses_edited_subtitle_and_survives_missing_character_images(client, project, script):
    # 画像を作らずに書き出す: 立ち絵は仮の枠になり、警告が出る
    for name in ("霊夢", "魔理沙"):
        project_character(client, project["id"], name)
    parse(client, script["id"], TEXT)
    client.post(f"/api/scripts/{script['id']}/layout", json={})
    item = next(i for i in client.get(f"/api/scripts/{script['id']}/timeline").json()["items"] if i["track_type"] == "subtitle")
    assert client.put(f"/api/timeline-items/{item['id']}", json={"text_override": "編集した字幕", "font_size": 60}).status_code == 200
    assert _render(client, project)["status"] == "succeeded"
    assert any("仮の枠" in w for w in _status(client, project)["last_success"]["warnings"])


def test_render_endpoints_are_private_to_the_owner(client, other, project, script):
    _setup(client, project, script)
    _render(client, project)
    pid = project["id"]
    assert other.post(f"/api/projects/{pid}/render", json={}).status_code == 404
    assert other.get(f"/api/projects/{pid}/render-status").status_code == 404
    assert other.get(f"/api/projects/{pid}/download").status_code == 404
    # 他人の台本IDを指定しても書き出せない
    other_project = other.post("/api/projects", json={"title": "別"}).json()
    assert other.post(f"/api/projects/{other_project['id']}/render", json={"script_id": script["id"]}).status_code == 404
