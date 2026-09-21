from __future__ import annotations

import re


def score_meaning(value: float) -> str:
    value = float(value)
    if value < 40:
        return "매우 나쁨"
    if value < 55:
        return "좋지 않음"
    if value < 65:
        return "보통"
    if value < 75:
        return "좋음"
    return "매우 좋음"


def _replace_score_pair(match: re.Match[str]) -> str:
    market = float(match.group(1))
    entry = float(match.group(2))
    return (
        f"전체 시장 분위기: {score_meaning(market)} ({market:.0f}/100)\n"
        f"지금 매수 타이밍: {score_meaning(entry)} ({entry:.0f}/100)"
    )


def _replace_context(match: re.Match[str]) -> str:
    value = float(match.group(1))
    return f"비슷한 코인들의 흐름: {score_meaning(value)} ({value:.0f}/100)"


def telegram_plain_text(text: str) -> str:
    """Convert internal trading jargon into ordinary Korean before Telegram delivery."""
    result = str(text)
    result = result.replace("PAPER 일일 요약", "가상매매 오늘 요약")
    result = result.replace("PAPER 강제청산", "가상 보유분 강제 정리")
    result = result.replace("PAPER 리스크오프 청산", "시장 약세로 가상 보유분 정리")
    result = result.replace("PAPER 매수", "가상 매수")
    result = result.replace("PAPER 진입 차단", "가상 매수 보류")
    result = result.replace("시장 위험 확대", "지금은 매수하지 않는 구간")
    result = result.replace("시장 강세 · 눌림 대기", "시장 흐름은 좋지만 지금 가격은 기다리는 구간")
    result = result.replace("KILL SWITCH 활성", "긴급 정지 켜짐")
    result = result.replace("KILL SWITCH 해제", "긴급 정지 해제")
    result = result.replace("신규 진입 일시정지", "새 매수 잠시 멈춤")
    result = result.replace("신규 진입 재개", "새 매수 다시 시작")
    result = result.replace("리스크오프", "시장 약세")
    result = re.sub(
        r"Regime\s+(-?\d+(?:\.\d+)?)\s*/\s*Entry\s+(-?\d+(?:\.\d+)?)",
        _replace_score_pair,
        result,
    )
    result = re.sub(
        r"Context\s+(-?\d+(?:\.\d+)?)",
        _replace_context,
        result,
    )
    result = result.replace("PAPER", "가상매매")
    return result
