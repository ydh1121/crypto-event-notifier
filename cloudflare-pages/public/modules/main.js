import{store}from'./core/store.js';
import{createRouter}from'./core/router.js';
import{createAuth}from'./core/auth.js';
import{createSnapshotPoller}from'./core/snapshot.js';
import{esc}from'./shared/format.js';
import{installSectorImeGuard}from'./shared/sector-ime-guard.js?v=37';
import{installTableSortEnhancer}from'./shared/table-sort-enhancer.js?v=37';
import{installSamePageInteractionContinuity}from'./shared/ui-continuity.js?v=38';
import{installAmountInputUx}from'./shared/amount-input-ux.js?v=1';
import{installMainstreamUi}from'./shared/mainstream-ui.js?v=1';
import{installThemeToggle}from'./shared/theme.js?v=1';
import{installStrategyDrilldown}from'./shared/strategy-drilldown-v4.js?v=1';
import{installInformationArchitectureV5}from'./shared/information-architecture-v5.js?v=1';
import{createHomePage}from'./pages/v4/home.js?v=1';
import{createDashboardPage}from'./pages/dashboard.js';
import{createResearchPage}from'./pages/research.js?v=40';
import{installDexLaunchResearchPanel}from'./pages/dex-launch-panel.js?v=44';
import{createAssetsPage}from'./pages/assets.js?v=49';
import{createPaperPage}from'./pages/paper.js?v=46';
import{createStrategyPage}from'./pages/strategy.js?v=46.2';
import{createSectorsPage}from'./pages/sectors-v36.js?v=46';
import{createRecordsPage}from'./pages/records.js?v=48';
import{createSystemPage}from'./pages/system.js?v=35';

installSectorImeGuard();
installTableSortEnhancer();
installThemeToggle();

const root=document.getElementById('pageRoot');
const nav=document.getElementById('mainNav');
const journey=document.getElementById('journeyNav');
const reader=document.getElementById('readerModeControl');

installSamePageInteractionContinuity(root);
installAmountInputUx(root);
installDexLaunchResearchPanel({store,root});
installMainstreamUi(document.body);
installInformationArchitectureV5(root);

let router=null;
const pages={
  dashboard:()=>createHomePage({store,navigate:name=>router.go(name)}),
  'dashboard-detail':()=>createDashboardPage({store,navigate:name=>router.go(name)}),
  research:()=>createResearchPage({store}),
  assets:()=>createAssetsPage({store}),
  paper:()=>createPaperPage({store}),
  strategy:()=>createStrategyPage({store}),
  sectors:()=>createSectorsPage({store,navigate:name=>router.go(name)}),
  records:()=>createRecordsPage({store}),
  system:()=>createSystemPage({store}),
};

const GROUPS={
  research:[['research','코인'],['dashboard-detail','시장현황'],['sectors','테마']],
  'dashboard-detail':[['research','코인'],['dashboard-detail','시장현황'],['sectors','테마']],
  sectors:[['research','코인'],['dashboard-detail','시장현황'],['sectors','테마']],
  paper:[['paper','모의투자'],['strategy','매매방법 비교']],
  strategy:[['paper','모의투자'],['strategy','매매방법 비교']],
};

function renderJourney(name){
  if(root)root.dataset.pageRoute=name;
  if(!journey)return;
  const items=GROUPS[name]||[];
  journey.classList.toggle('hidden',!items.length);
  journey.innerHTML=items.map(([route,label])=>`<button data-journey-route="${route}" class="${route===name?'active':''}">${label}</button>`).join('');
}

function readerMode(){return store.get().ui.readerMode==='detail'?'detail':'simple'}
function renderReader(){
  const mode=readerMode();
  document.documentElement.dataset.readerMode=mode;
  reader?.querySelectorAll('[data-reader-mode]').forEach(button=>{
    const active=button.dataset.readerMode===mode;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',active?'true':'false');
  });
}
reader?.addEventListener('click',event=>{
  const button=event.target.closest('[data-reader-mode]');
  if(!button)return;
  const mode=button.dataset.readerMode==='detail'?'detail':'simple';
  if(mode===readerMode())return;
  store.setUi({readerMode:mode},{scope:'reader-mode'});
  renderReader();
  router?.render();
});
journey?.addEventListener('click',event=>{
  const button=event.target.closest('[data-journey-route]');
  if(button)router.go(button.dataset.journeyRoute);
});

router=createRouter({store,root,nav,pages,onChange:renderJourney});
installStrategyDrilldown({store,root,navigate:name=>router.go(name)});
const poller=createSnapshotPoller({store,onUnauthorized:()=>auth.showAuth()});
const auth=createAuth({
  store,
  onReady(){poller.start();router.go(store.get().ui.route||'dashboard',{replace:true});renderShell()},
  onLogout(){poller.stop()},
});

function renderShell(){
  const user=store.get().user;
  const userBtn=document.getElementById('userMenuBtn');
  if(userBtn){
    const name=String(user?.display_name||'사용자').trim()||'사용자';
    userBtn.innerHTML=`<span>${esc(name)}</span><small>${user?.role==='owner'?'관리자':'계정'}</small>`;
  }
}
store.subscribe((_,meta)=>{
  if(['snapshot','error','user','session-reset'].includes(meta.type))renderShell();
  if(meta.type==='ui'&&meta.scope==='reader-mode')renderReader();
});
document.getElementById('userMenuBtn')?.addEventListener('click',()=>router.go('system'));
renderReader();
auth.boot();
