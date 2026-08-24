const personalToolsState={market:'',holding:null,rows:[]};

function isSafePrivateHost(host){
  if(!host)return true;
  if(host==='localhost'||host==='127.0.0.1'||host==='::1')return true;
  const parts=host.split('.').map(Number);
  if(parts.length===4&&parts.every(Number.isFinite)){
    if(parts[0]===10||parts[0]===127)return true;
    if(parts[0]===192&&parts[1]===168)return true;
    if(parts[0]===172&&parts[1]>=16&&parts[1]<=31)return true;
    if(parts[0]===100&&parts[1]>=64&&parts[1]<=127)return true;
    return false;
  }
  return host.endsWith('.ts.net');
}

function showPublicAccessWarning(){
  const host=window.location.hostname;
  if(window.location.protocol!=='http:'||isSafePrivateHost(host)||document.getElementById('publicAccessWarning'))return;
  const banner=document.createElement('div');
  banner.id='publicAccessWarning';
  banner.className='public-access-warning';
  banner.textContent='공인 IP의 HTTP 주소로 접속 중입니다. 휴대폰 연결 코드와 화면 내용이 암호화되지 않을 수 있습니다. 이 주소는 사용하지 말고 HTTPS Cloudflare 연결 주소를 사용하세요.';
  document.body.prepend(banner);
}

function ensurePersonalTools(){
  if(document.getElementById('personalTools'))return;
  const workspace=document.querySelector('[data-view-panel="assets"] .asset-workspace');
  if(!workspace)return;
  workspace.insertAdjacentHTML('afterend',`
    <section id="personalTools" class="personal-tools">
      <article class="panel">
        <div class="tool-head"><div><p class="panel-kicker">내 실제 보유분</p><h3>보유 수량과 평단</h3><p>거래소 계좌와 자동으로 연결하지 않습니다. 현재 가지고 있는 수량과 평균 매수가를 직접 적어두는 메모입니다.</p></div></div>
        <form id="holdingForm" class="holding-form">
          <label>보유 수량<input id="holdingVolume" type="number" min="0" step="any" inputmode="decimal" placeholder="예: 125000"></label>
          <label>평균 매수가<input id="holdingAvg" type="number" min="0" step="any" inputmode="decimal" placeholder="예: 0.777"></label>
        </form>
        <div id="holdingSummary" class="holding-summary"></div>
        <div class="tool-actions"><button id="saveHolding" class="button">보유 정보 저장</button><button id="clearHolding" class="button secondary">초기화</button></div>
        <p class="form-note">이 정보는 로컬 SQLite에 저장되고 DB 백업에 포함됩니다. GitHub에는 올라가지 않습니다.</p>
      </article>
      <article class="panel">
        <div class="tool-head"><div><p class="panel-kicker">평단 계산</p><h3>물타기 계산기</h3><p>추가 매수할 가격과 금액을 적으면 회차별 새 평단을 계산합니다. 코인마다 최대 20회까지 저장할 수 있습니다.</p></div></div>
        <div id="entryWeightGuide" class="entry-guide"></div>
        <div id="averagingRows" class="avg-list"></div>
        <div class="tool-actions"><button id="addAveragingRow" class="button secondary">매수 회차 추가</button><button id="saveAveragingPlan" class="button">계획 저장</button><button id="clearAveragingPlan" class="button secondary">계획 비우기</button></div>
        <div id="averagingSummary" class="avg-summary"></div>
      </article>
    </section>`);
  bindPersonalTools();
}

function holdingInputs(){
  return {
    volume:Math.max(0,Number(document.getElementById('holdingVolume')?.value||0)),
    avg:Math.max(0,Number(document.getElementById('holdingAvg')?.value||0)),
  };
}

function currentAssetPrice(){return Number(ui.snapshot?.assets?.[ui.selectedMarket]?.price||0)}
function currentSuggestedEntry(){return ui.snapshot?.assets?.[ui.selectedMarket]?.suggested_entry||{}}

function renderHoldingSummary(){
  const box=document.getElementById('holdingSummary');if(!box)return;
  const {volume,avg}=holdingInputs(),price=currentAssetPrice();
  const cost=volume*avg,value=volume*price,pnl=value-cost,pnlPct=cost>0?pnl/cost*100:0;
  box.innerHTML=`
    <div class="mini-stat"><span>매수 원금</span><strong>${money(cost)}</strong></div>
    <div class="mini-stat"><span>현재 평가금액</span><strong>${money(value)}</strong></div>
    <div class="mini-stat"><span>현재 손익</span><strong class="${clsSign(pnl)}">${money(pnl)}</strong></div>
    <div class="mini-stat"><span>수익률</span><strong class="${clsSign(pnlPct)}">${signedPct(pnlPct)}</strong></div>`;
}

function normalizeRows(rows){
  const result=(rows||[]).slice(0,20).map(row=>({price:Number(row.price||0),amount_krw:Number(row.amount_krw||0)}));
  return result.length?result:[{price:0,amount_krw:0}];
}

function calculateAveragingLocal(){
  const {volume,avg}=holdingInputs();let totalVolume=volume,totalCost=volume*avg;
  const rows=[];
  document.querySelectorAll('.avg-row').forEach((row,index)=>{
    const price=Math.max(0,Number(row.querySelector('[data-avg-price]')?.value||0));
    const amount=Math.max(0,Number(row.querySelector('[data-avg-amount]')?.value||0));
    let afterAvg=totalVolume>0?totalCost/totalVolume:0;
    if(price>0&&amount>0){totalVolume+=amount/price;totalCost+=amount;afterAvg=totalCost/totalVolume}
    const after=row.querySelector('.avg-after');if(after)after.textContent=price>0&&amount>0?`${index+1}회 매수 후 예상 평단 ${num(afterAvg,12)}원`:'가격과 금액을 입력하세요.';
    rows.push({price,amount_krw:amount});
  });
  const finalAvg=totalVolume>0?totalCost/totalVolume:0;
  const current=currentAssetPrice();const value=totalVolume*current,pnl=value-totalCost;
  const box=document.getElementById('averagingSummary');
  if(box)box.innerHTML=`
    <div class="mini-stat"><span>모두 매수 후 평단</span><strong>${num(finalAvg,12)}원</strong></div>
    <div class="mini-stat"><span>총 들어간 금액</span><strong>${money(totalCost)}</strong></div>
    <div class="mini-stat"><span>총 보유 수량</span><strong>${num(totalVolume,8)}</strong></div>
    <div class="mini-stat"><span>현재가 기준 예상 손익</span><strong class="${clsSign(pnl)}">${money(pnl)}</strong></div>`;
  personalToolsState.rows=rows;
  return rows;
}

function renderAveragingRows(rows){
  const list=document.getElementById('averagingRows');if(!list)return;
  const data=normalizeRows(rows);
  list.innerHTML=data.map((row,index)=>`<div class="avg-row">
    <div class="avg-round">${index+1}회</div>
    <label>매수가<input data-avg-price type="number" min="0" step="any" inputmode="decimal" value="${row.price||''}" placeholder="가격"></label>
    <label>매수금액<input data-avg-amount type="number" min="0" step="1000" inputmode="numeric" value="${row.amount_krw||''}" placeholder="원"></label>
    <button type="button" class="avg-remove" aria-label="회차 삭제">×</button>
    <div class="avg-after"></div>
  </div>`).join('');
  list.querySelectorAll('input').forEach(input=>input.addEventListener('input',calculateAveragingLocal));
  list.querySelectorAll('.avg-remove').forEach(btn=>btn.onclick=()=>{btn.closest('.avg-row')?.remove();if(!list.children.length)renderAveragingRows([]);calculateAveragingLocal()});
  calculateAveragingLocal();
}

function renderEntryGuide(){
  const box=document.getElementById('entryWeightGuide');if(!box)return;
  const item=ui.snapshot?.assets?.[ui.selectedMarket];const s=currentSuggestedEntry();
  if(!item){box.innerHTML='<strong>진입 비중 계산 중</strong><p>시장 데이터를 불러오면 표시됩니다.</p>';return}
  const amount=Number(s.amount_krw||0),accountPct=Number(s.account_pct||0),limitPct=Number(s.asset_limit_pct||0);
  if(item.action==='BUY_CANDIDATE'&&amount>0){
    box.innerHTML=`<strong>현재 추천 진입: 전체 가상계좌의 약 ${accountPct.toFixed(1)}%</strong><p>약 ${money(amount)}를 한 번에 진입하는 수준입니다. 이 코인에 정한 최대 보유한도의 약 ${limitPct.toFixed(1)}%입니다.</p>`;
  }else{
    box.innerHTML=`<strong>지금은 새 진입 비중을 안내하지 않습니다.</strong><p>${esc(actionLabel(item.action))} 상태입니다. 매수 후보가 되면 텔레그램과 이 화면에 권장 금액과 비중을 함께 표시합니다.</p>`;
  }
}

async function loadPersonalTools(){
  ensurePersonalTools();
  const market=ui.selectedMarket;if(!market)return;
  personalToolsState.market=market;
  try{
    const [holding,averaging]=await Promise.all([api(`/api/holdings/${encodeURIComponent(market)}`),api(`/api/averaging/${encodeURIComponent(market)}`)]);
    if(personalToolsState.market!==market)return;
    personalToolsState.holding=holding;
    document.getElementById('holdingVolume').value=Number(holding.volume||0)||'';
    document.getElementById('holdingAvg').value=Number(holding.avg_price||0)||'';
    renderHoldingSummary();renderAveragingRows(averaging.plan?.rows||[]);renderEntryGuide();
  }catch(err){console.warn('personal tools',err)}
}

function bindPersonalTools(){
  document.getElementById('holdingVolume')?.addEventListener('input',()=>{renderHoldingSummary();calculateAveragingLocal()});
  document.getElementById('holdingAvg')?.addEventListener('input',()=>{renderHoldingSummary();calculateAveragingLocal()});
  document.getElementById('saveHolding').onclick=async()=>{
    const {volume,avg}=holdingInputs();
    try{await api(`/api/holdings/${encodeURIComponent(ui.selectedMarket)}`,{method:'PUT',body:{volume,avg_price:avg}});await loadPersonalTools();alert('보유 수량과 평단을 저장했습니다.')}catch(err){alert(err.message)}
  };
  document.getElementById('clearHolding').onclick=async()=>{
    if(!confirm('이 코인의 보유 수량과 평단 기록을 지울까요?'))return;
    try{await api(`/api/holdings/${encodeURIComponent(ui.selectedMarket)}`,{method:'DELETE'});await loadPersonalTools()}catch(err){alert(err.message)}
  };
  document.getElementById('addAveragingRow').onclick=()=>{
    const list=document.getElementById('averagingRows');if(!list||list.children.length>=20)return;
    const rows=calculateAveragingLocal();rows.push({price:0,amount_krw:0});renderAveragingRows(rows);
  };
  document.getElementById('saveAveragingPlan').onclick=async()=>{
    const rows=calculateAveragingLocal();
    try{await api(`/api/averaging/${encodeURIComponent(ui.selectedMarket)}`,{method:'PUT',body:{rows}});alert(`${ui.selectedMarket.replace('KRW-','')} 물타기 계획을 저장했습니다.`)}catch(err){alert(err.message)}
  };
  document.getElementById('clearAveragingPlan').onclick=async()=>{
    if(!confirm('저장한 물타기 계획을 비울까요?'))return;
    try{await api(`/api/averaging/${encodeURIComponent(ui.selectedMarket)}`,{method:'DELETE'});renderAveragingRows([])}catch(err){alert(err.message)}
  };
}

function renderVpnFreePhoneAccess(){
  const n=ui.network||{},cf=n.cloudflare||{},lan=n.lan||{},ts=n.tailscale||{};
  const pill=document.getElementById('tailscalePill');
  if(pill){pill.textContent=cf.active?'HTTPS 연결됨':'외부 연결 설정';pill.className=`status-pill ${cf.active?'good':'neutral'}`}
  const body=document.getElementById('phoneAccessBody');if(!body)return;
  body.classList.remove('empty-state');
  let html='';
  if(cf.active&&cf.url){
    html+=accessCard('외부 접속 · 권장',true,cf.url,'','휴대폰에 VPN 앱을 켤 필요가 없습니다. Cloudflare가 HTTPS로 이 PC와 휴대폰을 연결합니다.');
  }else{
    html+=`<div class="access-card"><div class="access-card-top"><h4>외부 접속 · 권장</h4><span class="status-pill neutral">설정 전</span></div><p>VPN 없이 휴대폰에서 접속하려면 기존 트레이더를 종료한 뒤 보안 실행 파일을 사용합니다.</p><div class="access-url"><code>.\\start-trader-secure.bat</code><button class="copy-button" data-copy=".\\start-trader-secure.bat">복사</button></div><p>실행하면 무료 HTTPS 주소가 표시됩니다. 주소는 프로그램을 다시 켤 때 바뀔 수 있습니다.</p></div>`;
  }
  if(!cf.active&&lan.url)html+=accessCard('같은 Wi-Fi',true,lan.url,'','같은 Wi-Fi 안에서만 사용하는 내부 주소입니다.');
  if(ts.installed){
    html+=`<details class="access-optional"><summary>다른 연결 방법 보기</summary><p>Tailscale은 휴대폰 VPN 연결이 필요한 선택사항입니다. 사용하지 않아도 됩니다.</p>${ts.url?`<div class="access-url"><code>${esc(ts.url)}</code></div>`:''}</details>`;
  }
  body.innerHTML=html;
  document.querySelectorAll('[data-copy]').forEach(btn=>btn.onclick=()=>copyText(btn.dataset.copy,btn));
  const warning=document.querySelector('.phone-warning');
  if(warning)warning.textContent='공인 IP의 http://주소로 8765 포트에 직접 접속하지 않습니다. VPN을 쓰지 않을 경우 위 HTTPS Cloudflare 연결을 사용합니다.';
}

function augmentPhoneAccess(){
  const panel=document.querySelector('.phone-panel');if(!panel)return;
  const cf=ui.network?.cloudflare||{};
  let extra=document.getElementById('phoneToolsExtra');
  if(!extra){extra=document.createElement('div');extra.id='phoneToolsExtra';extra.className='phone-code-extra';panel.appendChild(extra)}
  const accessText=cf.active&&cf.url?'현재 HTTPS 외부 연결이 켜져 있습니다. 휴대폰에서는 위 주소를 사용하세요.':'현재는 VPN 없는 HTTPS 외부 연결이 꺼져 있습니다.';
  extra.innerHTML=`<div class="network-direct-note">${esc(accessText)}</div>${isLoopback()?'<div class="button-row"><button id="rotatePhoneCode" class="button secondary compact">휴대폰 연결 코드 새로 만들기</button></div>':''}`;
  const rotate=document.getElementById('rotatePhoneCode');if(rotate)rotate.onclick=async()=>{
    if(!confirm('기존 휴대폰 연결 코드를 폐기하고 새 코드로 바꿀까요? 기존 폰에서는 다시 입력해야 합니다.'))return;
    try{const result=await api('/api/local/phone-code/rotate',{method:'POST'});localPhoneCode=result.code;localPhoneCodeVisible=true;if(typeof augmentLocalPhoneCode==='function')augmentLocalPhoneCode();alert('새 휴대폰 연결 코드를 만들었습니다.')}catch(err){alert(err.message)}
  };
}

const baseSelectMarket=selectMarket;
selectMarket=function(market,openAssetView=false){baseSelectMarket(market,openAssetView);setTimeout(loadPersonalTools,0)};
const baseRenderSelectedAsset=renderSelectedAsset;
renderSelectedAsset=function(){baseRenderSelectedAsset();renderEntryGuide();renderHoldingSummary()};
renderNetwork=function(){renderVpnFreePhoneAccess();augmentPhoneAccess()};

ensurePersonalTools();showPublicAccessWarning();
setTimeout(loadPersonalTools,0);
