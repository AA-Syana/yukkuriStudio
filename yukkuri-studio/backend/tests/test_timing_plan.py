from app.services.timing_plan import PlanInput, estimate_duration_ms, plan_layout


def _plan(items, **kw):
    return {p.id: (p.start_ms, p.end_ms) for p in plan_layout(items, **kw)}


def test_sequential_with_gap():
    items = [PlanInput("a", 0, 1000), PlanInput("b", 1, 2000), PlanInput("c", 2, 500)]
    assert _plan(items, gap_ms=300) == {"a": (0, 1000), "b": (1300, 3300), "c": (3600, 4100)}


def test_start_offset_and_zero_gap():
    items = [PlanInput("a", 0, 1000), PlanInput("b", 1, 1000)]
    assert _plan(items, gap_ms=0, start_ms=5000) == {"a": (5000, 6000), "b": (6000, 7000)}


def test_order_follows_order_index_not_input_order():
    items = [PlanInput("b", 1, 1000), PlanInput("a", 0, 1000)]
    assert _plan(items, gap_ms=0) == {"a": (0, 1000), "b": (1000, 2000)}


def test_simultaneous_group_starts_together_and_next_follows_the_longest():
    items = [
        PlanInput("a", 0, 1000),
        PlanInput("b", 1, 2000, group="g"),
        PlanInput("c", 2, 3000, group="g"),
        PlanInput("d", 3, 500),
    ]
    assert _plan(items, gap_ms=300) == {"a": (0, 1000), "b": (1300, 3300), "c": (1300, 4300), "d": (4600, 5100)}


def test_non_adjacent_group_member_joins_group_start():
    items = [PlanInput("a", 0, 1000, group="g"), PlanInput("b", 1, 1000), PlanInput("c", 2, 1000, group="g")]
    out = _plan(items, gap_ms=0)
    assert out["a"] == (0, 1000) and out["b"] == (1000, 2000) and out["c"] == (0, 1000)  # cはaと同時


def test_locked_item_is_kept_and_followers_continue_after_it():
    items = [
        PlanInput("a", 0, 1000),
        PlanInput("b", 1, 1000, locked=True, start_ms=10_000, end_ms=11_000),
        PlanInput("c", 2, 1000),
    ]
    assert _plan(items, gap_ms=300) == {"a": (0, 1000), "b": (10_000, 11_000), "c": (11_300, 12_300)}


def test_locked_item_earlier_than_cursor_does_not_move_time_backwards():
    items = [
        PlanInput("a", 0, 5000),
        PlanInput("b", 1, 1000, locked=True, start_ms=0, end_ms=1000),
        PlanInput("c", 2, 1000),
    ]
    assert _plan(items, gap_ms=0)["c"] == (5000, 6000)


def test_overwrite_locked_replaces_manual_timing():
    items = [PlanInput("a", 0, 1000, locked=True, start_ms=7000, end_ms=8000)]
    placement = plan_layout(items, gap_ms=0, overwrite_locked=True)[0]
    assert (placement.start_ms, placement.end_ms, placement.kept_locked) == (0, 1000, False)


def test_locked_without_times_is_laid_out_normally():
    placement = plan_layout([PlanInput("a", 0, 1000, locked=True)], gap_ms=0)[0]
    assert (placement.start_ms, placement.end_ms, placement.kept_locked) == (0, 1000, False)


def test_estimated_flag_is_reported_and_minimum_duration_enforced():
    placements = plan_layout([PlanInput("a", 0, 0, estimated=True)], gap_ms=0)
    assert placements[0].estimated and placements[0].end_ms - placements[0].start_ms >= 100


def test_estimate_duration_from_text():
    assert estimate_duration_ms("あ") == 800  # 最小値
    assert estimate_duration_ms("あ" * 10) == 1700
    assert estimate_duration_ms("あ い\nう") == 800  # 空白は数えない


# ---- Phase 4 ----
def test_audio_item_end_reflects_playback_speed():
    from app.services.timing_plan import audio_item_end_ms

    assert audio_item_end_ms(1000, 2000, 1.0) == 3000
    assert audio_item_end_ms(1000, 2000, 2.0) == 2000  # 2倍速なら長さは半分
    assert audio_item_end_ms(1000, 2000, 0.5) == 5000
    assert audio_item_end_ms(0, 50, 2.0) == 100  # 最小の長さ
    assert audio_item_end_ms(0, 1000, 0) == 1000  # 不正な速度は等速として扱う


def test_undo_picks_newest_live_and_redo_picks_oldest_undone():
    from app.services.timing_plan import pick_redo, pick_undo

    assert pick_undo([]) is None and pick_redo([]) is None
    assert pick_undo([(1, False), (2, False), (3, False)]) == 3
    assert pick_redo([(1, False), (2, False), (3, False)]) is None
    # 3 と 2 を戻した状態: 次に戻すのは 1、やり直すのは直前に戻した 2
    state = [(1, False), (2, True), (3, True)]
    assert pick_undo(state) == 1 and pick_redo(state) == 2
    assert pick_undo([(1, True)]) is None
