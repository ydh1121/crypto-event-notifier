let localPhoneCode=null;
let localPhoneCodeVisible=false;
let simpleHoldingMap={};

function easyScoreMeaning(value){
  const v=Number(value);
  if(!Number.isFinite(v))return '확인 중';
  if(v<40)return '매우 나쁨';
  if(v<55)return '좋지 않음';
  if(v<65)return '보통';
  if(v<75)return '좋음';
  return '매우 좋음';
}
function easyScoreTone(value){
  const v=Number(value);
  if(!Number.isFinite(v))return 'neutral';
  if(v<55)return 'bad';
  if(v<65)return 'warn';
  return 'good';
}
function easyScoreValue(value){
  const v=Number(value);
  return Number.isFinite(v)?`${Math.round(v)}/100`:'-';
}
function easyScoreBlock(label,value,help=''){
  const meaning=easyScoreMeaning(value),tone=easyScoreTone(value),width=Math.max(0,Math.min(100,Number(value)||0));
  return `<div class="easy-score ${tone}"><div class="easy-score-head"><span>${esc(label)}</span><b>${esc(meaning)}</b></div><div class="easy-score-value"><strong>${easyScoreValue(value)}</strong>${help?`<small>${esc(help)}</small>`:''}</div><div class="score-track"><i style="width:${width}%"></i></div></div>`;
}
function actionLabel(action){
  return ({WATCH:'조금 더 지켜보기',WAIT_PULLBACK:'가격이 내려오길 기다림',BUY_CANDIDATE:'매수 후보',RISK_OFF:'지금은 매수하지 않음',ERROR:'확인 필요'})[action]||'확인 중';
}
function actionTone(action){
  return action==='BUY_CANDIDATE'?'good':action==='RISK_OFF'||action==='ERROR'?'bad':action==='WAIT_PULLBACK'?'warn':'neutral';
}
function decisionCopy(item){
  const action=item?.action;
  if(action==='BUY_CANDIDATE')return ['매수를 검토할 수 있는 구간입니다.','시장 분위기와 현재 가격 위치가 모두 기준을 넘었습니다.','good'];
  if(action==='WAIT_PULLBACK')return ['지금은 가격이 조금 내려오길 기다립니다.','시장 분위기는 괜찮지만 현재 가격은 서둘러 살 자리는 아닙니다.','warn'];
  if(action==='RISK_OFF')return ['지금은 새로 사지 않는 편이 낫습니다.','전체 시장 분위기가 좋지 않아 관찰만 하는 구간입니다.','bad'];
  if(action==='ERROR')return ['분석 결과를 확인해야 합니다.',item?.error||'잠시 뒤 다시 확인하거나 기록 화면에서 오류를 확인하세요.','bad'];
  return ['아직은 조금 더 지켜봅니다.','지금 당장 살 정도로 조건이 충분히 모이지 않았습니다.','neutral'];
}
function holdingFor(market){return simpleHoldingMap[market]||null}

function applyPlainStaticCopy(){
  const eyebrow=document.querySelector('.brand-block .eyebrow');if(eyebrow)eyebrow.textContent='가상매매 · 실시간 감시';
  const title=document.querySelector('.brand-block h1');if(title)title.textContent='코인 상태판';
  if($('settingsBtn'))$('settingsBtn').textContent='휴대폰 연결';
  const tabs=document.querySelectorAll('.view-tab');['홈','코인','결과','기록','설정'].forEach((t,i)=>{if(tabs[i])tabs[i].textContent=t});

  const intro=document.querySelector('[data-view-panel="overview"] .section-intro > div:first-child');
  if(intro)intro.innerHTML='<p class="section-kicker">한눈에 보기</p><h2>지금 살지, 기다릴지만 먼저 봅니다.</h2><p class="section-copy">어려운 지표는 뒤로 숨기고, 현재 판단과 내 보유 상태를 먼저 보여줍니다.</p>';

  const kpiLabels=document.querySelectorAll('[data-view-panel="overview"] .kpi-grid .metric-card > span');
  ['가상 계좌','남은 현금','오늘 하락폭','확정 손익'].forEach((text,i)=>{if(kpiLabels[i])kpiLabels[i].textContent=text});
  const marketTitle=document.querySelector('.market-panel h3');if(marketTitle)marketTitle.textContent='전체 시장은 어떤가요?';
  const marketKick=document.querySelector('.market-panel .panel-kicker');if(marketKick)marketKick.textContent='시장 요약';
  const systemKick=document.querySelector('.system-panel .panel-kicker');if(systemKick)systemKick.textContent='프로그램';

  const assetHead=document.querySelector('[data-view-panel="assets"] .section-head > div');
  if(assetHead)assetHead.innerHTML='<p class="section-kicker">코인별 보기</p><h2>내 코인 상태</h2><p>가격, 내 평단, 손익, 현재 판단을 한 화면에서 확인합니다.</p>';
  const contextTitle=document.querySelector('.context-panel h3');if(contextTitle)contextTitle.textContent='비슷한 코인 흐름';
  const contextKick=document.querySelector('.context-panel .panel-kicker');if(contextKick)contextKick.textContent='참고';
  const scorePanel=$('scoreChart')?.closest('.chart-panel');if(scorePanel){const h=scorePanel.querySelector('h3');if(h)h.textContent='시장 분위기와 매수 타이밍 변화'}
  const legends=scorePanel?.querySelectorAll('.chart-legend span')||[];if(legends[0])legends[0].textContent='시장 분위기';if(legends[1])legends[1].textContent='매수 타이밍';

  const perfHead=document.querySelector('[data-view-panel="performance"] .section-head > div');
  if(perfHead)perfHead.innerHTML='<p class="section-kicker">가상매매 결과</p><h2>이 판단이 실제로 잘 맞았는지</h2><p>가상으로 사고판 결과를 누적해서 확인합니다.</p>';
  const eqTitle=$('equityChart')?.closest('.chart-panel')?.querySelector('h3');if(eqTitle)eqTitle.textContent='가상 계좌 변화';
  const activityHead=document.querySelector('[data-view-panel="activity"] .section-head > div');
  if(activityHead)activityHead.innerHTML='<p class="section-kicker">기록</p><h2>최근에 무슨 일이 있었나요?</h2><p>매수·매도, 차단, 설정 변경과 오류를 시간순으로 보여줍니다.</p>';
  const settingHead=document.querySelector('[data-view-panel="settings"] > .section-head > div');
  if(settingHead)settingHead.innerHTML='<p class="section-kicker">설정</p><h2>필요할 때만 바꾸세요.</h2><p>평소에는 기본값을 그대로 사용해도 됩니다.</p>';

  if($('pauseBtn'))$('pauseBtn').textContent='새 매수 잠시 멈춤';
  if($('resumeBtn'))$('resumeBtn').textContent='다시 시작';
  if($('killBtn'))$('killBtn').textContent='긴급 정지';
  if($('resetKillBtn'))$('resetKillBtn').textContent='긴급 정지 해제';
  moveSafetyControlsToSettings();
  simplifyAdvancedSettings();
  addHoldingsOverviewShell();

  const telegramCopy=document.querySelector('#telegramStatePill')?.closest('.panel')?.querySelector('.panel-copy');
  if(telegramCopy)telegramCopy.textContent='매수 후보, 가상 매수·매도, 시장 악화와 중요한 오류만 알려드립니다.';
  const phoneTitle=document.querySelector('.phone-panel h3');if(phoneTitle)phoneTitle.textContent='휴대폰에서 보기';
  const deferred=document.querySelector('.deferred-panel .panel-copy');if(deferred)deferred.textContent='실제 돈으로 주문하는 기능은 별도 작업으로 만듭니다. 지금은 가상매매만 합니다.';

  const dialog=$('settingsDialog');
  if(dialog){
    const h2=dialog.querySelector('h2');if(h2)h2.textContent='휴대폰 연결';
    const tokenInput=$('tokenInput');if(tokenInput){const label=tokenInput.closest('label');if(label?.childNodes?.length)label.childNodes[0].nodeValue='휴대폰 연결 코드';tokenInput.placeholder='PC 설정 화면에 표시되는 연결 코드'}
    if($('connectionHint'))$('connectionHint').textContent='PC에서는 코드가 필요 없습니다. 휴대폰에서 처음 접속할 때만 입력합니다.';
  }
}

function moveSafetyControlsToSettings(){
  const controls=document.querySelector('.engine-controls');
  const settings=document.querySelector('[data-view-panel="settings"] .settings-grid');
  if(!controls||!settings||document.getElementById('safetyControlCard'))return;
  const card=document.createElement('article');card.id='safetyControlCard';card.className='panel safety-control-card';
  card.innerHTML='<div class="panel-head"><div><p class="panel-kicker">안전 제어</p><h3>매수 중지와 긴급 정지</h3></div></div><p class="panel-copy">평소에는 건드리지 않아도 됩니다. 문제가 생겼을 때만 사용합니다.</p>';
  card.appendChild(controls);settings.prepend(card);
}
function simplifyAdvancedSettings(){
  const panel=document.querySelector('.settings-panel');if(!panel||panel.dataset.simpleWrapped)return;
  const form=panel.querySelector('#runtimeConfigForm');if(!form)return;
  panel.dataset.simpleWrapped='1';
  const details=document.createElement('details');details.className='advanced-settings';
  const summary=document.createElement('summary');summary.textContent='고급 설정 보기';
  form.parentNode.insertBefore(details,form);details.appendChild(summary);details.appendChild(form);
  const head=panel.querySelector('.panel-head');if(head){const h=head.querySelector('h3');if(h)h.textContent='매수 기준';const m=head.querySelector('.muted');if(m)m.textContent='필요할 때만 변경'}
}
function addHoldingsOverviewShell(){
  if(document.getElementById('myHoldingsOverview'))return;
  const overview=document.querySelector('[data-view-panel="overview"]');
  const grid=overview?.querySelector('.kpi-grid');if(!overview||!grid)return;
  const section=document.createElement('section');section.id='myHoldingsOverview';section.className='panel my-holdings-overview';
  section.innerHTML='<div class="panel-head"><div><p class="panel-kicker">내 실제 보유분</p><h3>내 코인 현황</h3></div><button class="button secondary compact" id="openAssetsFromHoldings">코인별 보기</button></div><div id="myHoldingsOverviewBody" class="holdings-overview-body empty-state">보유 정보를 불러오는 중입니다.</div>';
  grid.insertAdjacentElement('afterend',section);
  section.querySelector('#openAssetsFromHoldings').onclick=()=>switchView('assets');
}

scoreCell=function(label,value,type=''){
  const easyLabel=label==='Regime'?'시장 분위기':label==='Entry'?'매수 타이밍':label;
  const help=label==='Regime'?'전체 시장이 매수에 유리한지':label==='Entry'?'지금 가격이 사기 좋은 자리인지':'';
  return easyScoreBlock(easyLabel,value,help);
};
renderKpis=function(){
  const p=ui.snapshot?.portfolio||{},a=ui.analytics||{};
  $('equityValue').textContent=money(p.equity_krw);
  $('returnValue').innerHTML=`처음보다 <span class="${clsSign(a.return_pct)}">${signedPct(a.return_pct)}</span>`;
  $('cashValue').textContent=money(p.cash_krw);
  $('exposureValue').textContent=`가상 보유 ${money(p.exposure_krw)}`;
  $('ddValue').textContent=pct(p.daily_drawdown_pct);
  $('maxDdValue').textContent=`기록상 최대 ${pct(a.max_drawdown_pct)}`;
  $('realizedValue').innerHTML=`<span class="${clsSign(a.realized_pnl_krw)}">${money(a.realized_pnl_krw)}</span>`;
  $('winRateValue').textContent=`끝난 거래 ${a.closed_trades??0}회 · 이긴 비율 ${pct(a.win_rate_pct,1)}`;
};
renderMarketPulse=function(){
  const market=ui.snapshot?.market||{},f=market.factors||{};
  const items=[['알트코인 전체',f.alt_breadth],['Base 계열',f.base_strength],['게임 코인',f.gaming_strength],['선물시장',f.derivatives_risk_on]];
  $('marketPulse').classList.remove('empty-state');
  $('marketPulse').innerHTML=items.map(([label,value])=>`<div class="pulse-item easy-pulse"><span>${esc(label)}</span><strong>${esc(easyScoreMeaning(value))}</strong><small>${easyScoreValue(value)}</small></div>`).join('');
  $('marketUpdated').textContent=market.ts?`${timeText(market.ts)} 기준`:'-';
};
renderSystemSummary=function(){
  const s=ui.snapshot||{},sync=s.sync||{},backup=s.backup||{};
  $('systemSummary').innerHTML=[['감시 프로그램',s.kill_switch?'긴급 정지':s.paused?'새 매수 멈춤':'정상'],['텔레그램',ui.telegram?.enabled?'연결됨':'확인 필요'],['백업',backup.status==='error'?'오류':backup.status==='done'||backup.status==='success'?'완료':'대기']].map(([k,v])=>`<div class="system-line"><span>${k}</span><b>${esc(v)}</b></div>`).join('');
};
assetCard=function(market,item){
  const holding=holdingFor(market),selected=market===ui.selectedMarket,decision=decisionCopy(item),pnl=holding?Number(holding.unrealized_pnl_krw||0):null,pnlPct=holding?Number(holding.unrealized_pnl_pct||0):null;
  return `<article class="asset-card simple-asset-card ${selected?'is-selected':''}" data-market="${esc(market)}">
    <div class="asset-card-top"><div class="asset-title"><h3>${esc(item.symbol||market.replace('KRW-',''))}</h3><span class="market-code">현재가 ${num(item.price,8)}원</span></div><div class="asset-actions"><span class="asset-action ${esc(item.action||'')}">${esc(actionLabel(item.action))}</span><button class="icon-button remove-asset" data-market="${esc(market)}" title="감시 제거" aria-label="감시 제거">×</button></div></div>
    <div class="simple-decision ${actionTone(item.action)}"><strong>${esc(decision[0])}</strong><small>${esc(decision[1])}</small></div>
    ${holding&&Number(holding.volume)>0?`<div class="holding-strip"><span>내 평단 <b>${num(holding.avg_price,8)}원</b></span><span>현재 손익 <b class="${clsSign(pnl)}">${money(pnl)} · ${signedPct(pnlPct)}</b></span></div>`:''}
    <div class="simple-score-row"><span>시장 <b>${esc(easyScoreMeaning(item.regime_score))}</b> ${easyScoreValue(item.regime_score)}</span><span>타이밍 <b>${esc(easyScoreMeaning(item.entry_score))}</b> ${easyScoreValue(item.entry_score)}</span></div>
  </article>`;
};

diagnosticRows=function(obj){
  return Object.entries(obj||{}).map(([key,value])=>{
    const labels={btc_return_pct:'비트코인 흐름',eth_return_pct:'이더리움 흐름',eth_vs_btc_pct:'이더리움이 비트보다 강한 정도',asset_vs_majors_pct:'이 코인의 상대 강도',alt_breadth:'알트코인 전체 분위기',context_strength:'비슷한 코인 분위기',derivatives_risk_on:'선물시장 안정 정도',news_modifier:'뉴스 영향',asset_return_pct:'이 코인 최근 흐름',pullback_pct:'최근 고점에서 내려온 폭',fib_retrace_pct:'가격 조정 위치',orderbook_imbalance:'매수·매도 호가 균형',volatility_pct:'가격 흔들림'};
    let formatted=key.includes('pct')?pct(value):key==='orderbook_imbalance'?num(value,3):key==='news_modifier'?num(value,1):`${easyScoreMeaning(value)} · ${easyScoreValue(value)}`;
    return `<div class="diagnostic-row"><span>${labels[key]||esc(key)}</span><b>${formatted}</b></div>`;
  }).join('');
};
renderSelectedAsset=function(){
  const item=ui.snapshot?.assets?.[ui.selectedMarket];
  if(!item){$('assetDetailHeader').innerHTML='<div class="empty-state">코인을 선택하세요.</div>';return}
  const holding=holdingFor(ui.selectedMarket),d=item.diagnostics||{},decision=decisionCopy(item),checks=d.checks||{};
  $('assetDetailHeader').innerHTML=`<div class="asset-detail-name"><h3>${esc(item.symbol||ui.selectedMarket.replace('KRW-',''))}</h3><p>현재가 ${num(item.price,8)}원</p></div><div class="asset-detail-price">${holding&&Number(holding.volume)>0?`<span>내 평단</span><strong>${num(holding.avg_price,8)}원</strong><small class="${clsSign(holding.unrealized_pnl_krw)}">${money(holding.unrealized_pnl_krw)} · ${signedPct(holding.unrealized_pnl_pct)}</small>`:`<span>내 평단</span><strong>-</strong><small>아래에서 입력할 수 있습니다.</small>`}</div>`;
  $('assetDecision').className=`decision-block ${decision[2]}`;$('assetDecision').innerHTML=`<strong>${esc(decision[0])}</strong><p>${esc(decision[1])}</p>`;
  $('assetScoreGrid').innerHTML=`${easyScoreBlock('전체 시장 분위기',item.regime_score,'높을수록 시장이 매수에 유리합니다.')}${easyScoreBlock('지금 매수 타이밍',item.entry_score,'높을수록 현재 가격 자리가 좋습니다.')}${easyScoreBlock('비슷한 코인 흐름',item.context_score,'관련 코인들이 함께 강한지 봅니다.')}`;
  $('assetDiagnostics').innerHTML=`<details class="technical-details"><summary>왜 이렇게 판단했는지 자세히 보기</summary><div class="diagnostic-detail-body"><div class="diagnostic-group"><h4>시장 쪽 이유</h4>${diagnosticRows(d.regime||{})}<div class="diagnostic-row"><span>시장 기준</span><b class="${checks.regime_pass?'diagnostic-pass':'diagnostic-fail'}">${checks.regime_pass?'통과':'아직 부족'}</b></div></div><div class="diagnostic-group"><h4>가격 쪽 이유</h4>${diagnosticRows(d.entry||{})}<div class="diagnostic-row"><span>매수 기준</span><b class="${checks.entry_pass?'diagnostic-pass':'diagnostic-fail'}">${checks.entry_pass?'통과':'아직 부족'}</b></div></div></div></details>`;
  const c=item.context_details||{},markets=c.markets||[];
  $('assetContext').classList.remove('empty-state');$('assetContext').innerHTML=`<div class="easy-context"><span>비슷한 코인들의 흐름</span><strong>${esc(easyScoreMeaning(item.context_score))}</strong><small>${easyScoreValue(item.context_score)}</small></div>${markets.length?`<div class="context-markets">${markets.map(m=>`<span class="context-chip">${esc(String(m).replace('KRW-',''))}</span>`).join('')}</div>`:'<p class="plain-help">관련 코인 묶음은 아직 기본값으로 분석 중입니다.</p>'}`;
};

async function loadSimpleHoldings(){
  try{
    const rows=await api('/api/holdings');
    simpleHoldingMap=Object.fromEntries((rows||[]).map(r=>[r.market,r]));
    renderMyHoldingsOverview(rows||[]);
    if(ui.snapshot)renderAssets();
  }catch(err){console.warn('holdings overview',err)}
}
function renderMyHoldingsOverview(rows){
  const box=document.getElementById('myHoldingsOverviewBody');if(!box)return;
  const active=(rows||[]).filter(r=>Number(r.volume)>0);
  if(!active.length){box.className='holdings-overview-body empty-state';box.textContent='보유 수량과 평단을 입력한 코인이 없습니다.';return}
  const invested=active.reduce((s,r)=>s+Number(r.invested_krw||0),0),value=active.reduce((s,r)=>s+Number(r.value_krw||0),0),pnl=value-invested,pnlPct=invested>0?pnl/invested*100:0;
  box.className='holdings-overview-body';
  box.innerHTML=`<div class="holdings-total"><span>전체 평가금액</span><strong>${money(value)}</strong><small class="${clsSign(pnl)}">현재 손익 ${money(pnl)} · ${signedPct(pnlPct)}</small></div><div class="holdings-list">${active.map(r=>`<button class="holding-row" data-holding-market="${esc(r.market)}"><span><b>${esc(r.market.replace('KRW-',''))}</b><small>평단 ${num(r.avg_price,8)}원</small></span><span><b>${money(r.value_krw)}</b><small class="${clsSign(r.unrealized_pnl_krw)}">${signedPct(r.unrealized_pnl_pct)}</small></span></button>`).join('')}</div>`;
  box.querySelectorAll('[data-holding-market]').forEach(btn=>btn.onclick=()=>{ui.selectedMarket=btn.dataset.holdingMarket;localStorage.setItem('cryptoTraderSelectedMarket',ui.selectedMarket);switchView('assets');setTimeout(()=>{renderAssets();loadSelectedHistory();if(typeof loadPersonalTools==='function')loadPersonalTools()},0)});
}

async function loadLocalPhoneCode(){
  if(!isLoopback())return;
  try{const result=await api('/api/local/phone-code');localPhoneCode=result.code;augmentLocalPhoneCode()}catch{}
}
function augmentLocalPhoneCode(){
  const panel=document.querySelector('.phone-panel');if(!panel||!isLoopback()||!localPhoneCode)return;
  let card=document.getElementById('localPhoneCodeCard');
  if(!card){card=document.createElement('div');card.id='localPhoneCodeCard';card.className='access-card phone-code-card';panel.appendChild(card)}
  const shown=localPhoneCodeVisible?localPhoneCode:'••••••••••••••••';
  card.innerHTML=`<div class="access-card-top"><h4>휴대폰 연결 코드</h4><span class="status-pill good">PC에서만 확인</span></div><p>휴대폰에서 처음 접속할 때 한 번 입력합니다.</p><div class="access-url"><code>${esc(shown)}</code><button id="togglePhoneCode" class="copy-button">${localPhoneCodeVisible?'숨기기':'보기'}</button><button id="copyPhoneCode" class="copy-button">복사</button></div>`;
  card.querySelector('#togglePhoneCode').onclick=()=>{localPhoneCodeVisible=!localPhoneCodeVisible;augmentLocalPhoneCode()};
  card.querySelector('#copyPhoneCode').onclick=()=>copyText(localPhoneCode,card.querySelector('#copyPhoneCode'));
}

function addMobileNavLabels(){
  const tabs=document.querySelectorAll('.view-tab');
  const icons=['⌂','◆','↗','≡','⚙'];
  tabs.forEach((tab,i)=>{if(!tab.querySelector('.nav-icon'))tab.innerHTML=`<span class="nav-icon">${icons[i]}</span><span>${tab.textContent}</span>`});
}

function loadLiquidNavigationEnhancements(){
  if(!document.querySelector('link[data-crypto-liquid-nav]')){
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href='./liquid-navigation.css?v=1';
    link.dataset.cryptoLiquidNav='true';
    document.head.appendChild(link);
  }
  if(!document.querySelector('script[data-crypto-liquid-nav]')){
    const script=document.createElement('script');
    script.src='./liquid-navigation.js?v=1';
    script.dataset.cryptoLiquidNav='true';
    document.body.appendChild(script);
  }
}

applyPlainStaticCopy();
addMobileNavLabels();
loadSimpleHoldings();
loadLocalPhoneCode();
setInterval(loadSimpleHoldings,15000);
setTimeout(()=>{applyPlainStaticCopy();addMobileNavLabels();loadSimpleHoldings();loadLocalPhoneCode()},500);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',loadLiquidNavigationEnhancements,{once:true});
else setTimeout(loadLiquidNavigationEnhancements,0);
