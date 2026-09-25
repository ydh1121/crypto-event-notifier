"""Local review of the real coin/strategy journal. Python stdlib only.

PAPER reads are always read-only. Opt-in planning saves versioned plans and manual
executions in the separate holdings journal after a verified backup. No runner,
Git change, credentials or exchange orders. Explicit price refresh uses public
tickers only. Holdings amounts stay on this PC. Bind address is fixed to loopback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import secrets
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .strategy_lab_market import read_strategy_lab_market
from .runtime_review import compare_activity, read_runtime
from .holdings_review import read_holdings, resolve_holdings_path
from .manual_planning_store import ManualPlanningStore
from .manual_trading import PlanningError, identity
from .holding_quotes import HoldingQuotes

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "cloudflare-pages/public"
REPORT_SCHEMA = 2
INDEX = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>코인별 전략 · 로컬 검토</title><style>body{margin:0;padding:24px;font-family:system-ui;background:#fff;color:#202124}.review-label{font-size:13px;color:#775113;margin:0 auto 16px;max-width:1600px}#pageRoot{max-width:1600px;margin:auto}@media(max-width:760px){body{padding:16px}}</style>
<p class="review-label">로컬 DB 조회 전용 · 주문·수집 프로그램과 별도 실행</p><div id="reviewRoot"><nav aria-label="매매 화면"><button data-review-page="paper" aria-pressed="true">가상매매</button><button data-review-page="holdings" aria-pressed="false">실전 계획</button></nav><div id="pageRoot"></div></div><style>#reviewRoot{max-width:1600px;margin:auto}#reviewRoot>nav{display:flex;gap:8px;margin-bottom:24px}#reviewRoot>nav button{font:inherit;min-height:44px;padding:8px 18px;border:1px solid #d7dce2;border-radius:8px;background:white;white-space:nowrap}#reviewRoot>nav [aria-pressed=true]{color:#0757b4;background:#edf4fc;border-color:#a8c9eb}</style><script type="module" src="/review.js"></script></html>"""
SCRIPT = """import {createPaperWorkbench} from '/modules/pages/paper-workbench.js';
import {createHoldingsWorkbench} from '/modules/pages/holdings-workbench.js';
const state={snapshot:null,ui:{paperExchange:'bithumb',paperMarket:'KRW-B3',paperLabStyle:'aggressive',paperTab:'coins',paperFilter:'all',paperStrategyFilter:'all',paperSort:'return_desc',paperSearch:'',paperRange:'24h'}};
const listeners=new Set();const store={get:()=>state,setUi(patch,meta={}){Object.assign(state.ui,patch);for(const f of listeners)f(state,{type:'ui',...meta});},subscribe(f){listeners.add(f);return()=>listeners.delete(f);}};
const container=document.getElementById('pageRoot');const paperRoot=document.createElement('div'),holdingsRoot=document.createElement('div');container.append(paperRoot,holdingsRoot);holdingsRoot.hidden=true;
const page=createPaperWorkbench({store,allowOverview:false});page.mount(paperRoot);
const holdingsPage=createHoldingsWorkbench({store,onRefreshPrices:async()=>{const r=await fetch('/api/holding-quotes');if(!r.ok)throw Error('가격을 조회하지 못했습니다.');await refresh();},onPaper:(exchange,market,style)=>{show('paper');page.openAccount(exchange,market,style);}});holdingsPage.mount(holdingsRoot);
function show(name){paperRoot.hidden=name!=='paper';holdingsRoot.hidden=name!=='holdings';for(const b of document.querySelectorAll('[data-review-page]'))b.setAttribute('aria-pressed',String(b.dataset.reviewPage===name));}
document.querySelector('#reviewRoot>nav').addEventListener('click',e=>{const b=e.target.closest('[data-review-page]');if(b)show(b.dataset.reviewPage);});
async function refresh(first=false){try{const r=await fetch('/api/review-state');if(!r.ok)throw Error('DB 조회 실패');state.snapshot=await r.json();if(first){page.render();holdingsPage.refresh();}else for(const f of listeners)f(state,{type:'snapshot-live'});}catch(e){document.querySelector('.review-label').textContent=e.message;}}
await refresh(true);setInterval(()=>refresh(),10000);
"""


def read_state(path: Path, holdings_path: Path | None = None, quotes: HoldingQuotes | None = None,
               confirmed_exchange: str | None = None) -> dict:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("""SELECT exchange,market,price,ts AS signal_ts FROM research_signals_mx
            WHERE strategy='adaptive' ORDER BY market""").fetchall()
        exchanges = {ex: {"exchange": ex, "leaderboard": []} for ex in ("bithumb", "upbit")}
        for r in rows:
            row = dict(r);row['symbol'] = row['market'].removeprefix('KRW-')
            if row['exchange'] in exchanges:
                exchanges[row['exchange']]['leaderboard'].append(row)
        extra, quote_status = quotes.snapshot() if quotes else ([], {"status": "not_requested"})
        holdings = read_holdings(holdings_path, [dict(r) for r in rows] + extra, confirmed_exchange=confirmed_exchange)
        holdings['public_quotes'] = quote_status
        return {"public": {"exchanges": exchanges}, "private_visible": False, "local_holdings": holdings}
    finally:
        conn.close()


def read_detail(path: Path, exchange: str, market: str) -> dict:
    lab = read_strategy_lab_market(exchange, market, path)
    return {"exchange": exchange, "market": market, "strategy": "adaptive", "data": {"version": 5, "strategy_lab": lab}}


def review_journal(detail: dict, experiment: str, revision: str, offset: int, limit: int) -> tuple[int, dict]:
    account = next((e for e in detail['data']['strategy_lab']['experiments'] if e['experiment_id']==experiment), None)
    if account is None:
        return 404, {"error": {"code": "JOURNAL_UNAVAILABLE", "message": "선택한 계좌가 없습니다."}}
    if revision and revision != account['revision']:
        return 409, {"error": {"code": "JOURNAL_CHANGED", "message": "계좌가 갱신되었습니다."}}
    journal = account['journal']
    trades = [dict(zip(journal['columns'], row)) for row in reversed(journal['rows'])][offset:offset+limit]
    summary = {k:v for k,v in account.items() if k != 'journal'}
    return 200, {"ok": True, "exchange": detail['exchange'], "market": detail['market'], "journal": {
        "account": summary, "trades": trades, "total": journal['total'], "revision": account['revision'],
        "offset": offset, "limit": limit, "next_offset": offset+len(trades) if offset+len(trades)<journal['total'] else None}}


def handler(path: Path, *, fixture: bool = False, holdings_path: Path | None = None, quotes=None,
            confirmed_exchange: str | None = None, enable_planning: bool = False):
    quotes = quotes if quotes is not None else HoldingQuotes()
    planning = ManualPlanningStore(holdings_path) if enable_planning else None
    if planning and planning.path == path.resolve():
        raise ValueError('PAPER and manual journals must be separate')
    csrf = secrets.token_urlsafe(32)
    class ReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def send(self, status, payload, content_type='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else (json.dumps(payload,ensure_ascii=False,allow_nan=False).encode() if content_type.startswith('application/json') else payload.encode())
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(body)

        def do_GET(self):
            # Fixed loopback binding plus Host/Origin checks prevent rebinding and
            # cross-site reads of the local journal. No remote auth bypass.
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected or self.headers.get('Origin', f'http://{expected}') != f'http://{expected}' or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send(403, {'error': {'message': 'Local review only'}})
            url=urlsplit(self.path)
            try:
                if url.path=='/': return self.send(200,INDEX.replace('로컬 DB 조회 전용', '테스트 데이터 · 실제 계좌 아님' if fixture else '계획·수동 체결 로컬 저장' if planning else '로컬 DB 조회 전용'),'text/html; charset=utf-8')
                if url.path=='/review.js': return self.send(200,SCRIPT,'text/javascript; charset=utf-8')
                if url.path=='/api/review-state':
                    state=read_state(path,holdings_path,quotes,confirmed_exchange)
                    state['local_holdings']['planning_enabled']=bool(planning)
                    return self.send(200,state)
                if url.path=='/api/manual-planning' and planning:
                    query={k:v[0] for k,v in parse_qs(url.query).items()}
                    account=self.planning_account(query)
                    return self.send(200,{**planning.read(query,account),'csrf_token':csrf})
                if url.path=='/api/holding-quotes':
                    if fixture: return self.send(409,{'error':{'message':'테스트 데이터에서는 외부 가격을 조회하지 않습니다.'}})
                    quotes.refresh(read_holdings(holdings_path,[],confirmed_exchange=confirmed_exchange)['holdings'])
                    return self.send(200,quotes.snapshot()[1])
                if url.path=='/api/market-detail':
                    query=parse_qs(url.query); get=lambda key,default='':query.get(key,[default])[0]
                    exchange,market=get('exchange','bithumb'),get('market').upper()
                    if exchange not in {'bithumb','upbit'} or not market.startswith('KRW-') or len(market)>80:
                        return self.send(422,{'error':{'message':'코인 선택을 확인하세요.'}})
                    detail=read_detail(path,exchange,market)
                    if get('experiment'):
                        offset,limit=int(get('offset','0')),int(get('limit','30'))
                        if offset<0 or not 1<=limit<=100:return self.send(422,{'error':{'message':'조회 범위를 확인하세요.'}})
                        status,payload=review_journal(detail,get('experiment'),get('revision'),offset,limit)
                        return self.send(status,payload)
                    for a in detail['data']['strategy_lab']['experiments']:
                        a['journal']={k:v for k,v in a['journal'].items() if k not in {'rows','columns'}}
                    return self.send(200,{'ok':True,'detail':detail})
                if url.path.startswith('/modules/'):
                    target=(PUBLIC/url.path.lstrip('/')).resolve()
                    if PUBLIC.resolve() in target.parents and target.is_file() and target.suffix in {'.js','.css'}:
                        return self.send(200,target.read_bytes(),'text/javascript; charset=utf-8' if target.suffix=='.js' else 'text/css; charset=utf-8')
                return self.send(404,{'error':{'message':'조회 경로가 없습니다.'}})
            except PlanningError as exc:
                return self.send(exc.status,{'error':{'message':str(exc)}})
            except (sqlite3.Error, ValueError, OSError):
                return self.send(503,{'error':{'message':'로컬 데이터 조회를 완료하지 못했습니다.'}})

        def planning_account(self, selection):
            exchange,market,_,experiment=identity(selection)
            holdings=read_holdings(holdings_path,[],confirmed_exchange=confirmed_exchange)
            if not any(h['exchange']==exchange and h['market']==market and h['recording_available'] for h in holdings['holdings']):
                raise PlanningError('보유 목록에 등록된 원화 코인과 전략을 선택하세요.')
            detail=read_detail(path,exchange,market)
            account=next((a for a in detail['data']['strategy_lab']['experiments'] if a['experiment_id']==experiment),None)
            if account is None:
                raise PlanningError('이 코인의 전략 기록을 찾지 못했습니다.')
            return account

        def do_POST(self):
            if not planning or self.path!='/api/manual-planning':
                return self.send(405,{'error':{'message':'조회 전용입니다.'}})
            expected=f'127.0.0.1:{self.server.server_port}'
            token=self.headers.get('X-Planning-Token','')
            if (self.headers.get('Host')!=expected or self.headers.get('Origin')!=f'http://{expected}'
                or self.headers.get('Sec-Fetch-Site')=='cross-site'
                or not token.isascii() or not secrets.compare_digest(token,csrf)):
                return self.send(403,{'error':{'message':'이 조회창에서 다시 저장하세요.'}})
            try:
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise PlanningError('저장 요청 형식을 확인하세요.')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:raise PlanningError('저장 요청 크기를 확인하세요.')
                self.connection.settimeout(10)
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise PlanningError('저장 요청을 확인하세요.')
                account=self.planning_account(payload)
                result=planning.write(payload,payload.get('action'),payload,account)
                return self.send(200,{**result,'csrf_token':csrf})
            except PlanningError as exc:
                return self.send(exc.status,{'error':{'message':str(exc)}})
            except (ValueError,UnicodeError):
                return self.send(422,{'error':{'message':'입력한 저장 내용을 확인하세요.'}})
            except (OSError,sqlite3.Error):
                return self.send(503,{'error':{'message':'저장을 완료하지 못했습니다. 입력값을 유지합니다.'}})

        def do_PUT(self): self.send(405,{'error':{'message':'지원하지 않는 저장 방식입니다.'}})
        do_DELETE=do_PATCH=do_PUT
    return ReviewHandler


def write_report(path: Path, report: dict):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.crypto-review-',
                                     dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        except BaseException:
            stream.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def review_build(root: Path = ROOT) -> dict:
    """Identify this extracted review package, never the separate PC checkout."""
    result = {'report_schema': REPORT_SCHEMA, 'source_commit': None,
              'integrity': 'unavailable'}
    try:
        raw = (root / 'SOURCE_MANIFEST.json').read_bytes()
        result['manifest_sha256'] = hashlib.sha256(raw).hexdigest()
        manifest = json.loads(raw)
        files = manifest.get('files')
        commit = manifest.get('source_commit')
        if (not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit)
                or manifest.get('mode') not in {'read_only','local_planning'} or not isinstance(files, dict)
                or 'b3_trader/strategy_journal_review.py' not in files
                or 'b3_trader/runtime_review.py' not in files):
            raise ValueError('Invalid review manifest')
        for name, expected in files.items():
            target = (root / name).resolve()
            if root.resolve() not in target.parents or target.is_symlink():
                raise ValueError('Nonlocal manifest entry')
            if not isinstance(expected, str) or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('Review files differ from manifest')
        result.update(source_commit=commit, integrity='verified')
    except FileNotFoundError:
        result['integrity'] = 'mismatch' if 'manifest_sha256' in result else 'unavailable'
    except (OSError, ValueError, TypeError, AttributeError):
        result['integrity'] = 'mismatch'
    return result


def finish_runtime_observation(db, path, report, seconds, stop_event):
    try:
        if stop_event.wait(seconds):
            if 'runtime_review' not in report:
                return
            report['runtime_review'].update(status='interrupted')
        else:
            after = read_runtime(db)
            report['runtime_review'].update(status='complete', after=after,
                changes=compare_activity(report['runtime_review']['before'], after))
    except KeyboardInterrupt:
        report['runtime_review'].update(status='interrupted')
    except (OSError, sqlite3.Error, ValueError) as exc:
        report['runtime_review'].update(status='read_failed', error_type=type(exc).__name__)
    report['review_finished_at'] = time.time()
    write_report(path, report)
    print(f'Review {report["runtime_review"]["status"]}: {path.resolve()}', flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--holdings-db',type=Path,help='Existing manual holdings journal; separate from PAPER')
    parser.add_argument('--holdings-exchange',choices=['bithumb','upbit'],help='Explicit owner-confirmed exchange for this real-holdings portfolio; no DB write')
    parser.add_argument('--enable-planning',action='store_true',help='Allow explicit plan/manual-record saves in the separate existing holdings journal')
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--report-only',action='store_true',help='Save both observations and exit without a browser or server')
    parser.add_argument('--fixture',action='store_true',help='Label synthetic test data explicitly')
    parser.add_argument('--open-browser',action='store_true')
    parser.add_argument('--observe-seconds',type=float,default=30)
    args=parser.parse_args()
    if not math.isfinite(args.observe_seconds) or not 0 <= args.observe_seconds <= 300:
        parser.error('Observation interval must be between 0 and 300 seconds.')
    if args.report_only and not args.report:
        parser.error('--report-only requires --report.')
    if not args.db.is_file():parser.error('Existing canonical database is required; no database will be created.')
    args.holdings_db, args.holdings_source = resolve_holdings_path(args.db,args.holdings_db)
    if args.holdings_db == args.db.resolve():
        parser.error('Holdings and PAPER databases must be separate.')
    protected = {Path(str(db)+suffix) for db in (args.db.resolve(), args.holdings_db) if db is not None for suffix in ('','-wal','-shm')}
    if args.report and args.report.resolve() in protected:
        parser.error('The report must be separate from the database and its WAL/SHM files.')
    build = review_build()
    print(f'Review schema {REPORT_SCHEMA} / package {build["source_commit"] or "unversioned"} / {build["integrity"]}',flush=True)
    if build['integrity'] == 'mismatch':
        parser.error('Review package files do not match. Extract the complete ZIP into its own new folder.')
    # Bind before generating output, so an old viewer occupying this port cannot
    # leave a new report that appears to belong to the old browser window.
    server = None
    if not args.report_only:
        try:
            server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.db,fixture=args.fixture,holdings_path=args.holdings_db,confirmed_exchange=args.holdings_exchange,enable_planning=args.enable_planning))
        except OSError:
            parser.error('Review port is in use. Use RUN_CHECK.cmd to check without opening a viewer.')
    try:
        return run_review(args, build, server)
    finally:
        if server:
            server.server_close()


def run_review(args, build, server):
    started_at = time.time()
    sample=read_detail(args.db,'bithumb','KRW-B3')
    account_observed_at = time.time()
    exp=next((e for e in sample['data']['strategy_lab']['experiments'] if e['style']=='aggressive'),None)
    observation_stop = threading.Event()
    if args.report:
        holdings = read_holdings(args.holdings_db, [],confirmed_exchange=args.holdings_exchange)
        events=sample['data']['strategy_lab'].get('events',[])
        event_market='KRW-B3'
        if not events:
            events=read_detail(args.db,'bithumb','KRW-BTC')['data']['strategy_lab'].get('events',[])
            event_market='KRW-BTC'
        report={'review_build':build,'review_started_at':started_at,'account_observed_at':account_observed_at,
                'db_path':str(args.db.resolve()),'db_size':args.db.stat().st_size,'paper_only':True,
                'mode':'read_only','scope':'bithumb|KRW-B3|aggressive','account':exp,
                'event_review':{'exchange':'bithumb','market':event_market,'events':events[:1]},
                'holdings_review':{'status':holdings['status'],'path_source':args.holdings_source,
                    'confirmed_exchange':args.holdings_exchange,
                    'db_path':str(args.holdings_db) if args.holdings_db else None,
                    'holding_count':holdings.get('holding_count'),'closed_count':holdings.get('closed_count'),
                    'identity_complete_count':sum(1 for h in holdings['holdings'] if not h['closed'] and h['exchange'] and h['api_market']),
                    'krw_planning_count':sum(1 for h in holdings['holdings'] if h['planning_available']),
                    'unknown_exchange_count':sum(1 for h in holdings['holdings'] if not h['closed'] and not h['exchange']),
                    'stored_unknown_exchange_count':sum(1 for h in holdings['holdings'] if not h['closed'] and not h['stored_exchange']),
                    'non_krw_count':sum(1 for h in holdings['holdings'] if not h['closed'] and h['quote_currency'] != 'KRW')},
                'runtime_review':{'status':'waiting_for_second_observation','before':read_runtime(args.db)},
                'limitations':['Stored drawdown is not fill-only replay.','No runner was started.','No remote publication.']}
        write_report(args.report, report)
        print(f'Checking for {args.observe_seconds:g} seconds. Keep the collection window open; this check ends separately.',flush=True)
    if args.report_only:
        finish_runtime_observation(args.db,args.report,report,args.observe_seconds,observation_stop)
        return 0 if report['runtime_review']['status'] == 'complete' else 1
    print(f'READ ONLY: http://127.0.0.1:{server.server_port}/',flush=True)
    print(f'B3 aggressive journal match: {exp.get("reconciliation",{}).get("matches") if exp else "account unavailable"}',flush=True)
    if args.open_browser:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{server.server_port}/')
    observation = None
    if args.report:
        observation=threading.Thread(target=finish_runtime_observation,
            args=(args.db,args.report,report,args.observe_seconds,observation_stop),daemon=True)
        observation.start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        observation_stop.set()
        if observation:
            observation.join()
    return 0


if __name__=='__main__':raise SystemExit(main())
