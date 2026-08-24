const ui={
  apiBase:localStorage.getItem('cryptoTraderApiBase')||window.location.origin,
  token:localStorage.getItem('cryptoTraderToken')||'',
  view:localStorage.getItem('cryptoTraderView')||'overview',
  selectedMarket:localStorage.getItem('cryptoTraderSelectedMarket')||'KRW-B3',
  assetRange:localStorage.getItem('cryptoTraderAssetRange')||'24h',
  portfolioRange:localStorage.getItem('cryptoTraderPortfolioRange')||'7d',
  snapshot:null,
  analytics:null,
  telegram:{configured:false,enabled:false,token_configured:false,chat_id:''},
  network:null,
  assetHistory:null,
  portfolioHistory:null,
};
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
const num=(v,d=1)=>v==null||Number.isNaN(Number(v))?'-':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:d});
const money=v=>v==null||Number.isNaN(Number(v))?'-':`${Math.round(Number(v)).toLocaleString('ko-KR')}원`;
const pct=(v,d=2)=>v==null||Number.isNaN(Number(v))?'-':`${Number(v).toFixed(d)}%`;
const signedPct=(v,d=2)=>v==null||Number.isNaN(Number(v))?'-':`${Number(v)>=0?'+':''}${Number(v).toFixed(d)}%`;
const score=v=>v==null||Number.isNaN(Number(v))?'-':Number(v).toFixed(1);
const timeText=ts=>ts?new Date(Number(ts)*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-';
const shortTime=ts=>ts?new Date(Number(ts)*1000).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):'-';
const clsSign=v=>Number(v)>0?'positive':Number(v)<0?'negative':'';

class ApiError extends Error{constructor(status,body){super(`${status} ${body}`);this.status=status;this.body=body}}
function isLoopback(){const h=window.location.hostname;return h==='127.0.0.1'||h==='localhost'||h==='::1'}
async function api(path,options={}){
  const headers={...(options.headers||{})};
  if(ui.token)headers.Authorization=`Bearer ${ui.token}`;
  if(options.body&&typeof options.body!=='string'){
    headers['content-type']='application/json';
    options.body=JSON.stringify(options.body);
  }
  const response=await fetch(`${ui.apiBase}${path}`,{...options,headers});
  if(!response.ok){
    const body=await response.text();
    if(response.status===401&&!isLoopback()){
      localStorage.removeItem('cryptoTraderToken');ui.token='';
      openConnectionSettings('Dashboard token이 없거나 맞지 않습니다. 로컬 PC 콘솔의 토큰을 입력하세요.');
    }
    throw new ApiError(response.status,body);
  }
  return response.json();
}

function openConnectionSettings(message=''){
  if(message)$('connectionHint').textContent=message;
  $('apiBaseInput').value=ui.apiBase;
  $('tokenInput').value=ui.token;
  $('settingsDialog').showModal();
}
function switchView(view){
  ui.view=view;
  localStorage.setItem('cryptoTraderView',view);
  document.querySelectorAll('.view-tab').forEach(btn=>btn.classList.toggle('is-active',btn.dataset.view===view));
  document.querySelectorAll('[data-view-panel]').forEach(panel=>panel.classList.toggle('is-active',panel.dataset.viewPanel===view));
  if(view==='assets')loadSelectedHistory();
  if(view==='performance')loadPortfolioHistory();
  if(view==='activity')refreshActivity();
  if(view==='settings'){loadRuntimeConfig();loadNetwork();}
  window.scrollTo({top:0,behavior:'instant'});
}
document.querySelectorAll('.view-tab').forEach(btn=>btn.onclick=()=>switchView(btn.dataset.view));

function actionLabel(action){
  return ({WATCH:'WATCH',WAIT_PULLBACK:'눌림 대기',BUY_CANDIDATE:'매수 후보',RISK_OFF:'위험 회피',ERROR:'오류'})[action]||action||'대기';
}
function decisionCopy(item){
  const action=item?.action;
  if(action==='BUY_CANDIDATE')return ['시장과 진입 조건이 함께 충족됐습니다.','PAPER 주문 전 스프레드·슬리피지·BTC 급락 차단 조건을 한 번 더 확인합니다.',''];
  if(action==='WAIT_PULLBACK')return ['시장 강도는 좋지만 지금 가격은 비쌉니다.','추격하지 않고 조정폭, 피보나치 위치와 호가가 좋아질 때까지 기다립니다.','wait'];
  if(action==='RISK_OFF')return ['현재 시장 국면이 진입에 불리합니다.','Regime이 회복되기 전에는 신규 매수보다 방어를 우선합니다.','risk'];
  if(action==='ERROR')return ['이 자산 분석에서 오류가 발생했습니다.',item.error||'시스템 이벤트에서 오류 내용을 확인하세요.','risk'];
  return ['아직 매수 조건이 부족합니다.','시장 국면과 진입 품질 중 필요한 조건이 더 쌓이는지 계속 감시합니다.',''];
}
function systemState(snapshot){
  if(snapshot?.kill_switch)return ['KILL SWITCH','bad'];
  if(snapshot?.paused)return ['신규 진입 일시정지','warn'];
  return ['정상 감시','good'];
}
function statusClass(scoreValue){const v=Number(scoreValue);if(v>=65)return'good';if(v<45)return'bad';return'warn'}

function renderHeader(){
  if(!ui.snapshot)return;
  const [label,tone]=systemState(ui.snapshot);
  $('enginePill').textContent=label;$('enginePill').className=`status-pill ${tone}`;
  $('connectionPill').textContent=isLoopback()?'로컬 연결':'원격 연결';$('connectionPill').className='status-pill good';
}
function renderKpis(){
  const p=ui.snapshot?.portfolio||{},a=ui.analytics||{};
  $('equityValue').textContent=money(p.equity_krw);
  $('returnValue').innerHTML=`수익률 <span class="${clsSign(a.return_pct)}">${signedPct(a.return_pct)}</span>`;
  $('cashValue').textContent=money(p.cash_krw);
  $('exposureValue').textContent=`노출 ${money(p.exposure_krw)}`;
  $('ddValue').textContent=pct(p.daily_drawdown_pct);
  $('maxDdValue').textContent=`최대 DD ${pct(a.max_drawdown_pct)}`;
  $('realizedValue').innerHTML=`<span class="${clsSign(a.realized_pnl_krw)}">${money(a.realized_pnl_krw)}</span>`;
  $('winRateValue').textContent=`완료 ${a.closed_trades??0}회 · 승률 ${pct(a.win_rate_pct,1)}`;
}
function renderMarketPulse(){
  const market=ui.snapshot?.market||{},f=market.factors||{},d=market.details||{};
  const items=[
    ['알트 확산',f.alt_breadth,'상위 알트의 상대강도'],
    ['Base',f.base_strength,'Base 바스켓'],
    ['Gaming',f.gaming_strength,'게임 바스켓'],
    ['파생 위험선호',f.derivatives_risk_on,'Funding · OI'],
  ];
  $('marketPulse').classList.remove('empty-state');
  $('marketPulse').innerHTML=items.map(([label,value,sub])=>`<div class="pulse-item"><span>${label}</span><strong class="${statusClass(value)==='good'?'positive':statusClass(value)==='bad'?'negative':''}">${score(value)}</strong><small>${sub}</small></div>`).join('');
  $('marketUpdated').textContent=market.ts?`${timeText(market.ts)} 갱신`:'-';
}
function telegramLabel(){if(ui.telegram.enabled)return'연결';if(ui.telegram.configured)return'비활성';return'미설정'}
function renderSystemSummary(){
  const s=ui.snapshot||{},sync=s.sync||{},backup=s.backup||{};
  $('systemSummary').innerHTML=[
    ['Telegram',telegramLabel()],
    ['GitHub',sync.status||'idle'],
    ['백업',backup.status||'idle'],
    ['업타임',`${Math.floor((s.uptime_seconds||0)/60)}분`],
  ].map(([k,v])=>`<div class="system-line"><span>${k}</span><b>${esc(v)}</b></div>`).join('');
}
function scoreCell(label,value,type=''){
  const width=Math.max(0,Math.min(100,Number(value)||0));
  return `<div class="score-cell ${type}"><div class="score-label-row"><span>${label}</span><strong>${score(value)}</strong></div><div class="score-track"><i style="width:${width}%"></i></div></div>`;
}
function assetCard(market,item){
  const p=item.position||{},selected=market===ui.selectedMarket;
  return `<article class="asset-card ${selected?'is-selected':''}" data-market="${esc(market)}">
    <div class="asset-card-top"><div class="asset-title"><h3>${esc(item.symbol||market.replace('KRW-',''))}</h3><span class="market-code">${esc(market)}</span></div><div class="asset-actions"><span class="asset-action ${esc(item.action||'')}">${esc(actionLabel(item.action))}</span><button class="icon-button remove-asset" data-market="${esc(market)}" title="감시 제거" aria-label="감시 제거">×</button></div></div>
    <div class="asset-price-row"><strong class="asset-price">${num(item.price,8)}</strong><span class="asset-change ${clsSign(item.asset_return_pct)}">${signedPct(item.asset_return_pct)}</span></div>
    <div class="score-pair">${scoreCell('Regime',item.regime_score)}${scoreCell('Entry',item.entry_score,'entry')}</div>
    <div class="asset-meta"><span>상대강도</span><b class="${clsSign(item.asset_vs_majors_pct)}">${signedPct(item.asset_vs_majors_pct)}</b><span>조정폭</span><b>${pct(item.pullback_pct)}</b><span>호가</span><b>${num(item.orderbook_imbalance,3)}</b><span>보유가치</span><b>${money(p.value_krw)}</b></div>
    <span class="asset-context-tag">${esc(item.context_mode||'generic_alt')}</span>
  </article>`;
}
function renderAssets(){
  const assets=ui.snapshot?.assets||{};
  const markets=Object.keys(assets);
  if(!markets.includes(ui.selectedMarket)&&markets.length){ui.selectedMarket=markets[0];localStorage.setItem('cryptoTraderSelectedMarket',ui.selectedMarket)}
  $('assetGrid').innerHTML=markets.length?markets.map(m=>assetCard(m,assets[m])).join(''):'<div class="panel empty-state">등록된 감시 자산이 없습니다.</div>';
  $('assetSelect').innerHTML=markets.map(m=>`<option value="${esc(m)}" ${m===ui.selectedMarket?'selected':''}>${esc(assets[m].symbol||m)}</option>`).join('');
  document.querySelectorAll('.asset-card').forEach(card=>card.onclick=e=>{
    if(e.target.closest('.remove-asset'))return;
    selectMarket(card.dataset.market,true);
  });
  document.querySelectorAll('.remove-asset').forEach(btn=>btn.onclick=async e=>{
    e.stopPropagation();const market=btn.dataset.market;
    if(!confirm(`${market} 감시를 제거할까요?`))return;
    try{await api(`/api/assets/${encodeURIComponent(market)}`,{method:'DELETE'});await refreshState()}catch(err){alert(err.message)}
  });
  renderSelectedAsset();
}
function selectMarket(market,openAssetView=false){
  ui.selectedMarket=market;localStorage.setItem('cryptoTraderSelectedMarket',market);
  if($('assetSelect'))$('assetSelect').value=market;
  renderAssets();
  loadSelectedHistory();
  if(openAssetView)switchView('assets');
}
$('assetSelect').onchange=e=>selectMarket(e.target.value,false);

function diagnosticRows(obj){
  return Object.entries(obj||{}).map(([key,value])=>{
    const labels={btc_return_pct:'BTC 수익률',eth_return_pct:'ETH 수익률',eth_vs_btc_pct:'ETH/BTC 상대',asset_vs_majors_pct:'메이저 대비',alt_breadth:'알트 확산',context_strength:'컨텍스트',derivatives_risk_on:'파생 위험선호',news_modifier:'뉴스 보정',asset_return_pct:'자산 수익률',pullback_pct:'조정폭',fib_retrace_pct:'Fib 되돌림',orderbook_imbalance:'호가 imbalance',volatility_pct:'변동성'};
    let formatted=key.includes('pct')?pct(value):key==='orderbook_imbalance'?num(value,3):score(value);
    return `<div class="diagnostic-row"><span>${labels[key]||esc(key)}</span><b>${formatted}</b></div>`;
  }).join('');
}
function renderSelectedAsset(){
  const item=ui.snapshot?.assets?.[ui.selectedMarket];
  if(!item){$('assetDetailHeader').innerHTML='<div class="empty-state">자산을 선택하세요.</div>';return}
  const p=item.position||{},d=item.diagnostics||{},decision=decisionCopy(item);
  $('assetDetailHeader').innerHTML=`<div class="asset-detail-name"><h3>${esc(item.symbol||ui.selectedMarket)}</h3><p>${esc(ui.selectedMarket)} · ${esc(item.context_mode||'generic_alt')}</p></div><div class="asset-detail-price"><strong>${num(item.price,8)}</strong><span class="${clsSign(item.asset_return_pct)}">${signedPct(item.asset_return_pct)} · 보유 ${money(p.value_krw)}</span></div>`;
  $('assetDecision').className=`decision-block ${decision[2]}`;$('assetDecision').innerHTML=`<strong>${esc(decision[0])}</strong><p>${esc(decision[1])}</p>`;
  $('assetScoreGrid').innerHTML=`<div class="score-detail"><span>Regime</span><strong>${score(item.regime_score)}</strong></div><div class="score-detail"><span>Entry</span><strong>${score(item.entry_score)}</strong></div><div class="score-detail"><span>Context</span><strong>${score(item.context_score)}</strong></div>`;
  const checks=d.checks||{};
  $('assetDiagnostics').innerHTML=`<div class="diagnostic-group"><h4>시장 국면</h4>${diagnosticRows(d.regime||{})}<div class="diagnostic-row"><span>Regime 기준</span><b class="${checks.regime_pass?'diagnostic-pass':'diagnostic-fail'}">${checks.regime_pass?'충족':'미충족'} · ${score(d.thresholds?.regime)}</b></div></div><div class="diagnostic-group"><h4>진입 위치</h4>${diagnosticRows(d.entry||{})}<div class="diagnostic-row"><span>Entry 기준</span><b class="${checks.entry_pass?'diagnostic-pass':'diagnostic-fail'}">${checks.entry_pass?'충족':'미충족'} · ${score(d.thresholds?.entry)}</b></div></div>`;
  const c=item.context_details||{},markets=c.markets||[];
  $('assetContext').classList.remove('empty-state');
  $('assetContext').innerHTML=`<div class="context-score"><span>${esc(item.context_mode||'generic_alt')}</span><strong>${score(item.context_score)}</strong></div><div class="context-markets">${markets.length?markets.map(m=>`<span class="context-chip">${esc(m)}</span>`).join(''):'<span class="context-chip">알트 전체 흐름 사용</span>'}</div>${c.median_return_pct!=null?`<div class="list-item">관련시장 중앙값 <b>${signedPct(c.median_return_pct)}</b><small>상승 비율 ${pct((c.positive_ratio||0)*100,0)}</small></div>`:''}`;
}

function svgChart(points,series,{domain=null,markers=[],moneyAxis=false}={}){
  if(!Array.isArray(points)||points.length<2)return '<div class="chart-empty">아직 차트를 그릴 만큼 데이터가 없습니다. 잠시 더 수집하면 자동으로 표시됩니다.</div>';
  const W=900,H=260,pad={l:46,r:18,t:18,b:30};
  const ts=points.map(p=>Number(p.ts));const xmin=Math.min(...ts),xmax=Math.max(...ts);const xspan=Math.max(1,xmax-xmin);
  let values=[];series.forEach(s=>points.forEach(p=>{const v=Number(p[s.key]);if(Number.isFinite(v))values.push(v)}));
  if(!values.length)return '<div class="chart-empty">표시할 값이 없습니다.</div>';
  let ymin=domain?domain[0]:Math.min(...values),ymax=domain?domain[1]:Math.max(...values);if(ymin===ymax){const bump=Math.abs(ymin)*.01||1;ymin-=bump;ymax+=bump}
  if(!domain){const padY=(ymax-ymin)*.12;ymin-=padY;ymax+=padY}
  const x=v=>pad.l+(Number(v)-xmin)/xspan*(W-pad.l-pad.r);const y=v=>pad.t+(ymax-Number(v))/(ymax-ymin)*(H-pad.t-pad.b);
  const grids=[0,.25,.5,.75,1].map(t=>{const yy=pad.t+t*(H-pad.t-pad.b);const val=ymax-t*(ymax-ymin);const label=moneyAxis?Math.round(val).toLocaleString('ko-KR'):Number(val).toFixed(domain?0:4).replace(/\.0+$/,'');return `<line class="chart-grid-line" x1="${pad.l}" y1="${yy}" x2="${W-pad.r}" y2="${yy}"/><text class="chart-axis-label" x="4" y="${yy+3}">${esc(label)}</text>`}).join('');
  const lines=series.map(s=>{const coords=points.map(p=>{const v=Number(p[s.key]);return Number.isFinite(v)?`${x(p.ts).toFixed(1)},${y(v).toFixed(1)}`:null}).filter(Boolean).join(' ');return `<polyline class="chart-line ${s.className}" points="${coords}"/>`}).join('');
  const markerSvg=markers.map(m=>{const mx=x(m.ts),my=y(m.price);if(!Number.isFinite(mx)||!Number.isFinite(my))return'';if(m.side==='buy')return `<path class="chart-marker-buy" d="M ${mx} ${my-7} l 6 10 h -12 z"><title>PAPER 매수 ${num(m.price,8)}</title></path>`;return `<path class="chart-marker-sell" d="M ${mx} ${my+7} l 6 -10 h -12 z"><title>PAPER 매도 ${num(m.price,8)}</title></path>`}).join('');
  const firstLabel=shortTime(xmin),lastLabel=shortTime(xmax);
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">${grids}${lines}${markerSvg}<text class="chart-axis-label" x="${pad.l}" y="${H-8}">${esc(firstLabel)}</text><text class="chart-axis-label" text-anchor="end" x="${W-pad.r}" y="${H-8}">${esc(lastLabel)}</text></svg>`;
}
function renderHistoryCharts(){
  const data=ui.assetHistory||{},points=data.points||[],fills=data.fills||[];
  $('priceChartTitle').textContent=`${ui.selectedMarket.replace('KRW-','')} 가격 흐름`;
  $('priceChart').classList.remove('empty-state');$('scoreChart').classList.remove('empty-state');
  $('priceChart').innerHTML=svgChart(points,[{key:'price',className:'primary'}],{markers:fills});
  $('scoreChart').innerHTML=svgChart(points,[{key:'regime_score',className:'regime'},{key:'entry_score',className:'entry'}],{domain:[0,100]});
}
async function loadSelectedHistory(){
  if(!ui.selectedMarket)return;
  try{ui.assetHistory=await api(`/api/history?market=${encodeURIComponent(ui.selectedMarket)}&range=${encodeURIComponent(ui.assetRange)}`);renderHistoryCharts()}catch(err){console.warn(err)}
}

function renderPerformance(){
  const a=ui.analytics||{};
  const metrics=[
    ['총 손익',money(a.total_pnl_krw),signedPct(a.return_pct),clsSign(a.total_pnl_krw)],
    ['실현손익',money(a.realized_pnl_krw),`미실현 ${money(a.unrealized_pnl_krw)}`,clsSign(a.realized_pnl_krw)],
    ['승률',pct(a.win_rate_pct,1),`${a.closed_trades??0}회 완료`,''],
    ['Profit Factor',a.profit_factor_infinite?'∞':num(a.profit_factor,2),`최대 DD ${pct(a.max_drawdown_pct)}`,''],
  ];
  $('performanceGrid').innerHTML=metrics.map(([label,value,sub,tone])=>`<article class="metric-card"><span>${label}</span><strong class="${tone}">${value}</strong><small>${sub}</small></article>`).join('');
  const markets=a.per_market||{};
  $('marketPerformance').innerHTML=Object.keys(markets).length?Object.entries(markets).map(([market,s])=>`<div class="list-item"><div class="list-item-head"><b>${esc(market)}</b><span class="amount ${clsSign(s.realized_pnl_krw)}">${money(s.realized_pnl_krw)}</span></div><small>완료 ${s.closed_trades||0}회 · 승 ${s.wins||0} / 패 ${s.losses||0}</small></div>`).join(''):'<div class="list-item">완료된 PAPER 거래가 아직 없습니다.</div>';
  const count=Number(a.closed_trades||0);let note='아직 완료 거래가 없습니다. 지금은 점수 분포와 진입 차단 로그를 모으는 단계입니다.';if(count>0&&count<10)note=`완료 거래가 ${count}회라 표본이 아직 작습니다. 승률만 보고 기준값을 바꾸지 말고 최소 10~20회 이상 누적한 뒤 조건별 성과를 비교하는 편이 안전합니다.`;if(count>=10)note=`완료 거래 ${count}회가 쌓였습니다. 자산별 손익과 최대 낙폭을 함께 보고 Regime/Entry 기준 조정을 검토할 수 있습니다.`;
  $('performanceNote').innerHTML=`<strong>현재 해석</strong><br>${esc(note)}`;
}
function renderEquityChart(){
  const points=ui.portfolioHistory?.points||[];
  $('equityChart').classList.remove('empty-state');
  $('equityChart').innerHTML=svgChart(points,[{key:'equity_krw',className:'equity'}],{moneyAxis:true});
  $('equityChartMeta').textContent=points.length?`${points.length}개 샘플 · ${ui.portfolioRange.toUpperCase()}`:'데이터 수집 중';
}
async function loadPortfolioHistory(){
  try{ui.portfolioHistory=await api(`/api/portfolio/history?range=${encodeURIComponent(ui.portfolioRange)}`);renderEquityChart()}catch(err){console.warn(err)}
}

const eventNames={execution_risk_blocked:'진입 차단',paper_buy_blocked:'PAPER 매수 차단',asset_loop_error:'자산 분석 오류',engine_error:'엔진 오류',runtime_config_updated:'전략 설정 변경',asset_added:'감시 자산 추가',asset_removed:'감시 자산 제거',telegram_config_updated:'텔레그램 설정',paper_portfolio_restored:'PAPER 계좌 복원',manual_pause:'신규 진입 일시정지',manual_resume:'신규 진입 재개',manual_kill_switch:'Kill switch',manual_kill_switch_reset:'Kill 해제'};
async function refreshActivity(){
  try{
    const [fills,events]=await Promise.all([api('/api/fills?limit=80'),api('/api/events?limit=120')]);
    $('fillsList').innerHTML=fills.length?fills.map(r=>`<div class="list-item"><div class="list-item-head"><b>${esc(r.market)} ${r.side==='buy'?'매수':'매도'}</b><span class="amount">${money(r.krw)}</span></div><small>${timeText(r.ts)} · ${num(r.price,8)} · ${esc(r.reason)}</small></div>`).join(''):'<div class="list-item">아직 체결 기록이 없습니다.</div>';
    $('eventsList').innerHTML=events.length?events.map(r=>{const p=r.payload||{},market=p.market?` · ${esc(p.market)}`:'';const detail=p.reason||p.message||p.error||'';return `<div class="list-item"><div class="list-item-head"><b>${esc(eventNames[r.kind]||r.kind)}</b><span>${timeText(r.ts)}</span></div><small>${market}${detail?` · ${esc(detail)}`:''}</small></div>`}).join(''):'<div class="list-item">이벤트가 없습니다.</div>';
  }catch(err){console.warn(err)}
}

function renderSettingsStatus(){
  const t=ui.telegram,s=ui.snapshot||{},backup=s.backup||{},sync=s.sync||{};
  $('telegramStatePill').textContent=t.enabled?'연결':t.configured?'비활성':'미설정';$('telegramStatePill').className=`status-pill ${t.enabled?'good':t.configured?'warn':'neutral'}`;
  $('backupSyncStatus').innerHTML=`<div class="list-item"><div class="list-item-head"><b>GitHub</b><span>${esc(sync.status||'idle')}</span></div><small>${sync.to?`현재 ${esc(String(sync.to).slice(0,7))}`:'자동 동기화 상태'}</small></div><div class="list-item"><div class="list-item-head"><b>Google Drive 백업</b><span>${esc(backup.status||'idle')}</span></div><small>${esc(backup.drive||'rclone 연결 전이면 로컬 백업만 저장됩니다.')}</small></div>`;
  $('systemDetail').innerHTML=`<div class="list-item"><div class="list-item-head"><b>모드</b><span>PAPER</span></div><small>실제 주문은 비활성</small></div><div class="list-item"><div class="list-item-head"><b>업타임</b><span>${Math.floor((s.uptime_seconds||0)/60)}분</span></div></div>${s.last_error?`<div class="list-item"><div class="list-item-head"><b>최근 오류</b><span>${esc(s.last_error.scope)}</span></div><small>${esc(s.last_error.message)}</small></div>`:''}`;
}
async function loadNetwork(){
  try{ui.network=await api('/api/network');renderNetwork()}catch(err){console.warn(err)}
}
function accessCard(title,status,url,copy,label){
  return `<div class="access-card"><div class="access-card-top"><h4>${title}</h4><span class="status-pill ${status?'good':'neutral'}">${status?'사용 가능':'대기'}</span></div><p>${esc(label)}</p>${url?`<div class="access-url"><code>${esc(url)}</code><button class="copy-button" data-copy="${esc(url)}">복사</button></div>`:''}${copy?`<p>${esc(copy)}</p>`:''}</div>`;
}
function renderNetwork(){
  const n=ui.network||{},lan=n.lan||{},ts=n.tailscale||{};
  $('tailscalePill').textContent=ts.connected?'Tailscale 연결':ts.installed?'로그인 필요':'설치 필요';$('tailscalePill').className=`status-pill ${ts.connected?'good':ts.installed?'warn':'neutral'}`;
  $('phoneAccessBody').classList.remove('empty-state');
  $('phoneAccessBody').innerHTML=accessCard('같은 Wi-Fi',!!lan.url,lan.url,'','집/사무실 Wi-Fi에서 PC와 폰이 같은 네트워크일 때 사용합니다.')+accessCard('외부 접속',!!ts.connected,ts.url,ts.installed&&!ts.connected?'Tailscale 앱에서 같은 계정으로 로그인하세요.':'','Tailscale을 사용합니다. PC와 폰 모두 같은 tailnet에 로그인해야 합니다.')+(!ts.installed?`<div class="access-card"><div class="access-card-top"><h4>PC에 Tailscale 설치</h4></div><p>PowerShell에서 아래 스크립트를 실행하면 winget 설치와 로그인 절차를 시작합니다.</p><div class="access-url"><code>.\scripts\setup-phone-access.ps1</code><button class="copy-button" data-copy=".\\scripts\\setup-phone-access.ps1">복사</button></div></div>`:'');
  document.querySelectorAll('[data-copy]').forEach(btn=>btn.onclick=()=>copyText(btn.dataset.copy,btn));
}
async function copyText(text,button){try{await navigator.clipboard.writeText(text);const old=button.textContent;button.textContent='복사됨';setTimeout(()=>button.textContent=old,1200)}catch{alert(text)}}

async function loadTelegramStatus(){try{ui.telegram=await api('/api/telegram/status')}catch{}return ui.telegram}
async function loadRuntimeConfig(){try{const cfg=await api('/api/config');for(const [key,value]of Object.entries(cfg)){const input=document.querySelector(`[data-config="${key}"]`);if(input)input.value=value}}catch(err){console.warn(err)}}

async function refreshState(){
  try{
    const [snapshot,analytics]=await Promise.all([api('/api/state'),api('/api/analytics')]);
    ui.snapshot=snapshot;ui.analytics=analytics;
    await loadTelegramStatus();
    renderHeader();renderKpis();renderMarketPulse();renderSystemSummary();renderAssets();renderPerformance();renderSettingsStatus();
  }catch(err){$('connectionPill').textContent='연결 필요';$('connectionPill').className='status-pill bad';console.warn(err)}
}

$('settingsBtn').onclick=()=>openConnectionSettings(isLoopback()?'이 PC에서는 자동 인증됩니다. 폰이나 다른 기기에서 접속할 때만 Dashboard token을 입력하세요.':'로컬 PC 콘솔에 표시된 Dashboard token을 입력하세요.');
$('saveSettings').onclick=()=>{
  ui.apiBase=$('apiBaseInput').value.trim().replace(/\/$/,'')||window.location.origin;ui.token=$('tokenInput').value.trim();localStorage.setItem('cryptoTraderApiBase',ui.apiBase);if(ui.token)localStorage.setItem('cryptoTraderToken',ui.token);else localStorage.removeItem('cryptoTraderToken');setTimeout(()=>{refreshState();loadSelectedHistory();loadPortfolioHistory();loadNetwork()},0);
};
$('addAssetForm').onsubmit=async e=>{e.preventDefault();const ticker=$('tickerInput').value.trim();if(!ticker)return;try{const added=await api('/api/assets',{method:'POST',body:{ticker}});$('tickerInput').value='';ui.selectedMarket=added.market||`KRW-${ticker.toUpperCase()}`;localStorage.setItem('cryptoTraderSelectedMarket',ui.selectedMarket);await refreshState();await loadSelectedHistory()}catch(err){alert(err.message)}};
for(const [id,path]of[['pauseBtn','/api/control/pause'],['resumeBtn','/api/control/resume'],['killBtn','/api/control/kill'],['resetKillBtn','/api/control/reset-kill']])$(id).onclick=async()=>{if(id==='killBtn'&&!confirm('PAPER 보유분을 강제청산하고 신규 진입을 막을까요?'))return;try{await api(path,{method:'POST'});await refreshState()}catch(err){alert(err.message)}};
$('runtimeConfigForm').onsubmit=async e=>{e.preventDefault();const payload={};document.querySelectorAll('[data-config]').forEach(input=>payload[input.dataset.config]=Number(input.value));try{await api('/api/config',{method:'PATCH',body:payload});await loadRuntimeConfig();alert('전략 설정을 저장했습니다.')}catch(err){alert(err.message)}};
$('telegramSettings').onclick=async()=>{await loadTelegramStatus();$('telegramTokenInput').value='';$('telegramTokenInput').placeholder=ui.telegram.token_configured?'토큰 저장됨 · 변경할 때만 입력':'BotFather에서 발급한 토큰';$('telegramChatIdInput').value=ui.telegram.chat_id||'';$('telegramEnabledInput').checked=!!ui.telegram.enabled;$('telegramStatusHint').textContent=ui.telegram.configured?'현재 설정은 이 PC에만 저장되어 있습니다. 토큰 값은 다시 표시하지 않습니다.':'Bot token과 Chat ID를 입력하고 알림 활성화를 켜세요.';$('telegramDialog').showModal()};
$('saveTelegram').onclick=async e=>{e.preventDefault();try{ui.telegram=await api('/api/telegram/config',{method:'PUT',body:{enabled:$('telegramEnabledInput').checked,token:$('telegramTokenInput').value.trim(),chat_id:$('telegramChatIdInput').value.trim()}});$('telegramDialog').close();renderSettingsStatus();renderSystemSummary();alert('텔레그램 설정을 저장했습니다.')}catch(err){alert(err.message)}};
$('telegramTest').onclick=async()=>{try{await api('/api/telegram/test',{method:'POST'});alert('텔레그램 테스트 메시지를 보냈습니다.')}catch(err){alert(err.status===409?'텔레그램 설정을 먼저 완료하세요.':err.message)}};
$('backupNow').onclick=async()=>{try{await api('/api/backup',{method:'POST'});await refreshState()}catch(err){alert(err.message)}};
$('syncNow').onclick=async()=>{try{await api('/api/sync',{method:'POST'});await refreshState()}catch(err){alert(err.message)}};
$('refreshActivity').onclick=refreshActivity;

document.querySelectorAll('[data-range-group="asset"] button').forEach(btn=>btn.onclick=()=>{ui.assetRange=btn.dataset.range;localStorage.setItem('cryptoTraderAssetRange',ui.assetRange);document.querySelectorAll('[data-range-group="asset"] button').forEach(b=>b.classList.toggle('is-active',b===btn));loadSelectedHistory()});
document.querySelectorAll('[data-range-group="portfolio"] button').forEach(btn=>btn.onclick=()=>{ui.portfolioRange=btn.dataset.range;localStorage.setItem('cryptoTraderPortfolioRange',ui.portfolioRange);document.querySelectorAll('[data-range-group="portfolio"] button').forEach(b=>b.classList.toggle('is-active',b===btn));loadPortfolioHistory()});
document.querySelectorAll('[data-range-group="asset"] button').forEach(b=>b.classList.toggle('is-active',b.dataset.range===ui.assetRange));
document.querySelectorAll('[data-range-group="portfolio"] button').forEach(b=>b.classList.toggle('is-active',b.dataset.range===ui.portfolioRange));

if(isLoopback()){localStorage.removeItem('cryptoTraderToken');ui.token=''}
switchView(['overview','assets','performance','activity','settings'].includes(ui.view)?ui.view:'overview');
refreshState();loadSelectedHistory();loadPortfolioHistory();loadNetwork();refreshActivity();loadRuntimeConfig();
setInterval(refreshState,5000);
setInterval(()=>{if(ui.view==='assets')loadSelectedHistory();if(ui.view==='performance')loadPortfolioHistory()},30000);
setInterval(()=>{if(ui.view==='activity')refreshActivity()},15000);
setInterval(()=>{if(ui.view==='settings')loadNetwork()},30000);
