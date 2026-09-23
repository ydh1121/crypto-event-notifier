"""Local, read-only review of the real coin/strategy journal. Python stdlib only.

Never starts a runner, changes Git, loads credentials, migrates SQLite, sends data
outside this PC, or accepts mutation routes. Bind address is fixed to loopback.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .strategy_lab_market import read_strategy_lab_market
from .runtime_review import compare_activity, read_runtime

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "cloudflare-pages/public"
INDEX = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>코인별 전략 · 로컬 검토</title><style>body{margin:0;padding:24px;font-family:system-ui;background:#fff;color:#202124}.review-label{font-size:13px;color:#775113;margin:0 auto 16px;max-width:1600px}#pageRoot{max-width:1600px;margin:auto}@media(max-width:760px){body{padding:16px}}</style>
<p class="review-label">로컬 DB 조회 전용 · 주문·수집 프로그램과 별도 실행</p><div id="pageRoot"></div><script type="module" src="/review.js"></script></html>"""
SCRIPT = """import {createPaperWorkbench} from '/modules/pages/paper-workbench.js';
const state={snapshot:null,ui:{paperExchange:'bithumb',paperMarket:'KRW-B3',paperLabStyle:'aggressive',paperTab:'coins',paperFilter:'all',paperStrategyFilter:'all',paperSort:'return_desc',paperSearch:'',paperRange:'24h'}};
const listeners=new Set();const store={get:()=>state,setUi(patch,meta={}){Object.assign(state.ui,patch);for(const f of listeners)f(state,{type:'ui',...meta});},subscribe(f){listeners.add(f);return()=>listeners.delete(f);}};
const page=createPaperWorkbench({store,allowOverview:false});page.mount(document.getElementById('pageRoot'));
async function refresh(first=false){try{const r=await fetch('/api/review-state');if(!r.ok)throw Error('DB 조회 실패');state.snapshot=await r.json();if(first)page.render();else for(const f of listeners)f(state,{type:'snapshot-live'});}catch(e){document.querySelector('.review-label').textContent=e.message;}}
await refresh(true);setInterval(()=>refresh(),10000);
"""


def read_state(path: Path) -> dict:
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
        return {"public": {"exchanges": exchanges}, "private_visible": False}
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


def handler(path: Path, *, fixture: bool = False):
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
                if url.path=='/': return self.send(200,INDEX.replace('로컬 DB 조회 전용', '테스트 데이터 · 실제 계좌 아님') if fixture else INDEX,'text/html; charset=utf-8')
                if url.path=='/review.js': return self.send(200,SCRIPT,'text/javascript; charset=utf-8')
                if url.path=='/api/review-state': return self.send(200,read_state(path))
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
            except (sqlite3.Error, ValueError, OSError):
                return self.send(503,{'error':{'message':'로컬 데이터 조회를 완료하지 못했습니다.'}})

        def do_POST(self): self.send(405,{'error':{'message':'조회 전용입니다.'}})
        do_PUT=do_DELETE=do_PATCH=do_POST
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


def finish_runtime_observation(db, path, report, seconds, stop_event):
    if stop_event.wait(seconds):
        return
    try:
        after = read_runtime(db)
        report['runtime_review'].update(status='complete', after=after,
            changes=compare_activity(report['runtime_review']['before'], after))
    except (OSError, sqlite3.Error, ValueError) as exc:
        report['runtime_review'].update(status='read_failed', error_type=type(exc).__name__)
    write_report(path, report)
    print('Runtime observation saved to the local review result.', flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--fixture',action='store_true',help='Label synthetic test data explicitly')
    parser.add_argument('--open-browser',action='store_true')
    parser.add_argument('--observe-seconds',type=float,default=30)
    args=parser.parse_args()
    if not math.isfinite(args.observe_seconds) or not 0 <= args.observe_seconds <= 300:
        parser.error('Observation interval must be between 0 and 300 seconds.')
    if not args.db.is_file():parser.error('Existing canonical database is required; no database will be created.')
    if args.report and args.report.resolve() in {args.db.resolve(), Path(str(args.db.resolve())+'-wal'), Path(str(args.db.resolve())+'-shm')}:
        parser.error('The report must be separate from the database and its WAL/SHM files.')
    sample=read_detail(args.db,'bithumb','KRW-B3')
    exp=next((e for e in sample['data']['strategy_lab']['experiments'] if e['style']=='aggressive'),None)
    observation_stop = threading.Event()
    if args.report:
        events=sample['data']['strategy_lab'].get('events',[])
        event_market='KRW-B3'
        if not events:
            events=read_detail(args.db,'bithumb','KRW-BTC')['data']['strategy_lab'].get('events',[])
            event_market='KRW-BTC'
        report={'db_path':str(args.db.resolve()),'db_size':args.db.stat().st_size,'paper_only':True,
                'mode':'read_only','scope':'bithumb|KRW-B3|aggressive','account':exp,
                'event_review':{'exchange':'bithumb','market':event_market,'events':events[:1]},
                'runtime_review':{'status':'waiting_for_second_observation','before':read_runtime(args.db)},
                'limitations':['Stored drawdown is not fill-only replay.','No runner was started.','No remote publication.']}
        write_report(args.report, report)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.db,fixture=args.fixture))
    print(f'READ ONLY: http://127.0.0.1:{server.server_port}/',flush=True)
    print(f'B3 aggressive journal match: {exp.get("reconciliation",{}).get("matches") if exp else "account unavailable"}',flush=True)
    if args.open_browser:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{server.server_port}/')
    if args.report:
        threading.Thread(target=finish_runtime_observation,
            args=(args.db,args.report,report,args.observe_seconds,observation_stop),daemon=True).start()
        print(f'Observing process and database activity for {args.observe_seconds:g} seconds; no runner is started.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        observation_stop.set()
        server.server_close()


if __name__=='__main__':main()
