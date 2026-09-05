(function(){
  if(window.__dashboardSyncWatchUi)return;
  window.__dashboardSyncWatchUi=true;

  const BUILD='2026.08.24-7';
  let seenCommit='';
  let capitalLoaded=false;

  function ensureCapitalAssets(){
    if(!document.querySelector('link[data-research-capital]')){
      const link=document.createElement('link');
      link.rel='stylesheet';
      link.href=`./research-capital.css?v=${encodeURIComponent(BUILD)}`;
      link.dataset.researchCapital='1';
      document.head.appendChild(link);
    }
    if(!capitalLoaded&&!window.__researchCapitalLoaded&&!document.querySelector('script[data-research-capital]')){
      capitalLoaded=true;
      const script=document.createElement('script');
      script.src=`./research-capital.js?v=${encodeURIComponent(BUILD)}`;
      script.dataset.researchCapital='1';
      script.onload=()=>{capitalLoaded=false};
      script.onerror=()=>{capitalLoaded=false;script.remove()};
      document.body.appendChild(script);
    }
  }

  function normalizeBuildMarker(){
    const staticMarker=document.querySelector('#staticUiBuild');
    const dynamic=document.querySelector('#uiBuildMarker');
    if(dynamic)dynamic.remove();
    if(staticMarker){
      const pill=staticMarker.querySelector('.status-pill');
      if(pill)pill.textContent=`UI ${BUILD}`;
      const copy=staticMarker.querySelector('.panel-copy');
      if(copy)copy.textContent='이 표시가 보이면 최신 대시보드 파일이 로컬 브라우저에 적용된 상태입니다.';
    }
  }

  function reloadForCommit(commit){
    const url=new URL(location.href);
    url.searchParams.set('build',String(commit||BUILD).slice(0,12));
    location.replace(url.toString());
  }

  async function pollBuild(){
    if(document.hidden)return;
    try{
      const response=await fetch(`./runtime-build.json?t=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)return;
      const data=await response.json();
      const commit=String(data?.commit||'').trim();
      if(!commit)return;
      if(!seenCommit){seenCommit=commit;return}
      if(commit!==seenCommit){
        seenCommit=commit;
        reloadForCommit(commit);
      }
    }catch(_err){}
  }

  function install(){
    normalizeBuildMarker();
    ensureCapitalAssets();
    pollBuild();
    setInterval(pollBuild,3000);
    setInterval(()=>{normalizeBuildMarker();ensureCapitalAssets()},5000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollBuild()});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
