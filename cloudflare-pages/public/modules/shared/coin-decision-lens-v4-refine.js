const MODES=[['short','단타'],['swing','스윙'],['dca','적립식']];
const FRAMES=[['15m','15분'],['30m','30분'],['1h','1시간'],['4h','4시간'],['1d','일봉'],['1w','주봉']];

function esc(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}

export function installCoinDecisionLens({store,root}){
  if(!root)return()=>{};
  let mode='short',frame='15m',queued=false;

  function renderState(panel){
    if(!panel)return;
    panel.querySelectorAll('[data-decision-mode]').forEach(button=>button.classList.toggle('active',button.dataset.decisionMode===mode));
    panel.querySelectorAll('[data-decision-frame]').forEach(button=>button.classList.toggle('active',button.dataset.decisionFrame===frame));
    const modeLabel=MODES.find(([key])=>key===mode)?.[1]||'단타';
    const frameLabel=FRAMES.find(([key])=>key===frame)?.[1]||'15분';
    const selected=panel.querySelector('[data-decision-selected]');
    const selectedLabel=`${modeLabel} · ${frameLabel}`;
    if(selected&&selected.textContent!==selectedLabel)selected.textContent=selectedLabel;
    const dca=panel.querySelector('[data-dca-note]');
    if(dca)dca.hidden=mode!=='dca';
  }

  function enhance(){
    if(root.dataset.pageRoute!=='research')return;
    const detail=root.querySelector('.research-detail');
    const hero=detail?.querySelector('.decision-hero');
    if(!detail||!hero)return;
    let panel=detail.querySelector('.v4-refine-decision-lens');
    if(!panel){
      const sourceLabel=String(store?.get?.().ui?.researchSourceStrategyLabel||'').trim();
      panel=document.createElement('section');
      panel.className='v4-refine-decision-lens';
      panel.innerHTML=`<header><div><span>매매 기준</span><h3>이 코인을 어떤 방식으로 볼지 선택</h3></div>${sourceLabel?`<strong>${esc(sourceLabel)}에서 이동</strong>`:''}</header><div class="v4-refine-lens-line"><b>매매 방식</b><div class="v4-refine-chip-group">${MODES.map(([key,label])=>`<button type="button" data-decision-mode="${key}">${label}</button>`).join('')}</div></div><div class="v4-refine-lens-line"><b>시간 기준</b><div class="v4-refine-chip-group frames">${FRAMES.map(([key,label])=>`<button type="button" data-decision-frame="${key}">${label}</button>`).join('')}</div></div><div class="v4-refine-lens-result"><span><small>선택 기준</small><b data-decision-selected></b></span><p>현재 V4에서 실제 계산 중인 진입·추가매수·목표·손실 제한 값은 아래 기존 영역에 그대로 표시합니다. 시간 기준별 별도 계산값은 계산기가 연결되기 전에는 만들지 않습니다.</p></div><div class="v4-refine-dca-note" data-dca-note hidden><b>적립식 적격성</b><span>프로젝트 존속기간 · 실제 실적 · 투자사 · 사업성 · 개발 지속성 · 공급구조를 기준으로 별도 판정할 예정이며, 아직 실제 적격성 계산값은 없습니다.</span></div>`;
      hero.after(panel);
    }
    renderState(panel);
  }

  function queue(){if(queued)return;queued=true;queueMicrotask(()=>{queued=false;enhance()})}
  function click(event){
    const modeButton=event.target.closest('[data-decision-mode]');
    if(modeButton&&root.contains(modeButton)){mode=modeButton.dataset.decisionMode||'short';renderState(modeButton.closest('.v4-refine-decision-lens'));return}
    const frameButton=event.target.closest('[data-decision-frame]');
    if(frameButton&&root.contains(frameButton)){frame=frameButton.dataset.decisionFrame||'15m';renderState(frameButton.closest('.v4-refine-decision-lens'))}
  }

  const observer=new MutationObserver(queue);
  observer.observe(root,{childList:true,subtree:true});
  root.addEventListener('click',click);
  queue();
  return()=>{observer.disconnect();root.removeEventListener('click',click)};
}
