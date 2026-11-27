from helpers import dialogues, library_character, parse, project_character

SCENARIO = "[霊夢]\nこんにちは！\n今日は実況をやります\n[魔理沙]\nよろしくな"


def test_multiple_scripts_per_project(client, project):
    pid = project["id"]
    second = client.post(f"/api/projects/{pid}/scripts", json={}).json()
    assert second["title"] == "台本2" and second["content"] == ""  # タイトル省略時は連番
    third = client.post(f"/api/projects/{pid}/scripts", json={"title": " 第3回 ", "content": "[霊夢]\nやあ"}).json()
    assert third["title"] == "第3回"
    assert [s["title"] for s in client.get(f"/api/projects/{pid}/scripts").json()] == ["台本1", "台本2", "第3回"]
    assert client.get(f"/api/projects/{pid}").json()["script_count"] == 3


def test_script_update_and_delete(client, script):
    sid = script["id"]
    res = client.put(f"/api/scripts/{sid}", json={"title": "改題", "content": "本文"})
    assert (res.json()["title"], res.json()["content"]) == ("改題", "本文")
    assert client.put(f"/api/scripts/{sid}", json={"title": "   "}).json()["title"] == "改題"  # 空のタイトルでは消えない
    assert client.delete(f"/api/scripts/{sid}").status_code == 204
    assert client.get(f"/api/scripts/{sid}").status_code == 404


def test_scripts_are_independent(client, project, script):
    project_character(client, project["id"], "霊夢")
    other_script = client.post(f"/api/projects/{project['id']}/scripts", json={}).json()
    parse(client, script["id"], "[霊夢]\n一つ目の台本")
    parse(client, other_script["id"], "[霊夢]\n二つ目の台本")
    assert [d["text"] for d in dialogues(client, script["id"])] == ["一つ目の台本"]
    assert [d["text"] for d in dialogues(client, other_script["id"])] == ["二つ目の台本"]


def test_parse_links_known_speakers_and_reports_unknown(client, project, script):
    copy = project_character(client, project["id"], "霊夢")
    library_character(client, "魔理沙")  # ライブラリにはあるが、プロジェクトには未追加
    result = parse(client, script["id"], SCENARIO + "\n[咲夜]\nお茶です")

    ds = result["dialogues"]
    assert [(d["speaker_name"], d["text"]) for d in ds] == [
        ("霊夢", "こんにちは！"), ("霊夢", "今日は実況をやります"), ("魔理沙", "よろしくな"), ("咲夜", "お茶です"),
    ]
    assert [d["character_id"] for d in ds] == [copy["id"], copy["id"], None, None]
    assert [d["order_index"] for d in ds] == [0, 1, 2, 3]

    unknown = {u["name"]: u for u in result["unknown_speakers"]}
    assert set(unknown) == {"魔理沙", "咲夜"}
    assert unknown["魔理沙"]["library_character_id"] and unknown["咲夜"]["library_character_id"] is None
    assert unknown["魔理沙"]["count"] == 1 and result["speakerless_lines"] == 0
    # キャラクターは勝手に作られない
    assert [c["name"] for c in client.get(f"/api/projects/{project['id']}/characters").json()] == ["霊夢"]


def test_parse_counts_lines_without_speaker(client, script):
    result = parse(client, script["id"], "前書き\n[霊夢]\nこんにちは")
    assert result["speakerless_lines"] == 1
    assert [d["speaker_name"] for d in result["dialogues"]] == [None, "霊夢"]


def test_parse_increments_version_and_save_does_not_parse(client, script):
    sid = script["id"]
    client.put(f"/api/scripts/{sid}", json={"content": SCENARIO})
    assert dialogues(client, sid) == []  # 保存しただけではセリフに分割されない
    assert client.post(f"/api/scripts/{sid}/parse", json={}).json()["dialogues"]
    assert client.get(f"/api/scripts/{sid}").json()["version"] == 2


def test_reparse_blocked_after_manual_edit_unless_forced(client, project, script):
    sid = script["id"]
    project_character(client, project["id"], "霊夢")
    d = parse(client, sid, "[霊夢]\nこんにちは")["dialogues"][0]
    client.put(f"/api/dialogues/{d['id']}", json={"text": "手で直した"})

    client.put(f"/api/scripts/{sid}", json={"content": "[霊夢]\n新しい"})
    blocked = client.post(f"/api/scripts/{sid}/parse", json={})
    assert blocked.status_code == 409
    assert dialogues(client, sid)[0]["text"] == "手で直した"  # 守られている
    assert client.post(f"/api/scripts/{sid}/parse", json={"force": True}).status_code == 200
    assert dialogues(client, sid)[0]["text"] == "新しい"


def test_dialogue_create_update_delete(client, project, script):
    sid = script["id"]
    reimu = project_character(client, project["id"], "霊夢")
    marisa = project_character(client, project["id"], "魔理沙")

    created = client.post(f"/api/scripts/{sid}/dialogues", json={"text": " 追加 ", "character_id": reimu["id"]}).json()
    assert created["text"] == "追加" and created["speaker_name"] == "霊夢" and created["is_user_edited"] is True

    res = client.put(f"/api/dialogues/{created['id']}", json={"character_id": marisa["id"], "emotion": "happy"})
    assert res.status_code == 200
    assert (res.json()["speaker_name"], res.json()["emotion"], res.json()["text"]) == ("魔理沙", "happy", "追加")

    assert client.put(f"/api/dialogues/{created['id']}", json={"start_ms": 2000, "end_ms": 1000}).status_code == 422
    assert client.put(f"/api/dialogues/{created['id']}", json={"emotion": "dancing"}).status_code == 422
    assert client.put(f"/api/dialogues/{created['id']}", json={"text": "  "}).status_code == 422

    assert client.delete(f"/api/dialogues/{created['id']}").status_code == 204
    assert dialogues(client, sid) == []


def test_dialogue_speaker_must_be_in_the_project(client, project, script):
    """ライブラリのキャラクターは、プロジェクトに追加するまで話者にできない。"""
    lib = library_character(client, "霊夢")
    res = client.post(f"/api/scripts/{script['id']}/dialogues", json={"text": "x", "character_id": lib["id"]})
    assert res.status_code == 422
    other_project = client.post("/api/projects", json={"title": "別"}).json()
    foreign = project_character(client, other_project["id"], "魔理沙")
    res = client.post(f"/api/scripts/{script['id']}/dialogues", json={"text": "x", "character_id": foreign["id"]})
    assert res.status_code == 422


def test_group_and_ungroup(client, project, script):
    sid = script["id"]
    project_character(client, project["id"], "霊夢")
    ds = parse(client, sid, "[霊夢]\n一\n二\n三")["dialogues"]
    ids = [d["id"] for d in ds[:2]]

    grouped = client.post(f"/api/scripts/{sid}/dialogues/group", json={"dialogue_ids": ids}).json()
    assert len({d["simultaneous_group"] for d in grouped}) == 1 and grouped[0]["simultaneous_group"]
    assert dialogues(client, sid)[2]["simultaneous_group"] is None

    assert client.post(f"/api/scripts/{sid}/dialogues/group", json={"dialogue_ids": ids[:1]}).status_code == 422
    assert client.post(f"/api/scripts/{sid}/dialogues/group", json={"dialogue_ids": ids + ["nope"]}).status_code == 404

    client.post(f"/api/scripts/{sid}/dialogues/ungroup", json={"dialogue_ids": ids})
    assert all(d["simultaneous_group"] is None for d in dialogues(client, sid))


def test_group_rejects_dialogues_of_another_script(client, project, script):
    second = client.post(f"/api/projects/{project['id']}/scripts", json={}).json()
    a = parse(client, script["id"], "[霊夢]\n一")["dialogues"][0]
    b = parse(client, second["id"], "[霊夢]\n二")["dialogues"][0]
    res = client.post(f"/api/scripts/{script['id']}/dialogues/group", json={"dialogue_ids": [a["id"], b["id"]]})
    assert res.status_code == 404


def test_deleting_script_removes_its_dialogues_and_audio(client, project, script):
    project_character(client, project["id"], "霊夢")
    d = parse(client, script["id"], "[霊夢]\nこんにちは")["dialogues"][0]
    client.post(f"/api/dialogues/{d['id']}/regenerate")
    asset_id = dialogues(client, script["id"])[0]["audio_asset_id"]
    assert client.delete(f"/api/scripts/{script['id']}").status_code == 204
    assert client.get(f"/api/assets/{asset_id}/file").status_code == 404
