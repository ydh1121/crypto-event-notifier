(function(){
  if(window.__researchCapitalLoaded)return;
  window.__researchCapitalLoaded=true;

  const q=(selector,root=document)=>root.querySelector(selector);
  const qa=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const n=value=>Number(value||0);
  const won=value=>`${Math.round(n(value)).toLocaleString('ko-KR')}원`;
  const pct=(value,d=2)=>`${n(value)>=0?'+':''}${n(value).toFixed(d)}%`;
  const tone=value=>n(value)>0?'positive':n(value)<0?'negative':'';
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let summary=null;
  let detailMarket='';
  let detailSignature='';
  let busy=false;
  let timer=0;

  async function apiJson(path){
    if(typeof window.api==='function')return window.api(path);
    if(typeof api==='function')return api(path);
    const response=await fetch(path,{cache:'no-store'});
    if(!response.ok)throw new Error(`${response.status}`);
    return response.json();
  }

  function loadComponentManager(){
    if(!document.querySelector('link[data-research-components]')){
      const link=document.createElement('link');link.rel='stylesheet';link.href='./research-components.css?v=1';link.dataset.researchComponents='1';document.head.appendChild(link);
    }
    if(!window.__researchComponentsLoaded&&!document.querySelector('script[data-research-components]')){
      const script=document.createElement('script');script.src='./research-components.js?v=1';script.dataset.researchComponents='1';document.body.appendChild(script);
    }
  }

  function aggregateNumbers(data){
    const count=Math.max(0,n(data?.market_count));
    const start=n(data?.aggregate_virtual_capital_krw)||(n(data?.per_market_start_krw)||10_000_000)*count;
    const equity=n(data?.equity_krw);
    const cash=n(data?.cash_krw);
    const pnl=equity-start;
    const returnPct=start>0?pnl/start*100:0;
    const invested=Math.max(0,equity-cash);
    return {count,start,equity,cash,pnl,returnPct,invested};
  }

  function renderAggregate(){
    const grid=q('#demoSummaryGrid');if(!grid||!summary)return;
    let box=q('#demoCapitalOverview');
    if(!box){box=document.createElement('section');box.id='demoCapitalOverview';box.className='demo-capital-overview';grid.insertAdjacentElement('beforebegin',box)}
    const x=aggregateNumbers(summary);
    const signature=[x.count,x.start,x.equity,x.cash,x.pnl].join('|');
    if(box.dataset.signature===signature)return;
    box.dataset.signature=signature;
    box.innerHTML=`
      <div class="demo-capital-primary">
        <span>전체 가상 운용자금</span>
        <div class="demo-capital-flow"><b>${won(x.start)}</b><i>→</i><strong class="${tone(x.pnl)}">${won(x.equity)}</strong></div>
        <small>${x.count.toLocaleString('ko-KR')}개 코인 × 코인당 1,000만원</small>
      </div>
      <div class="demo-capital-metrics">
        <div class="focus"><span>전체 증감액</span><b class="${tone(x.pnl)}">${x.pnl>=0?'+':''}${won(x.pnl)}</b><small class="${tone(x.returnPct)}">원금 대비 ${pct(x.returnPct)}</small></div>
        <div><span>현재 매수 중 자금</span><b>${won(x.invested)}</b><small>보유 포지션 평가금액</small></div>
        <div><span>남아 있는 현금</span><b>${won(x.cash)}</b><small>전체 가상계좌 현금 합계</small></div>
      </div>`;
  }

  function decorateLeaderboard(){
    if(!summary)return;
    const map=new Map((Array.isArray(summary.leaderboard)?summary.leaderboard:[]).map(row=>[row.market,row]));
    qa('#demoList .demo-rank-row').forEach(button=>{
      const row=map.get(button.dataset.market);if(!row)return;
      const side=q('.demo-rank-side',button);if(!side)return;
      let delta=q('.demo-rank-capital-delta',side);
      if(!delta){delta=document.createElement('small');delta.className='demo-rank-capital-delta';side.appendChild(delta)}
      const pnl=n(row.equity_krw)-10_000_000;
      delta.className=`demo-rank-capital-delta ${tone(pnl)}`;
      delta.textContent=`${pnl>=0?'+':''}${won(pnl)}`;
      delta.title='가상계좌 1,000만원 대비 현재 증감액';
    });
  }

  function selectedMarket(){return q('#demoList .demo-rank-row.is-active')?.dataset.market||''}

  function detailNumbers(data){
    const s=data?.summary||{},account=data?.account||{},position=data?.position||{};
    const start=10_000_000;
    const equity=n(s.equity_krw)||n(account.cash_krw)+n(position.value_krw);
    const pnl=equity-start;
    return {
      start,equity,pnl,returnPct:start>0?pnl/start*100:0,
      cash:n(account.cash_krw),positionValue:n(position.value_krw),
      realized:n(s.realized_pnl_krw||account.realized_pnl),unrealized:n(position.unrealized_pnl_krw),
      stateLabel:data?.state_label||s.state_label||(s.has_position?'보유 중':n(s.closed_trades)>0?'매매 완료 · 대기':'미진입'),
    };
  }

  function renderDetailCapital(data){
    const detail=q('#demoDetail');if(!detail||!data)return;
    const head=q('.demo-detail-head',detail);if(!head)return;
    let box=q('#demoCoinCapital',detail);
    if(!box){box=document.createElement('section');box.id='demoCoinCapital';box.className='demo-coin-capital';head.insertAdjacentElement('afterend',box)}
    const x=detailNumbers(data);
    const signature=[x.equity,x.cash,x.positionValue,x.realized,x.unrealized,x.stateLabel].join('|');
    if(box.dataset.signature===signature)return;
    box.dataset.signature=signature;
    box.innerHTML=`
      <div class="demo-coin-capital-main">
        <div><span>이 코인 가상계좌</span><b>${won(x.start)} <i>→</i> <strong class="${tone(x.pnl)}">${won(x.equity)}</strong></b><small>${esc(x.stateLabel)}</small></div>
        <div class="demo-coin-capital-pnl ${tone(x.pnl)}"><span>원금 대비 증감</span><strong>${x.pnl>=0?'+':''}${won(x.pnl)}</strong><small>${pct(x.returnPct)}</small></div>
      </div>
      <div class="demo-coin-capital-grid">
        <div><span>남은 현금</span><b>${won(x.cash)}</b></div>
        <div><span>현재 보유금액</span><b>${won(x.positionValue)}</b></div>
        <div><span>확정 손익</span><b class="${tone(x.realized)}">${x.realized>=0?'+':''}${won(x.realized)}</b></div>
        <div><span>미실현 손익</span><b class="${tone(x.unrealized)}">${x.unrealized>=0?'+':''}${won(x.unrealized)}</b></div>
      </div>`;
  }

  async function syncDetail({force=false}={}){
    const market=selectedMarket();if(!market)return;
    try{
      const response=await fetch(`./demo-runtime/${encodeURIComponent(market)}.json?t=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)return;
      const data=await response.json();
      const s=data?.summary||{},position=data?.position||{};
      const signature=[market,s.signal_ts,s.equity_krw,s.cash_krw,position.value_krw,position.unrealized_pnl_krw,data?.state_label].join('|');
      if(!force&&signature===detailSignature&&q('#demoCoinCapital'))return;
      detailSignature=signature;detailMarket=market;renderDetailCapital(data);
    }catch(_err){}
  }

  async function sync({forceDetail=false}={}){
    if(busy||document.hidden||!q('#demoResearch'))return;
    busy=true;
    try{
      summary=await apiJson('/api/demo');
      renderAggregate();
      decorateLeaderboard();
      await syncDetail({force:forceDetail});
    }catch(_err){}finally{busy=false}
  }

  function install(){
    loadComponentManager();
    sync({forceDetail:true});
    timer=window.setInterval(()=>sync({forceDetail:false}),15000);
    document.addEventListener('click',event=>{
      if(!event.target.closest?.('#demoList .demo-rank-row'))return;
      setTimeout(()=>syncDetail({force:true}),80);
    },true);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync({forceDetail:true})});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();