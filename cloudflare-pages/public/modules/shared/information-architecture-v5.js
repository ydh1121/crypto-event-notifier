const qs=(root,selector)=>root?.querySelector(selector)||null;

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

function organizeResearch(root){
  const workspace=qs(root,'.research-workspace');
  const listing=qs(root,'.listing-history-panel');
  if(workspace&&listing){
    workspace.after(listing);
    wrapAdvancedSection(listing,{title:'상장 전후 반응',summary:'선택 코인 분석과 분리해 필요할 때만 확인합니다.'});
  }
}

function organizeAssets(root){
  const workspace=qs(root,'.asset-workspace');
  const history=qs(root,'.asset-history-panel');
  if(workspace&&history){
    workspace.after(history);
    wrapAdvancedSection(history,{title:'자산 변화 이력',summary:'현재 보유 판단을 먼저 보고 과거 흐름은 필요할 때 확인합니다.'});
  }
}

function strategyPanels(root){
  const breakdown=qs(root,'#strategyBreakdown');
  const evidence=qs(root,'#strategyEvidence');
  if(!breakdown||!evidence)return;
  let shell=qs(root,'.v5-strategy-sections');
  if(!shell){
    shell=document.createElement('section');
    shell.className='v5-strategy-sections';
    shell.innerHTML='<nav class="v5-section-tabs" aria-label="선택 매매방법 상세"><button type="button" data-v5-strategy-tab="coins" class="active">코인별 성과</button><button type="button" data-v5-strategy-tab="evidence">성적·검증</button></nav><div data-v5-strategy-panel="coins"></div><div data-v5-strategy-panel="evidence" class="hidden"></div>';
    breakdown.before(shell);
    shell.querySelector('[data-v5-strategy-panel="coins"]').appendChild(breakdown);
    shell.querySelector('[data-v5-strategy-panel="evidence"]').appendChild(evidence);
  }
}

function selectStrategyPanel(root,key){
  root.querySelectorAll('[data-v5-strategy-tab]').forEach(button=>button.classList.toggle('active',button.dataset.v5StrategyTab===key));
  root.querySelectorAll('[data-v5-strategy-panel]').forEach(panel=>panel.classList.toggle('hidden',panel.dataset.v5StrategyPanel!==key));
}

function organizeStrategy(root){strategyPanels(root)}

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
}

function organizeSystem(root){
  const operations=qs(root,'.operations-grid');
  const diagnostics=qs(root,'.component-panel');
  if(operations&&!operations.closest('[data-v5-collapsible]'))wrapAdvancedSection(operations,{title:'서비스 운영 상태',summary:'투자 판단과 관계없는 서버·백업·연결 상태입니다.'});
  if(diagnostics&&!diagnostics.closest('[data-v5-collapsible]'))wrapAdvancedSection(diagnostics,{title:'세부 실행 상태',summary:'문제가 있을 때만 확인하는 운영 정보입니다.'});
}

function organize(root){
  const route=root?.dataset?.pageRoute||'';
  if(route==='research')organizeResearch(root);
  else if(route==='assets')organizeAssets(root);
  else if(route==='strategy')organizeStrategy(root);
  else if(route==='paper')organizePaper(root);
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
    const tab=event.target.closest('[data-v5-strategy-tab]');
    if(tab){selectStrategyPanel(root,tab.dataset.v5StrategyTab);return}
  });
  queue();
  return()=>observer.disconnect();
}
