"""ユーザーごとのデータの分離。他人のデータは「存在しない」(404)として扱われ、内容が漏れない。"""
import io

from helpers import dialogues, library_character, parse, project_character


def _world(client):
    """自分のデータ一式(プロジェクト・台本・セリフ・音声・キャラクター・画像)を作る。"""
    project = client.post("/api/projects", json={"title": "秘密の作品"}).json()
    script = client.get(f"/api/projects/{project['id']}/scripts").json()[0]
    char = project_character(client, project["id"], "霊夢")
    d = parse(client, script["id"], "[霊夢]\n内緒のセリフ")["dialogues"][0]
    client.post(f"/api/dialogues/{d['id']}/regenerate")
    client.post(f"/api/characters/{char['id']}/generate-image", json={"expression": "happy"})
    d = dialogues(client, script["id"])[0]
    char = client.get(f"/api/projects/{project['id']}/characters").json()[0]
    return {
        "project": project, "script": script, "char": char, "dialogue": d,
        "audio": d["audio_asset_id"], "image": char["images"][0]["asset_id"],
    }


def test_other_user_gets_404_everywhere(client, other):
    w = _world(client)
    pid, sid, did = w["project"]["id"], w["script"]["id"], w["dialogue"]["id"]
    expected_404 = [
        other.get(f"/api/projects/{pid}"),
        other.put(f"/api/projects/{pid}", json={"title": "乗っ取り"}),
        other.delete(f"/api/projects/{pid}"),
        other.get(f"/api/projects/{pid}/scripts"),
        other.post(f"/api/projects/{pid}/scripts", json={}),
        other.get(f"/api/scripts/{sid}"),
        other.put(f"/api/scripts/{sid}", json={"content": "x"}),
        other.post(f"/api/scripts/{sid}/parse", json={}),
        other.delete(f"/api/scripts/{sid}"),
        other.get(f"/api/scripts/{sid}/dialogues"),
        other.get(f"/api/scripts/{sid}/unknown-speakers"),
        other.post(f"/api/scripts/{sid}/dialogues", json={"text": "x"}),
        other.post(f"/api/scripts/{sid}/dialogues/group", json={"dialogue_ids": [did, did]}),
        other.put(f"/api/dialogues/{did}", json={"text": "x"}),
        other.delete(f"/api/dialogues/{did}"),
        other.post(f"/api/dialogues/{did}/regenerate"),
        other.post(f"/api/projects/{pid}/generate", json={"script_id": sid}),
        other.post(f"/api/scripts/{sid}/analyze"),
        other.get(f"/api/assets/{w['audio']}/file"),
        other.get(f"/api/assets/{w['image']}/file"),
        other.get(f"/api/projects/{pid}/video"),
        other.get(f"/api/projects/{pid}/video/stream"),
        other.post(f"/api/projects/{pid}/video", files={"file": ("a.mp4", io.BytesIO(b"x"), "video/mp4")}),
    ]
    assert [r.status_code for r in expected_404] == [404] * len(expected_404)
    assert "秘密" not in "".join(r.text for r in expected_404)  # エラー内容からも漏れない

    # 自分のデータは無傷
    assert client.get(f"/api/projects/{pid}").json()["title"] == "秘密の作品"
    assert dialogues(client, sid)[0]["text"] == "内緒のセリフ"
    assert client.get(f"/api/assets/{w['audio']}/file").status_code == 200


def test_other_user_cannot_see_my_jobs(client, other):
    w = _world(client)
    jobs = client.get("/api/generation-jobs").json()
    assert jobs and other.get("/api/generation-jobs").json() == []
    assert other.get("/api/generation-jobs", params={"project_id": w["project"]["id"]}).json() == []
    for j in jobs:
        assert other.get(f"/api/generation-jobs/{j['id']}").status_code == 404
        assert other.post(f"/api/generation-jobs/{j['id']}/retry").status_code == 404


def test_other_user_cannot_use_my_character_as_speaker(client, other):
    w = _world(client)
    theirs = other.post("/api/projects", json={"title": "他人"}).json()
    their_script = other.get(f"/api/projects/{theirs['id']}/scripts").json()[0]
    res = other.post(f"/api/scripts/{their_script['id']}/dialogues", json={"text": "x", "character_id": w["char"]["id"]})
    assert res.status_code == 422


def test_other_user_cannot_delete_my_library_character(client, other):
    """他人が自分のライブラリのキャラクターを削除しようとしても、消えない。"""
    lib = library_character(client, "霊夢")
    assert other.delete(f"/api/characters/{lib['id']}").status_code == 404
    assert client.get(f"/api/characters/{lib['id']}").status_code == 200
