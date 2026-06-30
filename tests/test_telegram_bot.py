from app.telegram_bot import format_conclusive_result, handle_text, parse_command, parse_state_days, parse_state_question


def test_parse_command_strips_bot_username():
    parsed = parse_command("/digest@xcise_X_bot DL 7")

    assert parsed is not None
    assert parsed.command == "/digest"
    assert parsed.args == ["DL", "7"]


def test_parse_state_days_accepts_optional_state():
    assert parse_state_days(["DL", "7"]) == ("DL", 7)
    assert parse_state_days(["3"]) == (None, 3)


def test_parse_state_question_accepts_ut_code():
    assert parse_state_question(["DNHDD", "licence", "fee"]) == ("DNHDD", "licence fee")


def test_format_conclusive_result_labels_non_definitive():
    text = format_conclusive_result(
        {
            "answer_status": "REPORTED_ONLY",
            "definitive": False,
            "evidence_tier": "REPORTED_NOT_CONFIRMED",
            "confidence": 0.58,
            "conclusion": "Only news evidence found.",
            "top_sources": [{"tier": "REPORTED_NOT_CONFIRMED", "state": "Delhi", "title": "News item", "url": "https://example.com"}],
        },
        "DL",
        "licence fee",
    )

    assert "Status: REPORTED_ONLY" in text
    assert "Not conclusive means" in text


def test_watch_all_is_disabled_in_telegram():
    text = handle_text(123, "/watch ALL")

    assert "disabled inside Telegram" in text
