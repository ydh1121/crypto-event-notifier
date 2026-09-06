function marketFromRow(row){
  const text=String(row?.querySelector('small')?.textContent||'').trim().toUpperCase();
  if(/^KRW-[A-Z0-9._-]+$/.test(text))return text;
  const symbol=String(row?.querySelector('b')?.textContent||'').trim().toUpperCase();
  return symbol?`KRW-${symbol}`:'';
}

export function installStrategyDrilldown({store,root,navigate}){
  if(!root||typeof navigate!=='function')return()=>{};
  const selector='.strategy-breakdown-table .strategy-coin-row:not(.columns)';
  const enhance=()=>{
    root.querySelectorAll(selector).forEach(row=>{
      if(row.dataset.strategyDrilldownReady==='1')return;
      row.dataset.strategyDrilldownReady='1';
      row.classList.add('strategy-coin-drilldown');
      row.setAttribute('role','button');
      row.setAttribute('tabindex','0');
      row.setAttribute('aria-label',`${marketFromRow(row).replace(/^KRW-/,'')} 코인 상세 보기`);
      row.setAttribute('title','코인 상세 보기');
    });
  };
  const open=row=>{
    const market=marketFromRow(row);
    if(!market)return;
    const exchange=String(store.get().ui.strategyExchange||'bithumb').toLowerCase()==='upbit'?'upbit':'bithumb';
    store.setUi({researchExchange:exchange,researchMarket:market,researchFilter:'all',researchSearch:''},{scope:'strategy-coin-drilldown'});
    navigate('research');
  };
  const click=event=>{
    const row=event.target.closest(selector);
    if(row&&root.contains(row))open(row);
  };
  const keydown=event=>{
    if(event.key!=='Enter'&&event.key!==' ')return;
    const row=event.target.closest(selector);
    if(!row||!root.contains(row))return;
    event.preventDefault();
    open(row);
  };
  let queued=false;
  const observer=new MutationObserver(()=>{
    if(queued)return;
    queued=true;
    queueMicrotask(()=>{queued=false;enhance()});
  });
  root.addEventListener('click',click);
  root.addEventListener('keydown',keydown);
  observer.observe(root,{subtree:true,childList:true});
  enhance();
  return()=>{
    observer.disconnect();
    root.removeEventListener('click',click);
    root.removeEventListener('keydown',keydown);
  };
}
