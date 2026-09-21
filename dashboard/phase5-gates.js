(function(){
  if(window.__phase5GatesLoaded)return;
  window.__phase5GatesLoaded=true;

  const q=(selector,root=document)=>root.querySelector(selector);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const labels={PASS:'통과',WAITING:'대기',BLOCKED:'외부 조건 필요',FAILED:'실패'};
  const tones={PASS:'good',WAITING:'warn',BLOCKED:'warn',FAILED:'bad'};
  let busy=false;

  async function apiJson(path){
    if(typeof window.api==='function')return window.api(path);
    if(typeof api==='function')return api(path);
    const response=await fetch(path,{cache:'no-store'});
    if(!response.ok)throw new Error(`${response.status}`);
    return response.json();
  }

  function ensurePanel(){
    const grid=q('[data-view-panel="settings"] .settings-grid');
    if(!grid)return null;
    let panel=q('#phase5GatePanel');
    if(panel)return panel;
    panel=document.createElement('article');
    panel.id='phase5GatePanel';
    panel.className='panel phase5-gate-panel wide-settings';
    const anchor=q('#staticUiBuild',grid);
    if(anchor)grid.insertBefore(panel,anchor);else grid.appendChild(panel);
    return panel;
  }

  function render(data){
    const panel=ensurePanel();if(!panel)return;
    const summary=data?.summary||{};
    const gates=Array.isArray(data?.gates)?data.gates:[];
    const overall=String(data?.overall_status||'FAILED').toUpperCase();
    panel.innerHTML=`
      <div class="panel-head phase5-gate-head">
        <div>
          <p class="panel-kicker">PHASE 5 GATE MATRIX</p>
          <h3>실데이터 검증 게이트</h3>
          <p class="panel-copy">코드 통과와 실제 데이터 준비 상태를 분리해 보여줍니다. 대기·외부 조건 필요는 실패가 아닙니다.</p>
        </div>
        <span class="status-pill ${tones[overall]||'neutral'}">${esc(labels[overall]||overall)}</span>
      </div>
      <div class="phase5-gate-summary">
        ${['PASS','WAITING','BLOCKED','FAILED'].map(key=>`<div><span>${esc(labels[key])}</span><b>${Number(summary[key]||0)}</b></div>`).join('')}
      </div>
      <div class="phase5-gate-list">
        ${gates.map(gate=>{
          const status=String(gate?.status||'FAILED').toUpperCase();
          return `<section class="phase5-gate-row">
            <div class="phase5-gate-title"><b>${esc(gate?.id||'unknown')}</b><span class="status-pill ${tones[status]||'neutral'}">${esc(labels[status]||status)}</span></div>
            <p>${esc(gate?.summary||'')}</p>
            ${gate?.action_required?`<small>${esc(gate.action_required)}</small>`:''}
          </section>`;
        }).join('')}
      </div>
      <p class="research-component-footnote">조회 전용 · 외부 네트워크 요청 0 · API credential 값은 표시하지 않습니다.</p>`;
  }

  async function sync(){
    if(busy||document.hidden)return;
    busy=true;
    try{render(await apiJson('/api/research/phase5-gates'));}
    catch(_err){
      const panel=ensurePanel();
      if(panel)panel.innerHTML='<div class="empty-state">Phase 5 게이트 상태를 불러오는 중입니다.</div>';
    }finally{busy=false;}
  }

  function install(){
    ensurePanel();sync();
    window.setInterval(sync,15000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
