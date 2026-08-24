(()=>{
  if(window.__assetParityShellLoaded)return;
  window.__assetParityShellLoaded=true;

  const q=(selector,root=document)=>root.querySelector(selector);
  let scheduled=0;

  function setText(node,text){if(node&&node.textContent!==text)node.textContent=text}

  function buildShell(){
    const panel=q('[data-view-panel="coin"]');
    if(!panel)return;

    const head=q('.page-head',panel);
    if(head){
      setText(q('.kicker',head),'ASSET WORKSPACE');
      setText(q('h2',head),'자산 분석');
      setText(q('p:not(.kicker)',head),'선택한 자산의 현재 판단, 가상계좌, 매매 계획과 실제 보유분을 한 화면에서 봅니다.');
      const picker=q('.coin-picker',head);
      if(picker&&picker.firstChild?.nodeType===Node.TEXT_NODE)picker.firstChild.nodeValue='자산 ';
    }

    let layout=q('#assetLocalLayout',panel);
    if(!layout){
      layout=document.createElement('section');
      layout.id='assetLocalLayout';
      layout.className='asset-local-layout';
      layout.innerHTML='<div id="assetLocalPrimary" class="asset-local-primary"></div><aside id="assetLocalAside" class="asset-local-aside"><div class="asset-local-aside-head"><p class="kicker">MY ASSETS</p><h3>내 실제 자산</h3><p>로그인 계정에 조회 권한이 있는 보유분만 표시합니다.</p></div></aside>';
      head?.insertAdjacentElement('afterend',layout);
    }

    const primary=q('#assetLocalPrimary',layout);
    const aside=q('#assetLocalAside',layout);
    const coinCard=q('#coinDetailCard');
    const detail=q('#marketResearchDetail');
    const holdings=q('#holdingsCard');

    if(coinCard&&coinCard.parentElement!==primary)primary.appendChild(coinCard);
    if(detail&&detail.parentElement!==primary)primary.appendChild(detail);
    if(holdings&&holdings.parentElement!==aside)aside.appendChild(holdings);

    panel.classList.add('asset-local-ready');
  }

  function schedule(){
    cancelAnimationFrame(scheduled);
    scheduled=requestAnimationFrame(buildShell);
  }

  const observer=new MutationObserver(schedule);
  function install(){
    buildShell();
    observer.observe(document.body,{childList:true,subtree:true});
    document.addEventListener('click',event=>{
      if(event.target.closest?.('[data-view="coin"]')||event.target.closest?.('[data-open-market]'))setTimeout(schedule,50);
    });
    document.getElementById('coinSelect')?.addEventListener('change',()=>setTimeout(schedule,30));
    window.addEventListener('resize',schedule,{passive:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
