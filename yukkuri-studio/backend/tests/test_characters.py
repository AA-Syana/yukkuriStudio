"""キャラクター: ライブラリ(管理画面)と、プロジェクト用のコピー(編集画面)。

仕様(ユーザー決定): 編集画面(プロジェクト側)での状態を優先する。ライブラリでの編集は、次にプロジェクトへ
追加するときから反映される。
"""
import pytest

from helpers import PNG, add_to_project, dialogues, images_of, job, library_character, parse, project_character


# ---------------- ライブラリ ----------------
def test_library_crud(client):
    c = library_character(
        client, "  霊夢  ", description="巫女", personality="のんびり", speaking_style="〜ね",
        appearance_details={"hair_color": "黒", "outfit": "紅白の巫女服"}, voice_settings={"speed": 1.2},
    )
    assert c["name"] == "霊夢" and c["project_id"] is None and c["source_character_id"] is None
    assert c["appearance_details"]["hair_color"] == "黒" and c["project_count"] == 0

    got = client.get(f"/api/characters/{c['id']}").json()
    assert got["description"] == "巫女" and got["voice_settings"] == {"speed": 1.2}

    res = client.put(f"/api/characters/{c['id']}", json={"personality": "元気"})
    assert res.json()["personality"] == "元気" and res.json()["description"] == "巫女"  # 送った項目だけ変わる

    assert client.delete(f"/api/characters/{c['id']}").status_code == 204
    assert client.get("/api/characters").json() == []
    assert client.get(f"/api/characters/{c['id']}").status_code == 404


def test_library_name_must_be_unique_per_user(client, other):
    a = library_character(client, "霊夢")
    assert client.post("/api/characters", json={"name": "霊夢"}).status_code == 409
    b = library_character(client, "魔理沙")
    assert client.put(f"/api/characters/{b['id']}", json={"name": "霊夢"}).status_code == 409
    assert client.put(f"/api/characters/{a['id']}", json={"name": "霊夢"}).status_code == 200  # 自分自身と同じ名前はOK
    assert other.post("/api/characters", json={"name": "霊夢"}).status_code == 201  # 別ユーザーなら同名でよい


@pytest.mark.parametrize(
    "body",
    [{"name": "  "}, {}, {"name": "あ" * 101}, {"name": "x", "appearance_details": {"unknown_key": "a"}},
     {"name": "x", "appearance_details": {"hair_color": "あ" * 201}}],
)
def test_library_validation(client, body):
    assert client.post("/api/characters", json=body).status_code == 422


def test_library_only_lists_library_characters(client, project):
    lib = library_character(client, "霊夢")
    add_to_project(client, project["id"], lib["id"])
    assert [c["id"] for c in client.get("/api/characters").json()] == [lib["id"]]  # コピーは混ざらない
    assert client.get("/api/characters").json()[0]["project_count"] == 1


# ---------------- プロジェクトへの追加(コピー) ----------------
def test_add_copies_the_library_character(client, project):
    lib = library_character(client, "霊夢", personality="のんびり", voice_settings={"pitch": 0.2})
    copy = add_to_project(client, project["id"], lib["id"])
    assert copy["id"] != lib["id"]
    assert copy["project_id"] == project["id"] and copy["source_character_id"] == lib["id"]
    assert (copy["name"], copy["personality"], copy["voice_settings"]) == ("霊夢", "のんびり", {"pitch": 0.2})
    assert [c["id"] for c in client.get(f"/api/projects/{project['id']}/characters").json()] == [copy["id"]]


def test_add_is_idempotent(client, project):
    lib = library_character(client)
    first = add_to_project(client, project["id"], lib["id"])
    second = add_to_project(client, project["id"], lib["id"])
    assert first["id"] == second["id"]
    assert len(client.get(f"/api/projects/{project['id']}/characters").json()) == 1


def test_add_copies_images_and_voice_sample_as_separate_files(client, project):
    lib = library_character(client)
    client.post(f"/api/characters/{lib['id']}/generate-image", json={"expression": "happy"})
    client.post(f"/api/characters/{lib['id']}/generate-voice")
    copy = add_to_project(client, project["id"], lib["id"])

    lib_img = images_of(client, lib)["happy"]
    copy_img = images_of(client, copy)["happy"]
    assert copy_img["asset_id"] != lib_img["asset_id"]  # ファイルも別物
    assert client.get(f"/api/assets/{copy_img['asset_id']}/file").status_code == 200
    assert client.get(f"/api/characters/{lib['id']}").json()["voice_sample_asset_id"]
    assert client.get(f"/api/projects/{project['id']}/characters").json()[0]["voice_sample_asset_id"]


def test_library_edit_does_not_change_existing_copy_but_applies_to_next_add(client, project):
    """ユーザー決定: ライブラリの編集は、次回以降の追加から反映される。"""
    lib = library_character(client, "霊夢", personality="のんびり")
    copy = add_to_project(client, project["id"], lib["id"])

    client.put(f"/api/characters/{lib['id']}", json={"personality": "せっかち", "voice_settings": {"speed": 1.5}})

    now = client.get(f"/api/projects/{project['id']}/characters").json()[0]
    assert now["personality"] == "のんびり" and now["voice_settings"] == {}  # 編集画面側が優先

    other_project = client.post("/api/projects", json={"title": "次の作品"}).json()
    fresh = add_to_project(client, other_project["id"], lib["id"])
    assert fresh["personality"] == "せっかち" and fresh["voice_settings"] == {"speed": 1.5}  # 次回の制作から反映
    assert copy["id"] != fresh["id"]


def test_project_edit_does_not_change_library(client, project):
    lib = library_character(client, "霊夢", personality="のんびり")
    copy = add_to_project(client, project["id"], lib["id"])
    res = client.put(f"/api/projects/{project['id']}/characters/{copy['id']}", json={"personality": "この作品だけ"})
    assert res.json()["personality"] == "この作品だけ"
    assert client.get(f"/api/characters/{lib['id']}").json()["personality"] == "のんびり"


def test_removing_and_readding_picks_up_latest_library_content(client, project):
    lib = library_character(client, "霊夢", personality="旧")
    copy = add_to_project(client, project["id"], lib["id"])
    client.put(f"/api/characters/{lib['id']}", json={"personality": "新"})
    assert client.delete(f"/api/projects/{project['id']}/characters/{copy['id']}").status_code == 204
    assert add_to_project(client, project["id"], lib["id"])["personality"] == "新"


def test_library_image_changes_do_not_affect_copy(client, project):
    lib = library_character(client)
    client.post(f"/api/characters/{lib['id']}/generate-image", json={"expression": "happy"})
    copy = add_to_project(client, project["id"], lib["id"])
    assert client.delete(f"/api/characters/{lib['id']}/images/happy").status_code == 204
    assert "happy" in images_of(client, copy)


def test_deleting_library_character_keeps_project_copies_and_their_files(client, project, script):
    lib = library_character(client, "霊夢")
    client.post(f"/api/characters/{lib['id']}/generate-image", json={"expression": "happy"})
    copy = add_to_project(client, project["id"], lib["id"])
    d = parse(client, script["id"], "[霊夢]\nこんにちは")["dialogues"][0]
    assert d["character_id"] == copy["id"]

    assert client.delete(f"/api/characters/{lib['id']}").status_code == 204  # 使用中でも削除できる

    kept = client.get(f"/api/projects/{project['id']}/characters").json()[0]
    assert kept["id"] == copy["id"] and kept["source_character_id"] is None  # コピー元が無くなっただけ
    assert client.get(f"/api/assets/{kept['images'][0]['asset_id']}/file").status_code == 200  # 画像は残る
    assert dialogues(client, script["id"])[0]["character_id"] == copy["id"]  # セリフの話者も残る


def test_add_name_conflict_with_existing_project_character(client, project):
    first = library_character(client, "霊夢")
    add_to_project(client, project["id"], first["id"])
    client.put(f"/api/characters/{first['id']}", json={"name": "霊夢(旧)"})
    second = library_character(client, "霊夢")  # ライブラリでは空いた名前
    res = client.post(f"/api/projects/{project['id']}/characters", json={"source_character_id": second["id"]})
    assert res.status_code == 409


def test_project_character_rename_conflict(client, project):
    a = project_character(client, project["id"], "霊夢")
    project_character(client, project["id"], "魔理沙")
    assert client.put(f"/api/projects/{project['id']}/characters/{a['id']}", json={"name": "魔理沙"}).status_code == 409


def test_same_library_character_can_be_used_in_many_projects(client):
    lib = library_character(client, "霊夢")
    p1 = client.post("/api/projects", json={"title": "1"}).json()
    p2 = client.post("/api/projects", json={"title": "2"}).json()
    c1, c2 = add_to_project(client, p1["id"], lib["id"]), add_to_project(client, p2["id"], lib["id"])
    assert c1["id"] != c2["id"]
    assert client.get(f"/api/characters/{lib['id']}").json()["project_count"] == 2


def test_add_backfills_dialogues_waiting_for_that_speaker(client, project, script):
    lib = library_character(client, "霊夢")
    parsed = parse(client, script["id"], "[霊夢]\nこんにちは\n[魔理沙]\nやあ")
    assert {u["name"]: u["library_character_id"] for u in parsed["unknown_speakers"]} == {"霊夢": lib["id"], "魔理沙": None}

    copy = add_to_project(client, project["id"], lib["id"])
    by_name = {d["speaker_name"]: d for d in dialogues(client, script["id"])}
    assert by_name["霊夢"]["character_id"] == copy["id"] and by_name["魔理沙"]["character_id"] is None
    left = client.get(f"/api/scripts/{script['id']}/unknown-speakers").json()
    assert [u["name"] for u in left] == ["魔理沙"]


def test_removing_from_project_keeps_dialogues_and_library(client, project, script):
    copy = project_character(client, project["id"], "霊夢")
    parse(client, script["id"], "[霊夢]\nこんにちは")
    assert client.delete(f"/api/projects/{project['id']}/characters/{copy['id']}").status_code == 204
    d = dialogues(client, script["id"])[0]
    assert d["character_id"] is None and d["speaker_name"] == "霊夢"  # 後でキャラクターを追加すれば結びつけ直せる
    assert len(client.get("/api/characters").json()) == 1  # ライブラリは消えない


# ---------------- 種類の取り違え・他人のデータ ----------------
def test_library_endpoints_reject_project_copies_and_vice_versa(client, project):
    lib = library_character(client, "霊夢")
    copy = add_to_project(client, project["id"], lib["id"])
    assert client.put(f"/api/characters/{copy['id']}", json={"personality": "x"}).status_code == 404
    assert client.delete(f"/api/characters/{copy['id']}").status_code == 404
    assert client.put(f"/api/projects/{project['id']}/characters/{lib['id']}", json={"personality": "x"}).status_code == 404
    # コピーを「コピー元」にして追加することはできない
    res = client.post(f"/api/projects/{project['id']}/characters", json={"source_character_id": copy["id"]})
    assert res.status_code == 404


def test_other_users_cannot_see_or_use_my_characters(client, other, project):
    lib = library_character(client, "霊夢")
    copy = add_to_project(client, project["id"], lib["id"])
    theirs = other.post("/api/projects", json={"title": "他人の"}).json()

    assert other.get("/api/characters").json() == []
    assert other.get(f"/api/characters/{lib['id']}").status_code == 404
    assert other.put(f"/api/characters/{lib['id']}", json={"personality": "x"}).status_code == 404
    assert other.delete(f"/api/characters/{lib['id']}").status_code == 404
    assert other.post(f"/api/projects/{theirs['id']}/characters", json={"source_character_id": lib["id"]}).status_code == 404
    assert other.get(f"/api/projects/{project['id']}/characters").status_code == 404
    assert other.post(f"/api/characters/{lib['id']}/generate-image", json={}).status_code == 404
    assert other.post(f"/api/characters/{copy['id']}/generate-voice").status_code == 404
    assert other.delete(f"/api/characters/{lib['id']}/images/happy").status_code == 404
    assert client.get(f"/api/characters/{lib['id']}").status_code == 200  # 自分のものは無事


# ---------------- 画像・音声サンプル(キャラクター単体の生成) ----------------
def test_library_character_image_generation_has_no_project(client):
    lib = library_character(client)
    started = client.post(f"/api/characters/{lib['id']}/generate-image", json={}).json()
    assert started["project_id"] is None  # プロジェクトに属さないジョブ
    done = job(client, started["id"])
    assert done["status"] == "succeeded" and done["progress"] == 100
    assert len(images_of(client, lib)) == 5


def test_image_prompt_uses_appearance_details(client, providers, monkeypatch):
    seen = {}
    original = providers.image.generate

    def spy(req):
        seen["prompt"] = req.prompt
        return original(req)

    monkeypatch.setattr(providers.image, "generate", spy)
    lib = library_character(client, appearance_details={"hair_color": "金髪", "outfit": "魔女の服"})
    client.post(f"/api/characters/{lib['id']}/generate-image", json={"expression": "neutral"})
    assert "金髪" in seen["prompt"] and "魔女の服" in seen["prompt"] and "赤いリボンの巫女" in seen["prompt"]


def test_voice_sample_and_staleness(client):
    lib = library_character(client)
    assert lib["voice_sample_asset_id"] is None and lib["voice_sample_stale"] is None
    started = client.post(f"/api/characters/{lib['id']}/generate-voice").json()
    assert job(client, started["id"])["status"] == "succeeded"

    c = client.get(f"/api/characters/{lib['id']}").json()
    assert c["voice_sample_asset_id"] and c["voice_sample_stale"] is False
    f = client.get(f"/api/assets/{c['voice_sample_asset_id']}/file")
    assert f.headers["content-type"] == "audio/wav" and f.content[:4] == b"RIFF"

    client.put(f"/api/characters/{lib['id']}", json={"voice_settings": {"speed": 2.0}})
    assert client.get(f"/api/characters/{lib['id']}").json()["voice_sample_stale"] is True


def test_image_generation_rejects_bad_expression(client):
    lib = library_character(client)
    assert client.post(f"/api/characters/{lib['id']}/generate-image", json={"expression": "dancing"}).status_code == 422
    assert client.post("/api/characters/nope/generate-image", json={}).status_code == 404


def test_all_expressions_reference_neutral(client, providers, monkeypatch):
    lib = library_character(client)
    refs = {}
    original = providers.image.generate

    def spy(req):
        refs[req.expression] = req.reference_path
        return original(req)

    monkeypatch.setattr(providers.image, "generate", spy)
    client.post(f"/api/characters/{lib['id']}/generate-image", json={})
    assert refs["neutral"] is None  # 最初の「通常」は参照なし
    assert all(v is not None for k, v in refs.items() if k != "neutral")  # 以降は「通常」を参照


def test_upload_and_delete_image_for_library_and_copy(client, project):
    lib = library_character(client)
    copy = add_to_project(client, project["id"], lib["id"])
    for target in (lib, copy):
        url = f"/api/characters/{target['id']}/images/upload"
        for name, data in (("a.png", PNG), ("a.jpg", b"\xff\xd8\xff\xe0" + b"0" * 8)):
            assert client.post(url, data={"expression": "happy"}, files={"file": (name, data)}).status_code == 201
        assert images_of(client, target)["happy"]["source"] == "uploaded"
        assert client.post(url, data={"expression": "happy"}, files={"file": ("a.svg", b"<svg/>")}).status_code == 415
        assert client.post(url, data={"expression": "happy"}, files={"file": ("a.png", b"not an image")}).status_code == 422
        assert client.post(url, data={"expression": "dancing"}, files={"file": ("a.png", PNG)}).status_code == 422
        assert client.delete(f"/api/characters/{target['id']}/images/happy").status_code == 204
        assert client.delete(f"/api/characters/{target['id']}/images/happy").status_code == 404
