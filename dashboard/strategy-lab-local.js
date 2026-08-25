(()=>{
  if(window.__strategyLabLocalLoaded)return;
  window.__strategyLabLocalLoaded=true;

  const q=(s,r=document)=>r.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=v=>Number(v||0),pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`,tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  let state=null,busy=false,timer=0;

  async function apiJson(path,options={}){
    if(typeof window.api==='function')return window.api(path,options);
    if(typeof api==='function')return api(path,options);
    const headers={...(options.headers||{})};
    if(options.body&&typeof options.body!=='string'){headers['content-type']='application/json';options.body=JSON.stringify(options.body)}
    const response=await fetch(path,{...options,headers,cache:'no-store'});
    if(!response.ok){const body=await response.json().catch(()=>({}));const err=new Error(body.detail||`${response.status}`);err.status=response.status;throw err}
    return response.json();
  }

  function ensurePanel(){
    const grid=q('[data-view-panel="settings"] .settings-grid');if(!grid)return null;
    let panel=q('#strategyLabLocalPanel');if(panel)return panel;
    panel=document.createElement('article');panel.id='strategyLabLocalPanel';panel.className='panel strategy-lab-local wide-settings';
    const anchor=q('#researchComponentPanel',grid)||q('#staticUiBuild',grid);if(anchor)grid.insertBefore(panel,anchor);else grid.appendChild(panel);
    return panel;
  }

  function builtins(){return Array.isArray(state?.builtins)?state.builtins:[]}
  function styleOptions(selected=''){return builtins().map(s=>`<option value="${esc(s.style)}" ${s.style===selected?'selected':''}>${esc(s.label||s.style)}</option>`).join('')}
  function selectedSpec(key){return builtins().find(s=>s.style===key)||builtins()[0]||{}}
  function advancedFields(spec){const fields=[['entry_regime','시장 기준',0.1],['entry_score','진입 기준',0.1],['opportunity','기회 기준',0.1],['base_weight_pct','1회 비중 %',0.1],['max_position_pct','최대 비중 %',0.1],['max_buys','최대 매수회차',1],['add_drop_pct','추가매수 하락 %',0.1],['take_profit_pct','익절 %',0.1],['stop_loss_pct','손절 %',0.1],['exit_regime','청산 시장기준',0.1],['min_hold_seconds','최소 보유초',60],['max_volatility_pct','최대 변동성 %',0.1]];return fields.map(([k,label,step])=>`<label>${label}<input data-lab-override="${k}" type="number" step="${step}" placeholder="기본 ${esc(spec[k]??'-')}"></label>`).join('')}

  function render(){
    const panel=ensurePanel();if(!panel||!state)return;
    const custom=Array.isArray(state.custom)?state.custom:[],can=Boolean(state.can_control),baseA=builtins()[1]?.style||builtins()[0]?.style||'balanced',baseB=builtins()[3]?.style||builtins()[0]?.style||'dca',spec=selectedSpec(baseA);
    panel.innerHTML=`<div class="strategy-lab-local-head"><div><p class="panel-kicker">PHASE 4 · LOCAL ONLY</p><h3>조합형 전략 실험</h3><p>두 기본전략을 섞어 별도 PAPER 실험을 만듭니다. 실제 생성·중지는 이 PC에서만 가능하고 외부 Pages는 결과만 조회합니다.</p></div><span class="status-pill ${can?'good':'neutral'}">${can?'이 PC에서 생성 가능':'조회만 가능'}</span></div><div class="strategy-lab-local-grid"><section class="strategy-lab-builder"><h4>새 실험 만들기</h4><form id="strategyLabLocalForm"><div class="strategy-lab-form-grid"><label class="wide">실험 이름<input id="labCustomLabel" maxlength="48" placeholder="예: 역추세 + 분할매수 60/40" required></label><label>거래소<select id="labCustomExchange"><option value="bithumb">빗썸</option><option value="upbit">업비트</option></select></label><label>주 전략<select id="labPrimary">${styleOptions(baseA)}</select></label><label>보조 전략<select id="labSecondary">${styleOptions(baseB)}</select></label><label>주 전략 비중<div class="strategy-lab-mix"><input id="labMix" type="range" min="0" max="100" value="60"><output id="labMixOutput">60%</output></div></label><details class="strategy-lab-advanced"><summary>세부 기준 직접 덮어쓰기</summary><div id="labAdvancedGrid" class="strategy-lab-advanced-grid">${advancedFields(spec)}</div></details></div><div class="strategy-lab-builder-actions"><button class="button" type="submit" ${can?'':'disabled'}>연구 시작</button><span id="labCreateStatus" class="muted"></span></div><p class="strategy-lab-builder-note">최대 사용자 실험은 전체 12개, 거래소별 6개입니다. 새 실험은 기존 adaptive 및 기본 12개 전략 계좌와 완전히 분리됩니다.</p></form></section><section class="strategy-lab-custom-list"><h4>사용자 실험</h4><div class="strategy-lab-custom-list-body">${custom.length?custom.map(r=>`<article class="strategy-lab-custom-row" data-exp="${esc(r.experiment_id)}"><div><h5>${esc(r.label)}</h5><p>${r.exchange==='upbit'?'업비트':'빗썸'} · ${esc(selectedSpec(r.primary_style)?.label||r.primary_style)} ${(n(r.mix_ratio)*100).toFixed(0)}% + ${esc(selectedSpec(r.secondary_style)?.label||r.secondary_style)} ${(100-n(r.mix_ratio)*100).toFixed(0)}%</p><div class="metrics"><span>수익 <b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b></span><span>DD <b>${pct(r.max_drawdown_pct)}</b></span><span>완료 <b>${n(r.closed_trades).toFixed(0)}</b></span><span>보유 <b>${n(r.active_positions).toFixed(0)}</b></span></div></div><div class="strategy-lab-custom-row-actions"><span class="status-pill ${r.status==='running'?'good':'neutral'}">${r.status==='running'?'실행 중':'일시정지'}</span><button type="button" class="button secondary compact" data-lab-status="${r.status==='running'?'paused':'running'}" ${can?'':'disabled'}>${r.status==='running'?'일시정지':'재개'}</button></div></article>`).join(''):`<div class="strategy-lab-local-empty">아직 사용자 조합 실험이 없습니다.</div>`}</div></section></div>`;
    bindForm();
  }

  function bindForm(){const form=q('#strategyLabLocalForm');if(!form)return;const mix=q('#labMix'),out=q('#labMixOutput'),primary=q('#labPrimary');mix?.addEventListener('input',()=>{if(out)out.textContent=`${mix.value}%`});primary?.addEventListener('change',()=>{const box=q('#labAdvancedGrid');if(box)box.innerHTML=advancedFields(selectedSpec(primary.value))});form.addEventListener('submit',createExperiment)}

  async function createExperiment(event){event.preventDefault();if(busy||!state?.can_control)return;busy=true;const status=q('#labCreateStatus');if(status)status.textContent='생성 중…';try{const overrides={};document.querySelectorAll('#strategyLabLocalPanel [data-lab-override]').forEach(input=>{if(input.value!=='')overrides[input.dataset.labOverride]=Number(input.value)});await apiJson('/api/research/strategy-lab/experiments',{method:'POST',body:{exchange:q('#labCustomExchange').value,label:q('#labCustomLabel').value,primary_style:q('#labPrimary').value,secondary_style:q('#labSecondary').value,mix_ratio:Number(q('#labMix').value)/100,overrides}});if(status)status.textContent='생성 완료';await sync()}catch(err){if(status)status.textContent=err?.message||'생성 실패'}finally{busy=false}}

  async function changeStatus(button){if(busy||!state?.can_control)return;const row=button.closest('[data-exp]');if(!row)return;busy=true;button.disabled=true;try{await apiJson(`/api/research/strategy-lab/experiments/${encodeURIComponent(row.dataset.exp)}`,{method:'PATCH',body:{status:button.dataset.labStatus}});await sync()}catch(err){window.alert(err?.message||'상태를 변경하지 못했습니다.')}finally{busy=false}}

  async function sync(){if(busy||document.hidden)return;try{state=await apiJson('/api/research/strategy-lab');render()}catch(_err){const panel=ensurePanel();if(panel&&!state)panel.innerHTML='<div class="empty-state">Strategy Lab 상태를 불러오는 중입니다.</div>'}}
  function install(){ensurePanel();sync();document.addEventListener('click',e=>{const b=e.target.closest?.('#strategyLabLocalPanel [data-lab-status]');if(b)changeStatus(b)});timer=setInterval(sync,10000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync()})}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();