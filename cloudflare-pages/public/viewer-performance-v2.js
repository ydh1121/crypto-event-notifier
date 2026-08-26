(()=>{
  if(window.__viewerPerformanceV2Loaded)return;
  window.__viewerPerformanceV2Loaded=true;

  const STEP=80;
  let limit=STEP;
  let installed=false;

  const n=v=>Number(v||0);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const won=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
  const pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const price=v=>{const x=n(v);if(!x)return'-';return`${x.toLocaleString('ko-KR',{maximumFractionDigits:x<1?8:x<100?4:2})}원`};
  const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  const stateLabel=row=>row?.state_label||(row?.has_position?'보유 중':n(row?.closed_trades)>0?'매매 완료 · 대기':'미진입');
  const setText=(node,value)=>{if(node&&node.textContent!==String(value))node.textContent=String(value)};
  const setTone=(node,value)=>{if(!node)return;node.classList.remove('positive','negative');const t=tone(value);if(t)node.classList.add(t)};

  function stats(){return window.__viewerPerformance?.stats||{}}
  function reset(){limit=STEP;if(typeof state!=='undefined')state.listSignature=''}

  function ensureStructure(node){
    if(node.querySelector('[data-market-slot="rank"]'))return;
    node.innerHTML='<div class="rank" data-market-slot="rank"></div><div class="market-name"><b data-market-slot="symbol"></b><i data-market-slot="state"></i><small data-market-slot="name"></small></div><div class="market-metric"><span>현재가</span><b data-market-slot="price"></b><small data-market-slot="avg"></small></div><div class="market-metric"><span>보유금액</span><b data-market-slot="holding"></b><small data-market-slot="unrealized"></small></div><div class="market-metric market-return"><span>수익률</span><b data-market-slot="return"></b><small data-market-slot="trades"></small></div>';
  }

  function updateNode(node,row,index){
    const signature=[index,row.market,row.symbol,row.name,stateLabel(row),row.price,row.position_avg_price,row.position_value_krw,row.unrealized_pnl_krw,row.return_pct,row.closed_trades,row.win_rate_pct].join('|');
    if(node.dataset.marketRenderSignature===signature)return;
    node.dataset.marketRenderSignature=signature;
    ensureStructure(node);
    node.type='button';node.classList.add('market-row');node.dataset.openMarket=row.market||'';
    setText(node.querySelector('[data-market-slot="rank"]'),index+1);
    setText(node.querySelector('[data-market-slot="symbol"]'),row.symbol||row.market||'');
    setText(node.querySelector('[data-market-slot="state"]'),stateLabel(row));
    setText(node.querySelector('[data-market-slot="name"]'),row.name||row.market||'');
    setText(node.querySelector('[data-market-slot="price"]'),price(row.price));
    setText(node.querySelector('[data-market-slot="avg"]'),row.position_avg_price?`평단 ${price(row.position_avg_price)}`:'평단 없음');
    setText(node.querySelector('[data-market-slot="holding"]'),won(row.position_value_krw));
    setText(node.querySelector('[data-market-slot="unrealized"]'),`미실현 ${n(row.unrealized_pnl_krw)>=0?'+':''}${won(row.unrealized_pnl_krw)}`);
    const ret=node.querySelector('[data-market-slot="return"]');setText(ret,pct(row.return_pct));setTone(ret,row.return_pct);
    setText(node.querySelector('[data-market-slot="trades"]'),`${n(row.closed_trades)}회 · 승률 ${n(row.win_rate_pct).toFixed(1)}%`);
    const s=stats();s.marketNodeWrites=n(s.marketNodeWrites)+1;
  }

  function footer(total,shown){
    if(shown>=total)return null;
    const wrap=document.createElement('div');wrap.className='viewer-result-more';
    wrap.innerHTML=`<span><b>${shown.toLocaleString('ko-KR')}</b> / ${total.toLocaleString('ko-KR')}개 표시</span><button type="button" data-viewer-more-results>다음 ${Math.min(STEP,total-shown)}개 보기</button>`;
    return wrap;
  }

  function pagedRender(){
    const all=filteredRows();
    const shown=Math.min(limit,all.length),list=all.slice(0,shown);
    const ex=state.snapshot?.public?.exchange||window.cryptoResearchExchange?.mode||'';
    const signature=`v2|${ex}|${state.filter}|${state.sort}|${state.search}|${shown}|${all.length}|${list.map((row,index)=>[index,row.market,row.price,row.position_value_krw,row.unrealized_pnl_krw,row.return_pct,row.closed_trades,row.win_rate_pct].join(':')).join(';')}`;
    if(signature===state.listSignature)return;
    state.listSignature=signature;
    const box=document.getElementById('marketList');if(!box)return;
    const scroll=box.scrollTop,s=stats();s.marketPasses=n(s.marketPasses)+1;s.marketRowsRendered=shown;s.marketRowsTotal=all.length;
    if(!all.length){box.innerHTML='<div class="empty">조건에 맞는 코인이 없습니다.</div>';document.dispatchEvent(new CustomEvent('viewer:marketrowsupdated'));return}

    const existing=new Map([...box.querySelectorAll(':scope>[data-open-market]')].map(node=>[node.dataset.openMarket,node]));
    const wanted=new Set(list.map(row=>String(row.market||'')));
    [...box.children].filter(node=>!node.matches('[data-open-market]')).forEach(node=>node.remove());
    let cursor=box.firstElementChild;
    list.forEach((row,index)=>{
      const market=String(row.market||'');let node=existing.get(market);
      if(!node){node=document.createElement('button');node.className='market-row';node.dataset.openMarket=market}
      updateNode(node,row,index);
      if(node!==cursor)box.insertBefore(node,cursor||null);
      cursor=node.nextElementSibling;
    });
    [...box.querySelectorAll(':scope>[data-open-market]')].forEach(node=>{if(!wanted.has(node.dataset.openMarket||''))node.remove()});
    const more=footer(all.length,shown);if(more)box.appendChild(more);
    box.scrollTop=Math.max(0,Math.min(scroll,box.scrollHeight-box.clientHeight));
    document.dispatchEvent(new CustomEvent('viewer:marketrowsupdated',{detail:{shown,total:all.length}}));
  }

  function install(){
    if(installed)return;
    if(typeof state==='undefined'||typeof filteredRows!=='function'||typeof renderMarkets!=='function'||!window.__viewerPerformance){setTimeout(install,60);return}
    installed=true;
    pagedRender.__viewerPaged=true;
    window.renderMarkets=pagedRender;
    const s=stats();s.resultPageSize=STEP;s.marketRowsRendered=0;s.marketRowsTotal=0;

    document.addEventListener('click',event=>{
      const more=event.target.closest?.('[data-viewer-more-results]');
      if(more){limit+=STEP;state.listSignature='';pagedRender();return}
      if(event.target.closest?.('#filterRow [data-filter]')){reset();setTimeout(()=>{if(state.activeView==='results')pagedRender()},0)}
    });
    document.getElementById('sortSelect')?.addEventListener('change',()=>{reset();setTimeout(()=>{if(state.activeView==='results')pagedRender()},0)});
    let searchTimer=0;document.getElementById('searchInput')?.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{reset();if(state.activeView==='results')pagedRender()},60)});
    document.addEventListener('phase3exchangechange',()=>{reset();setTimeout(()=>{if(state.activeView==='results')pagedRender()},0)});
    document.addEventListener('viewer:viewchange',event=>{if(event.detail?.view==='results'){state.listSignature='';pagedRender()}});
    window.__viewerPerformance.version=3;
    window.__viewerPerformance.resultPaging={pageSize:STEP,get limit(){return limit},reset};
  }

  setTimeout(install,35);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(install,35),{once:true});
})();
