(()=>{
  if(window.__assetAveragingViewerLoaded)return;
  window.__assetAveragingViewerLoaded=true;

  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const n=value=>Math.max(0,Number(value||0));
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const won=value=>`${Math.round(Number(value||0)).toLocaleString('ko-KR')}원`;
  const num=(value,digits=8)=>Number(value||0).toLocaleString('ko-KR',{maximumFractionDigits:digits});
  const pct=(value,digits=2)=>`${Number(value||0)>=0?'+':''}${Number(value||0).toFixed(digits)}%`;
  const tone=value=>Number(value||0)>0?'positive':Number(value||0)<0?'negative':'';
  const price=value=>{const v=Number(value||0);if(!v)return'-';const digits=v>=1000?0:v>=100?1:v>=1?3:v>=.1?5:8;return `${v.toLocaleString('ko-KR',{maximumFractionDigits:digits})}원`};

  const plans=new Map();
  const detailCache=new Map();
  let activeMarket='';
  let detailSeq=0;
  let bound=false;

  function viewerState(){try{return state}catch{return null}}
  function currentMarket(){return $('#coinSelect')?.value||viewerState()?.coinMarket||''}
  function publicRow(market){return (viewerState()?.snapshot?.public?.leaderboard||[]).find(row=>row?.market===market)||null}
  function privateHolding(market){
    const snapshot=viewerState()?.snapshot;if(!snapshot?.private_visible)return null;
    const rows=snapshot?.private?.manual_holdings?.holdings;
    return Array.isArray(rows)?rows.find(row=>row?.market===market)||null:null;
  }
  function canViewPrivate(){const s=viewerState();return Boolean(s?.snapshot?.private_visible&&s?.snapshot?.private?.manual_holdings)}

  function planFor(market){
    if(!plans.has(market))plans.set(market,{volume:0,avg:0,rows:[{price:0,amount_krw:0}],baselineTouched:false});
    return plans.get(market);
  }

  function ensureTool(){
    const panel=$('[data-view-panel="coin"]');if(!panel)return null;
    let root=$('#assetAveragingTool',panel);if(root)return root;
    const layout=$('#assetLocalLayout',panel);if(!layout)return null;
    root=document.createElement('section');
    root.id='assetAveragingTool';
    root.className='asset-calc-tools';
    root.innerHTML=`
      <article class="asset-calc-panel">
        <div class="asset-calc-head">
          <div><p class="kicker">내 실제 보유분</p><h3>계산 시작값</h3><p>조회 권한이 있으면 선택한 코인의 실제 보유 수량과 평단을 자동으로 불러옵니다. 여기서 바꾼 값은 PC나 DB에 저장되지 않습니다.</p></div>
          <span id="assetCalcSourcePill" class="asset-calc-pill">확인 중</span>
        </div>
        <form id="assetCalcHoldingForm" class="asset-calc-holding-form" autocomplete="off">
          <label>보유 수량<input id="assetCalcVolume" type="number" min="0" step="any" inputmode="decimal" placeholder="예: 125000"></label>
          <label>평균 매수가<input id="assetCalcAvg" type="number" min="0" step="any" inputmode="decimal" placeholder="예: 0.777"></label>
        </form>
        <div id="assetCalcHoldingSummary" class="asset-calc-summary"></div>
        <div class="asset-calc-actions">
          <button id="assetCalcReloadHolding" type="button" class="asset-calc-button">실제 보유분 다시 불러오기</button>
          <button id="assetCalcClearHolding" type="button" class="asset-calc-button secondary">기준값 비우기</button>
        </div>
        <p class="asset-calc-note">이 입력값은 현재 브라우저 탭에서 계산할 때만 사용합니다. 원격 저장 API는 연결하지 않았습니다.</p>
      </article>
      <article class="asset-calc-panel asset-calc-main">
        <div class="asset-calc-head"><div><p class="kicker">평단 계산</p><h3>물타기 계산기</h3><p>추가 매수 가격과 금액을 넣으면 각 회차 이후의 새 평단과 최종 예상 손익을 계산합니다. 최대 20회까지 계산할 수 있습니다.</p></div></div>
        <div id="assetCalcEntryGuide" class="asset-calc-guide"></div>
        <div id="assetCalcRows" class="asset-calc-list"></div>
        <div class="asset-calc-actions calc-actions">
          <button id="assetCalcAddRow" type="button" class="asset-calc-button secondary">매수 회차 추가</button>
          <button id="assetCalcClearRows" type="button" class="asset-calc-button secondary">계산 초기화</button>
        </div>
        <div id="assetCalcSummary" class="asset-calc-summary"></div>
      </article>`;
    layout.insertAdjacentElement('afterend',root);
    bindTool(root);
    return root;
  }

  function readBaseline(){return {volume:n($('#assetCalcVolume')?.value),avg:n($('#assetCalcAvg')?.value)}}
  function readRows(){return $$('#assetCalcRows .asset-calc-row').slice(0,20).map(row=>({price:n($('[data-calc-price]',row)?.value),amount_krw:n($('[data-calc-amount]',row)?.value)}))}

  function saveActive(){
    if(!activeMarket)return;
    const p=planFor(activeMarket),base=readBaseline();
    p.volume=base.volume;p.avg=base.avg;p.rows=readRows();
  }

  function seedBaseline(market,force=false){
    const p=planFor(market);if(p.baselineTouched&&!force)return p;
    const holding=privateHolding(market);
    p.volume=n(holding?.volume);p.avg=n(holding?.avg_price);p.baselineTouched=false;
    return p;
  }

  function refreshUntouchedBaseline(market){
    const p=planFor(market);if(p.baselineTouched)return false;
    const holding=privateHolding(market),volume=n(holding?.volume),avg=n(holding?.avg_price);
    if(p.volume===volume&&p.avg===avg)return false;
    p.volume=volume;p.avg=avg;
    const volumeInput=$('#assetCalcVolume'),avgInput=$('#assetCalcAvg');
    if(volumeInput)volumeInput.value=volume||'';
    if(avgInput)avgInput.value=avg||'';
    return true;
  }

  function renderRows(rows){
    const list=$('#assetCalcRows');if(!list)return;
    const data=(Array.isArray(rows)&&rows.length?rows:[{price:0,amount_krw:0}]).slice(0,20);
    list.innerHTML=data.map((row,index)=>`<div class="asset-calc-row">
      <div class="asset-calc-round">${index+1}회</div>
      <label>매수가<input data-calc-price type="number" min="0" step="any" inputmode="decimal" value="${row.price||''}" placeholder="가격"></label>
      <label>매수금액<input data-calc-amount type="number" min="0" step="1000" inputmode="numeric" value="${row.amount_krw||''}" placeholder="원"></label>
      <button type="button" class="asset-calc-remove" aria-label="${index+1}회차 삭제">×</button>
      <div class="asset-calc-after"></div>
    </div>`).join('');
    $$('input',list).forEach(input=>input.addEventListener('input',()=>{saveActive();calculate()}));
    $$('.asset-calc-remove',list).forEach(button=>button.addEventListener('click',()=>{
      button.closest('.asset-calc-row')?.remove();
      if(!list.children.length)renderRows([]);
      saveActive();calculate();
    }));
  }

  function renderSource(){
    const market=activeMarket||currentMarket(),row=publicRow(market),holding=privateHolding(market),pill=$('#assetCalcSourcePill');
    if(pill){
      if(holding){pill.textContent='실제 보유분 연결';pill.className='asset-calc-pill good'}
      else if(canViewPrivate()){pill.textContent='선택 코인 미보유';pill.className='asset-calc-pill neutral'}
      else{pill.textContent='브라우저 계산용';pill.className='asset-calc-pill neutral'}
    }
    const base=readBaseline(),current=Number(row?.price||holding?.current_price||0),cost=base.volume*base.avg,value=base.volume*current,pnl=value-cost,pnlPct=cost>0?pnl/cost*100:0;
    const box=$('#assetCalcHoldingSummary');if(!box)return;
    box.innerHTML=`
      <div class="asset-calc-stat"><span>현재가</span><strong>${price(current)}</strong><small>${esc(market||'-')}</small></div>
      <div class="asset-calc-stat"><span>매수 원금</span><strong>${won(cost)}</strong><small>${num(base.volume,8)}개</small></div>
      <div class="asset-calc-stat"><span>현재 평가금액</span><strong>${won(value)}</strong><small>현재가 기준</small></div>
      <div class="asset-calc-stat"><span>현재 손익</span><strong class="${tone(pnl)}">${pnl>=0?'+':''}${won(pnl)}</strong><small class="${tone(pnlPct)}">${pct(pnlPct)}</small></div>`;
  }

  function calculate(){
    const market=activeMarket||currentMarket(),p=planFor(market),base=readBaseline();
    let totalVolume=base.volume,totalCost=base.volume*base.avg;
    const rows=$$('#assetCalcRows .asset-calc-row');
    rows.forEach((row,index)=>{
      const buyPrice=n($('[data-calc-price]',row)?.value),amount=n($('[data-calc-amount]',row)?.value);
      let afterAvg=totalVolume>0?totalCost/totalVolume:0;
      if(buyPrice>0&&amount>0){totalVolume+=amount/buyPrice;totalCost+=amount;afterAvg=totalCost/totalVolume}
      const after=$('.asset-calc-after',row);if(after)after.textContent=buyPrice>0&&amount>0?`${index+1}회 매수 후 예상 평단 ${num(afterAvg,12)}원`:'가격과 금액을 입력하세요.';
    });
    p.volume=base.volume;p.avg=base.avg;p.rows=readRows();
    const finalAvg=totalVolume>0?totalCost/totalVolume:0,row=publicRow(market),holding=privateHolding(market),current=Number(row?.price||holding?.current_price||0),value=totalVolume*current,pnl=value-totalCost,pnlPct=totalCost>0?pnl/totalCost*100:0;
    const box=$('#assetCalcSummary');if(box)box.innerHTML=`
      <div class="asset-calc-stat primary"><span>모두 매수 후 평단</span><strong>${finalAvg?`${num(finalAvg,12)}원`:'-'}</strong><small>현재 평단 ${base.avg?`${num(base.avg,12)}원`:'-'}</small></div>
      <div class="asset-calc-stat"><span>총 들어간 금액</span><strong>${won(totalCost)}</strong><small>추가매수 포함</small></div>
      <div class="asset-calc-stat"><span>총 보유 수량</span><strong>${num(totalVolume,8)}</strong><small>예상 수량</small></div>
      <div class="asset-calc-stat"><span>현재가 기준 예상 손익</span><strong class="${tone(pnl)}">${pnl>=0?'+':''}${won(pnl)}</strong><small class="${tone(pnlPct)}">${pct(pnlPct)}</small></div>`;
    renderSource();
  }

  function renderGuide(){
    const box=$('#assetCalcEntryGuide');if(!box)return;
    const market=activeMarket||currentMarket(),row=publicRow(market),detail=detailCache.get(market),tradePlan=detail?.data?.trade_plan||{},next=Number(tradePlan.next_add_price||tradePlan.expected_entry_price||0),weight=Number(tradePlan.suggested_weight_pct||row?.suggested_weight_pct||0);
    if(next>0){
      box.innerHTML=`<strong>현재 연구 기준 다음 검토 가격 ${price(next)}</strong><p>${Number(tradePlan.next_add_price||0)>0?'다음 추가매수 기준':'예상 진입가'}입니다.${weight>0?` 현재 제안 비중은 ${weight.toFixed(2)}%입니다.`:''} 이 값은 계산기에 자동 주문으로 연결되지 않습니다.</p>`;
    }else if(row){
      box.innerHTML=`<strong>현재가 ${price(row.price)} · 기회점수 ${Number(row.opportunity_score||0).toFixed(1)}</strong><p>${weight>0?`현재 연구 제안 비중 ${weight.toFixed(2)}%. `:''}가격과 금액을 직접 넣어 시나리오를 계산하세요.</p>`;
    }else{
      box.innerHTML='<strong>연구 데이터를 기다리는 중입니다.</strong><p>선택 자산의 현재가가 들어오면 예상 손익도 함께 계산합니다.</p>';
    }
  }

  async function loadDetail(market){
    if(!market)return;
    const seq=++detailSeq;
    try{
      const response=await fetch(`/api/market-detail?exchange=bithumb&strategy=adaptive&market=${encodeURIComponent(market)}`,{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)return;
      const body=await response.json();if(seq!==detailSeq||currentMarket()!==market)return;
      detailCache.set(market,body.detail||null);renderGuide();
    }catch{}
  }

  function switchMarket(market,{forceSeed=false}={}){
    if(!market)return;
    if(activeMarket&&activeMarket!==market)saveActive();
    activeMarket=market;
    const p=seedBaseline(market,forceSeed);
    const volume=$('#assetCalcVolume'),avg=$('#assetCalcAvg');
    if(volume)volume.value=p.volume||'';if(avg)avg.value=p.avg||'';
    renderRows(p.rows);renderSource();renderGuide();calculate();loadDetail(market);
  }

  function bindTool(root){
    if(bound)return;bound=true;
    $('#assetCalcHoldingForm',root)?.addEventListener('submit',event=>event.preventDefault());
    $('#assetCalcVolume',root)?.addEventListener('input',()=>{const p=planFor(activeMarket);p.baselineTouched=true;saveActive();calculate()});
    $('#assetCalcAvg',root)?.addEventListener('input',()=>{const p=planFor(activeMarket);p.baselineTouched=true;saveActive();calculate()});
    $('#assetCalcReloadHolding',root)?.addEventListener('click',()=>{const p=planFor(activeMarket);p.baselineTouched=false;switchMarket(activeMarket,{forceSeed:true})});
    $('#assetCalcClearHolding',root)?.addEventListener('click',()=>{const p=planFor(activeMarket);p.volume=0;p.avg=0;p.baselineTouched=true;$('#assetCalcVolume').value='';$('#assetCalcAvg').value='';calculate()});
    $('#assetCalcAddRow',root)?.addEventListener('click',()=>{saveActive();const p=planFor(activeMarket);if(p.rows.length>=20)return;p.rows.push({price:0,amount_krw:0});renderRows(p.rows);calculate();const rows=$$('#assetCalcRows .asset-calc-row');rows.at(-1)?.scrollIntoView({block:'nearest',behavior:'smooth'})});
    $('#assetCalcClearRows',root)?.addEventListener('click',()=>{const p=planFor(activeMarket);p.rows=[{price:0,amount_krw:0}];renderRows(p.rows);calculate()});
  }

  function sync(){
    const root=ensureTool();if(!root)return;
    const market=currentMarket();if(!market)return;
    if(market!==activeMarket)switchMarket(market);
    else{
      refreshUntouchedBaseline(market);
      renderSource();renderGuide();calculate();
    }
  }

  function install(){
    ensureTool();sync();
    $('#coinSelect')?.addEventListener('change',()=>setTimeout(sync,30));
    document.addEventListener('click',event=>{if(event.target.closest?.('[data-view="coin"]')||event.target.closest?.('[data-open-market]'))setTimeout(sync,100)});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(sync,60)});
    setInterval(()=>{if(!document.hidden&&$('[data-view-panel="coin"]')?.classList.contains('active'))sync()},5000);
    setTimeout(sync,250);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
