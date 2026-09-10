const PAGE_ROOT_ID='pageRoot';
const DETAIL_TABS=['summary','coins','evidence'];
let activeDetailTab='summary';
let savedRailScroll=0;
let scheduled=0;

function root(){
  return document.getElementById(PAGE_ROOT_ID);
}

function strategyRoot(){
  const page=root();
  return page?.dataset?.pageRoute==='strategy'?page:null;
}

function text(node){
  return String(node?.textContent||'').trim();
}

function escHtml(value){
  return String(value??'').replace(/[&<>'"]/g,char=>({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    "'":'&#39;',
    '"':'&quot;',
  })[char]);
}

function readerMode(){
  return document.documentElement.dataset.readerMode==='detail'?'detail':'simple';
}

function enhanceRailRow(row){
  if(!row||row.dataset.strategyV5Row==='ready')return;
  const cells=[...row.children];
  if(cells.length<7)return;

  const title=text(cells[0]?.querySelector('b'))||text(cells[0]);
  const description=text(cells[0]?.querySelector('small'));
  const returnValue=text(cells[1]);
  const drawdownValue=text(cells[2]);
  const status=text(cells[6]?.querySelector('.status-badge'))||text(cells[6]);
  const returnClass=cells[1]?.className||'';
  const drawdownClass=cells[2]?.className||'';
  const selected=row.classList.contains('selected')||row.getAttribute('aria-pressed')==='true';

  row.dataset.strategyV5Row='ready';
  row.classList.add('strategy-v5-strategy-item');
  row.setAttribute('aria-current',selected?'true':'false');
  row.innerHTML=`<span class="strategy-v5-item-copy"><b>${escHtml(title)}</b><small>${escHtml(description)}</small></span><span class="strategy-v5-item-facts"><span><small>수익률</small><b class="${escHtml(returnClass)}">${escHtml(returnValue)}</b></span><span><small>최대 하락</small><b class="${escHtml(drawdownClass)}">${escHtml(drawdownValue)}</b></span><em>${escHtml(status)}</em></span>`;
}

function ensureRail(list){
  if(!list)return;
  const columns=list.querySelector('.strategy-row.columns');
  if(columns)columns.hidden=true;

  if(!list.querySelector('.strategy-v5-rail-head')){
    const head=document.createElement('div');
    head.className='strategy-v5-rail-head';
    head.innerHTML='<span><b>시험 전략</b><small>선택하면 오른쪽 결과만 바뀝니다.</small></span><em>수익률 순</em>';
    list.prepend(head);
  }

  list.querySelectorAll('[data-strategy-key]').forEach(enhanceRailRow);
  requestAnimationFrame(()=>{
    list.scrollTop=savedRailScroll;
  });
}

function makeTabs(){
  const nav=document.createElement('nav');
  nav.className='strategy-v5-detail-tabs';
  nav.setAttribute('aria-label','선택 전략 보기');
  nav.innerHTML='<button type="button" data-strategy-v5-tab="summary">요약</button><button type="button" data-strategy-v5-tab="coins">코인별 성과</button><button type="button" data-strategy-v5-tab="evidence">검증 흐름</button><button type="button" class="strategy-v5-back" data-strategy-v5-back>전략 목록</button>';
  return nav;
}

function ensureDetailShell(page,workspace,detail,breakdown,evidence){
  let shell=workspace.querySelector('.strategy-v5-detail-shell');
  if(shell)return shell;

  shell=document.createElement('section');
  shell.className='strategy-v5-detail-shell';
  shell.setAttribute('aria-label','선택 전략 상세');

  const tabs=makeTabs();
  const panels=document.createElement('div');
  panels.className='strategy-v5-detail-panels';

  detail.before(shell);
  detail.classList.add('strategy-v5-panel');
  detail.dataset.strategyV5Panel='summary';
  breakdown.classList.add('strategy-v5-panel');
  breakdown.dataset.strategyV5Panel='coins';
  evidence.classList.add('strategy-v5-panel');
  evidence.dataset.strategyV5Panel='evidence';

  panels.append(detail,breakdown,evidence);
  shell.append(tabs,panels);
  return shell;
}

function applyDetailTab(shell){
  if(!shell)return;
  if(readerMode()==='simple'&&activeDetailTab!=='summary')activeDetailTab='summary';

  shell.querySelectorAll('[data-strategy-v5-tab]').forEach(button=>{
    const active=button.dataset.strategyV5Tab===activeDetailTab;
    button.classList.toggle('active',active);
    button.setAttribute('aria-selected',active?'true':'false');
  });

  shell.querySelectorAll('[data-strategy-v5-panel]').forEach(panel=>{
    panel.hidden=panel.dataset.strategyV5Panel!==activeDetailTab;
  });
}

function enhanceOverview(page){
  const body=page.querySelector('#strategyBody');
  const workspace=body?.querySelector('.strategy-workspace');
  const list=workspace?.querySelector('.strategy-table');
  const detail=workspace?.querySelector('#strategyDetail');
  const breakdown=body?.querySelector('#strategyBreakdown');
  const evidence=body?.querySelector('#strategyEvidence');
  if(!body||!workspace||!list||!detail||!breakdown||!evidence)return false;

  ensureRail(list);
  const shell=ensureDetailShell(page,workspace,detail,breakdown,evidence);
  workspace.dataset.strategyWorkspaceV5='ready';
  body.dataset.strategyWorkspaceV5='ready';
  applyDetailTab(shell);
  return true;
}

function enhance(){
  scheduled=0;
  const page=strategyRoot();
  if(!page)return;
  enhanceOverview(page);
}

function scheduleEnhance(){
  if(scheduled)cancelAnimationFrame(scheduled);
  scheduled=requestAnimationFrame(enhance);
}

function openDetailModeForDeepTab(){
  if(readerMode()==='detail')return false;
  const button=document.querySelector('[data-reader-mode="detail"]');
  if(!(button instanceof HTMLElement))return false;
  button.click();
  return true;
}

function onClick(event){
  const page=strategyRoot();
  if(!page)return;

  const strategy=event.target.closest('[data-strategy-key]');
  if(strategy&&page.contains(strategy)){
    const list=page.querySelector('.strategy-table');
    savedRailScroll=list?.scrollTop||0;
    return;
  }

  const tab=event.target.closest('[data-strategy-v5-tab]');
  if(tab&&page.contains(tab)){
    event.preventDefault();
    event.stopPropagation();
    const value=String(tab.dataset.strategyV5Tab||'');
    if(!DETAIL_TABS.includes(value))return;
    activeDetailTab=value;
    if(value!=='summary'&&openDetailModeForDeepTab()){
      scheduleEnhance();
      return;
    }
    applyDetailTab(page.querySelector('.strategy-v5-detail-shell'));
    return;
  }

  const back=event.target.closest('[data-strategy-v5-back]');
  if(back&&page.contains(back)){
    event.preventDefault();
    event.stopPropagation();
    page.querySelector('.strategy-table')?.scrollIntoView({block:'start',behavior:'auto'});
  }
}

const page=root();
if(page){
  page.addEventListener('click',onClick,true);
  const observer=new MutationObserver(scheduleEnhance);
  observer.observe(page,{childList:true,subtree:true});
  scheduleEnhance();
}
