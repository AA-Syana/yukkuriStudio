from helpers import dialogues, library_character, parse, project_character


def test_project_crud_and_default_script(client):
    res = client.post("/api/projects", json={"title": "  実況1  ", "description": "第1回"})
    assert res.status_code == 201
    p = res.json()
    assert p["title"] == "実況1" and p["description"] == "第1回"  # 前後の空白は除去される
    assert p["script_count"] == 1 and p["character_count"] == 0

    scripts = client.get(f"/api/projects/{p['id']}/scripts").json()
    assert [s["title"] for s in scripts] == ["台本1"]  # 作成直後から書き始められる

    assert [x["id"] for x in client.get("/api/projects").json()] == [p["id"]]
    updated = client.put(f"/api/projects/{p['id']}", json={"title": "改名"}).json()
    assert updated["title"] == "改名" and updated["description"] == "第1回"  # 送った項目だけ変わる
    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_project_validation(client):
    assert client.post("/api/projects", json={"title": "   "}).status_code == 422
    assert client.post("/api/projects", json={}).status_code == 422
    assert client.post("/api/projects", json={"title": "あ" * 101}).status_code == 422


def test_projects_are_listed_per_user(client, other):
    mine = client.post("/api/projects", json={"title": "自分"}).json()
    theirs = other.post("/api/projects", json={"title": "他人"}).json()
    assert [p["id"] for p in client.get("/api/projects").json()] == [mine["id"]]
    assert [p["id"] for p in other.get("/api/projects").json()] == [theirs["id"]]


def test_delete_project_with_everything_attached(client, project, script, storage, Session):
    """ジョブ・音声・キャラクターのコピー・画像がある状態でも削除でき、関連データとファイルが消える。ライブラリは残る。
    (PostgreSQLでは外部キー違反で失敗しやすい操作。テストDBも外部キー制約を有効にしている)"""
    from sqlalchemy import func, select

    from app.models import Asset, Character, GenerationJob

    pid = project["id"]
    lib = library_character(client, "霊夢")
    copy = client.post(f"/api/projects/{pid}/characters", json={"source_character_id": lib["id"]}).json()
    client.post(f"/api/characters/{copy['id']}/generate-image", json={"expression": "happy"})
    d = parse(client, script["id"], "[霊夢]\nこんにちは")["dialogues"][0]
    client.post(f"/api/dialogues/{d['id']}/regenerate")
    assert storage.absolute(pid).exists()

    assert client.delete(f"/api/projects/{pid}").status_code == 204

    assert not storage.absolute(pid).exists()  # 音声・コピーした画像のフォルダごと消える
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(GenerationJob)) == 0
        assert db.scalar(select(func.count()).select_from(Character).where(Character.project_id == pid)) == 0
        assert db.scalar(select(func.count()).select_from(Asset).where(Asset.dialogue_id == d["id"])) == 0
    assert [c["id"] for c in client.get("/api/characters").json()] == [lib["id"]]  # ライブラリは無傷


def test_deleting_a_project_does_not_touch_other_projects(client, storage):
    a = client.post("/api/projects", json={"title": "A"}).json()
    b = client.post("/api/projects", json={"title": "B"}).json()
    project_character(client, b["id"], "魔理沙")
    client.delete(f"/api/projects/{a['id']}")
    assert [c["name"] for c in client.get(f"/api/projects/{b['id']}/characters").json()] == ["魔理沙"]
    assert dialogues(client, client.get(f"/api/projects/{b['id']}/scripts").json()[0]["id"]) == []
