from __future__ import annotations

import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from .bithumb_client import BithumbClient
from .http_retry import post_with_retry
from .research_control import atomic_json
from .upbit_client import UpbitClient

STATE_PATH = Path("b3_trader/data/research-platform/coin-profile-enrichment-state.json")
BATCH_SIZE = 8
CMC_INFO_URL = "https://pro-api.coinmarketcap.com/public-api/v2/cryptocurrency/info"
CG_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
CG_DETAIL_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"
BITHUMB_MANUAL_URL = "https://feed.bithumb.com/manual"
USER_AGENT = "crypto-research-coin-profiler/32"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "", _text(value).lower())


def _safe_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _clean_html(value: Any, limit: int = 5000) -> str:
    text = _text(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()[:limit]


def _first_sentences(value: Any, limit: int = 520) -> str:
    text = _clean_html(value, 3000)
    if not text:
        return ""
    chunks = re.split(r"(?<=[.!?。！？])\s+|(?<=다\.)\s*", text)
    out = ""
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        candidate = (out + " " + chunk).strip()
        if len(candidate) > limit:
            break
        out = candidate
        if len(out) >= 180:
            break
    return (out or text[:limit]).strip()


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


class CoinProfileEnricher:
    """Continuously researches every KRW market using public/reference sources only.

    The component never touches orders or private balances. It resolves exchange
    names first, then cross-checks CoinMarketCap, CoinGecko and the project's
    official links. Bithumb's Korean asset manual is used when its public page
    exposes a matching PDF link. Results are sent to the read-only Pages D1
    cache through the existing ingest-token boundary.
    """

    def __init__(self) -> None:
        load_dotenv(override=True)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json,text/html;q=0.9,*/*;q=0.7", "User-Agent": USER_AGENT})
        self.bithumb = BithumbClient(timeout=8.0)
        self.upbit = UpbitClient(timeout=8.0)

    @staticmethod
    def _endpoint() -> tuple[str, str]:
        ingest = os.getenv("CLOUDFLARE_VIEWER_INGEST_URL", "").strip()
        token = os.getenv("CLOUDFLARE_VIEWER_INGEST_TOKEN", "").strip()
        if not ingest or not token:
            return "", ""
        if ingest.endswith("/api/ingest"):
            base = ingest[: -len("/api/ingest")]
        else:
            base = ingest.rstrip("/")
        return base + "/api/ingest-coin-profiles", token

    def _markets(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for exchange, source in (("bithumb", self.bithumb.market_all()), ("upbit", self.upbit.krw_markets(details=True))):
            for row in source:
                market = _text(row.get("market")).upper()
                if not market.startswith("KRW-"):
                    continue
                symbol = market.removeprefix("KRW-")
                rows.append({
                    "exchange": exchange,
                    "market": market,
                    "symbol": symbol,
                    "korean_name": _text(row.get("korean_name")) or symbol,
                    "english_name": _text(row.get("english_name")) or symbol,
                })
        rows.sort(key=lambda row: (row["exchange"], row["market"]))
        return rows

    def _cmc_batch(self, rows: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
        symbols = sorted({row["symbol"] for row in rows})
        if not symbols:
            return {}
        response = self.session.get(
            CMC_INFO_URL,
            params={"symbol": ",".join(symbols), "aux": "urls,logo,description,tags,platform,date_added,notice,status"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for key, raw in data.items():
            values = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
            for item in values:
                if not isinstance(item, dict):
                    continue
                symbol = _text(item.get("symbol") or key).upper()
                if symbol:
                    grouped.setdefault(symbol, []).append(item)
        return grouped

    @staticmethod
    def _choose_cmc(raw: Any, row: dict[str, str]) -> tuple[dict[str, Any] | None, float]:
        candidates = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        candidates = [item for item in candidates if isinstance(item, dict)]
        if not candidates:
            return None, 0.0
        wanted = _normalize(row.get("english_name"))
        exact = [item for item in candidates if wanted and _normalize(item.get("name")) == wanted]
        if exact:
            return exact[0], 0.98
        if len(candidates) == 1:
            return candidates[0], 0.88
        return candidates[0], 0.55

    def _coingecko(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, float]:
        response = self.session.get(CG_SEARCH_URL, params={"query": row["symbol"]}, timeout=15)
        if not response.ok:
            return None, 0.0
        search = response.json()
        candidates = [item for item in (search.get("coins") or []) if isinstance(item, dict) and _text(item.get("symbol")).upper() == row["symbol"]]
        if not candidates:
            return None, 0.0
        wanted = _normalize(row.get("english_name"))
        candidates.sort(key=lambda item: (0 if wanted and _normalize(item.get("name")) == wanted else 1, int(item.get("market_cap_rank") or 999999)))
        chosen = candidates[0]
        confidence = 0.98 if wanted and _normalize(chosen.get("name")) == wanted else (0.84 if len(candidates) == 1 else 0.62)
        coin_id = _text(chosen.get("id"))
        if not coin_id:
            return None, 0.0
        detail = self.session.get(
            CG_DETAIL_URL.format(coin_id=coin_id),
            params={"localization": "true", "tickers": "false", "market_data": "false", "community_data": "false", "developer_data": "false", "sparkline": "false"},
            timeout=18,
        )
        if not detail.ok:
            return None, 0.0
        value = detail.json()
        return (value if isinstance(value, dict) else None), confidence

    def _official_meta(self, url: str) -> dict[str, str]:
        safe = _safe_url(url)
        if not safe:
            return {}
        try:
            response = self.session.get(safe, timeout=12, allow_redirects=True, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            response.raise_for_status()
        except requests.RequestException:
            return {}
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            return {}
        text = response.text[:350_000]
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        desc_match = re.search(r"<meta[^>]+(?:name|property)=[\"'](?:description|og:description)[\"'][^>]+content=[\"'](.*?)[\"']", text, re.I | re.S)
        if not desc_match:
            desc_match = re.search(r"<meta[^>]+content=[\"'](.*?)[\"'][^>]+(?:name|property)=[\"'](?:description|og:description)[\"']", text, re.I | re.S)
        return {
            "url": response.url,
            "title": _clean_html(title_match.group(1) if title_match else "", 240),
            "description": _clean_html(desc_match.group(1) if desc_match else "", 1000),
        }

    def _bithumb_manual(self, row: dict[str, str]) -> dict[str, str]:
        if row["exchange"] != "bithumb":
            return {}
        for params in ({"keyword": row["symbol"]}, {"search": row["symbol"]}):
            try:
                response = self.session.get(BITHUMB_MANUAL_URL, params=params, timeout=12)
                if not response.ok:
                    continue
            except requests.RequestException:
                continue
            html_text = response.text
            urls = re.findall(r"https://feed-content\.bithumb\.com/cms/[^\"'<>\s]+\.pdf", html_text, flags=re.I)
            if not urls:
                urls = [html.unescape(x) for x in re.findall(r"href=[\"']([^\"']+\.pdf)[\"']", html_text, flags=re.I)]
            for candidate in urls[:6]:
                if row["symbol"].upper() not in html_text.upper() and row["korean_name"] not in html_text:
                    continue
                result = self._read_manual_pdf(candidate)
                if result:
                    result["url"] = candidate
                    return result
        return {}

    def _read_manual_pdf(self, url: str) -> dict[str, str]:
        try:
            from io import BytesIO
            from pypdf import PdfReader
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            if len(response.content) > 8_000_000:
                return {}
            reader = PdfReader(BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:6])
        except Exception:
            return {}
        text = re.sub(r"[ \t]+", " ", text)
        intro = re.search(r"가상자산\s*소개\s*(.*?)\s*가상자산\s*기본\s*정보", text, re.S)
        purpose = re.search(r"가상자산의\s*이용목적\s*(.*?)\s*가상자산\s*백서", text, re.S)
        homepage = re.search(r"가상자산\s*홈페이지\s*(https?://\S+)", text, re.S)
        whitepaper = re.search(r"가상자산\s*백서\s*(https?://\S+)", text, re.S)
        return {
            "description_ko": _clean_html(intro.group(1) if intro else "", 1800),
            "purpose_ko": _clean_html(purpose.group(1) if purpose else "", 500),
            "homepage": _safe_url((homepage.group(1) if homepage else "").rstrip(".,)")),
            "whitepaper": _safe_url((whitepaper.group(1) if whitepaper else "").rstrip(".,)")),
        }

    @staticmethod
    def _url_first(urls: Any, key: str) -> str:
        if not isinstance(urls, dict):
            return ""
        for item in urls.get(key) or []:
            safe = _safe_url(item)
            if safe:
                return safe
        return ""

    def _build_profile(self, row: dict[str, str], cmc_raw: Any) -> dict[str, Any]:
        cmc, cmc_conf = self._choose_cmc(cmc_raw, row)
        try:
            cg, cg_conf = self._coingecko(row)
        except requests.RequestException:
            cg, cg_conf = None, 0.0
        manual = self._bithumb_manual(row)
        cmc_urls = cmc.get("urls") if isinstance(cmc, dict) and isinstance(cmc.get("urls"), dict) else {}
        cg_links = cg.get("links") if isinstance(cg, dict) and isinstance(cg.get("links"), dict) else {}
        homepage = _safe_url(manual.get("homepage")) or self._url_first(cmc_urls, "website")
        if not homepage and isinstance(cg_links.get("homepage"), list):
            homepage = next((_safe_url(v) for v in cg_links.get("homepage") or [] if _safe_url(v)), "")
        official = self._official_meta(homepage)
        cg_desc = cg.get("description") if isinstance(cg, dict) and isinstance(cg.get("description"), dict) else {}
        cmc_desc = _clean_html(cmc.get("description") if isinstance(cmc, dict) else "", 3500)
        ko_desc = _clean_html(manual.get("description_ko"), 3500) or _clean_html(cg_desc.get("ko"), 3500)
        en_desc = cmc_desc or _clean_html(cg_desc.get("en"), 3500) or _clean_html(official.get("description"), 1800)
        cmc_tags = _list(cmc.get("tags") if isinstance(cmc, dict) else [])
        cg_categories = _list(cg.get("categories") if isinstance(cg, dict) else [])
        categories: list[str] = []
        for item in [*cmc_tags, *cg_categories]:
            if item not in categories:
                categories.append(item)
        docs = self._url_first(cmc_urls, "technical_doc")
        source_code = self._url_first(cmc_urls, "source_code")
        whitepaper = _safe_url(manual.get("whitepaper")) or docs
        community: list[str] = []
        for key in ("twitter", "reddit", "message_board", "chat", "announcement"):
            value = self._url_first(cmc_urls, key)
            if value and value not in community:
                community.append(value)
        if isinstance(cg_links, dict):
            for value in (
                cg_links.get("subreddit_url"),
                f"https://x.com/{_text(cg_links.get('twitter_screen_name'))}" if _text(cg_links.get("twitter_screen_name")) else "",
                f"https://t.me/{_text(cg_links.get('telegram_channel_identifier'))}" if _text(cg_links.get("telegram_channel_identifier")) else "",
            ):
                safe = _safe_url(value)
                if safe and safe not in community:
                    community.append(safe)
            repos = cg_links.get("repos_url") if isinstance(cg_links.get("repos_url"), dict) else {}
            if not source_code:
                source_code = next((_safe_url(v) for v in repos.get("github") or [] if _safe_url(v)), "")
        evidence: list[dict[str, Any]] = []
        if manual:
            evidence.append({"source": "bithumb_manual", "url": manual.get("url", ""), "label": "빗썸 가상자산 설명서", "language": "ko", "weight": 1.0})
        if cmc:
            evidence.append({"source": "coinmarketcap", "url": f"https://coinmarketcap.com/currencies/{_text(cmc.get('slug'))}/" if _text(cmc.get("slug")) else "", "label": "CoinMarketCap metadata", "language": "en", "weight": cmc_conf})
        if cg:
            evidence.append({"source": "coingecko", "url": f"https://www.coingecko.com/en/coins/{_text(cg.get('id'))}" if _text(cg.get("id")) else "", "label": "CoinGecko metadata", "language": "multi", "weight": cg_conf})
        if official:
            evidence.append({"source": "official_site", "url": official.get("url", homepage), "label": official.get("title") or "공식 홈페이지", "language": "unknown", "weight": 1.0})
        if source_code:
            evidence.append({"source": "source_code", "url": source_code, "label": "공식 소스코드", "language": "code", "weight": 0.9})
        source_count = len({item["source"] for item in evidence})
        best_conf = max(cmc_conf, cg_conf, 0.0)
        if manual and source_count >= 2:
            status = "verified"
        elif source_count >= 3 and best_conf >= 0.8:
            status = "corroborated"
        elif source_count >= 1:
            status = "single_source"
        else:
            status = "unresolved"
        business_ko = _first_sentences(ko_desc)
        business_en = _first_sentences(en_desc)
        summary_source = "bithumb_manual" if manual.get("description_ko") else "coingecko_ko" if _clean_html(cg_desc.get("ko") if isinstance(cg_desc, dict) else "") else "coinmarketcap" if cmc_desc else "official_site" if official.get("description") else ""
        return {
            "exchange": row["exchange"], "market": row["market"], "symbol": row["symbol"],
            "korean_name": row["korean_name"],
            "english_name": _text(cmc.get("name") if isinstance(cmc, dict) else "") or _text(cg.get("name") if isinstance(cg, dict) else "") or row["english_name"],
            "provider": "multi-source" if source_count >= 2 else (evidence[0]["source"] if evidence else "exchange"),
            "provider_id": _text(cmc.get("id") if isinstance(cmc, dict) else "") or _text(cg.get("id") if isinstance(cg, dict) else ""),
            "description_ko": ko_desc, "description_en": en_desc,
            "business_summary_ko": business_ko, "business_summary_en": business_en,
            "categories": categories[:40], "tags": cmc_tags[:40], "homepage": homepage,
            "image_url": _safe_url(cmc.get("logo") if isinstance(cmc, dict) else "") or _safe_url((cg.get("image") or {}).get("small") if isinstance(cg, dict) and isinstance(cg.get("image"), dict) else ""),
            "official_docs": docs, "whitepaper": whitepaper, "source_code": source_code,
            "community": community[:12], "evidence": evidence[:12], "research_status": status,
            "summary_source": summary_source, "source_count": source_count, "match_confidence": round(best_conf, 3),
            "verified_at": int(time.time()),
        }

    def run_once(self) -> dict[str, Any]:
        endpoint, token = self._endpoint()
        if not endpoint or not token:
            return {"status": "not_configured", "configured": False}
        markets = self._markets()
        if not markets:
            return {"status": "waiting_for_markets", "configured": True, "processed": 0}
        state = _read_json(STATE_PATH)
        cursor = int(state.get("cursor") or 0) % len(markets)
        count = min(BATCH_SIZE, len(markets))
        batch = [markets[(cursor + offset) % len(markets)] for offset in range(count)]
        cmc_data: dict[str, Any] = {}
        try:
            cmc_data = self._cmc_batch(batch)
        except requests.RequestException:
            cmc_data = {}
        profiles: list[dict[str, Any]] = []
        failures: list[str] = []
        for row in batch:
            try:
                profiles.append(self._build_profile(row, cmc_data.get(row["symbol"])))
            except Exception as exc:
                failures.append(f"{row['exchange']}|{row['market']}: {type(exc).__name__}: {exc}")
            time.sleep(0.12)
        if profiles:
            body = json.dumps({"profiles": profiles}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            response, retries = post_with_retry(
                endpoint, data=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
                timeout=35, attempts=4,
            )
            try:
                remote = response.json()
            except ValueError:
                remote = {"ok": True, "stored": len(profiles)}
        else:
            retries = 0
            remote = {"ok": False, "stored": 0}
        next_cursor = (cursor + count) % len(markets)
        cycles = int(state.get("completed_cycles") or 0) + (1 if next_cursor <= cursor else 0)
        result = {
            "status": "researched", "configured": True, "market_total": len(markets),
            "processed": len(profiles), "failed": len(failures), "failures": failures[:4],
            "stored": int(remote.get("stored") or 0) if isinstance(remote, dict) else 0,
            "cursor": next_cursor, "completed_cycles": cycles, "retries": retries,
            "research_status": {name: sum(1 for p in profiles if p.get("research_status") == name) for name in ("verified", "corroborated", "single_source", "unresolved")},
        }
        atomic_json(STATE_PATH, {**result, "updated_at": time.time()})
        return result


def main() -> None:
    result = CoinProfileEnricher().run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
