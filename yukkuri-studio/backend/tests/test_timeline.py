from helpers import dialogues, job, parse, project_character

TEXT = "[霊夢]\nこんにちは\n[魔理沙]\nやあ\n"


def _setup(client, project, script, text=TEXT):
    project_character(client, project["id"], "霊夢")
    project_character(client, project["id"], "魔理沙")
    return parse(client, script["id"], text)["dialogues"]


def _layout(client, script, **body):
    res = client.post(f"/api/scripts/{script['id']}/layout", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def _voice(client, dialogue_id):
    res = client.post(f"/api/dialogues/{dialogue_id}/regenerate")
    assert job(client, res.json()["id"])["status"] == "succeeded"


def test_parse_leaves_timing_unplaced(client, project, script):
    ds = _setup(client, project, script)
    assert all(d["start_ms"] is None and d["timing_stale"] and not d["timing_locked"] for d in ds)
    tl = client.get(f"/api/scripts/{script['id']}/timeline").json()
    assert tl["items"] == [] and tl["total_ms"] == 0 and any("未配置" in w for w in tl["warnings"])


def test_layout_without_audio_uses_estimates_and_warns(client, project, script):
    _setup(client, project, script)
    out = _layout(client, script, gap_ms=300)
    a, b = out["dialogues"]
    assert a["start_ms"] == 0 and b["start_ms"] == a["end_ms"] + 300
    tracks = {(i["dialogue_id"], i["track_type"]) for i in out["timeline"]["items"]}
    # 音声が無いので audio は作らない。立ち絵と字幕は作る
    assert tracks == {(d["id"], t) for d in out["dialogues"] for t in ("character", "subtitle")}
    assert any("見積もって" in w for w in out["timeline"]["warnings"])
    assert out["timeline"]["total_ms"] == b["end_ms"]


def test_layout_uses_real_audio_length_and_creates_audio_items(client, project, script):
    ds = _setup(client, project, script)
    for d in ds:
        _voice(client, d["id"])
    out = _layout(client, script, gap_ms=0)
    for d in out["dialogues"]:
        assert d["end_ms"] - d["start_ms"] == max(100, d["audio_duration_ms"]) and not d["timing_stale"]
    assert {i["track_type"] for i in out["timeline"]["items"]} == {"audio", "character", "subtitle"}
    assert not any("見積もって" in w for w in out["timeline"]["warnings"])


def test_regenerating_audio_makes_timing_stale_until_relayout(client, project, script):
    ds = _setup(client, project, script)
    _layout(client, script)
    _voice(client, ds[0]["id"])
    assert dialogues(client, script["id"])[0]["timing_stale"] is True
    _layout(client, script)
    assert dialogues(client, script["id"])[0]["timing_stale"] is False


def test_simultaneous_group_starts_together(client, project, script):
    ds = _setup(client, project, script)
    assert client.post(f"/api/scripts/{script['id']}/dialogues/group",
                       json={"dialogue_ids": [d["id"] for d in ds]}).status_code == 200
    a, b = _layout(client, script)["dialogues"]
    assert a["start_ms"] == b["start_ms"] == 0


def test_manual_timing_locks_and_survives_relayout_unless_overwritten(client, project, script):
    ds = _setup(client, project, script, TEXT + "[霊夢]\nさようなら\n")
    _layout(client, script)
    res = client.put(f"/api/dialogues/{ds[1]['id']}", json={"start_ms": 10_000, "end_ms": 11_000})
    assert res.status_code == 200 and res.json()["timing_locked"] is True
    out = _layout(client, script, gap_ms=300)["dialogues"]
    assert (out[1]["start_ms"], out[1]["end_ms"]) == (10_000, 11_000)
    assert out[2]["start_ms"] == 11_300  # 手動指定の後ろから続く
    out = _layout(client, script, overwrite_locked=True)["dialogues"]
    assert out[1]["start_ms"] < 10_000 and out[1]["timing_locked"] is False


def test_unlock_by_api(client, project, script):
    ds = _setup(client, project, script)
    client.put(f"/api/dialogues/{ds[0]['id']}", json={"start_ms": 5000, "end_ms": 6000})
    res = client.put(f"/api/dialogues/{ds[0]['id']}", json={"timing_locked": False})
    assert res.json()["timing_locked"] is False
    assert _layout(client, script)["dialogues"][0]["start_ms"] == 0


def test_manual_timing_updates_timeline_items_and_keeps_user_positions(client, project, script):
    ds = _setup(client, project, script)
    _layout(client, script)
    client.put(f"/api/dialogues/{ds[0]['id']}", json={"start_ms": 2000, "end_ms": 3500})
    items = [i for i in client.get(f"/api/scripts/{script['id']}/timeline").json()["items"]
             if i["dialogue_id"] == ds[0]["id"]]
    assert items and all((i["start_ms"], i["end_ms"]) == (2000, 3500) for i in items)


def test_start_and_end_must_be_given_together(client, project, script):
    ds = _setup(client, project, script)
    assert client.put(f"/api/dialogues/{ds[0]['id']}", json={"start_ms": 1000}).status_code == 422


def test_relayout_is_idempotent_and_does_not_duplicate_items(client, project, script):
    _setup(client, project, script)
    first = _layout(client, script)["timeline"]
    second = _layout(client, script)["timeline"]
    assert len(first["items"]) == len(second["items"]) == 4
    assert [i["id"] for i in first["items"]] == [i["id"] for i in second["items"]]


def test_character_items_are_spread_by_project_order(client, project, script):
    _setup(client, project, script)
    items = [i for i in _layout(client, script)["timeline"]["items"] if i["track_type"] == "character"]
    xs = sorted(i["position_x"] for i in items)
    assert 0 < xs[0] < xs[1] < 1


def test_removing_dialogues_removes_timeline_items(client, project, script):
    ds = _setup(client, project, script)
    _layout(client, script)
    client.delete(f"/api/dialogues/{ds[0]['id']}")
    ids = {i["dialogue_id"] for i in client.get(f"/api/scripts/{script['id']}/timeline").json()["items"]}
    assert ids == {ds[1]["id"]}


def test_layout_validation(client, project, script):
    _setup(client, project, script)
    assert client.post(f"/api/scripts/{script['id']}/layout", json={"gap_ms": -1}).status_code == 422


def test_timeline_is_private_to_the_owner(client, other, project, script):
    _setup(client, project, script)
    assert other.post(f"/api/scripts/{script['id']}/layout", json={}).status_code == 404
    assert other.get(f"/api/scripts/{script['id']}/timeline").status_code == 404
