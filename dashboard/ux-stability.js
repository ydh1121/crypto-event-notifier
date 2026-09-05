// Interaction stability and convenience layer.
// Loaded last so it can preserve state around the legacy 5s render loop without
// moving trading logic out of the existing engine modules.

const UX_DETAIL_KEY='cryptoTraderTechnicalDetailOpen';

function uxDetailStorageKey(market){
  return `${UX_DETAIL_KEY}:${market||'none'}`;
}

function rememberTechnicalDetail(details,market){
  if(!details)return;
  localStorage.setItem(uxDetailStorageKey(market),details.open?'1':'0');
}

function restoreTechnicalDetail(){
  const details=document.querySelector('#assetDiagnostics details.technical-details');
  if(!details)return;
  const key=uxDetailStorageKey(ui.selectedMarket);
  details.open=localStorage.getItem(key)==='1';
  details.ontoggle=()=>rememberTechnicalDetail(details,ui.selectedMarket);
}

if(typeof renderSelectedAsset==='function'){
  const renderSelectedAssetBeforeUx=renderSelectedAsset;
  renderSelectedAsset=function(){
    const current=document.querySelector('#assetDiagnostics details.technical-details');
    if(current)rememberTechnicalDetail(current,ui.selectedMarket);
    renderSelectedAssetBeforeUx();
    restoreTechnicalDetail();
    const summary=document.querySelector('#assetDiagnostics details.technical-details > summary');
    if(summary)summary.textContent='판단 근거 자세히 보기';
  };
}

// iOS/browser-origin convenience: a one-time link may carry the phone code in
// the URL fragment. Fragments are not sent in HTTP requests. After importing it
// the fragment is immediately removed from the address bar.
(function importPhoneCodeFromFragment(){
  if(isLoopback())return;
  const match=String(location.hash||'').match(/^#(?:connect|code)=([^&]+)$/i);
  if(!match)return;
  try{
    const code=decodeURIComponent(match[1]).trim();
    if(!code)return;
    ui.token=code;
    localStorage.setItem('cryptoTraderToken',code);
    history.replaceState(null,'',location.pathname+location.search);
  }catch{}
})();

function ethBtcCopy(change){
  const v=Number(change);
  if(!Number.isFinite(v))return ['확인 중','ETH와 BTC의 상대 흐름을 계산 중입니다.'];
  if(v>=2)return ['ETH가 더 강함',`24시간 기준 ETH가 BTC보다 ${Math.abs(v).toFixed(2)}% 더 강합니다.`];
  if(v<=-2)return ['BTC가 더 강함',`24시간 기준 BTC가 ETH보다 ${Math.abs(v).toFixed(2)}% 더 강합니다.`];
  return ['비슷한 흐름',`24시간 상대 차이는 ${Math.abs(v).toFixed(2)}%입니다.`];
}

if(typeof renderMarketPulse==='function'){
  const renderMarketPulseBeforeUx=renderMarketPulse;
  renderMarketPulse=function(){
    renderMarketPulseBeforeUx();
    const box=document.getElementById('marketPulse');
    const d=ui.snapshot?.market?.details||{};
    if(!box||d.eth_btc_ratio==null)return;
    let card=document.getElementById('ethBtcPulse');
    if(!card){
      card=document.createElement('div');
      card.id='ethBtcPulse';
      card.className='pulse-item easy-pulse eth-btc-pulse';
      box.appendChild(card);
    }
    const [label,help]=ethBtcCopy(d.eth_btc_24h_change_pct);
    card.innerHTML=`<span>ETH / BTC</span><strong>${esc(label)}</strong><small>${num(d.eth_btc_ratio,8)} · ${esc(help)}</small>`;
  };
}

// ETH/BTC is a market-strength reference, not a KRW coin position. Treat a
// ticker-box request as a shortcut to the built-in reference instead of showing
// an unsupported-market error.
const addAssetFormUx=document.getElementById('addAssetForm');
if(addAssetFormUx&&typeof addAssetFormUx.onsubmit==='function'){
  const addAssetBeforeUx=addAssetFormUx.onsubmit;
  addAssetFormUx.onsubmit=async function(event){
    const raw=String(document.getElementById('tickerInput')?.value||'').trim().toUpperCase().replace(/\s+/g,'');
    if(['ETH/BTC','ETH-BTC','BTC/ETH','BTC-ETH'].includes(raw)){
      event.preventDefault();
      const input=document.getElementById('tickerInput');if(input)input.value='';
      if(typeof switchView==='function')switchView('overview');
      showUxToast('ETH/BTC는 자동으로 감시 중입니다. 홈의 시장 요약에서 볼 수 있습니다.');
      return false;
    }
    return addAssetBeforeUx.call(this,event);
  };
}

// Keep cards geometrically stable whether a holding was entered or not.
if(typeof assetCard==='function'){
  assetCard=function(market,item){
    const holding=typeof holdingFor==='function'?holdingFor(market):null;
    const selected=market===ui.selectedMarket;
    const decision=decisionCopy(item);
    const hasHolding=!!(holding&&Number(holding.volume)>0);
    const pnl=hasHolding?Number(holding.unrealized_pnl_krw||0):0;
    const pnlPct=hasHolding?Number(holding.unrealized_pnl_pct||0):0;
    const holdingHtml=hasHolding
      ?`<div class="holding-strip"><span>내 평단 <b>${num(holding.avg_price,8)}원</b></span><span>현재 손익 <b class="${clsSign(pnl)}">${money(pnl)} · ${signedPct(pnlPct)}</b></span></div>`
      :'<div class="holding-strip is-empty"><span>내 보유 정보 <b>입력 안 함</b></span><span class="holding-empty-note">코인 화면에서 입력</span></div>';
    return `<article class="asset-card simple-asset-card ${selected?'is-selected':''}" data-market="${esc(market)}">
      <div class="asset-card-top"><div class="asset-title"><h3>${esc(item.symbol||market.replace('KRW-',''))}</h3><span class="market-code">현재가 ${num(item.price,8)}원</span></div><div class="asset-actions"><span class="asset-action ${esc(item.action||'')}">${esc(actionLabel(item.action))}</span><button class="icon-button remove-asset" data-market="${esc(market)}" title="감시 제거" aria-label="감시 제거">×</button></div></div>
      <div class="simple-decision ${actionTone(item.action)}"><strong>${esc(decision[0])}</strong><small>${esc(decision[1])}</small></div>
      ${holdingHtml}
      <div class="simple-score-row"><span>시장 <b>${esc(easyScoreMeaning(item.regime_score))}</b> ${easyScoreValue(item.regime_score)}</span><span>타이밍 <b>${esc(easyScoreMeaning(item.entry_score))}</b> ${easyScoreValue(item.entry_score)}</span></div>
    </article>`;
  };
}

function showUxToast(message){
  let toast=document.getElementById('uxToast');
  if(!toast){
    toast=document.createElement('div');
    toast.id='uxToast';
    toast.className='ux-toast';
    toast.setAttribute('role','status');
    toast.setAttribute('aria-live','polite');
    document.body.appendChild(toast);
  }
  toast.textContent=String(message||'');
  toast.classList.add('is-visible');
  clearTimeout(showUxToast.timer);
  showUxToast.timer=setTimeout(()=>toast.classList.remove('is-visible'),2600);
}

function polishStaticCopy(){
  const telegramPanel=document.getElementById('telegramStatePill')?.closest('.panel');
  const copy=telegramPanel?.querySelector('.panel-copy');
  if(copy)copy.textContent='매수하기 좋은 조건이 처음 충족될 때만 알려드립니다. 상태 변화, 오류, 백업 같은 운영 알림은 보내지 않습니다.';
  const input=document.getElementById('tickerInput');
  if(input)input.placeholder='코인명 입력 · 예: XRP, SEI, SOL';
  const addHead=document.querySelector('[data-view-panel="overview"] .section-head');
  const p=addHead?.querySelector('p');if(p)p.textContent='보고 싶은 코인을 추가하면 같은 기준으로 계속 감시합니다. ETH/BTC는 시장 기준으로 자동 계산됩니다.';
  const stableHint=document.querySelector('.phone-panel .panel-copy');
  if(stableHint&&ui.network?.cloudflare?.mode==='named_tunnel')stableHint.textContent='고정 HTTPS 주소를 사용 중입니다. 서버를 다시 켜도 주소와 휴대폰 로그인이 유지됩니다.';
}

function addOneTapPhoneLink(){
  if(!isLoopback()||!localPhoneCode)return;
  const panel=document.querySelector('.phone-panel');
  const cf=ui.network?.cloudflare||{};
  if(!panel||!cf.active||!cf.url)return;
  let card=document.getElementById('oneTapPhoneLink');
  if(!card){
    card=document.createElement('div');
    card.id='oneTapPhoneLink';
    card.className='access-card one-tap-phone-link';
    panel.appendChild(card);
  }
  const link=`${String(cf.url).replace(/\/$/,'')}/#connect=${encodeURIComponent(localPhoneCode)}`;
  card.innerHTML=`<div class="access-card-top"><h4>휴대폰용 바로가기</h4><span class="status-pill good">PC에서만 생성</span></div><p>${cf.mode==='named_tunnel'?'이 링크를 휴대폰에서 한 번 열면 이후에는 같은 주소로 바로 접속합니다.':'현재 임시 주소와 연결 코드를 한 링크에 넣습니다. 서버를 다시 켜 주소가 바뀌면 PC에서 새 링크만 다시 복사하면 됩니다.'}</p><button id="copyOneTapPhoneLink" class="button secondary">휴대폰용 링크 복사</button><p class="plain-help">연결 코드는 주소의 # 뒤에만 들어가며 서버 요청에는 포함되지 않습니다. 링크를 다른 사람에게 보내지 마세요.</p>`;
  card.querySelector('#copyOneTapPhoneLink').onclick=()=>copyText(link,card.querySelector('#copyOneTapPhoneLink'));
}

if(typeof renderVpnFreePhoneAccess==='function'){
  const renderPhoneBeforeUx=renderVpnFreePhoneAccess;
  renderVpnFreePhoneAccess=function(){
    renderPhoneBeforeUx();
    const cf=ui.network?.cloudflare||{};
    const body=document.getElementById('phoneAccessBody');
    if(!body)return;
    const first=body.querySelector('.access-card');
    if(first&&cf.active){
      const p=first.querySelector('p');
      if(p)p.textContent=cf.mode==='named_tunnel'
        ?'고정 HTTPS 주소입니다. 서버를 다시 켜도 같은 주소를 사용합니다.'
        :'현재는 임시 HTTPS 주소입니다. 고정 주소 설정을 완료하면 재시작 때 주소를 다시 찾을 필요가 없습니다.';
    }
    addOneTapPhoneLink();
  };
}

polishStaticCopy();
restoreTechnicalDetail();
setTimeout(()=>{polishStaticCopy();addOneTapPhoneLink()},700);

/* --------------------------------------------------------------------------
   Dashboard UX v2 — compact navigation, price-first asset presentation,
   beginner-friendly settings status. UI only: no trading logic changes.
   -------------------------------------------------------------------------- */

const V2_NAV=[
  ['overview','홈','<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h13V9.5"/><path d="M9.5 21v-7h5v7"/>'],
  ['assets','코인','<circle cx="12" cy="12" r="8.5"/><path d="M9 9.2h4.1a2.1 2.1 0 0 1 0 4.2H9z"/><path d="M9 13.4h4.8a2.2 2.2 0 0 1 0 4.4H9z"/><path d="M11 7v2.2M14 7v2.2M11 17.8V20M14 17.8V20"/>'],
  ['performance','결과','<path d="M4 18V10"/><path d="M10 18V6"/><path d="M16 18v-5"/><path d="M3 21h18"/><path d="m15.5 7.5 2-2 2 2"/>'],
  ['activity','기록','<path d="M6 4h12a2 2 0 0 1 2 2v14H4V6a2 2 0 0 1 2-2Z"/><path d="M8 9h8M8 13h8M8 17h5"/>'],
  ['settings','설정','<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.87.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.64 15 1.7 1.7 0 0 0 3.08 14H3v-4h.08A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.64 1.7 1.7 0 0 0 10.03 3.08V3h4v.08A1.7 1.7 0 0 0 15 4.64a1.7 1.7 0 0 0 1.87-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.36 9 1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z"/>'],
];

function installV2Navigation(){
  document.querySelectorAll('.view-tab').forEach(tab=>{
    const row=V2_NAV.find(([view])=>view===tab.dataset.view);
    if(!row)return;
    tab.innerHTML=`<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">${row[2]}</svg><span>${row[1]}</span>`;
    tab.setAttribute('aria-label',row[1]);
  });
}

function enhanceV2AssetHero(){
  const item=ui.snapshot?.assets?.[ui.selectedMarket];
  const target=document.getElementById('assetDetailHeader');
  if(!item||!target)return;
  const holding=typeof holdingFor==='function'?holdingFor(ui.selectedMarket):null;
  const hasHolding=!!(holding&&Number(holding.volume)>0);
  const price=Number(item.price||0);
  const pnl=hasHolding?Number(holding.unrealized_pnl_krw||0):0;
  const pnlPct=hasHolding?Number(holding.unrealized_pnl_pct||0):0;
  const tone=actionTone(item.action);
  target.className='asset-detail-header v2-asset-hero';
  target.innerHTML=`
    <div class="v2-asset-top">
      <span class="v2-asset-symbol">${esc(item.symbol||ui.selectedMarket.replace('KRW-',''))}</span>
      <span class="v2-decision-badge ${tone}">${esc(actionLabel(item.action))}</span>
    </div>
    <div class="v2-current-price">
      <span>현재 가격</span>
      <strong>${num(price,8)}원</strong>
      <small class="${clsSign(item.asset_return_pct)}">24시간 ${signedPct(item.asset_return_pct)}</small>
    </div>
    <div class="v2-holding-line">
      <div class="v2-holding-chip"><span>내 평단</span><b>${hasHolding?`${num(holding.avg_price,8)}원`:'입력 안 함'}</b></div>
      <div class="v2-holding-chip"><span>현재 손익</span><b class="${hasHolding?clsSign(pnl):''}">${hasHolding?`${money(pnl)} · ${signedPct(pnlPct)}`:'-'}</b></div>
    </div>`;
}

if(typeof renderSelectedAsset==='function'){
  const renderSelectedAssetBeforeV2=renderSelectedAsset;
  renderSelectedAsset=function(){
    renderSelectedAssetBeforeV2();
    enhanceV2AssetHero();
  };
}

assetCard=function(market,item){
  const holding=typeof holdingFor==='function'?holdingFor(market):null;
  const selected=market===ui.selectedMarket;
  const decision=decisionCopy(item);
  const hasHolding=!!(holding&&Number(holding.volume)>0);
  const pnl=hasHolding?Number(holding.unrealized_pnl_krw||0):0;
  const pnlPct=hasHolding?Number(holding.unrealized_pnl_pct||0):0;
  const holdingHtml=hasHolding
    ?`<div class="holding-strip"><span>내 평단 <b>${num(holding.avg_price,8)}원</b></span><span>현재 손익 <b class="${clsSign(pnl)}">${money(pnl)} · ${signedPct(pnlPct)}</b></span></div>`
    :'<div class="holding-strip is-empty"><span>내 보유 정보 <b>입력 안 함</b></span><span class="holding-empty-note">코인 화면에서 입력</span></div>';
  return `<article class="asset-card simple-asset-card ${selected?'is-selected':''}" data-market="${esc(market)}">
    <div class="asset-card-top">
      <div class="asset-title"><h3>${esc(item.symbol||market.replace('KRW-',''))}</h3></div>
      <div class="asset-actions"><span class="asset-action ${esc(item.action||'')}">${esc(actionLabel(item.action))}</span><button class="icon-button remove-asset" data-market="${esc(market)}" title="감시 제거" aria-label="감시 제거">×</button></div>
    </div>
    <div class="v2-card-price"><div><span>현재 가격</span><strong>${num(item.price,8)}원</strong></div><b class="v2-card-change ${clsSign(item.asset_return_pct)}">${signedPct(item.asset_return_pct)}</b></div>
    <div class="simple-decision ${actionTone(item.action)}"><strong>${esc(decision[0])}</strong><small>${esc(decision[1])}</small></div>
    ${holdingHtml}
    <div class="simple-score-row"><span>시장 <b>${esc(easyScoreMeaning(item.regime_score))}</b></span><span>타이밍 <b>${esc(easyScoreMeaning(item.entry_score))}</b></span></div>
  </article>`;
};

function friendlySyncStatus(value){
  const raw=String(value||'').toLowerCase();
  if(['up_to_date','published','success','done'].includes(raw))return '최신 상태';
  if(raw==='blocked_dirty_worktree')return '내 변경사항 보존 중';
  if(raw==='idle'||!raw)return '대기';
  if(raw.includes('error')||raw.includes('fail'))return '확인 필요';
  if(raw.includes('sync'))return '동기화 중';
  return String(value||'대기').replaceAll('_',' ');
}

function friendlyBackupStatus(value){
  const raw=String(value||'').toLowerCase();
  if(['success','done','completed'].includes(raw))return '백업 완료';
  if(raw==='idle'||!raw)return '대기';
  if(raw.includes('error')||raw.includes('fail'))return '확인 필요';
  if(raw.includes('run')||raw.includes('progress'))return '백업 중';
  return String(value||'대기').replaceAll('_',' ');
}

if(typeof renderSettingsStatus==='function'){
  const renderSettingsBeforeV2=renderSettingsStatus;
  renderSettingsStatus=function(){
    renderSettingsBeforeV2();
    const statusBox=document.getElementById('backupSyncStatus');
    const s=ui.snapshot||{},sync=s.sync||{},backup=s.backup||{};
    if(statusBox){
      statusBox.innerHTML=`
        <div class="list-item"><div class="list-item-head"><b>코드 동기화</b><span class="v2-status-text">${esc(friendlySyncStatus(sync.status))}</span></div><small>설정과 대시보드 변경사항을 안전하게 보존합니다.</small></div>
        <div class="list-item"><div class="list-item-head"><b>Google Drive 백업</b><span class="v2-status-text">${esc(friendlyBackupStatus(backup.status))}</span></div><small>${backup.drive?esc(backup.drive):'연결 전에는 이 PC에만 백업합니다.'}</small></div>`;
    }
    const system=document.getElementById('systemDetail');
    if(system){
      const up=Math.floor((s.uptime_seconds||0)/60);
      system.innerHTML=`<div class="list-item"><div class="list-item-head"><b>운영 방식</b><span>가상매매</span></div><small>실제 주문은 하지 않습니다.</small></div><div class="list-item"><div class="list-item-head"><b>실행 시간</b><span>${up}분</span></div></div>${s.last_error?`<div class="list-item"><div class="list-item-head"><b>최근 문제</b><span>확인 필요</span></div><small>${esc(s.last_error.message||'기록 화면에서 확인하세요.')}</small></div>`:''}`;
    }
  };
}

function simplifyRemotePhonePanel(){
  if(isLoopback())return;
  const cf=ui.network?.cloudflare||{};
  const body=document.getElementById('phoneAccessBody');
  if(!body||!cf.active)return;
  body.innerHTML=`<div class="access-card"><div class="access-card-top"><h4>외부 연결</h4><span class="status-pill good">정상</span></div><p>현재 휴대폰에서 안전한 HTTPS 연결로 접속 중입니다.</p></div>`;
  const warning=document.querySelector('.phone-warning');if(warning)warning.style.display='none';
}

if(typeof renderVpnFreePhoneAccess==='function'){
  const renderPhoneBeforeV2=renderVpnFreePhoneAccess;
  renderVpnFreePhoneAccess=function(){
    renderPhoneBeforeV2();
    simplifyRemotePhonePanel();
  };
}

function v2PolishStaticCopy(){
  const brand=document.querySelector('.brand-row h1');if(brand)brand.textContent='코인 상태판';
  const phoneTitle=document.querySelector('.phone-panel h3');if(phoneTitle)phoneTitle.textContent='휴대폰 연결';
  const backupPanel=document.getElementById('backupSyncStatus')?.closest('.panel');
  const backupTitle=backupPanel?.querySelector('h3');if(backupTitle)backupTitle.textContent='백업과 동기화';
  const systemTitle=document.getElementById('systemDetail')?.closest('.panel')?.querySelector('h3');if(systemTitle)systemTitle.textContent='프로그램 상태';
  const telegramTitle=document.getElementById('telegramStatePill')?.closest('.panel')?.querySelector('h3');if(telegramTitle)telegramTitle.textContent='매수 알림';
}

installV2Navigation();
v2PolishStaticCopy();
enhanceV2AssetHero();
simplifyRemotePhonePanel();
setTimeout(()=>{installV2Navigation();v2PolishStaticCopy();enhanceV2AssetHero();simplifyRemotePhonePanel()},900);
