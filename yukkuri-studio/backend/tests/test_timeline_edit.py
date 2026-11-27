from helpers import dialogues, job, parse, project_character

TEXT = "[霊夢]\nこんにちは\n[魔理沙]\nやあ\n"


def _setup(client, project, script, with_voice=False):
    project_character(client, project["id"], "霊夢")
    project_character(client, project["id"], "魔理沙")
    ds = parse(client, script["id"], TEXT)["dialogues"]
    if with_voice:
        for d in ds:
            res = client.post(f"/api/dialogues/{d['id']}/regenerate")
            assert job(client, res.json()["id"])["status"] == "succeeded"
    assert client.post(f"/api/scripts/{script['id']}/layout", json={"gap_ms": 300}).status_code == 200
    return ds


def _items(client, script, dialogue_id=None, track=None):
    items = client.get(f"/api/scripts/{script['id']}/timeline").json()["items"]
    return [i for i in items if (dialogue_id is None or i["dialogue_id"] == dialogue_id)
            and (track is None or i["track_type"] == track)]


def _put(client, item, **body):
    return client.put(f"/api/timeline-items/{item['id']}", json=body)


def _history(client, project):
    return client.get(f"/api/projects/{project['id']}/history").json()


def test_edit_subtitle_item(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    res = _put(client, sub, text_override="編集後の字幕", font_size=60, position_x=0.3, position_y=0.8,
               start_ms=500, end_ms=2500)
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["text_override"], out["font_size"], out["position_x"], out["times_edited"]) == ("編集後の字幕", 60, 0.3, True)
    assert out["text"] == "こんにちは"  # セリフ本体は変わらない(音声が古くならない)
    d = dialogues(client, script["id"])[0]
    assert d["is_user_edited"] is True and d["audio_stale"] is None


def test_blank_override_and_null_restore_defaults(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    _put(client, sub, text_override="x", font_size=50)
    out = _put(client, sub, text_override="  ", font_size=None).json()
    assert out["text_override"] is None and out["font_size"] is None


def test_edit_character_item_expression_and_scale(client, project, script):
    ds = _setup(client, project, script)
    ch = _items(client, script, ds[0]["id"], "character")[0]
    out = _put(client, ch, expression="happy", scale=1.5).json()
    assert (out["expression"], out["scale"]) == ("happy", 1.5)
    assert _put(client, ch, expression="nope").status_code == 422
    assert _put(client, ch, expression=None).json()["expression"] is None  # セリフの感情に従う


def test_fields_must_fit_the_track(client, project, script):
    ds = _setup(client, project, script)
    ch = _items(client, script, ds[0]["id"], "character")[0]
    assert _put(client, ch, font_size=40).status_code == 422
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    assert _put(client, sub, volume=1.0).status_code == 422


def test_validation_ranges_and_order(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    assert _put(client, sub, start_ms=2000, end_ms=1000).status_code == 422
    assert _put(client, sub, start_ms=1000, end_ms=1050).status_code == 422  # 100ms未満
    assert _put(client, sub, font_size=2).status_code == 422
    assert _put(client, sub, position_x=1.5).status_code == 422


def test_audio_volume_and_speed_change_the_audio_item_length(client, project, script):
    ds = _setup(client, project, script, with_voice=True)
    audio = _items(client, script, ds[0]["id"], "audio")[0]
    length = audio["end_ms"] - audio["start_ms"]
    out = _put(client, audio, volume=0.5, playback_speed=2.0).json()
    assert out["volume"] == 0.5 and out["playback_speed"] == 2.0
    assert abs((out["end_ms"] - out["start_ms"]) - length / 2) <= 1
    assert out["times_edited"] is False  # 速度による長さの変化は「手で時間を決めた」ではない
    assert _put(client, audio, volume=3).status_code == 422


def test_user_edited_times_and_settings_survive_relayout(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    ch = _items(client, script, ds[0]["id"], "character")[0]
    _put(client, sub, start_ms=5000, end_ms=7000, text_override="残る字幕")
    _put(client, ch, scale=2.0, position_x=0.2)
    client.post(f"/api/scripts/{script['id']}/layout", json={})
    sub2 = _items(client, script, ds[0]["id"], "subtitle")[0]
    ch2 = _items(client, script, ds[0]["id"], "character")[0]
    assert (sub2["start_ms"], sub2["end_ms"], sub2["text_override"]) == (5000, 7000, "残る字幕")
    assert ch2["scale"] == 2.0 and ch2["position_x"] == 0.2
    assert ch2["start_ms"] == 0  # 時間を編集していない項目は、通常どおり配置される
    # 「手動指定も振り直す」では時間だけ戻り、見た目の設定は残る
    client.post(f"/api/scripts/{script['id']}/layout", json={"overwrite_locked": True})
    sub3 = _items(client, script, ds[0]["id"], "subtitle")[0]
    assert sub3["start_ms"] == 0 and sub3["times_edited"] is False and sub3["text_override"] == "残る字幕"


def test_reparse_warns_after_item_edit(client, project, script):
    ds = _setup(client, project, script)
    _put(client, _items(client, script, ds[0]["id"], "subtitle")[0], font_size=50)
    client.put(f"/api/scripts/{script['id']}", json={"content": TEXT})
    assert client.post(f"/api/scripts/{script['id']}/parse", json={}).status_code == 409


# ---------------- 元に戻す / やり直し ----------------
def test_undo_and_redo_item_edit(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    _put(client, sub, text_override="変更1", font_size=70)
    h = _history(client, project)
    assert h["can_undo"] and not h["can_redo"] and h["undo_label"] == "字幕の編集"

    r = client.post(f"/api/projects/{project['id']}/history/undo")
    assert r.status_code == 200 and r.json()["can_redo"] is True
    now = _items(client, script, ds[0]["id"], "subtitle")[0]
    assert now["id"] == sub["id"] and now["text_override"] is None and now["font_size"] is None

    client.post(f"/api/projects/{project['id']}/history/redo")
    again = _items(client, script, ds[0]["id"], "subtitle")[0]
    assert again["text_override"] == "変更1" and again["font_size"] == 70


def test_new_edit_discards_redo_stack(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    _put(client, sub, font_size=60)
    client.post(f"/api/projects/{project['id']}/history/undo")
    assert _history(client, project)["can_redo"] is True
    _put(client, sub, font_size=80)
    assert _history(client, project)["can_redo"] is False


def test_undo_walks_back_through_multiple_edits_in_order(client, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    for size in (50, 60, 70):
        _put(client, sub, font_size=size)
    sizes = []
    for _ in range(3):
        client.post(f"/api/projects/{project['id']}/history/undo")
        sizes.append(_items(client, script, ds[0]["id"], "subtitle")[0]["font_size"])
    assert sizes == [60, 50, None]


def test_undo_layout_and_dialogue_move(client, project, script):
    ds = _setup(client, project, script)
    before = [(d["start_ms"], d["end_ms"]) for d in dialogues(client, script["id"])]
    client.put(f"/api/dialogues/{ds[1]['id']}", json={"start_ms": 9000, "end_ms": 10000})
    assert _history(client, project)["undo_label"] == "セリフの時間の変更"
    client.post(f"/api/projects/{project['id']}/history/undo")
    after = dialogues(client, script["id"])
    assert [(d["start_ms"], d["end_ms"]) for d in after] == before and after[1]["timing_locked"] is False
    assert all(i["start_ms"] == after[1]["start_ms"] for i in _items(client, script, ds[1]["id"]))

    # 最初の自動配置も戻せる(未配置に戻る)
    client.post(f"/api/projects/{project['id']}/history/undo")
    assert all(d["start_ms"] is None for d in dialogues(client, script["id"]))
    assert _items(client, script) == []


def test_nothing_to_undo_or_redo_is_409(client, project, script):
    assert client.post(f"/api/projects/{project['id']}/history/undo").status_code == 409
    assert client.post(f"/api/projects/{project['id']}/history/redo").status_code == 409


def test_noop_layout_is_not_recorded(client, project, script):
    _setup(client, project, script)
    client.post(f"/api/scripts/{script['id']}/layout", json={"gap_ms": 300})  # 同じ結果になる再配置
    client.post(f"/api/projects/{project['id']}/history/undo")  # 最初の配置だけを戻す
    assert _history(client, project)["can_undo"] is False


def test_history_for_vanished_dialogues_is_rejected(client, project, script):
    ds = _setup(client, project, script)
    _put(client, _items(client, script, ds[0]["id"], "subtitle")[0], font_size=50)
    client.delete(f"/api/dialogues/{ds[0]['id']}")
    r = client.post(f"/api/projects/{project['id']}/history/undo")
    assert r.status_code == 409


def test_edit_endpoints_are_private_to_the_owner(client, other, project, script):
    ds = _setup(client, project, script)
    sub = _items(client, script, ds[0]["id"], "subtitle")[0]
    assert other.put(f"/api/timeline-items/{sub['id']}", json={"font_size": 50}).status_code == 404
    assert other.get(f"/api/projects/{project['id']}/history").status_code == 404
    assert other.post(f"/api/projects/{project['id']}/history/undo").status_code == 404
