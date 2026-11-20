from app.services.script_parser import parse_scenario


def test_parse_basic_and_fullwidth_colon():
    lines = parse_scenario("霊夢: こんにちは！\n魔理沙：やあ")
    assert [(l.speaker, l.text) for l in lines] == [("霊夢", "こんにちは！"), ("魔理沙", "やあ")]


def test_parse_continuation_blank_and_comment():
    lines = parse_scenario("# メモ\n\n霊夢: 一行目\n二行目")
    assert [(l.speaker, l.text) for l in lines] == [("霊夢", "一行目"), ("霊夢", "二行目")]


def test_parse_no_speaker_at_start():
    assert parse_scenario("ナレーションのみ")[0].speaker is None
