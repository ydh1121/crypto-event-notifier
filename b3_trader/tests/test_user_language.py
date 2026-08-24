from b3_trader.user_language import score_meaning, telegram_plain_text


def test_score_meaning_bands():
    assert score_meaning(35) == "매우 나쁨"
    assert score_meaning(49.62) == "좋지 않음"
    assert score_meaning(60) == "보통"
    assert score_meaning(70) == "좋음"
    assert score_meaning(82) == "매우 좋음"


def test_telegram_plain_text_replaces_trading_jargon():
    text = "[B3] 시장 위험 확대\n가격 0.6813\nRegime 49.62 / Entry 52.23\nContext 48.2"
    friendly = telegram_plain_text(text)
    assert "지금은 매수하지 않는 구간" in friendly
    assert "전체 시장 분위기: 좋지 않음 (50/100)" in friendly
    assert "지금 매수 타이밍: 좋지 않음 (52/100)" in friendly
    assert "비슷한 코인들의 흐름: 좋지 않음 (48/100)" in friendly
    assert "Regime" not in friendly
    assert "Entry" not in friendly
    assert "Context" not in friendly
