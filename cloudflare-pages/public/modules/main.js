import{store}from'./core/store.js';
import{createRouter}from'./core/router.js';
import{createAuth}from'./core/auth.js';
import{createSnapshotPoller}from'./core/snapshot.js';
import{fullPublic}from'./shared/selectors.js';
import{age,esc}from'./shared/format.js';
import{installSectorImeGuard}from'./shared/sector-ime-guard.js?v=37';
import{installTableSortEnhancer}from'./shared/table-sort-enhancer.js?v=37';
import{createDashboardPage}from'./pages/dashboard.js';
import{createResearchPage}from'./pages/research.js';
import{createAssetsPage}from'./pages/assets.js';
import{createPaperPage}from'./pages/paper.js';
import{createStrategyPage}from'./pages/strategy.js';
import{createSectorsPage}from'./pages/sectors-v36.js?v=36';
import{createRecordsPage}from'./pages/records.js';
import{createSystemPage}from'./pages/system.js?v=35';

installSectorImeGuard();
installTableSortEnhancer();
const root=document.getElementById('pageRoot'),nav=document.getElementById('mainNav');
let router=null;
const pages={
  dashboard:()=>createDashboardPage({store,navigate:n=>router.go(n)}),
  research:()=>createResearchPage({store}),
  assets:()=>createAssetsPage({store}),
  paper:()=>createPaperPage({store}),
  strategy:()=>createStrategyPage({store}),
  sectors:()=>createSectorsPage({store,navigate:n=>router.go(n)}),
  records:()=>createRecordsPage({store}),
  system:()=>createSystemPage({store})
};
router=createRouter({store,root,nav,pages});
const poller=createSnapshotPoller({store,onUnauthorized:()=>auth.showAuth()});
const auth=createAuth({store,onReady(){poller.start();router.go(store.get().ui.route||'dashboard',{replace:true});renderShell()},onLogout(){poller.stop()}});
function latestSource(state){const pub=fullPublic(state),times=[pub.source_updated_at,pub.published_at,pub.exchanges?.bithumb?.source_updated_at,pub.exchanges?.upbit?.source_updated_at].map(Number).filter(Number.isFinite);return times.length?Math.max(...times):0}
function renderShell(){const s=store.get(),user=s.user,status=document.getElementById('systemStatusBtn'),userBtn=document.getElementById('userMenuBtn');if(userBtn)userBtn.innerHTML=`<span>${esc(user?.display_name||user?.email||'사용자')}</span><small>${user?.role==='owner'?'관리자':'조회'}</small>`;if(status){const ts=latestSource(s);status.textContent=s.error?'데이터 오류':ts?`● 최신 ${age(ts)}`:'● 데이터 대기';status.className=`utility-status ${s.error?'bad':ts?'good':'neutral'}`}}
store.subscribe((_,meta)=>{if(['snapshot','error','user','session-reset'].includes(meta.type))renderShell();if(meta.type==='snapshot'&&router.current()==='dashboard'&&!root.querySelector('[data-dashboard-root]'))router.render()});
document.getElementById('systemStatusBtn')?.addEventListener('click',()=>router.go('system'));
document.getElementById('userMenuBtn')?.addEventListener('click',()=>router.go('system'));
auth.boot();
