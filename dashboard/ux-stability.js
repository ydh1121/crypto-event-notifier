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
  };
}

polishStaticCopy();
restoreTechnicalDetail();
setTimeout(polishStaticCopy,700);
