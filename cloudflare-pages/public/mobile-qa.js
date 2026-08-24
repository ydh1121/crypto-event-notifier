(()=>{
  if(window.__viewerMobileQaLoaded)return;
  window.__viewerMobileQaLoaded=true;

  const intentLabels={
    add:'추가 매수',buy:'신규 매수',explore:'탐색 매수',idle_explore:'장기대기 탐색',
    sell:'매도',hold:'보유',wait:'관찰',analysis_error:'분석 오류'
  };

  function patchPlan(root){
    if(!root)return;
    const intent=root.querySelector('.parity-plan-head b');
    if(intent){
      const key=String(intent.textContent||'').trim().toLowerCase();
      if(intentLabels[key])intent.textContent=intentLabels[key];
    }
    [...root.querySelectorAll('.parity-plan-grid>div')].forEach(card=>{
      const label=String(card.querySelector('span')?.textContent||'').trim();
      const value=card.querySelector('strong,b');
      if(!value)return;
      const current=String(value.textContent||'').trim();
      if(current&&current!=='-'&&current!=='0 / 0')return;
      let replacement='계산 중';
      if(label.includes('추가매수')||label.includes('진입'))replacement='조건 충족 시 계산';
      else if(label.includes('목표가'))replacement='포지션 기준 계산 중';
      else if(label.includes('손절'))replacement='포지션 생성 후 계산';
      else if(label.includes('분할'))replacement='계획 계산 중';
      value.textContent=replacement;
      value.classList.add('mobile-plan-fallback');
    });
  }

  function patchRows(list){
    if(!list)return;
    [...list.querySelectorAll('[data-open-market]')].forEach(row=>{
      row.removeAttribute('style');
      row.style.minHeight='70px';
    });
  }

  function install(){
    const detail=document.querySelector('#parityResultDetail');
    const list=document.querySelector('#marketList');
    patchPlan(detail);patchRows(list);
    if(detail){new MutationObserver(()=>requestAnimationFrame(()=>patchPlan(detail))).observe(detail,{childList:true,subtree:true,characterData:true});}
    if(list){new MutationObserver(()=>requestAnimationFrame(()=>patchRows(list))).observe(list,{childList:true,subtree:true});}
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){patchPlan(detail);patchRows(list)}});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
