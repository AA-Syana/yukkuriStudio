import io

import pytest

from app.services.video_probe import VideoInfo, VideoProbeError, parse_probe_output


@pytest.fixture
def fake_probe(monkeypatch):
    monkeypatch.setattr(
        "app.api.videos.probe_video", lambda path: VideoInfo(duration_ms=12345, width=1920, height=1080, fps=29.97)
    )


def _upload(client, pid, name="a.mp4", data=b"dummy"):
    return client.post(f"/api/projects/{pid}/video", files={"file": (name, io.BytesIO(data), "video/mp4")})


def test_upload_and_get_video(client, project, fake_probe):
    res = _upload(client, project["id"])
    assert res.status_code == 201
    assert res.json()["duration_ms"] == 12345 and res.json()["width"] == 1920

    assert client.get(f"/api/projects/{project['id']}/video").json()["original_filename"] == "a.mp4"
    stream = client.get(f"/api/projects/{project['id']}/video/stream")
    assert stream.status_code == 200 and stream.content == b"dummy"


def test_reupload_replaces_video(client, project, fake_probe):
    _upload(client, project["id"], data=b"one")
    _upload(client, project["id"], data=b"two")
    assert client.get(f"/api/projects/{project['id']}/video/stream").content == b"two"


def test_rejects_non_mp4(client, project):
    assert _upload(client, project["id"], name="a.avi").status_code == 415


def test_video_missing_returns_404(client, project):
    assert client.get(f"/api/projects/{project['id']}/video").status_code == 404


def test_probe_failure_is_422_and_file_removed(client, project, monkeypatch):
    def boom(path):
        raise VideoProbeError("壊れた動画")

    monkeypatch.setattr("app.api.videos.probe_video", boom)
    assert _upload(client, project["id"]).status_code == 422
    assert client.get(f"/api/projects/{project['id']}/video").status_code == 404


def test_parse_probe_output():
    info = parse_probe_output(
        {
            "format": {"duration": "10.5"},
            "streams": [{"codec_type": "video", "width": 1280, "height": 720, "avg_frame_rate": "30000/1001"}],
        }
    )
    assert (info.duration_ms, info.width, info.height, info.fps) == (10500, 1280, 720, 29.97)
    with pytest.raises(VideoProbeError):
        parse_probe_output({"format": {"duration": "1"}, "streams": [{"codec_type": "audio"}]})
