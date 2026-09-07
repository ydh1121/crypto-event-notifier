const qs=(root,selector)=>root?.querySelector(selector)||null;
const qsa=(root,selector)=>[...(root?.querySelectorAll(selector)||[])];

function wrapAdvancedSection(section,{title,summary}){
  if(!section||section.closest('[data-v5-collapsible]'))return;
  const details=document.createElement('details');
  details.dataset.v5Collapsible='1';
  details.className='v5-collapsible';
  const head=document.createElement('summary');
  head.innerHTML=`<span><b>${title}</b><small>${summary}</small></span><strong>펼쳐보기</strong>`;
  section.before(details);
  details.append(head,section);
}

function makeTabs({anchor,group,tabs}){
  if(!anchor||anchor.closest(`[data-v5-tab-shell="${group}"]`))return null;
  const available=tabs.map(tab=>({...tab,nodes:tab.nodes.filter(Boolean)})).filter(tab=>tab.nodes.length);
  if(available.length<2)return null;
  const shell=document.createElement('section');
  shell.className='v5-tab-shell';
  shell.dataset.v5TabShell=group;
  const nav=document.createElement('nav');
  nav.className='v5-section-tabs';
  nav.setAttribute('aria-label',available[0].aria||'상세 정보');
  available.forEach((tab,index)=>{
    const button=document.createElement('button');
    button.type='button';
    button.dataset.v5Tab=tab.key;
    button.dataset.v5TabGroup=group;
    button.classList.toggle('active',index===0);
    button.textContent=tab.label;
    nav.appendChild(button);
  });
  shell.appendChild(nav);
  available.forEach((tab,index)=>{
    const panel=document.createElement('div');
    panel.dataset.v5Panel=tab.key;
    panel.dataset.v5PanelGroup=group;
    panel.className=`v5-tab-panel${index===0?'':' hidden'}`;
    tab.nodes.forEach(node=>panel.appendChild(node));
    shell.appendChild(panel);
  });
  anchor.before(shell);
  return shell;
}

function selectPanel(root,group,key){
  qsa(root,`[data-v5-tab-group="${group}"]`).forEach(button=>button.classList.toggle('active',button.dataset.v5Tab===key));
  qsa(root,`[data-v5-panel-group="${group}"]`).forEach(panel=>panel.classList.toggle('hidden',panel.dataset.v5Panel!==key));
}

function ensureDecisionLens(root){
  const detail=qs(root,'.research-detail');
  const hero=qs(detail,'.decision-hero');
  if(!detail||!hero||qs(detail,'.v5-decision-lens'))return;
  const section=document.createElement('section');
  section.className='v5-decision-lens';
  section.innerHTML=`<header><div><span>매매 기준 선택</span><h3>어떤 방식과 시간으로 볼까요?</h3></div><strong>의사결정 행렬 준비 중</strong></header>
    <div class="v5-lens-row"><b>매매 방식</b><div role="group" aria-label="매매 방식"><button type="button" data-v5-mode="short" class="active">단타</button><button type="button" data-v5-mode="swing">스윙</button><button type="button" data-v5-mode="dca">적립식</button></div></div>
    <div class="v5-lens-row"><b>시간 기준</b><div role="group" aria-label="시간 기준"><button type="button" data-v5-timeframe="15m" class="active">15분</button><button type="button" data-v5-timeframe="30m">30분</button><button type="button" data-v5-timeframe="1h">1시간</button><button type="button" data-v5-timeframe="4h">4시간</button><button type="button" data-v5-timeframe="1d">일봉</button><button type="button" data-v5-timeframe="1w">주봉</button></div></div>
    <div class="v5-lens-status"><span><b data-v5-lens-title>단타 · 15분</b><small>추천 진입·추가매수·불타기·손절·분할익절·완전익절</small></span><strong>아직 계산하지 않음</strong><p>현재 백엔드에는 이 조합별 의사결정 행렬이 없습니다. 실제 계산기가 준비되기 전에는 타점을 만들어 표시하지 않습니다. 아래 ‘현재 계산’에는 지금 엔진이 실제로 산출한 값만 표시합니다.</p></div>`;
  hero.after(section);
}

function updateDecisionLens(root){
  const lens=qs(root,'.v5-decision-lens');
  if(!lens)return;
  const modes={short:'단타',swing:'스윙',dca:'적립식'},frames={'15m':'15분','30m':'30분','1h':'1시간','4h':'4시간','1d':'일봉','1w':'주봉'};
  const mode=root.dataset.v5Mode||'short',frame=root.dataset.v5Timeframe||'15m';
  qsa(lens,'[data-v5-mode]').forEach(button=>button.classList.toggle('active',button.dataset.v5Mode===mode));
  qsa(lens,'[data-v5-timeframe]').forEach(button=>button.classList.toggle('active',button.dataset.v5Timeframe===frame));
  const title=qs(lens,'[data-v5-lens-title]');if(title)title.textContent=`${modes[mode]||'단타'} · ${frames[frame]||'15분'}`;
}

function organizeResearchDeep(root){
  const deep=qs(root,'#researchDeep');
  if(!deep||qs(deep,'[data-v5-tab-shell="research-deep"]'))return;
  const plan=qs(deep,'.deep-section');
  const context=qs(deep,'.major-context');
  const history=qsa(deep,':scope > section').find(node=>qs(node,'.history-toolbar'))||null;
  const records=qs(deep,'.detail-columns');
  if(!plan)return;
  makeTabs({anchor:plan,group:'research-deep',tabs:[
    {key:'current',label:'현재 계산',nodes:[plan]},
    {key:'evidence',label:'판단 근거',nodes:[context,history]},
    {key:'records',label:'기록',nodes:[records]},
  ]});
}

function organizeResearch(root){
  const workspace=qs(root,'.research-workspace');
  const listing=qs(root,'.listing-history-panel');
  if(workspace&&listing&&!listing.closest('[data-v5-collapsible]')){
    workspace.after(listing);
    wrapAdvancedSection(listing,{title:'상장 전후 반응',summary:'선택 코인 판단과 분리해 필요할 때만 확인합니다.'});
  }
  ensureDecisionLens(root);
  updateDecisionLens(root);
  organizeResearchDeep(root);
}

function organizeAssetDetail(root){
  const detail=qs(root,'.asset-detail');
  if(!detail||qs(detail,'[data-v5-tab-shell="asset-detail"]'))return;
  const decision=qs(detail,'.holding-plan-panel');
  const direct=qs(detail,'.direct-average-panel');
  const averaging=qs(detail,'.averaging-calculator');
  const compare=qs(detail,'.asset-research-sides');
  if(!decision)return;
  makeTabs({anchor:decision,group:'asset-detail',tabs:[
    {key:'decision',label:'관리 판단',nodes:[decision]},
    {key:'calculator',label:'추가매수 계산',nodes:[direct,averaging]},
    {key:'compare',label:'거래소 비교',nodes:[compare]},
  ]});
  const note=qs(detail,'.local-management-note');
  if(note)wrapAdvancedSection(note,{title:'보유정보 관리 안내',summary:'저장 위치와 조회 전용 범위는 필요할 때 확인합니다.'});
}

function organizeAssets(root){
  const workspace=qs(root,'.asset-workspace');
  const history=qs(root,'.asset-history-panel');
  if(workspace&&history&&!history.closest('[data-v5-collapsible]')){
    workspace.after(history);
    wrapAdvancedSection(history,{title:'자산 변화 이력',summary:'현재 보유 판단을 먼저 보고 과거 흐름은 필요할 때 확인합니다.'});
  }
  organizeAssetDetail(root);
}

function strategyPanels(root){
  const breakdown=qs(root,'#strategyBreakdown');
  const evidence=qs(root,'#strategyEvidence');
  if(!breakdown||!evidence||qs(root,'[data-v5-tab-shell="strategy-detail"]'))return;
  makeTabs({anchor:breakdown,group:'strategy-detail',tabs:[
    {key:'coins',label:'코인별 성과',nodes:[breakdown]},
    {key:'evidence',label:'성적·검증',nodes:[evidence]},
  ]});
}

function organizeStrategy(root){strategyPanels(root)}

function organizePaperDeep(root){
  const deep=qs(root,'#paperDeep');
  if(!deep||qs(deep,'[data-v5-tab-shell="paper-deep"]'))return;
  const plan=qs(deep,'.trade-plan-panel');
  const history=qsa(deep,':scope > section').find(node=>qs(node,'.history-toolbar'))||null;
  const records=qs(deep,'.detail-columns');
  if(!plan)return;
  makeTabs({anchor:plan,group:'paper-deep',tabs:[
    {key:'plan',label:'현재 매매계획',nodes:[plan]},
    {key:'history',label:'성적 흐름',nodes:[history]},
    {key:'records',label:'최근 기록',nodes:[records]},
  ]});
}

function organizePaper(root){
  const body=qs(root,'#paperBody');
  if(!body)return;
  const summary=qs(body,'.paper-combined');
  const exchangeGrid=qs(body,'.exchange-paper-grid');
  if(summary&&exchangeGrid&&!qs(body,'.v5-paper-summary-cluster')){
    const cluster=document.createElement('section');
    cluster.className='v5-paper-summary-cluster';
    summary.before(cluster);
    cluster.append(summary,exchangeGrid);
  }
  organizePaperDeep(root);
}

function organizeSectors(root){
  const detail=qs(root,'.sector-detail');
  if(detail&&!qs(detail,'[data-v5-tab-shell="sector-detail"]')){
    const coins=qs(detail,'.sector-coin-workspace');
    const historyHead=qs(detail,'.sector-history-head');
    const charts=qs(detail,'.sector-charts');
    if(coins&&historyHead&&charts)makeTabs({anchor:historyHead,group:'sector-detail',tabs:[
      {key:'coins',label:'테마 코인',nodes:[coins]},
      {key:'history',label:'흐름',nodes:[historyHead,charts]},
    ]});
  }
  const method=qs(root,'.sector-method');
  if(method)wrapAdvancedSection(method,{title:'테마 분류 기준',summary:'테마를 나누고 점수를 계산하는 기준입니다.'});
  qsa(root,'.market-lifecycle-panel,.market-lifecycle-card').forEach(section=>wrapAdvancedSection(section,{title:'시장 분류 보조정보',summary:'현재 테마 선택보다 우선하지 않는 보조 정보입니다.'}));
}

function organizeSystem(root){
  const operations=qs(root,'.operations-grid');
  const ci=qs(root,'[data-ci-panel]');
  const diagnostics=qs(root,'.component-panel');
  if(operations)wrapAdvancedSection(operations,{title:'서비스 운영 상태',summary:'투자 판단과 관계없는 서버·백업·연결 상태입니다.'});
  if(ci)wrapAdvancedSection(ci,{title:'코드 점검 상태',summary:'배포와 코드 검사 상태는 문제가 있을 때 확인합니다.'});
  if(diagnostics)wrapAdvancedSection(diagnostics,{title:'세부 실행 상태',summary:'문제가 있을 때만 확인하는 운영 정보입니다.'});
}

function organizeRecords(root){
  const head=qs(root,'.records-head,.page-head');
  if(head)root.classList.add('v5-records-page');
}

function organize(root){
  const route=root?.dataset?.pageRoute||'';
  if(route==='research')organizeResearch(root);
  else if(route==='assets')organizeAssets(root);
  else if(route==='strategy')organizeStrategy(root);
  else if(route==='paper')organizePaper(root);
  else if(route==='sectors')organizeSectors(root);
  else if(route==='records')organizeRecords(root);
  else if(route==='system')organizeSystem(root);
}

export function installInformationArchitectureV5(root){
  if(!root)return()=>{};
  let queued=false;
  const queue=()=>{
    if(queued)return;
    queued=true;
    requestAnimationFrame(()=>{queued=false;organize(root)});
  };
  const observer=new MutationObserver(queue);
  observer.observe(root,{childList:true,subtree:true});
  root.addEventListener('click',event=>{
    const tab=event.target.closest('[data-v5-tab][data-v5-tab-group]');
    if(tab){selectPanel(root,tab.dataset.v5TabGroup,tab.dataset.v5Tab);return}
    const mode=event.target.closest('[data-v5-mode]');
    if(mode){root.dataset.v5Mode=mode.dataset.v5Mode;updateDecisionLens(root);return}
    const frame=event.target.closest('[data-v5-timeframe]');
    if(frame){root.dataset.v5Timeframe=frame.dataset.v5Timeframe;updateDecisionLens(root);return}
  });
  queue();
  return()=>observer.disconnect();
}
