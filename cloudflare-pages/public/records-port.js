(()=>{
  if(window.__recordsPortLoaded)return;
  window.__recordsPortLoaded=true;

  const q=(selector,root=document)=>root.querySelector(selector);
  const n=value=>Number(value||0);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[ch]));
  const won=value=>`${Math.round(n(value)).toLocaleString('ko-KR')}원`;
  const pct=(value,d=2)=>`${n(value)>=0?'+':''}${n(value).toFixed(d)}%`;
  const tone=value=>n(value)>0?'positive':n(value)<0?'negative':'';
  const dt=value=>value?new Date(n(value)*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-';
  const age=value=>{const sec=Math.max(0,Date.now()/1000-n(value));if(!value)return'기록 대기';if(sec<60)return`${Math.round(sec)}초 전`;if(sec<3600)return`${Math.round(sec/60)}분 전`;return`${Math.round(sec/3600)}시간 전`};
  const stateRef=()=>typeof state!=='undefined'?state:null;
  let filter='all';

  function records(){return stateRef()?.snapshot?.public?.recent_records||{fills:[],feedback:[],fill_count:0,feedback_count:0,updated_at:0}}
  function ensureRoot(){
    const panel=q('[data-view-panel="records"]');if(!panel)return null;
    panel.classList.add('records-port-active');
    let root=q('#recordsPort',panel);if(root)return root;
    root=document.createElement('section');root.id='recordsPort';root.className='records-port';panel.appendChild(root);return root;
  }
  function itemsFrom(data){
    const fills=(Array.isArray(data.fills)?data.fills:[]).map(row=>({...row,kind:row.side==='sell'?'sell':'buy'}));
    const feedback=(Array.isArray(data.feedback)?data.feedback:[]).map(row=>({...row,kind:'learning'}));
    return [...fills,...feedback].sort((a,b)=>n(b.ts)-n(a.ts));
  }
  function summary(data,items){
    const recentBuys=items.filter(row=>row.kind==='buy').length,recentSells=items.filter(row=>row.kind==='sell').length;
    const realized=items.filter(row=>row.kind==='sell').reduce((sum,row)=>sum+n(row.realized_pnl),0);
    return `<div class="records-overview"><div class="records-metric"><span>누적 체결</span><b>${n(data.fill_count).toLocaleString('ko-KR')}건</b><small>최근 ${recentBuys}매수 · ${recentSells}매도 표시</small></div><div class="records-metric"><span>누적 학습</span><b>${n(data.feedback_count).toLocaleString('ko-KR')}건</b><small>완료 거래 후 프로필 조정</small></div><div class="records-metric"><span>최근 매도 손익</span><b class="${tone(realized)}">${realized>=0?'+':''}${won(realized)}</b><small>현재 표시 구간 기준</small></div><div class="records-metric"><span>마지막 기록</span><b>${age(data.updated_at)}</b><small>${dt(data.updated_at)}</small></div></div>`;
  }
  function rowHtml(row){
    const symbol=String(row.symbol||row.market||'').replace(/^KRW-/,'');
    if(row.kind==='learning'){
      const c=row.profile_change||{};
      return `<article class="record-row"><div class="record-kind learning"><i></i><b>학습</b></div><div class="record-market"><b>${esc(symbol)}</b><small>${esc(row.market||'')}</small></div><div class="record-main"><b>완료 거래를 반영해 기준값을 조정했습니다.</b><p>시장 ${n(c.regime_before).toFixed(1)} → ${n(c.regime_after).toFixed(1)} · 진입 ${n(c.entry_before).toFixed(1)} → ${n(c.entry_after).toFixed(1)} · 기본비중 ${n(c.weight_before).toFixed(1)}% → ${n(c.weight_after).toFixed(1)}%</p></div><div class="record-side"><b class="${tone(row.outcome_return_pct)}">${pct(row.outcome_return_pct)}</b><small>${dt(row.ts)}</small></div></article>`;
    }
    const isSell=row.kind==='sell';
    const amount=isSell?n(row.realized_pnl):n(row.krw);
    return `<article class="record-row"><div class="record-kind ${row.kind}"><i></i><b>${isSell?'매도':'매수'}</b></div><div class="record-market"><b>${esc(symbol)}</b><small>${esc(row.market||'')}</small></div><div class="record-main"><b>${isSell?'가상계좌 매도 체결':'가상계좌 매수 체결'} · ${n(row.price).toLocaleString('ko-KR',{maximumFractionDigits:8})}원</b><p>${isSell?`실현 수익률 ${pct(row.return_pct)}`:`매수금액 ${won(row.krw)}`}</p></div><div class="record-side"><b class="${isSell?tone(amount):''}">${isSell?`${amount>=0?'+':''}${won(amount)}`:won(amount)}</b><small>${dt(row.ts)}</small></div></article>`;
  }
  function render(){
    const root=ensureRoot();if(!root)return;
    const data=records(),all=itemsFrom(data);
    const filtered=filter==='all'?all:all.filter(row=>row.kind===filter);
    root.innerHTML=`${summary(data,all)}<div class="records-toolbar"><div class="records-filters"><button class="${filter==='all'?'is-active':''}" data-record-filter="all">전체 ${all.length}</button><button class="${filter==='buy'?'is-active':''}" data-record-filter="buy">매수 ${all.filter(x=>x.kind==='buy').length}</button><button class="${filter==='sell'?'is-active':''}" data-record-filter="sell">매도 ${all.filter(x=>x.kind==='sell').length}</button><button class="${filter==='learning'?'is-active':''}" data-record-filter="learning">학습 ${all.filter(x=>x.kind==='learning').length}</button></div><span class="records-age">최근 데이터 ${age(data.updated_at)}</span></div><div class="records-feed">${filtered.length?filtered.slice(0,100).map(rowHtml).join(''):'<div class="records-empty">표시할 기록이 아직 없습니다.</div>'}</div>`;
    root.querySelectorAll('[data-record-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.recordFilter||'all';render()});
  }
  function install(){render();setInterval(()=>{if(!document.hidden&&stateRef()?.user)render()},15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)render()})}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
