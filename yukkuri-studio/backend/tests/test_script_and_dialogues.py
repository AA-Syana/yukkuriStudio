def _parse(client, pid, text, **body):
    client.put(f"/api/projects/{pid}/script", json={"raw_text": text})
    return client.post(f"/api/projects/{pid}/script/parse", json=body)


def test_parse_creates_dialogues_and_characters(client, project):
    res = _parse(client, project["id"], "霊夢: こんにちは\n魔理沙: やあ\n霊夢: 元気？")
    assert res.status_code == 200
    body = res.json()
    assert [d["text"] for d in body["dialogues"]] == ["こんにちは", "やあ", "元気？"]
    assert sorted(c["name"] for c in body["created_characters"]) == ["霊夢", "魔理沙"]
    # 同名の話者は同じキャラクターに紐づく
    assert body["dialogues"][0]["character_id"] == body["dialogues"][2]["character_id"]


def test_reparse_blocked_after_manual_edit_unless_forced(client, project):
    pid = project["id"]
    dialogues = _parse(client, pid, "霊夢: こんにちは").json()["dialogues"]
    client.patch(f"/api/projects/{pid}/dialogues/{dialogues[0]['id']}", json={"text": "手動で変更"})

    assert _parse(client, pid, "霊夢: 新しい").status_code == 409
    assert client.get(f"/api/projects/{pid}/dialogues").json()[0]["text"] == "手動で変更"  # 上書きされていない

    forced = _parse(client, pid, "霊夢: 新しい", force=True)
    assert forced.status_code == 200
    assert forced.json()["dialogues"][0]["text"] == "新しい"


def test_dialogue_create_update_delete(client, project):
    pid = project["id"]
    ch = client.post(f"/api/projects/{pid}/characters", json={"name": "霊夢"}).json()
    d = client.post(f"/api/projects/{pid}/dialogues", json={"text": "追加", "character_id": ch["id"]}).json()
    assert d["is_user_edited"] is True

    upd = client.patch(f"/api/projects/{pid}/dialogues/{d['id']}", json={"start_ms": 1000, "end_ms": 2500})
    assert upd.json()["start_ms"] == 1000 and upd.json()["end_ms"] == 2500
    bad = client.patch(f"/api/projects/{pid}/dialogues/{d['id']}", json={"start_ms": 3000, "end_ms": 2000})
    assert bad.status_code == 422

    assert client.delete(f"/api/projects/{pid}/dialogues/{d['id']}").status_code == 204
    assert client.get(f"/api/projects/{pid}/dialogues").json() == []


def test_dialogue_rejects_foreign_character(client, project):
    res = client.post(f"/api/projects/{project['id']}/dialogues", json={"text": "x", "character_id": "nope"})
    assert res.status_code == 422


def test_group_and_ungroup(client, project):
    pid = project["id"]
    ds = _parse(client, pid, "霊夢: A\n魔理沙: B\n霊夢: C").json()["dialogues"]
    ids = [ds[0]["id"], ds[1]["id"]]

    grouped = client.post(f"/api/projects/{pid}/dialogues/group", json={"dialogue_ids": ids}).json()
    assert grouped[0]["simultaneous_group"] and grouped[0]["simultaneous_group"] == grouped[1]["simultaneous_group"]
    assert client.post(f"/api/projects/{pid}/dialogues/group", json={"dialogue_ids": ids[:1]}).status_code == 422

    ungrouped = client.post(f"/api/projects/{pid}/dialogues/ungroup", json={"dialogue_ids": ids}).json()
    assert all(d["simultaneous_group"] is None for d in ungrouped)


def test_character_crud_and_delete_keeps_dialogues(client, project):
    pid = project["id"]
    ds = _parse(client, pid, "霊夢: A").json()["dialogues"]
    cid = ds[0]["character_id"]

    upd = client.patch(f"/api/projects/{pid}/characters/{cid}", json={"personality": "元気", "voice_settings": {"pitch": 0.1}})
    assert upd.json()["personality"] == "元気" and upd.json()["voice_settings"] == {"pitch": 0.1}
    assert client.post(f"/api/projects/{pid}/characters", json={"name": "霊夢"}).status_code == 409  # 重複名

    assert client.delete(f"/api/projects/{pid}/characters/{cid}").status_code == 204
    remaining = client.get(f"/api/projects/{pid}/dialogues").json()
    assert len(remaining) == 1 and remaining[0]["character_id"] is None
