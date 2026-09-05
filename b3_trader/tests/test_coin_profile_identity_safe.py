from b3_trader.coin_profile_identity_safe import (
    _drop_ungrounded_profile,
    _manual_identity_matches,
    _manual_intro_identity_matches,
)


def row(symbol: str, korean_name: str, english_name: str) -> dict[str, str]:
    return {
        "exchange": "bithumb",
        "market": f"KRW-{symbol}",
        "symbol": symbol,
        "korean_name": korean_name,
        "english_name": english_name,
    }


def test_manual_identity_accepts_matching_header() -> None:
    text = "가상자산 설명서\n비트코인 (Bitcoin)\nBTC\n가상자산 소개\n비트코인은 디지털 자산입니다."
    assert _manual_identity_matches(row("BTC", "비트코인", "Bitcoin"), text)


def test_manual_identity_accepts_split_marker_matching_header() -> None:
    text = "가상자산 설명서\n비트코인 (Bitcoin)\nBTC\n가상자산\n소개\n비트코인은 디지털 자산입니다."
    assert _manual_identity_matches(row("BTC", "비트코인", "Bitcoin"), text)


def test_manual_identity_rejects_body_only_bitcoin_mentions() -> None:
    text = (
        "가상자산 설명서\n펌프 (PUMP)\nPUMPBTC\n가상자산 소개\n"
        "펌프는 비트코인을 스테이킹하고 Bitcoin 유동성을 제공하는 프로젝트입니다."
    )
    assert not _manual_identity_matches(row("BTC", "비트코인", "Bitcoin"), text)


def test_manual_identity_rejects_split_marker_body_only_bitcoin_mentions() -> None:
    text = (
        "가상자산 설명서\n펌프 (PUMP)\nPUMPBTC\n가상자산\n소개\n"
        "펌프는 비트코인을 스테이킹하고 Bitcoin 유동성을 제공하는 프로젝트입니다."
    )
    assert not _manual_identity_matches(row("BTC", "비트코인", "Bitcoin"), text)


def test_manual_identity_rejects_missing_header_marker() -> None:
    text = "펌프(PUMP)는 비트코인을 스테이킹하고 Bitcoin과 BTC 유동성을 제공합니다."
    assert not _manual_identity_matches(row("BTC", "비트코인", "Bitcoin"), text)


def test_manual_identity_rejects_prefix_name_collision() -> None:
    text = "가상자산 설명서\n그래비티토큰 (Grvt)\nGRVT\n가상자산 소개\n온체인 파생상품 프로젝트입니다."
    assert not _manual_identity_matches(row("G", "그래비티", "Gravity"), text)


def test_manual_identity_rejects_symbol_embedded_in_other_symbol() -> None:
    text = "가상자산 설명서\n엣지엑스 (edgeX)\nEDGEX\n가상자산 소개\n탈중앙 파생상품 거래소입니다."
    assert not _manual_identity_matches(row("EDGE", "디피니티브", "Definitive"), text)


def test_manual_identity_accepts_korean_and_english_when_symbol_is_one_char() -> None:
    text = "가상자산 설명서\n소닉 (Sonic)\nS\n가상자산 소개\n레이어1 네트워크입니다."
    assert _manual_identity_matches(row("S", "소닉", "Sonic"), text)


def test_manual_intro_accepts_current_project_lead() -> None:
    assert _manual_intro_identity_matches(
        row("BTC", "비트코인", "Bitcoin"),
        "비트코인(Bitcoin)은 중앙관리자 없이 전송되는 디지털 자산입니다.",
    )


def test_manual_intro_rejects_foreign_project_lead_even_when_btc_is_mentioned() -> None:
    assert not _manual_intro_identity_matches(
        row("BTC", "비트코인", "Bitcoin"),
        "펌프(PUMP)는 비트코인을 스테이킹하고 BTC 유동성을 제공하는 프로젝트입니다.",
    )


def test_ungrounded_profile_drops_template_business_content() -> None:
    profile = _drop_ungrounded_profile({
        "source_count": 0,
        "research_status": "unresolved",
        "business_summary_ko": "쎄타퓨엘(TFUEL)는 인공지능 프로젝트입니다.",
        "description_ko": "추정 설명",
        "description_en": "guessed description",
        "homepage": "https://wrong.example/",
        "categories": ["AI"],
        "tags": ["artificial intelligence"],
        "community": ["https://wrong.example/community"],
        "evidence": [],
        "match_confidence": 0.7,
    })
    assert profile["business_summary_ko"] == ""
    assert profile["description_ko"] == ""
    assert profile["homepage"] == ""
    assert profile["categories"] == []
    assert profile["research_status"] == "unresolved"
    assert profile["match_confidence"] == 0.0
    assert profile["ungrounded_content_removed"] is True
