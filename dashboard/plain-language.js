let localPhoneCode=null;
let localPhoneCodeVisible=false;

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

function applyPlainStaticCopy(){
  const eyebrow=document.querySelector('.brand-block .eyebrow');
  if(eyebrow)eyebrow.textContent='가상매매 테스트';
  const title=document.querySelector('.brand-block h1');
  if(title)title.textContent='코인 자동매매 모니터';
  if($('settingsBtn'))$('settingsBtn').textContent='휴대폰 연결';
  const intro=document.querySelector('[data-view-panel="overview"] .section-intro > div:first-child');
  if(intro)intro.innerHTML='<p class="section-kicker">현재 상태</p><h2>지금 사도 되는지 쉽게 알려드립니다.</h2><p class="section-copy">전체 시장이 좋은지와 지금 가격이 사기 좋은 자리를 따로 확인합니다. 두 조건이 모두 좋아야 가상 매수 후보가 됩니다.</p>';
  if($('pauseBtn'))$('pauseBtn').textContent='새 매수 잠시 멈춤';
  if($('resumeBtn'))$('resumeBtn').textContent='다시 시작';
  if($('killBtn'))$('killBtn').textContent='긴급 정지';
  if($('resetKillBtn'))$('resetKillBtn').textContent='긴급 정지 해제';

  const kpiLabels=document.querySelectorAll('[data-view-panel="overview"] .kpi-grid .metric-card > span');
  ['가상 계좌 총액','남은 현금','오늘 최대 하락','확정 손익'].forEach((text,i)=>{if(kpiLabels[i])kpiLabels[i].textContent=text});
  const marketTitle=document.querySelector('.market-panel h3');if(marketTitle)marketTitle.textContent='전체 시장 분위기';
  const marketKick=document.querySelector('.market-panel .panel-kicker');if(marketKick)marketKick.textContent='쉬운 시장 요약';
  const systemKick=document.querySelector('.system-panel .panel-kicker');if(systemKick)systemKick.textContent='프로그램 상태';

  const assetHead=document.querySelector('[data-view-panel="assets"] .section-head > div');
  if(assetHead)assetHead.innerHTML='<p class="section-kicker">코인 자세히 보기</p><h2>왜 사고 기다리는지 확인</h2><p>어려운 전문용어 대신 현재 판단과 이유를 먼저 보여줍니다.</p>';
  const contextTitle=document.querySelector('.context-panel h3');if(contextTitle)contextTitle.textContent='비슷한 코인들의 흐름';
  const contextKick=document.querySelector('.context-panel .panel-kicker');if(contextKick)contextKick.textContent='관련 시장';
  const scoreTitle=document.querySelector('#scoreChart')?.closest('.chart-panel')?.querySelector('h3');if(scoreTitle)scoreTitle.textContent='시장 분위기 / 매수 타이밍 변화';
  document.querySelectorAll('#scoreChart').forEach(()=>{});
  const legends=document.querySelectorAll('#scoreChart')?.length?document.querySelectorAll('#scoreChart')[0].closest('.chart-panel').querySelectorAll('.chart-legend span'):[];
  if(legends[0])legends[0].lastChild.textContent=' 시장 분위기';
  if(legends[1])legends[1].lastChild.textContent=' 매수 타이밍';

  const perfHead=document.querySelector('[data-view-panel="performance"] .section-head > div');
  if(perfHead)perfHead.innerHTML='<p class="section-kicker">가상매매 결과</p><h2>이 전략이 실제로 잘 맞는지 확인</h2><p>가상으로 사고판 기록을 모아 수익과 손실을 확인합니다.</p>';
  const equityTitle=document.querySelector('#equityChart')?.closest('.chart-panel')?.querySelector('h3');if(equityTitle)equityTitle.textContent='가상 계좌 총액 변화';

  const activityHead=document.querySelector('[data-view-panel="activity"] .section-head > div');
  if(activityHead)activityHead.innerHTML='<p class="section-kicker">기록</p><h2>무슨 일이 있었는지</h2><p>가상 매수·매도, 매수 보류, 설정 변경과 오류를 시간순으로 보여줍니다.</p>';

  const settingHead=document.querySelector('[data-view-panel="settings"] > .section-head > div');
  if(settingHead)settingHead.innerHTML='<p class="section-kicker">설정</p><h2>운영 설정</h2><p>평소에는 기본값을 그대로 써도 됩니다. 어려운 항목은 설명을 함께 표시합니다.</p>';
  const telegramCopy=document.querySelector('#telegramStatePill')?.closest('.panel')?.querySelector('.panel-copy');
  if(telegramCopy)telegramCopy.textContent='매수 후보, 가상 매수·매도, 시장이 나빠졌을 때와 중요한 오류를 쉬운 문장으로 알려드립니다.';
  const phoneTitle=document.querySelector('.phone-panel h3');if(phoneTitle)phoneTitle.textContent='휴대폰에서 보기';
  const phoneKick=document.querySelector('.phone-panel .panel-kicker');if(phoneKick)phoneKick.textContent='휴대폰 연결';
  const deferred=document.querySelector('.deferred-panel .panel-copy');if(deferred)deferred.textContent='실제 돈으로 주문하는 기능은 나중에 별도 작업으로 만듭니다. 지금은 가상매매만 합니다.';

  const dialog=$('settingsDialog');
  if(dialog){
    const h2=dialog.querySelector('h2');if(h2)h2.textContent='휴대폰 연결';
    const tokenInput=$('tokenInput');
    if(tokenInput){
      const label=tokenInput.closest('label');
      if(label&&label.childNodes.length)label.childNodes[0].nodeValue='휴대폰 연결 코드';
      tokenInput.placeholder='PC 설정 화면에 표시되는 연결 코드';
    }
    if($('connectionHint'))$('connectionHint').textContent='이 PC에서는 연결 코드가 필요 없습니다. 휴대폰이나 다른 기기에서 접속할 때만 한 번 입력합니다.';
  }
}

// Beginner-facing action names. Internal action codes stay unchanged for the engine and journal.
actionLabel=function(action){
  return ({WATCH:'조금 더 지켜보기',WAIT_PULLBACK:'가격이 내려오길 기다림',BUY_CANDIDATE:'매수 후보',RISK_OFF:'지금은 매수하지 않음',ERROR:'확인 필요'})[action]||'확인 중';
};
decisionCopy=function(item){
  const action=item?.action;
  if(action==='BUY_CANDIDATE')return ['가상 매수를 검토할 수 있는 구간입니다.','전체 시장과 현재 가격 위치가 모두 기준을 넘었습니다. 실제 가상 주문 전에는 가격 벌어짐과 급락 여부를 한 번 더 확인합니다.',''];
  if(action==='WAIT_PULLBACK')return ['시장 분위기는 좋지만 지금 가격은 조금 비싸 보입니다.','서둘러 따라 사지 않고 가격이 조금 내려오거나 매수 조건이 더 좋아질 때까지 기다립니다.','wait'];
  if(action==='RISK_OFF')return ['지금은 새로 사지 않는 편이 낫습니다.','전체 시장 분위기가 아직 좋지 않습니다. 시장이 회복될 때까지 관찰만 합니다.','risk'];
  if(action==='ERROR')return ['분석을 정상적으로 끝내지 못했습니다.',item.error||'활동 기록에서 오류 내용을 확인하세요.','risk'];
  return ['아직은 조금 더 지켜봅니다.','지금 당장 사야 할 정도로 조건이 모이지 않았습니다.',''];
};
scoreCell=function(label,value,type=''){
  const easyLabel=label==='Regime'?'시장 분위기':label==='Entry'?'매수 타이밍':label;
  const help=label==='Regime'?'비트코인·이더리움·알트 흐름을 종합':label==='Entry'?'현재 가격이 사기 좋은 자리인지 종합':'';
  return easyScoreBlock(easyLabel,value,help);
};

renderKpis=function(){
  const p=ui.snapshot?.portfolio||{},a=ui.analytics||{};
  $('equityValue').textContent=money(p.equity_krw);
  $('returnValue').innerHTML=`처음보다 <span class="${clsSign(a.return_pct)}">${signedPct(a.return_pct)}</span>`;
  $('cashValue').textContent=money(p.cash_krw);
  $('exposureValue').textContent=`현재 코인에 들어간 금액 ${money(p.exposure_krw)}`;
  $('ddValue').textContent=pct(p.daily_drawdown_pct);
  $('maxDdValue').textContent=`기록상 최대 하락 ${pct(a.max_drawdown_pct)}`;
  $('realizedValue').innerHTML=`<span class="${clsSign(a.realized_pnl_krw)}">${money(a.realized_pnl_krw)}</span>`;
  $('winRateValue').textContent=`끝난 거래 ${a.closed_trades??0}회 · 이긴 비율 ${pct(a.win_rate_pct,1)}`;
};

renderMarketPulse=function(){
  const market=ui.snapshot?.market||{},f=market.factors||{};
  const items=[
    ['알트코인 전체',f.alt_breadth,'여러 알트코인이 함께 강한지'],
    ['Base 계열',f.base_strength,'Base 관련 코인들의 흐름'],
    ['게임 코인',f.gaming_strength,'게임 관련 코인들의 흐름'],
    ['선물시장 과열 여부',f.derivatives_risk_on,'무리한 레버리지가 많은지'],
  ];
  $('marketPulse').classList.remove('empty-state');
  $('marketPulse').innerHTML=items.map(([label,value,sub])=>`<div class="pulse-item easy-pulse"><span>${esc(label)}</span><strong>${esc(easyScoreMeaning(value))}</strong><small>${easyScoreValue(value)} · ${esc(sub)}</small></div>`).join('');
  $('marketUpdated').textContent=market.ts?`${timeText(market.ts)} 기준`:'-';
};

assetCard=function(market,item){
  const p=item.position||{},selected=market===ui.selectedMarket;
  return `<article class="asset-card ${selected?'is-selected':''}" data-market="${esc(market)}">
    <div class="asset-card-top"><div class="asset-title"><h3>${esc(item.symbol||market.replace('KRW-',''))}</h3><span class="market-code">${esc(market)}</span></div><div class="asset-actions"><span class="asset-action ${esc(item.action||'')}">${esc(actionLabel(item.action))}</span><button class="icon-button remove-asset" data-market="${esc(market)}" title="감시 제거" aria-label="감시 제거">×</button></div></div>
    <div class="asset-price-row"><strong class="asset-price">${num(item.price,8)}</strong><span class="asset-change ${clsSign(item.asset_return_pct)}">${signedPct(item.asset_return_pct)}</span></div>
    <div class="score-pair">${easyScoreBlock('시장 분위기',item.regime_score)}${easyScoreBlock('매수 타이밍',item.entry_score)}</div>
    <div class="asset-meta"><span>비트·이더 대비</span><b class="${clsSign(item.asset_vs_majors_pct)}">${signedPct(item.asset_vs_majors_pct)}</b><span>최근 고점에서 내려온 폭</span><b>${pct(item.pullback_pct)}</b><span>매수·매도 호가 균형</span><b>${num(item.orderbook_imbalance,3)}</b><span>현재 보유</span><b>${money(p.value_krw)}</b></div>
  </article>`;
};

diagnosticRows=function(obj){
  return Object.entries(obj||{}).map(([key,value])=>{
    const labels={btc_return_pct:'비트코인 흐름',eth_return_pct:'이더리움 흐름',eth_vs_btc_pct:'이더리움이 비트보다 강한 정도',asset_vs_majors_pct:'이 코인이 비트·이더보다 강한 정도',alt_breadth:'알트코인 전체 분위기',context_strength:'비슷한 코인들의 분위기',derivatives_risk_on:'선물시장 안정 정도',news_modifier:'뉴스 영향',asset_return_pct:'이 코인 최근 흐름',pullback_pct:'최근 고점에서 내려온 폭',fib_retrace_pct:'가격 조정 위치',orderbook_imbalance:'매수·매도 호가 균형',volatility_pct:'가격 흔들림'};
    let formatted=key.includes('pct')?pct(value):key==='orderbook_imbalance'?num(value,3):key==='news_modifier'?num(value,1):`${easyScoreMeaning(value)} · ${easyScoreValue(value)}`;
    return `<div class="diagnostic-row"><span>${labels[key]||esc(key)}</span><b>${formatted}</b></div>`;
  }).join('');
};

renderSelectedAsset=function(){
  const item=ui.snapshot?.assets?.[ui.selectedMarket];
  if(!item){$('assetDetailHeader').innerHTML='<div class="empty-state">코인을 선택하세요.</div>';return}
  const p=item.position||{},d=item.diagnostics||{},decision=decisionCopy(item),checks=d.checks||{};
  $('assetDetailHeader').innerHTML=`<div class="asset-detail-name"><h3>${esc(item.symbol||ui.selectedMarket)}</h3><p>${esc(ui.selectedMarket)}</p></div><div class="asset-detail-price"><strong>${num(item.price,8)}</strong><span class="${clsSign(item.asset_return_pct)}">${signedPct(item.asset_return_pct)} · 현재 보유 ${money(p.value_krw)}</span></div>`;
  $('assetDecision').className=`decision-block ${decision[2]}`;$('assetDecision').innerHTML=`<strong>${esc(decision[0])}</strong><p>${esc(decision[1])}</p>`;
  $('assetScoreGrid').innerHTML=`${easyScoreBlock('전체 시장 분위기',item.regime_score,'65점 이상이면 1차 기준 통과')}${easyScoreBlock('지금 매수 타이밍',item.entry_score,'68점 이상이면 1차 기준 통과')}${easyScoreBlock('비슷한 코인 흐름',item.context_score,'관련 섹터·코인의 강도')}`;
  $('assetDiagnostics').innerHTML=`<details class="technical-details"><summary>왜 이렇게 판단했는지 자세히 보기</summary><div class="diagnostic-detail-body"><div class="diagnostic-group"><h4>전체 시장을 볼 때</h4>${diagnosticRows(d.regime||{})}<div class="diagnostic-row"><span>시장 기준 통과 여부</span><b class="${checks.regime_pass?'diagnostic-pass':'diagnostic-fail'}">${checks.regime_pass?'통과':'아직 부족'} · 기준 ${easyScoreValue(d.thresholds?.regime)}</b></div></div><div class="diagnostic-group"><h4>지금 가격을 볼 때</h4>${diagnosticRows(d.entry||{})}<div class="diagnostic-row"><span>매수 타이밍 기준 통과 여부</span><b class="${checks.entry_pass?'diagnostic-pass':'diagnostic-fail'}">${checks.entry_pass?'통과':'아직 부족'} · 기준 ${easyScoreValue(d.thresholds?.entry)}</b></div></div></div></details>`;
  const c=item.context_details||{},markets=c.markets||[];
  $('assetContext').classList.remove('empty-state');
  $('assetContext').innerHTML=`<div class="context-score easy-context"><span>비슷한 코인들의 현재 분위기</span><strong>${esc(easyScoreMeaning(item.context_score))}</strong><small>${easyScoreValue(item.context_score)}</small></div><div class="context-markets">${markets.length?markets.map(m=>`<span class="context-chip">${esc(m.replace('KRW-',''))}</span>`).join(''):'<span class="context-chip">알트코인 전체 흐름으로 판단 중</span>'}</div>${c.median_return_pct!=null?`<div class="list-item">비슷한 코인들의 가운데 수익률 <b>${signedPct(c.median_return_pct)}</b><small>오른 코인 비율 ${pct((c.positive_ratio||0)*100,0)}</small></div>`:''}`;
};

renderPerformance=function(){
  const a=ui.analytics||{};
  const pf=a.profit_factor_infinite?'손실 없이 수익만 있음':a.profit_factor==null?'-':`${num(a.profit_factor,2)}배`;
  const metrics=[
    ['전체 손익',money(a.total_pnl_krw),`처음보다 ${signedPct(a.return_pct)}`,clsSign(a.total_pnl_krw)],
    ['확정 손익',money(a.realized_pnl_krw),`아직 확정 안 된 손익 ${money(a.unrealized_pnl_krw)}`,clsSign(a.realized_pnl_krw)],
    ['이긴 비율',pct(a.win_rate_pct,1),`끝난 거래 ${a.closed_trades??0}회`,''],
    ['번 돈 ÷ 잃은 돈',pf,`기록상 최대 하락 ${pct(a.max_drawdown_pct)}`,''],
  ];
  $('performanceGrid').innerHTML=metrics.map(([label,value,sub,tone])=>`<article class="metric-card"><span>${label}</span><strong class="${tone}">${value}</strong><small>${sub}</small></article>`).join('');
  const markets=a.per_market||{};
  $('marketPerformance').innerHTML=Object.keys(markets).length?Object.entries(markets).map(([market,s])=>`<div class="list-item"><div class="list-item-head"><b>${esc(market.replace('KRW-',''))}</b><span class="amount ${clsSign(s.realized_pnl_krw)}">${money(s.realized_pnl_krw)}</span></div><small>끝난 거래 ${s.closed_trades||0}회 · 이김 ${s.wins||0} / 짐 ${s.losses||0}</small></div>`).join(''):'<div class="list-item">아직 끝난 가상매매가 없습니다.</div>';
  const count=Number(a.closed_trades||0);let note='아직 끝난 거래가 없습니다. 지금은 프로그램이 판단 기록을 모으는 중입니다.';if(count>0&&count<10)note=`끝난 거래가 ${count}회라 아직 데이터가 적습니다. 최소 10~20회 정도 모인 뒤 기준을 바꾸는 편이 안전합니다.`;if(count>=10)note=`끝난 거래가 ${count}회 모였습니다. 코인별 손익과 하락폭을 함께 보면서 기준 조정을 검토할 수 있습니다.`;
  $('performanceNote').innerHTML=`<strong>지금 볼 점</strong><br>${esc(note)}`;
};

if(typeof eventNames==='object')Object.assign(eventNames,{execution_risk_blocked:'가격 조건 때문에 가상 매수 보류',paper_buy_blocked:'가상 매수 보류',asset_loop_error:'코인 분석 오류',engine_error:'프로그램 오류',runtime_config_updated:'매매 기준 변경',asset_added:'감시 코인 추가',asset_removed:'감시 코인 제거',telegram_config_updated:'텔레그램 설정 변경',paper_portfolio_restored:'가상 계좌 기록 복원',manual_pause:'새 매수 잠시 멈춤',manual_resume:'새 매수 다시 시작',manual_kill_switch:'긴급 정지',manual_kill_switch_reset:'긴급 정지 해제'});

async function loadLocalPhoneCode(){
  if(!isLoopback())return null;
  try{localPhoneCode=await api('/api/local/phone-code');return localPhoneCode}catch{return null}
}
function phoneCodeCard(){
  if(!isLoopback())return `<div class="access-card phone-code-card"><div class="access-card-top"><h4>휴대폰 연결 코드</h4><span class="status-pill neutral">PC에서 확인</span></div><p>휴대폰에서 처음 연결할 때 한 번 필요합니다. 집 PC의 설정 화면에서 확인하세요.</p></div>`;
  const code=localPhoneCode?.code||'';
  const shown=localPhoneCodeVisible&&code?code:'••••••••••••••••';
  return `<div class="access-card phone-code-card"><div class="access-card-top"><h4>휴대폰 연결 코드</h4><span class="status-pill good">이 PC에서만 표시</span></div><p>휴대폰에서 처음 접속할 때 입력하는 비밀번호 같은 코드입니다.</p><div class="access-url"><code id="phoneCodeValue">${esc(shown)}</code><button id="togglePhoneCode" class="copy-button">${localPhoneCodeVisible?'숨기기':'보기'}</button>${code?'<button id="copyPhoneCode" class="copy-button">복사</button>':''}</div><small class="plain-help">같은 코드는 PC 폴더의 b3_trader/data/dashboard-token.txt 에도 저장됩니다.</small></div>`;
}
const originalRenderNetwork=renderNetwork;
renderNetwork=function(){
  originalRenderNetwork();
  const body=$('phoneAccessBody');
  if(!body)return;
  body.insertAdjacentHTML('afterbegin',phoneCodeCard());
  const toggle=$('togglePhoneCode');if(toggle)toggle.onclick=()=>{localPhoneCodeVisible=!localPhoneCodeVisible;renderNetwork()};
  const copy=$('copyPhoneCode');if(copy&&localPhoneCode?.code)copy.onclick=()=>copyText(localPhoneCode.code,copy);
  if(isLoopback()&&!localPhoneCode)loadLocalPhoneCode().then(()=>{if(ui.view==='settings')renderNetwork()});
};

const originalOpenConnectionSettings=openConnectionSettings;
openConnectionSettings=function(message=''){
  const easyMessage=message.replaceAll('Dashboard token','휴대폰 연결 코드').replace('로컬 PC 콘솔의 토큰','집 PC 설정 화면의 연결 코드');
  originalOpenConnectionSettings(easyMessage);
};

applyPlainStaticCopy();
if(isLoopback())loadLocalPhoneCode().then(()=>{if(ui.view==='settings'&&ui.network)renderNetwork()});
