// Historical Build38 module floor: sectors-v36.js?v=38
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
import{createHomePage}from'./pages/home.js?v=47';
import{createDashboardPage}from'./pages/dashboard.js';
import{createResearchPage}from'./pages/research.js?v=40';
import{installDexLaunchResearchPanel}from'./pages/dex-launch-panel.js?v=44';
import{createAssetsPage}from'./pages/assets.js?v=49';
import{createPaperPage}from'./pages/paper.js?v=46';
import{createStrategyPage}from'./pages/strategy.js?v=46.2';
import{createSectorsPage}from'./pages/sectors-v36.js?v=46';
import{createRecordsPage}from'./pages/records.js?v=48';
import{createSystemPage}from'./pages/system.js?v=35';
installSectorImeGuard();installTableSortEnhancer();
const root=document.getElementById('pageRoot'),nav=document.getElementById('mainNav'),journeyNav=document.getElementById('journeyNav'),readerModeControl=document.getElementById('readerModeControl');
installSamePageInteractionContinuity(root);installAmountInputUx(root);installDexLaunchResearchPanel({store,root});
let router=null;
const pages={dashboard:()=>createHomePage({store,navigate:n=>router.go(n)}),'dashboard-detail':()=>createDashboardPage({store,navigate:n=>router.go(n)}),research:()=>createResearchPage({store}),assets:()=>createAssetsPage({store}),paper:()=>createPaperPage({store}),strategy:()=>createStrategyPage({store}),sectors:()=>createSectorsPage({store,navigate:n=>router.go(n)}),records:()=>createRecordsPage({store}),system:()=>createSystemPage({store})};
const GROUPS={dashboard:[['dashboard','오늘 보기'],['dashboard-detail','상세 현황']],'dashboard-detail':[['dashboard','오늘 보기'],['dashboard-detail','상세 현황']],paper:[['paper','가상매매'],['strategy','전략 비교']],strategy:[['paper','가상매매'],['strategy','전략 비교']]};
function renderJourneyNav(name){if(root)root.dataset.pageRoute=name;if(!journeyNav)return;const items=GROUPS[name]||[];journeyNav.classList.toggle('hidden',!items.length);journeyNav.innerHTML=items.map(([route,label])=>`<button data-journey-route="${route}" class="${route===name?'active':''}">${label}</button>`).join('')}
function readerMode(){return store.get().ui.readerMode==='detail'?'detail':'simple'}
function renderReaderMode(){const mode=readerMode();document.documentElement.dataset.readerMode=mode;readerModeControl?.querySelectorAll('[data-reader-mode]').forEach(button=>{const active=button.dataset.readerMode===mode;button.classList.toggle('active',active);button.setAttribute('aria-pressed',active?'true':'false')})}
readerModeControl?.addEventListener('click',e=>{const button=e.target.closest('[data-reader-mode]');if(!button)return;const mode=button.dataset.readerMode==='detail'?'detail':'simple';if(mode===readerMode())return;store.setUi({readerMode:mode},{scope:'reader-mode'});renderReaderMode()});
journeyNav?.addEventListener('click',e=>{const b=e.target.closest('[data-journey-route]');if(b)router.go(b.dataset.journeyRoute)});
router=createRouter({store,root,nav,pages,onChange:renderJourneyNav});
const poller=createSnapshotPoller({store,onUnauthorized:()=>auth.showAuth()});
const auth=createAuth({store,onReady(){poller.start();router.go(store.get().ui.route||'dashboard',{replace:true});renderShell()},onLogout(){poller.stop()}});
function latestSource(state){const pub=fullPublic(state),times=[pub.source_updated_at,pub.published_at,pub.exchanges?.bithumb?.source_updated_at,pub.exchanges?.upbit?.source_updated_at].map(Number).filter(Number.isFinite);return times.length?Math.max(...times):0}
function renderShell(){const s=store.get(),user=s.user,status=document.getElementById('systemStatusBtn'),userBtn=document.getElementById('userMenuBtn');if(userBtn)userBtn.innerHTML=`<span>${esc(user?.display_name||user?.email||'사용자')}</span><small>${user?.role==='owner'?'관리자':'조회'}</small>`;if(status){const ts=latestSource(s);status.textContent=s.error?'데이터 오류':ts?`● 최신 ${age(ts)}`:'● 데이터 대기';status.className=`utility-status ${s.error?'bad':ts?'good':'neutral'}`}}
store.subscribe((_,meta)=>{if(['snapshot','error','user','session-reset'].includes(meta.type))renderShell();if(meta.type==='ui'&&meta.scope==='reader-mode')renderReaderMode();if(meta.type==='snapshot'&&router.current()==='dashboard-detail'&&!root.querySelector('[data-dashboard-root]'))router.render()});
document.getElementById('systemStatusBtn')?.addEventListener('click',()=>router.go('system'));document.getElementById('userMenuBtn')?.addEventListener('click',()=>router.go('system'));renderReaderMode();auth.boot();
