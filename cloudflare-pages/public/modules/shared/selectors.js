import{n}from'./format.js';
export const snapshot=state=>state?.snapshot||null;
export const fullPublic=state=>snapshot(state)?.public||{};
export function exchangePublic(state,exchange='bithumb'){
  const pub=fullPublic(state),selected=pub.exchanges?.[exchange];
  if(!selected)return pub;
  return {...pub,...selected,exchange,exchanges:pub.exchanges,exchange_records:pub.exchange_records||{},recent_records:pub.exchange_records?.[exchange]||pub.recent_records,research_node:pub.research_node,strategy_lab:pub.strategy_lab,published_at:pub.published_at,multi_exchange_updated_at:pub.multi_exchange_updated_at};
}
export const rowsFor=(state,exchange='bithumb')=>Array.isArray(exchangePublic(state,exchange).leaderboard)?exchangePublic(state,exchange).leaderboard:[];
export function combinedPaper(state){
  const pub=fullPublic(state),parts=['bithumb','upbit'].map(x=>pub.exchanges?.[x]).filter(Boolean);
  if(!parts.length){const p=pub,start=n(p.aggregate_virtual_capital_krw),equity=n(p.equity_krw);return{start,equity,pnl:n(p.pnl_krw||equity-start),cash:n(p.cash_krw),active:n(p.active_positions),markets:n(p.market_count)}}
  return parts.reduce((a,p)=>({start:a.start+n(p.aggregate_virtual_capital_krw),equity:a.equity+n(p.equity_krw),pnl:a.pnl+n(p.pnl_krw),cash:a.cash+n(p.cash_krw),active:a.active+n(p.active_positions),markets:a.markets+n(p.market_count)}),{start:0,equity:0,pnl:0,cash:0,active:0,markets:0});
}
export function paperStats(state,exchange='bithumb'){
  const p=exchangePublic(state,exchange),rows=rowsFor(state,exchange),start=n(p.aggregate_virtual_capital_krw),equity=n(p.equity_krw),pnl=n(p.pnl_krw||equity-start),closed=rows.reduce((s,r)=>s+n(r.closed_trades),0),wins=rows.reduce((s,r)=>s+n(r.closed_trades)*n(r.win_rate_pct)/100,0);
  return{...p,start,equity,pnl,returnPct:start?pnl/start*100:n(p.return_pct),closed,winRate:closed?wins/closed*100:0};
}
export function holdings(state){const s=snapshot(state);if(!s?.private_visible)return[];return Array.isArray(s.private?.manual_holdings?.holdings)?s.private.manual_holdings.holdings.filter(x=>n(x.volume)>0):[]}
export function holdingsSummary(state){const s=snapshot(state);return s?.private_visible?s.private?.manual_holdings:null}
export function findMarket(state,exchange,market){return rowsFor(state,exchange).find(r=>r.market===market)||null}
export function findHolding(state,market){return holdings(state).find(r=>r.market===market)||null}
export function allCandidateRows(state){const out=[];for(const ex of ['bithumb','upbit'])for(const row of rowsFor(state,ex))out.push({...row,__exchange:ex});return out}
export function strategyLab(state){return fullPublic(state).strategy_lab||{}}
export function strategyRows(state,exchange){const all=Array.isArray(strategyLab(state).experiments)?strategyLab(state).experiments:[];return all.filter(r=>r.exchange===exchange)}
export function recordsData(state,exchange){const pub=fullPublic(state);return pub.exchange_records?.[exchange]||exchangePublic(state,exchange).recent_records||{fills:[],feedback:[],fill_count:0,feedback_count:0,updated_at:0}}
export function commonExchangeRows(state){const b=rowsFor(state,'bithumb'),u=rowsFor(state,'upbit'),um=new Map(u.map(r=>[r.market,r]));return b.map(br=>({market:br.market,b:br,u:um.get(br.market)})).filter(x=>x.u)}
export function marketSummary(state,exchange){const rows=rowsFor(state,exchange);if(!rows.length)return{avgRegime:0,avgEntry:0,candidates:0,up:0,down:0};return{avgRegime:rows.reduce((s,r)=>s+n(r.regime_score),0)/rows.length,avgEntry:rows.reduce((s,r)=>s+n(r.entry_score),0)/rows.length,candidates:rows.filter(r=>n(r.opportunity_score)>=65).length,up:rows.filter(r=>n(r.return_pct)>0).length,down:rows.filter(r=>n(r.return_pct)<0).length}}
