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
BATCH_PER_EXCHANGE = 12
CMC_INFO_URL = "https://pro-api.coinmarketcap.com/public-api/v2/cryptocurrency/info"
CG_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
CG_DETAIL_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"
BITHUMB_MANUAL_URL = "https://feed.bithumb.com/manual"
UPBIT_DATALAB_URL = "https://datalab.upbit.com/assets/{symbol}/summary"
USER_AGENT = "crypto-research-coin-profiler/33"

UPBIT_SECTOR_LABELS = (
    "AI", "DEX", "DID", "NFT/게임", "RWA", "ZK 인프라", "광고", "교육/기타 콘텐츠",
    "데이터 인프라", "렌딩", "메타버스", "모놀리식 블록체인", "모듈러 블록체인", "밈",
    "상호운용성/브릿지", "소셜/DAO", "스테이블코인", "스테이블코인 연관", "스토리지",
    "애그리게이터", "오라클", "월렛/메시징", "유동화 스테이킹/리스테이킹", "의료",
    "크라우드펀딩", "지급결제", "팬토큰",
)

UPBIT_CATEGORY_ALIASES = {
    "AI": ["artificial intelligence"],
    "DEX": ["decentralized exchange"],
    "DID": ["decentralized identity"],
    "NFT/게임": ["gaming", "nft"],
    "RWA": ["real world asset"],
    "ZK 인프라": ["zero knowledge"],
    "광고": ["advertising"],
    "교육/기타 콘텐츠": ["creator economy"],
    "데이터 인프라": ["data infrastructure"],
    "렌딩": ["lending"],
    "메타버스": ["metaverse"],
    "모놀리식 블록체인": ["layer 1", "smart contract platform"],
    "모듈러 블록체인": ["modular blockchain", "data availability"],
    "밈": ["meme"],
    "상호운용성/브릿지": ["interoperability", "cross-chain"],
    "소셜/DAO": ["socialfi", "dao"],
    "스테이블코인": ["stablecoin"],
    "스테이블코인 연관": ["stablecoin infrastructure"],
    "스토리지": ["decentralized storage"],
    "애그리게이터": ["dex aggregator"],
    "오라클": ["oracle"],
    "월렛/메시징": ["wallet", "messaging protocol"],
    "유동화 스테이킹/리스테이킹": ["liquid staking", "restaking"],
    "의료": ["healthcare"],
    "크라우드펀딩": ["crowdfunding"],
    "지급결제": ["payments", "remittance"],
    "팬토큰": ["fan token"],
}

_KO_BUSINESS_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("liquid restaking", "restaking", "restake"), "스테이킹 자산을 재활용해 여러 네트워크의 검증과 보안을 지원하는 리스테이킹 인프라"),
    (("liquid staking",), "스테이킹 자산을 유동화 토큰으로 바꿔 보상을 받으면서 다른 온체인 서비스에서도 활용할 수 있게 하는 유동화 스테이킹 서비스"),
    (("lending", "borrowing", "money market"), "온체인에서 담보 대출·차입과 이자 시장을 제공하는 디파이 금융 프로토콜"),
    (("dex aggregator", "swap aggregator", "liquidity aggregator"), "여러 탈중앙화 거래소의 유동성을 비교해 더 나은 교환 경로를 찾아주는 DEX 애그리게이터"),
    (("decentralized exchange", "automated market maker", " amm ", "orderbook dex", "order book dex"), "온체인 토큰 교환과 유동성 공급을 제공하는 탈중앙화 거래 프로토콜"),
    (("oracle", "price feed"), "블록체인 밖의 가격·시장 데이터를 스마트컨트랙트에 전달하는 오라클 인프라"),
    (("data availability", "modular blockchain", "shared sequencer"), "롤업과 앱체인에 데이터 가용성·정산·시퀀싱 기능을 제공하는 모듈러 블록체인 인프라"),
    (("zero knowledge", "zero-knowledge", "zkvm", "zk proof", "zk-proof"), "영지식증명으로 계산 결과를 검증하거나 개인정보를 보호하는 ZK 인프라"),
    (("cross-chain", "cross chain", "interoperability", "bridge protocol", "omnichain"), "서로 다른 블록체인 사이의 자산·메시지 이동을 연결하는 상호운용성 인프라"),
    (("decentralized storage", "distributed storage", "storage network"), "사용자의 저장공간을 분산 네트워크로 연결해 파일·데이터 저장 서비스를 제공하는 탈중앙 스토리지 프로젝트"),
    (("gpu", "decentralized compute", "distributed compute", "computing network", "compute marketplace"), "GPU·컴퓨팅 자원을 네트워크로 연결해 연산 능력을 공급하는 분산 컴퓨팅 프로젝트"),
    (("ai agent", "ai agents", "artificial intelligence", "machine learning"), "인공지능 모델·에이전트·연산 또는 AI 데이터 서비스를 블록체인과 결합하는 프로젝트"),
    (("indexing", "data indexing", "blockchain data", "data marketplace", "data infrastructure"), "온체인·오프체인 데이터를 수집·색인·조회할 수 있게 하는 데이터 인프라"),
    (("real world asset", "real-world asset", "tokenized treasury", "tokenized securities", "tokenized asset"), "채권·국채·신용·부동산 같은 현실 자산과 현금흐름을 온체인으로 연결하는 RWA 프로젝트"),
    (("payment", "payments", "remittance", "merchant payment"), "가치 이전·송금·상거래 결제를 빠르게 처리하는 디지털 결제 네트워크"),
    (("gaming", "gamefi", "onchain game", "on-chain game"), "게임 경제·아이템·플레이어 활동을 블록체인에 연결하는 온체인 게임 프로젝트"),
    (("metaverse", "virtual world"), "가상세계와 디지털 자산 소유권을 블록체인에 연결하는 메타버스 프로젝트"),
    (("non-fungible", " nft ", "nft marketplace", "creator economy"), "NFT 발행·거래와 디지털 창작물의 소유권·수익화를 지원하는 프로젝트"),
    (("privacy", "anonymous transaction", "confidential transaction"), "거래정보와 사용자 데이터를 선택적으로 보호하는 프라이버시 기술 프로젝트"),
    (("decentralized identity", "digital identity", "social graph", "socialfi"), "사용자 신원·자격증명·소셜 그래프를 온체인에 연결하는 아이덴티티·소셜 프로젝트"),
    (("wallet", "account abstraction", "messaging protocol"), "지갑·계정 추상화 또는 온체인 메시징을 통해 사용자 접근성을 높이는 인프라"),
    (("fan token", "sports fan", "entertainment token"), "스포츠·엔터테인먼트 IP와 팬 참여·멤버십을 토큰 경제로 연결하는 프로젝트"),
    (("advertising", "attention economy", "ad network"), "광고 노출·사용자 관심·리워드와 광고주 정산을 블록체인에 연결하는 광고 플랫폼"),
    (("desci", "healthcare", "medical data", "biotech"), "의료·생명과학 데이터 또는 연구자금·연구 IP를 블록체인으로 관리하는 프로젝트"),
    (("crowdfunding", "quadratic funding", "grants platform"), "프로젝트·커뮤니티의 자금 모집과 보조금 배분을 온체인으로 운영하는 크라우드펀딩 프로젝트"),
    (("stablecoin",), "법정통화나 담보자산에 가치를 연동해 온체인 결제·송금·디파이에서 안정적인 교환수단을 제공하는 스테이블코인 프로젝트"),
    (("meme coin", "memecoin", "meme token"), "인터넷 문화와 커뮤니티 참여를 중심으로 토큰 경제와 브랜드를 형성하는 밈 프로젝트"),
    (("layer 2", "layer-2", "rollup"), "기반 블록체인의 거래를 묶어 처리해 수수료와 처리량을 개선하는 레이어2 확장 네트워크"),
    (("layer 1", "layer-1", "smart contract platform", "smart-contract platform"), "자체 합의·검증 네트워크 위에서 스마트컨트랙트와 앱을 실행하는 레이어1 블록체인"),
)

_UPBIT_BUSINESS = {
    "AI": "AI 모델·에이전트·연산 또는 데이터 서비스를 블록체인과 결합하는 프로젝트",
    "DEX": "온체인 토큰 교환과 유동성 공급을 제공하는 탈중앙화 거래 프로젝트",
    "DID": "탈중앙 신원·자격증명과 사용자 데이터 소유권을 다루는 프로젝트",
    "NFT/게임": "게임 경제 또는 NFT 기반 디지털 소유권과 거래를 제공하는 프로젝트",
    "RWA": "현실 자산의 권리·현금흐름을 토큰화해 온체인 금융에 연결하는 프로젝트",
    "ZK 인프라": "영지식증명 기반의 검증·확장·프라이버시 기술을 제공하는 프로젝트",
    "광고": "광고·사용자 관심·리워드와 마케팅 정산을 블록체인에 연결하는 프로젝트",
    "교육/기타 콘텐츠": "교육·콘텐츠 제작과 소비·저작권 또는 리워드를 블록체인에 연결하는 프로젝트",
    "데이터 인프라": "블록체인 데이터를 수집·색인·분석·유통하는 데이터 인프라 프로젝트",
    "렌딩": "담보 대출·차입과 온체인 이자 시장을 제공하는 디파이 프로젝트",
    "메타버스": "가상세계와 디지털 자산 소유권을 연결하는 메타버스 프로젝트",
    "모놀리식 블록체인": "자체 네트워크에서 합의·실행·정산을 처리하는 스마트컨트랙트 블록체인",
    "모듈러 블록체인": "블록체인의 실행·정산·데이터 가용성 기능을 분리해 확장성을 높이는 인프라",
    "밈": "커뮤니티와 인터넷 문화를 중심으로 유동성과 브랜드를 형성하는 밈 프로젝트",
    "상호운용성/브릿지": "서로 다른 블록체인 사이의 자산과 메시지 이동을 연결하는 프로젝트",
    "소셜/DAO": "소셜 네트워크·커뮤니티 또는 DAO 거버넌스를 온체인에서 운영하는 프로젝트",
    "스테이블코인": "외부 기준자산에 가격을 연동해 결제·송금·디파이에 쓰이는 스테이블코인",
    "스테이블코인 연관": "스테이블코인의 발행·유동성·담보·결제 생태계를 지원하는 프로젝트",
    "스토리지": "분산 네트워크로 파일·데이터 저장공간을 공급하는 스토리지 프로젝트",
    "애그리게이터": "여러 거래·유동성·수익 경로를 모아 최적 경로를 제시하는 애그리게이터",
    "오라클": "외부 가격·이벤트 데이터를 스마트컨트랙트에 전달하는 오라클 프로젝트",
    "월렛/메시징": "지갑·계정·메시징 기능을 제공해 온체인 사용성을 높이는 프로젝트",
    "유동화 스테이킹/리스테이킹": "스테이킹 자산의 유동화 또는 재사용을 통해 보안과 수익 기회를 제공하는 프로젝트",
    "의료": "의료·생명과학 데이터나 연구 협업을 블록체인에 연결하는 프로젝트",
    "크라우드펀딩": "기부·후원·보조금과 프로젝트 자금 배분을 온체인으로 운영하는 프로젝트",
    "지급결제": "송금·상거래 결제와 가치 이전을 빠르게 처리하는 결제 프로젝트",
    "팬토큰": "스포츠·엔터테인먼트 팬 참여와 멤버십·리워드를 토큰으로 연결하는 프로젝트",
}


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
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
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


def _has_keyword(corpus: str, keyword: str) -> bool:
    needle = keyword.lower().strip()
    if not needle:
        return False
    if len(needle) <= 4 and re.fullmatch(r"[a-z0-9]+", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", corpus, re.I) is not None
    return needle in corpus


def _same_project(a: dict[str, str], b: dict[str, str]) -> bool:
    if a.get("symbol") != b.get("symbol"):
        return False
    left, right = _normalize(a.get("english_name")), _normalize(b.get("english_name"))
    if not left or not right:
        return False
    if left == right:
        return True
    return len(left) >= 5 and len(right) >= 5 and (left in right or right in left)


class CoinProfileEnricher:
    """Continuously researches every KRW market using public/reference sources only.

    Bithumb and Upbit advance with independent cursors so one exchange can never
    starve the other. Korean project text is preferred; when a native Korean
    description is unavailable, a structured Korean summary is built only from
    corroborated project metadata/categories rather than exposing English as the
    primary UI copy.
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

    def _market_groups(self) -> tuple[dict[str, list[dict[str, str]]], dict[str, str]]:
        groups: dict[str, list[dict[str, str]]] = {"bithumb": [], "upbit": []}
        errors: dict[str, str] = {}
        sources: tuple[tuple[str, Any], ...] = (
            ("bithumb", lambda: self.bithumb.market_all()),
            ("upbit", lambda: self.upbit.krw_markets(details=True)),
        )
        for exchange, loader in sources:
            try:
                source = loader()
            except Exception as exc:
                errors[exchange] = f"{type(exc).__name__}: {exc}"
                continue
            for row in source:
                market = _text(row.get("market")).upper()
                if not market.startswith("KRW-"):
                    continue
                symbol = market.removeprefix("KRW-")
                groups[exchange].append({
                    "exchange": exchange,
                    "market": market,
                    "symbol": symbol,
                    "korean_name": _text(row.get("korean_name")) or symbol,
                    "english_name": _text(row.get("english_name")) or symbol,
                })
            groups[exchange].sort(key=lambda row: row["market"])
        return groups, errors

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
        if "html" not in response.headers.get("content-type", "").lower():
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

    def _upbit_datalab(self, symbol: str) -> dict[str, Any]:
        url = UPBIT_DATALAB_URL.format(symbol=symbol)
        try:
            response = self.session.get(url, timeout=12, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            if not response.ok:
                return {}
        except requests.RequestException:
            return {}
        visible = _clean_html(response.text, 180_000)
        labels: list[str] = []
        for label in UPBIT_SECTOR_LABELS:
            if label == "AI":
                found = re.search(r"(?<![A-Za-z])AI(?![A-Za-z])", visible) is not None
            else:
                found = label in visible
            if found and label not in labels:
                labels.append(label)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S)
        categories: list[str] = []
        for label in labels:
            categories.append(label)
            categories.extend(alias for alias in UPBIT_CATEGORY_ALIASES.get(label, []) if alias not in categories)
        return {"url": response.url, "title": _clean_html(title_match.group(1) if title_match else "", 200), "categories": categories[:16], "sector_labels": labels[:8]}

    @staticmethod
    def _url_first(urls: Any, key: str) -> str:
        if not isinstance(urls, dict):
            return ""
        for item in urls.get(key) or []:
            safe = _safe_url(item)
            if safe:
                return safe
        return ""

    @staticmethod
    def _structured_korean_summary(row: dict[str, str], corpus: str, upbit_categories: list[str]) -> str:
        name = row.get("korean_name") or row.get("english_name") or row["symbol"]
        symbol = row["symbol"]
        normalized = f" {corpus.lower()} "
        phrases: list[str] = []
        for keywords, phrase in _KO_BUSINESS_RULES:
            if any(_has_keyword(normalized, keyword) for keyword in keywords):
                if phrase not in phrases:
                    phrases.append(phrase)
            if len(phrases) >= 2:
                break
        if not phrases:
            for label in upbit_categories:
                phrase = _UPBIT_BUSINESS.get(label)
                if phrase:
                    phrases.append(phrase)
                    break
        if not phrases:
            return ""
        summary = f"{name}({symbol})는 {phrases[0]}입니다."
        if len(phrases) > 1:
            summary += f" 또한 {phrases[1]} 기능을 함께 제공합니다."
        return summary[:650]

    def _build_profile(self, row: dict[str, str], cmc_raw: Any, *, upbit_available: bool) -> dict[str, Any]:
        cmc, cmc_conf = self._choose_cmc(cmc_raw, row)
        manual = self._bithumb_manual(row)
        datalab = self._upbit_datalab(row["symbol"]) if upbit_available else {}
        need_cg = not manual.get("description_ko") or not cmc or cmc_conf < 0.8
        if need_cg:
            try:
                cg, cg_conf = self._coingecko(row)
            except requests.RequestException:
                cg, cg_conf = None, 0.0
        else:
            cg, cg_conf = None, 0.0
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
        upbit_categories = _list(datalab.get("sector_labels"))
        upbit_category_terms = _list(datalab.get("categories"))
        categories: list[str] = []
        for item in [*upbit_category_terms, *cmc_tags, *cg_categories]:
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
        if datalab:
            evidence.append({"source": "upbit_datalab", "url": datalab.get("url", ""), "label": "업비트 데이터랩", "language": "ko", "weight": 1.0})
        if cmc:
            evidence.append({"source": "coinmarketcap", "url": f"https://coinmarketcap.com/currencies/{_text(cmc.get('slug'))}/" if _text(cmc.get("slug")) else "", "label": "CoinMarketCap metadata", "language": "en", "weight": cmc_conf})
        if cg:
            evidence.append({"source": "coingecko", "url": f"https://www.coingecko.com/en/coins/{_text(cg.get('id'))}" if _text(cg.get("id")) else "", "label": "CoinGecko metadata", "language": "multi", "weight": cg_conf})
        if official:
            evidence.append({"source": "official_site", "url": official.get("url", homepage), "label": official.get("title") or "공식 홈페이지", "language": "unknown", "weight": 1.0})
        if source_code:
            evidence.append({"source": "source_code", "url": source_code, "label": "공식 소스코드", "language": "code", "weight": 0.9})
        source_count = len({item["source"] for item in evidence})
        best_conf = max(cmc_conf, cg_conf, 0.95 if manual or datalab else 0.0)
        if manual and source_count >= 2:
            status = "verified"
        elif datalab and source_count >= 2 and best_conf >= 0.8:
            status = "verified"
        elif source_count >= 3 and best_conf >= 0.8:
            status = "corroborated"
        elif source_count >= 1:
            status = "single_source"
        else:
            status = "unresolved"
        business_ko = _first_sentences(ko_desc)
        corpus = "\n".join([en_desc, _clean_html(official.get("description"), 1200), *categories, *cmc_tags])
        if not business_ko:
            business_ko = self._structured_korean_summary(row, corpus, upbit_categories)
        business_en = _first_sentences(en_desc)
        if manual.get("description_ko"):
            summary_source = "bithumb_manual"
        elif _clean_html(cg_desc.get("ko") if isinstance(cg_desc, dict) else ""):
            summary_source = "coingecko_ko"
        elif business_ko:
            summary_source = "structured_ko"
        elif cmc_desc:
            summary_source = "coinmarketcap"
        elif official.get("description"):
            summary_source = "official_site"
        else:
            summary_source = ""
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
        groups, market_errors = self._market_groups()
        total = sum(len(rows) for rows in groups.values())
        if not total:
            return {"status": "waiting_for_markets", "configured": True, "processed": 0, "market_errors": market_errors}
        state = _read_json(STATE_PATH)
        saved_cursors = state.get("cursors") if isinstance(state.get("cursors"), dict) else {}
        legacy_cursor = int(state.get("cursor") or 0)
        cursors = {
            "bithumb": int(saved_cursors.get("bithumb", legacy_cursor) or 0),
            "upbit": int(saved_cursors.get("upbit", 0) or 0),
        }
        batch: list[dict[str, str]] = []
        next_cursors: dict[str, int] = {}
        completed_cycles = dict(state.get("completed_cycles_by_exchange") or {}) if isinstance(state.get("completed_cycles_by_exchange"), dict) else {}
        for exchange in ("bithumb", "upbit"):
            rows = groups[exchange]
            if not rows:
                next_cursors[exchange] = 0
                continue
            cursor = cursors[exchange] % len(rows)
            count = min(BATCH_PER_EXCHANGE, len(rows))
            batch.extend(rows[(cursor + offset) % len(rows)] for offset in range(count))
            next_cursor = (cursor + count) % len(rows)
            next_cursors[exchange] = next_cursor
            if next_cursor <= cursor:
                completed_cycles[exchange] = int(completed_cycles.get(exchange) or 0) + 1
        cmc_data: dict[str, Any] = {}
        try:
            cmc_data = self._cmc_batch(batch)
        except requests.RequestException:
            cmc_data = {}
        bithumb_by_symbol = {row["symbol"]: row for row in groups["bithumb"]}
        upbit_by_symbol = {row["symbol"]: row for row in groups["upbit"]}
        profiles: list[dict[str, Any]] = []
        failures: list[str] = []
        base_cache: dict[tuple[str, str], dict[str, Any]] = {}
        for target in batch:
            preferred = bithumb_by_symbol.get(target["symbol"])
            research_row = preferred if preferred and _same_project(preferred, target) else target
            cache_key = (research_row["symbol"], _normalize(research_row["english_name"]))
            try:
                if cache_key not in base_cache:
                    base_cache[cache_key] = self._build_profile(
                        research_row,
                        cmc_data.get(research_row["symbol"]),
                        upbit_available=research_row["symbol"] in upbit_by_symbol,
                    )
                profile = dict(base_cache[cache_key])
                profile["exchange"] = target["exchange"]
                profile["market"] = target["market"]
                profile["korean_name"] = target["korean_name"] or profile.get("korean_name")
                profile["english_name"] = profile.get("english_name") or target["english_name"]
                profiles.append(profile)
            except Exception as exc:
                failures.append(f"{target['exchange']}|{target['market']}: {type(exc).__name__}: {exc}")
            time.sleep(0.08)
        if profiles:
            body = json.dumps({"profiles": profiles}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            response, retries = post_with_retry(
                endpoint, data=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
                timeout=40, attempts=4,
            )
            try:
                remote = response.json()
            except ValueError:
                remote = {"ok": True, "stored": len(profiles)}
        else:
            retries = 0
            remote = {"ok": False, "stored": 0}
        by_exchange = {
            exchange: {
                "market_total": len(groups[exchange]),
                "processed": sum(1 for p in profiles if p.get("exchange") == exchange),
                "korean_ready": sum(1 for p in profiles if p.get("exchange") == exchange and p.get("business_summary_ko")),
                "cursor": next_cursors.get(exchange, 0),
                "completed_cycles": int(completed_cycles.get(exchange) or 0),
            }
            for exchange in ("bithumb", "upbit")
        }
        result = {
            "status": "researched", "configured": True, "market_total": total,
            "processed": len(profiles), "failed": len(failures), "failures": failures[:6],
            "stored": int(remote.get("stored") or 0) if isinstance(remote, dict) else 0,
            "cursors": next_cursors, "completed_cycles_by_exchange": completed_cycles,
            "by_exchange": by_exchange, "market_errors": market_errors, "retries": retries,
            "korean_ready": sum(1 for p in profiles if p.get("business_summary_ko")),
            "research_status": {name: sum(1 for p in profiles if p.get("research_status") == name) for name in ("verified", "corroborated", "single_source", "unresolved")},
        }
        atomic_json(STATE_PATH, {**result, "updated_at": time.time()})
        return result


def main() -> None:
    result = CoinProfileEnricher().run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
