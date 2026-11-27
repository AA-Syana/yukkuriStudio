from app.constants import EMOTIONS
from helpers import dialogues, job, library_character, parse, project_character


def _setup(client, project, script, text="[霊夢]\nこんにちは", name="霊夢"):
    char = project_character(client, project["id"], name)
    return char, parse(client, script["id"], text)["dialogues"]


# ---------------- 音声 ----------------
def test_generate_voice_for_one_dialogue(client, project, script):
    _, ds = _setup(client, project, script)
    res = client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    assert res.status_code == 202 and res.json()["project_id"] == project["id"]
    done = job(client, res.json()["id"])
    assert done["status"] == "succeeded" and done["progress"] == 100

    d = dialogues(client, script["id"])[0]
    assert d["generation_status"] == "done" and d["audio_duration_ms"] > 0 and d["audio_stale"] is False
    f = client.get(f"/api/assets/{d['audio_asset_id']}/file")
    assert f.status_code == 200 and f.headers["content-type"] == "audio/wav" and f.content[:4] == b"RIFF"
    assert "sandbox" in f.headers["content-security-policy"] and f.headers["x-content-type-options"] == "nosniff"


def test_voice_follows_the_project_copy_not_the_library(client, project, script):
    """声の設定は、プロジェクト側(編集画面)のキャラクターが優先される。"""
    lib = library_character(client, "霊夢")
    copy = client.post(f"/api/projects/{project['id']}/characters", json={"source_character_id": lib["id"]}).json()
    d = parse(client, script["id"], "[霊夢]\nこんにちは、今日もいい天気ですね")["dialogues"][0]
    client.post(f"/api/dialogues/{d['id']}/regenerate")
    normal_ms = dialogues(client, script["id"])[0]["audio_duration_ms"]

    # ライブラリの声を変えても、既存の音声は古い扱いにならない(プロジェクト側の状態が優先)
    client.put(f"/api/characters/{lib['id']}", json={"voice_settings": {"speed": 2.0}})
    assert dialogues(client, script["id"])[0]["audio_stale"] is False

    # プロジェクト側のキャラクターを変えると、古い音声になり、再生成で反映される
    client.put(f"/api/projects/{project['id']}/characters/{copy['id']}", json={"voice_settings": {"speed": 2.0}})
    assert dialogues(client, script["id"])[0]["audio_stale"] is True
    client.post(f"/api/dialogues/{d['id']}/regenerate")
    after = dialogues(client, script["id"])[0]
    assert after["audio_duration_ms"] < normal_ms and after["audio_stale"] is False


def test_regenerate_replaces_old_audio(client, project, script):
    _, ds = _setup(client, project, script)
    client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    old_id = dialogues(client, script["id"])[0]["audio_asset_id"]
    client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    assert dialogues(client, script["id"])[0]["audio_asset_id"] != old_id
    assert client.get(f"/api/assets/{old_id}/file").status_code == 404


def test_text_edit_makes_audio_stale_and_generate_targets_only_stale(client, project, script):
    project_character(client, project["id"], "霊夢")
    a, _b = parse(client, script["id"], "[霊夢]\n一つ目\n二つ目")["dialogues"]
    client.post(f"/api/dialogues/{a['id']}/regenerate")
    a_audio = dialogues(client, script["id"])[0]["audio_asset_id"]

    client.put(f"/api/dialogues/{a['id']}", json={"text": "一つ目を修正"})
    assert dialogues(client, script["id"])[0]["audio_stale"] is True

    started = client.post(f"/api/projects/{project['id']}/generate", json={"script_id": script["id"]}).json()
    assert job(client, started["id"])["status"] == "succeeded"
    ds = dialogues(client, script["id"])
    assert all(d["audio_asset_id"] and d["audio_stale"] is False for d in ds)
    assert ds[0]["audio_asset_id"] != a_audio  # 古かった分は作り直された

    before = [d["audio_asset_id"] for d in ds]  # 全部最新なら、何も作り直さない
    client.post(f"/api/projects/{project['id']}/generate", json={"script_id": script["id"]})
    assert [d["audio_asset_id"] for d in dialogues(client, script["id"])] == before


def test_voice_failure_then_retry(client, project, script, providers, monkeypatch):
    _, ds = _setup(client, project, script)

    def boom(req):
        raise RuntimeError("接続できません")

    monkeypatch.setattr(providers.voice, "synthesize", boom)
    started = client.post(f"/api/dialogues/{ds[0]['id']}/regenerate").json()
    failed = job(client, started["id"])
    assert failed["status"] == "failed" and "接続できません" in failed["error"]
    assert dialogues(client, script["id"])[0]["generation_status"] == "failed"

    monkeypatch.undo()
    assert client.post(f"/api/generation-jobs/{started['id']}/retry").status_code == 202
    assert job(client, started["id"])["status"] == "succeeded"
    assert dialogues(client, script["id"])[0]["generation_status"] == "done"


def test_retry_only_for_failed_jobs(client, project, script):
    _, ds = _setup(client, project, script)
    started = client.post(f"/api/dialogues/{ds[0]['id']}/regenerate").json()
    assert client.post(f"/api/generation-jobs/{started['id']}/retry").status_code == 409
    assert client.post("/api/generation-jobs/unknown/retry").status_code == 404


def test_generate_all_partial_failure_keeps_successes(client, project, script, providers, monkeypatch):
    project_character(client, project["id"], "霊夢")
    parse(client, script["id"], "[霊夢]\n成功する\n失敗する")
    original = providers.voice.synthesize

    def flaky(req):
        if "失敗" in req.text:
            raise RuntimeError("x")
        return original(req)

    monkeypatch.setattr(providers.voice, "synthesize", flaky)
    started = client.post(f"/api/projects/{project['id']}/generate", json={"script_id": script["id"]}).json()
    result = job(client, started["id"])
    assert result["status"] == "failed" and "1件" in result["error"]
    ds = dialogues(client, script["id"])
    assert ds[0]["audio_asset_id"] and ds[1]["audio_asset_id"] is None

    monkeypatch.undo()
    client.post(f"/api/generation-jobs/{started['id']}/retry")
    assert all(d["audio_asset_id"] for d in dialogues(client, script["id"]))


def test_duplicate_active_job_is_not_created(client, project, script, monkeypatch):
    _, ds = _setup(client, project, script)
    monkeypatch.setattr("app.api.generation.run_job", lambda *a, **k: None)  # 実行されず queued のまま残す
    first = client.post(f"/api/dialogues/{ds[0]['id']}/regenerate").json()
    second = client.post(f"/api/dialogues/{ds[0]['id']}/regenerate").json()
    assert first["id"] == second["id"] and first["status"] == "queued"
    assert len(client.get("/api/generation-jobs", params={"project_id": project["id"]}).json()) == 1


def test_generate_validation(client, project, script):
    pid = project["id"]
    assert client.post(f"/api/projects/{pid}/generate", json={"script_id": script["id"]}).status_code == 422  # セリフなし
    assert client.post(f"/api/projects/{pid}/generate", json={"script_id": "nope"}).status_code == 404
    assert client.post(f"/api/projects/{pid}/generate", json={}).status_code == 422
    assert client.post("/api/dialogues/nope/regenerate").status_code == 404
    # 別プロジェクトの台本は指定できない
    other_project = client.post("/api/projects", json={"title": "別"}).json()
    other_script = client.get(f"/api/projects/{other_project['id']}/scripts").json()[0]
    assert client.post(f"/api/projects/{pid}/generate", json={"script_id": other_script["id"]}).status_code == 404


def test_deleting_dialogue_removes_its_audio(client, project, script):
    _, ds = _setup(client, project, script)
    client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    asset_id = dialogues(client, script["id"])[0]["audio_asset_id"]
    client.delete(f"/api/dialogues/{ds[0]['id']}")
    assert client.get(f"/api/assets/{asset_id}/file").status_code == 404


def test_reparse_removes_old_audio(client, project, script):
    _, ds = _setup(client, project, script)
    client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    asset_id = dialogues(client, script["id"])[0]["audio_asset_id"]
    parse(client, script["id"], "[霊夢]\n新しい")  # 手動編集していないので、確認なしで作り直される
    assert client.get(f"/api/assets/{asset_id}/file").status_code == 404


def test_removing_character_makes_audio_stale(client, project, script):
    char = project_character(client, project["id"], "霊夢", voice_settings={"speed": 1.5})
    d = parse(client, script["id"], "[霊夢]\nこんにちは")["dialogues"][0]
    client.post(f"/api/dialogues/{d['id']}/regenerate")
    assert dialogues(client, script["id"])[0]["audio_stale"] is False
    client.delete(f"/api/projects/{project['id']}/characters/{char['id']}")
    assert dialogues(client, script["id"])[0]["audio_stale"] is True  # 声の設定が外れるので、作り直しが必要


# ---------------- 解析 ----------------
def test_analysis_sets_emotions_but_keeps_manual_edits(client, project, script):
    project_character(client, project["id"], "霊夢")
    project_character(client, project["id"], "魔理沙")
    ds = parse(client, script["id"], "[霊夢]\nありがとう、嬉しい！\n[魔理沙]\nふざけるな！\n[霊夢]\nえっ！？まじで")["dialogues"]
    client.put(f"/api/dialogues/{ds[2]['id']}", json={"emotion": "sad"})  # 手動で変更

    started = client.post(f"/api/scripts/{script['id']}/analyze").json()
    assert job(client, started["id"])["status"] == "succeeded"
    assert [d["emotion"] for d in dialogues(client, script["id"])] == ["happy", "angry", "sad"]  # 3つ目は上書きされない


def test_analysis_works_for_unregistered_speakers(client, script):
    parse(client, script["id"], "[霊夢]\nありがとう、嬉しい！")  # キャラクター未登録でも解析できる
    started = client.post(f"/api/scripts/{script['id']}/analyze").json()
    assert job(client, started["id"])["status"] == "succeeded"
    assert dialogues(client, script["id"])[0]["emotion"] == "happy"


def test_analysis_suggestions_and_clearing_on_edit(client, project, script):
    project_character(client, project["id"], "霊夢")
    d = parse(client, script["id"], "[霊夢]\n" + "あ" * 61)["dialogues"][0]
    client.post(f"/api/scripts/{script['id']}/analyze")
    assert "長め" in dialogues(client, script["id"])[0]["suggestion"]
    client.put(f"/api/dialogues/{d['id']}", json={"text": "短くした"})
    assert dialogues(client, script["id"])[0]["suggestion"] is None


def test_emotion_change_makes_audio_stale(client, project, script):
    _, ds = _setup(client, project, script)
    client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    res = client.put(f"/api/dialogues/{ds[0]['id']}", json={"emotion": "angry"})
    assert res.json()["audio_stale"] is True


def test_analysis_requires_dialogues(client, script):
    assert client.post(f"/api/scripts/{script['id']}/analyze").status_code == 422


# ---------------- ジョブ一覧 ----------------
def test_job_list_is_filterable_and_per_user(client, other, project, script):
    _, ds = _setup(client, project, script)
    lib = library_character(client, "魔理沙")
    client.post(f"/api/dialogues/{ds[0]['id']}/regenerate")
    client.post(f"/api/characters/{lib['id']}/generate-voice")

    assert len(client.get("/api/generation-jobs").json()) == 2
    scoped = client.get("/api/generation-jobs", params={"project_id": project["id"]}).json()
    assert [j["job_type"] for j in scoped] == ["voice"]
    assert other.get("/api/generation-jobs").json() == []
