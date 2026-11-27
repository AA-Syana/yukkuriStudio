from app.services.script_parser import parse_scenario


def _pairs(text):
    return [(l.speaker, l.text) for l in parse_scenario(text)]


def test_bracket_format_multiple_lines_per_speaker():
    text = "[霊夢]\nこんにちは！\n今日は実況をやります\n[魔理沙]\nよろしくな"
    assert _pairs(text) == [("霊夢", "こんにちは！"), ("霊夢", "今日は実況をやります"), ("魔理沙", "よろしくな")]


def test_bracket_format_fullwidth_brackets_blank_lines_and_comments():
    text = "# メモ\n\n［霊夢］\n\n一行目\n# 途中のコメント\n二行目"
    assert _pairs(text) == [("霊夢", "一行目"), ("霊夢", "二行目")]


def test_colon_in_bracket_mode_is_not_a_speaker():
    # [話者] がある台本では、セリフ中のコロンを話者の区切りと誤認しない
    assert _pairs("[霊夢]\n注意: これはセリフです") == [("霊夢", "注意: これはセリフです")]


def test_lines_before_first_header_have_no_speaker():
    assert _pairs("前書き\n[霊夢]\nこんにちは") == [(None, "前書き"), ("霊夢", "こんにちは")]


def test_header_with_no_lines_produces_nothing():
    assert _pairs("[霊夢]\n[魔理沙]\nやあ") == [("魔理沙", "やあ")]


def test_legacy_colon_format_only_without_headers():
    assert _pairs("霊夢: こんにちは！\n魔理沙：やあ\n続きのセリフ") == [
        ("霊夢", "こんにちは！"), ("魔理沙", "やあ"), ("魔理沙", "続きのセリフ"),
    ]


def test_no_speaker_at_all():
    assert _pairs("ナレーションのみ") == [(None, "ナレーションのみ")]


def test_line_numbers_point_to_original_text():
    lines = parse_scenario("[霊夢]\n\nこんにちは")
    assert [l.line_no for l in lines] == [3]
