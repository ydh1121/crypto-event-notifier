// Cloudflare viewer v2 shell. Data contracts and route ownership remain unchanged.
import{store}from'./core/store.js';
import{createRouter}from'./core/router.js';
import{createAuth}from'./core/auth.js';
import{createSnapshotPoller}from'./core/snapshot.js';
import{fullPublic}from'./shared/selectors.js';
import{age,esc}from'./shared/format.js';
import{installSectorImeGuard}from'./shared/sector-ime-guard.js?v=37';
import{installTableSortEnhancer}from'./shared/table-sort-enhancer.js?v=37';
import{installSamePageInteractionContinuity}from'./shared/ui-continuity.js?v=38';
import{installAmountInputUx}from'./shared/amount-input-ux.js?v=1';
import{createHomePage}from'./pages/home.js?v=60';
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

const root=document.getElementById('pageRoot');
const nav=document.getElementById('mainNav');
const journeyNav=document.getElementById('journeyNav');
const readerModeControl=document.getElementById('readerModeControl');

installSamePageInteractionContinuity(root);
installAmountInputUx(root);
installDexLaunchResearchPanel({store,root});

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
  dashboard:[['dashboard','홈'],['dashboard-detail','시장 자세히']],
  'dashboard-detail':[['dashboard','홈'],['dashboard-detail','시장 자세히']],
  paper:[['paper','가상매매'],['strategy','방법 비교']],
  strategy:[['paper','가상매매'],['strategy','방법 비교']],
};

function renderJourneyNav(name){
  if(root)root.dataset.pageRoute=name;
  if(!journeyNav)return;
  const items=GROUPS[name]||[];
  journeyNav.classList.toggle('hidden',!items.length);
  journeyNav.innerHTML=items.map(([route,label])=>`<button data-journey-route="${route}" class="${route===name?'active':''}">${label}</button>`).join('');
}

function readerMode(){return store.get().ui.readerMode==='detail'?'detail':'simple'}
function renderReaderMode(){
  const mode=readerMode();
  document.documentElement.dataset.readerMode=mode;
  readerModeControl?.querySelectorAll('[data-reader-mode]').forEach(button=>{
    const active=button.dataset.readerMode===mode;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',active?'true':'false');
  });
}

readerModeControl?.addEventListener('click',event=>{
  const button=event.target.closest('[data-reader-mode]');
  if(!button)return;
  const mode=button.dataset.readerMode==='detail'?'detail':'simple';
  if(mode===readerMode())return;
  store.setUi({readerMode:mode},{scope:'reader-mode'});
  renderReaderMode();
});

journeyNav?.addEventListener('click',event=>{
  const button=event.target.closest('[data-journey-route]');
  if(button)router.go(button.dataset.journeyRoute);
});

router=createRouter({store,root,nav,pages,onChange:renderJourneyNav});
const poller=createSnapshotPoller({store,onUnauthorized:()=>auth.showAuth()});
const auth=createAuth({
  store,
  onReady(){poller.start();router.go(store.get().ui.route||'dashboard',{replace:true});renderShell()},
  onLogout(){poller.stop()},
});

function latestSource(state){
  const pub=fullPublic(state);
  const times=[pub.source_updated_at,pub.published_at,pub.exchanges?.bithumb?.source_updated_at,pub.exchanges?.upbit?.source_updated_at].map(Number).filter(Number.isFinite);
  return times.length?Math.max(...times):0;
}

function renderShell(){
  const state=store.get();
  const user=state.user;
  const status=document.getElementById('systemStatusBtn');
  const userBtn=document.getElementById('userMenuBtn');
  if(userBtn){
    const name=String(user?.display_name||'사용자').trim()||'사용자';
    userBtn.innerHTML=`<span>${esc(name)}</span><small>${user?.role==='owner'?'관리자':'조회'}</small>`;
  }
  if(status){
    const ts=latestSource(state);
    status.textContent=state.error?'자료 확인 필요':ts?`최신 ${age(ts)}`:'자료 기다리는 중';
    status.className=`utility-status ${state.error?'bad':ts?'good':'neutral'}`;
  }
}

store.subscribe((_,meta)=>{
  if(['snapshot','error','user','session-reset'].includes(meta.type))renderShell();
  if(meta.type==='ui'&&meta.scope==='reader-mode')renderReaderMode();
  if(meta.type==='snapshot'&&router.current()==='dashboard-detail'&&!root.querySelector('[data-dashboard-root]'))router.render();
});

document.getElementById('systemStatusBtn')?.addEventListener('click',()=>router.go('system'));
document.getElementById('userMenuBtn')?.addEventListener('click',()=>router.go('system'));
renderReaderMode();
auth.boot();
