function marketFromRow(row){
  const text=String(row?.querySelector('small')?.textContent||'').trim().toUpperCase();
  if(/^KRW-[A-Z0-9._-]+$/.test(text))return text;
  const symbol=String(row?.querySelector('b')?.textContent||'').trim().toUpperCase();
  return symbol?`KRW-${symbol}`:'';
}

function strategyContext(root){
  const section=root?.querySelector('.strategy-breakdown[data-strategy-coin-experiment]');
  const experiment=String(section?.dataset?.strategyCoinExperiment||'');
  const label=String(section?.querySelector('.strategy-breakdown-head h3')?.textContent||'').trim();
  const normalized=label.toLowerCase();
  let mode='';
  if(/적립|dca|accum/.test(normalized))mode='dca';
  else if(/스윙|swing/.test(normalized))mode='swing';
  else if(/단타|scalp|short|intraday/.test(normalized))mode='short';
  return{experiment,label,mode};
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
    const context=strategyContext(root);
    const patch={
      researchExchange:exchange,
      researchMarket:market,
      researchFilter:'all',
      researchSearch:'',
      researchSourceStrategyExperiment:context.experiment,
      researchSourceStrategyLabel:context.label,
    };
    if(context.mode)patch.researchDecisionMode=context.mode;
    store.setUi(patch,{scope:'strategy-coin-drilldown'});
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
