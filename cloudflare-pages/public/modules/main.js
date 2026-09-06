import{store}from'./core/store.js';
import{createRouter}from'./core/router.js';
import{createAuth}from'./core/auth.js';
import{createSnapshotPoller}from'./core/snapshot.js';
import{fullPublic}from'./shared/selectors.js';
import{age,esc}from'./shared/format.js';
import{createHomePage}from'./pages/v2/home.js?v=70';
import{createDashboardPage}from'./pages/v2/dashboard.js?v=70';
import{createResearchPage}from'./pages/v2/research.js?v=70';
import{createAssetsPage}from'./pages/v2/assets.js?v=70';
import{createPaperPage}from'./pages/v2/paper.js?v=70';
import{createStrategyPage}from'./pages/v2/strategy.js?v=70';
import{createSectorsPage}from'./pages/v2/sectors.js?v=70';
import{createRecordsPage}from'./pages/v2/records.js?v=70';
import{createSystemPage}from'./pages/v2/system.js?v=70';

const root=document.getElementById('pageRoot');
const nav=document.getElementById('mainNav');
const journey=document.getElementById('journeyNav');
const reader=document.getElementById('readerModeControl');
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
const GROUPS={dashboard:[['dashboard','홈'],['dashboard-detail','시장 자세히']],'dashboard-detail':[['dashboard','홈'],['dashboard-detail','시장 자세히']],paper:[['paper','가상매매'],['strategy','방법 비교']],strategy:[['paper','가상매매'],['strategy','방법 비교']]};

function renderJourney(name){if(root)root.dataset.pageRoute=name;if(!journey)return;const items=GROUPS[name]||[];journey.classList.toggle('hidden',!items.length);journey.innerHTML=items.map(([route,label])=>`<button data-journey-route="${route}" class="${route===name?'active':''}">${label}</button>`).join('')}
function readerMode(){return store.get().ui.readerMode==='detail'?'detail':'simple'}
function renderReader(){const mode=readerMode();document.documentElement.dataset.readerMode=mode;reader?.querySelectorAll('[data-reader-mode]').forEach(button=>{const active=button.dataset.readerMode===mode;button.classList.toggle('active',active);button.setAttribute('aria-pressed',active?'true':'false')})}
reader?.addEventListener('click',event=>{const button=event.target.closest('[data-reader-mode]');if(!button)return;const mode=button.dataset.readerMode==='detail'?'detail':'simple';if(mode===readerMode())return;store.setUi({readerMode:mode},{scope:'reader-mode'});renderReader();router?.render()});
journey?.addEventListener('click',event=>{const button=event.target.closest('[data-journey-route]');if(button)router.go(button.dataset.journeyRoute)});
router=createRouter({store,root,nav,pages,onChange:renderJourney});
const poller=createSnapshotPoller({store,onUnauthorized:()=>auth.showAuth()});
const auth=createAuth({store,onReady(){poller.start();router.go(store.get().ui.route||'dashboard',{replace:true});renderShell()},onLogout(){poller.stop()}});
function latestSource(state){const pub=fullPublic(state),times=[pub.source_updated_at,pub.published_at,pub.exchanges?.bithumb?.source_updated_at,pub.exchanges?.upbit?.source_updated_at].map(Number).filter(Number.isFinite);return times.length?Math.max(...times):0}
function renderShell(){const state=store.get(),user=state.user,status=document.getElementById('systemStatusBtn'),userBtn=document.getElementById('userMenuBtn');if(userBtn){const name=String(user?.display_name||'사용자').trim()||'사용자';userBtn.innerHTML=`<span>${esc(name)}</span><small>${user?.role==='owner'?'관리자':'조회'}</small>`}if(status){const ts=latestSource(state);status.textContent=state.error?'자료 확인 필요':ts?`최신 ${age(ts)}`:'자료 기다리는 중';status.className=`utility-status ${state.error?'bad':ts?'good':'neutral'}`}}
store.subscribe((_,meta)=>{if(['snapshot','error','user','session-reset'].includes(meta.type))renderShell();if(meta.type==='ui'&&meta.scope==='reader-mode')renderReader()});
document.getElementById('systemStatusBtn')?.addEventListener('click',()=>router.go('system'));
document.getElementById('userMenuBtn')?.addEventListener('click',()=>router.go('system'));
renderReader();auth.boot();
