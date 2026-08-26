from __future__ import annotations

import json
import re
import time
from io import BytesIO
from typing import Any

import requests

from .coin_profile_enricher import (
    CoinProfileEnricher,
    USER_AGENT,
    _clean_html,
    _first_sentences,
    _normalize,
    _safe_url,
    _same_project,
    _text,
)
from .http_retry import post_with_retry

PRECISION_PER_EXCHANGE = 3
BACKLOG_LIMIT = 48
MAX_REFERENCE_BYTES = 8_000_000


class CoinProfileResearchCycle:
    """Runs the normal full-market pass plus a bounded quality-repair pass.

    The first pass keeps advancing through every KRW market. The second pass only
    revisits cached projects whose Korean explanation, evidence quality, identity
    confidence, or representative sector is still weak. This prevents unresolved
    projects from waiting for another complete 477/287-market cycle.
    """

    def __init__(self) -> None:
        self.base = CoinProfileEnricher()
        self.session = self.base.session

    def _urls(self) -> tuple[str, str, str]:
        ingest, token = self.base._endpoint()
        if not ingest or not token:
            return "", "", ""
        root = ingest[: -len("/api/ingest-coin-profiles")] if ingest.endswith("/api/ingest-coin-profiles") else ingest.rstrip("/")
        return ingest, root + "/api/coin-profile-backlog", token

    def _backlog(self, url: str, token: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            response = self.session.get(
                url,
                params={"limit": BACKLOG_LIMIT},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            return [], {"status": "backlog_error", "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(payload, dict):
            return [], {"status": "backlog_error", "error": "invalid backlog payload"}
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        return [row for row in rows if isinstance(row, dict)], payload

    def _reference_text(self, url: str) -> str:
        safe = _safe_url(url)
        if not safe:
            return ""
        try:
            response = self.session.get(
                safe,
                timeout=18,
                allow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.8"},
            )
            response.raise_for_status()
        except requests.RequestException:
            return ""
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type or safe.lower().split("?", 1)[0].endswith(".pdf"):
            if len(response.content) > MAX_REFERENCE_BYTES:
                return ""
            try:
                from pypdf import PdfReader

                reader = PdfReader(BytesIO(response.content))
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:8])
            except Exception:
                return ""
            return _clean_html(text, 9000)
        if "html" in content_type or "text" in content_type or not content_type:
            return _clean_html(response.text[:500_000], 9000)
        return ""

    @staticmethod
    def _merge_evidence(profile: dict[str, Any], source: str, url: str, label: str, language: str, weight: float) -> None:
        evidence = profile.get("evidence") if isinstance(profile.get("evidence"), list) else []
        normalized = []
        seen: set[tuple[str, str]] = set()
        for item in evidence:
            if not isinstance(item, dict):
                continue
            key = (_text(item.get("source")), _safe_url(item.get("url")))
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)
        key = (source, _safe_url(url))
        if key not in seen:
            normalized.append({"source": source, "url": _safe_url(url), "label": label, "language": language, "weight": weight})
        profile["evidence"] = normalized[:16]

    def _deepen_profile(self, row: dict[str, str], profile: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        deep_chunks: list[str] = []
        references = (
            (profile.get("homepage"), "official_site_deep", "공식 홈페이지 본문"),
            (profile.get("official_docs"), "official_docs", "공식 Docs"),
            (profile.get("whitepaper"), "whitepaper", "공식 백서"),
        )
        seen_urls: set[str] = set()
        for raw_url, source, label in references:
            url = _safe_url(raw_url)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            text = self._reference_text(url)
            if not text:
                continue
            deep_chunks.append(text)
            language = "ko" if re.search(r"[가-힣]{8,}", text) else "en"
            self._merge_evidence(profile, source, url, label, language, 1.0)
            if language == "ko" and not _text(profile.get("description_ko")):
                profile["description_ko"] = _first_sentences(text, 1400)

        datalab = self.base._upbit_datalab(row["symbol"])
        categories = list(profile.get("categories") or []) if isinstance(profile.get("categories"), list) else []
        for item in datalab.get("categories") or []:
            value = _text(item)
            if value and value not in categories:
                categories.append(value)
        profile["categories"] = categories[:40]
        if datalab:
            self._merge_evidence(profile, "upbit_datalab", _text(datalab.get("url")), "업비트 데이터랩", "ko", 1.0)

        extra = "\n".join(deep_chunks)
        existing_en = _text(profile.get("description_en"))
        if extra and not re.search(r"[가-힣]{8,}", extra):
            deep_en = _first_sentences(extra, 2200)
            if deep_en and deep_en not in existing_en:
                profile["description_en"] = (existing_en + "\n" + deep_en).strip()[:6000]

        if not _text(profile.get("business_summary_ko")) or "sector_unresolved" in reasons:
            corpus = "\n".join([
                _text(profile.get("description_en")),
                extra,
                *[_text(item) for item in profile.get("categories") or []],
                *[_text(item) for item in profile.get("tags") or []],
            ])
            summary = self.base._structured_korean_summary(row, corpus, list(datalab.get("sector_labels") or []))
            if summary:
                profile["business_summary_ko"] = summary
                profile["summary_source"] = "precision_official"

        evidence = profile.get("evidence") if isinstance(profile.get("evidence"), list) else []
        unique_sources = {_text(item.get("source")) for item in evidence if isinstance(item, dict) and _text(item.get("source"))}
        source_count = len(unique_sources)
        profile["source_count"] = source_count
        has_korean = bool(_text(profile.get("business_summary_ko")) or _text(profile.get("description_ko")))
        trusted = any(source in unique_sources for source in {"bithumb_manual", "upbit_datalab", "official_site", "official_site_deep", "official_docs", "whitepaper"})
        if has_korean and trusted and source_count >= 2:
            profile["research_status"] = "verified"
        elif has_korean and source_count >= 2:
            profile["research_status"] = "corroborated"
        elif source_count >= 1:
            profile["research_status"] = "single_source"
        else:
            profile["research_status"] = "unresolved"
        if deep_chunks:
            profile["match_confidence"] = max(float(profile.get("match_confidence") or 0), 0.9)
        profile["verified_at"] = int(time.time())
        return profile

    def _precision_once(self, ingest: str, backlog_url: str, token: str) -> dict[str, Any]:
        backlog, backlog_meta = self._backlog(backlog_url, token)
        if not backlog:
            return {"status": backlog_meta.get("status") or "idle", "processed": 0, "stored": 0, "backlog": backlog_meta}

        groups, market_errors = self.base._market_groups()
        indexes = {exchange: {row["market"]: row for row in rows} for exchange, rows in groups.items()}
        selected: list[tuple[dict[str, str], list[str]]] = []
        counts = {"bithumb": 0, "upbit": 0}
        for item in backlog:
            exchange = "upbit" if _text(item.get("exchange")) == "upbit" else "bithumb"
            if counts[exchange] >= PRECISION_PER_EXCHANGE:
                continue
            market = _text(item.get("market")).upper()
            row = indexes.get(exchange, {}).get(market)
            if not row:
                continue
            reasons = [_text(value) for value in item.get("reasons") or [] if _text(value)]
            selected.append((row, reasons))
            counts[exchange] += 1
            if all(value >= PRECISION_PER_EXCHANGE for value in counts.values()):
                break
        if not selected:
            return {"status": "idle", "processed": 0, "stored": 0, "market_errors": market_errors, "backlog": backlog_meta}

        bithumb_by_symbol = {row["symbol"]: row for row in groups.get("bithumb", [])}
        upbit_by_symbol = {row["symbol"]: row for row in groups.get("upbit", [])}
        research_rows: list[dict[str, str]] = []
        for target, _ in selected:
            preferred = bithumb_by_symbol.get(target["symbol"])
            research_rows.append(preferred if preferred and _same_project(preferred, target) else target)
        try:
            cmc_data = self.base._cmc_batch(research_rows)
        except requests.RequestException:
            cmc_data = {}

        profiles: list[dict[str, Any]] = []
        failures: list[str] = []
        cache: dict[tuple[str, str], dict[str, Any]] = {}
        for (target, reasons), research_row in zip(selected, research_rows):
            key = (research_row["symbol"], _normalize(research_row["english_name"]))
            try:
                if key not in cache:
                    base_profile = self.base._build_profile(
                        research_row,
                        cmc_data.get(research_row["symbol"]),
                        upbit_available=research_row["symbol"] in upbit_by_symbol,
                    )
                    cache[key] = self._deepen_profile(research_row, base_profile, reasons)
                profile = dict(cache[key])
                profile["exchange"] = target["exchange"]
                profile["market"] = target["market"]
                profile["korean_name"] = target["korean_name"] or profile.get("korean_name")
                profile["english_name"] = profile.get("english_name") or target["english_name"]
                profiles.append(profile)
            except Exception as exc:
                failures.append(f"{target['exchange']}|{target['market']}: {type(exc).__name__}: {exc}")
            time.sleep(0.08)

        if not profiles:
            return {"status": "failed", "processed": 0, "stored": 0, "failed": len(failures), "failures": failures[:6], "market_errors": market_errors}

        body = json.dumps({"profiles": profiles}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        response, retries = post_with_retry(
            ingest,
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            timeout=45,
            attempts=4,
        )
        try:
            remote = response.json()
        except ValueError:
            remote = {"ok": True, "stored": len(profiles)}
        reason_counts: dict[str, int] = {}
        for _, reasons in selected:
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        return {
            "status": "researched",
            "processed": len(profiles),
            "stored": int(remote.get("stored") or 0) if isinstance(remote, dict) else 0,
            "failed": len(failures),
            "failures": failures[:6],
            "retries": retries,
            "selected_by_exchange": counts,
            "korean_ready": sum(1 for profile in profiles if profile.get("business_summary_ko") or profile.get("description_ko")),
            "reasons": reason_counts,
            "market_errors": market_errors,
            "backlog_summary": {"by_exchange": backlog_meta.get("by_exchange") or {}, "reasons": backlog_meta.get("reasons") or {}},
        }

    def run_once(self) -> dict[str, Any]:
        general = self.base.run_once()
        ingest, backlog_url, token = self._urls()
        if not ingest or not backlog_url or not token:
            return {**general, "precision": {"status": "not_configured", "processed": 0}}
        precision = self._precision_once(ingest, backlog_url, token)
        return {**general, "precision": precision}


def main() -> None:
    result = CoinProfileResearchCycle().run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
