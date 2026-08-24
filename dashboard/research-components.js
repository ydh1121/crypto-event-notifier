(function(){
  if(window.__researchComponentsLoaded)return;
  window.__researchComponentsLoaded=true;

  const q=(selector,root=document)=>root.querySelector(selector);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let busy=false;
  let timer=0;
  let snapshot=null;

  async function apiJson(path,options={}){
    if(typeof window.api==='function')return window.api(path,options);
    if(typeof api==='function')return api(path,options);
    const headers={...(options.headers||{})};
    if(options.body&&typeof options.body!=='string'){
      headers['content-type']='application/json';
      options.body=JSON.stringify(options.body);
    }
    const response=await fetch(path,{...options,headers,cache:'no-store'});
    if(!response.ok)throw new Error(`${response.status}`);
    return response.json();
  }

  function markBuild(){
    const pill=q('#staticUiBuild .status-pill');if(pill)pill.textContent='UI 2026.08.24-9';
    const copy=q('#staticUiBuild .panel-copy');if(copy)copy.textContent='Photo-eBook 내비게이션 + 24시간 연구 구성요소 관리 화면이 적용된 버전입니다.';
  }
  function ageText(ts){
    const value=Number(ts||0);if(!value)return'아직 없음';
    const sec=Math.max(0,Math.floor(Date.now()/1000-value));
    if(sec<10)return'방금 전';
    if(sec<60)return`${sec}초 전`;
    if(sec<3600)return`${Math.floor(sec/60)}분 전`;
    if(sec<86400)return`${Math.floor(sec/3600)}시간 전`;
    return`${Math.floor(sec/86400)}일 전`;
  }
  function intervalText(seconds){
    const sec=Number(seconds||0);if(sec>=3600)return`${Math.round(sec/3600)}시간마다`;
    if(sec>=60)return`${Math.round(sec/60)}분마다`;
    return`${Math.round(sec)}초마다`;
  }
  function statusMeta(status,enabled){
    if(!enabled)return['꺼짐','neutral'];
    return ({healthy:['정상','good'],running:['실행 중','good'],degraded:['확인 필요','bad'],starting:['시작 중','warn'],offline:['연결 안 됨','bad'],stopped:['꺼짐','neutral']})[status]||['확인 중','warn'];
  }
  function resultText(row){
    const result=row?.last_result||{};
    if(row.name==='warehouse-export'){
      const count=Number(result.exported_rows||0);
      if(result.status==='waiting_for_source_db')return'가상매매 DB 생성 대기 중';
      return count>0?`최근 ${count.toLocaleString('ko-KR')}개 기록 추가 저장`:'새로 저장할 기록 없음';
    }
    if(row.name==='reference-version-watch'){
      const refs=snapshot?.references||{};
      if(Number(refs.failed)>0)return`${refs.failed}개 확인 실패`;
      if(Number(refs.updates)>0)return`${refs.updates}개 새 버전 감지`;
      if(Number(refs.total)>0)return`${refs.total}개 레포 확인 완료`;
      return'첫 확인 대기 중';
    }
    return'';
  }

  function ensurePanel(){
    const grid=q('[data-view-panel="settings"] .settings-grid');if(!grid)return null;
    let panel=q('#researchComponentPanel');if(panel)return panel;
    panel=document.createElement('article');
    panel.id='researchComponentPanel';
    panel.className='panel research-component-panel wide-settings';
    const anchor=q('#staticUiBuild',grid);
    if(anchor)grid.insertBefore(panel,anchor);else grid.appendChild(panel);
    return panel;
  }

  function render(data){
    snapshot=data;
    const panel=ensurePanel();if(!panel)return;
    const rows=Array.isArray(data?.components)?data.components:[];
    const healthy=rows.filter(row=>row.enabled&&(row.status==='healthy'||row.status==='running')).length;
    const enabled=rows.filter(row=>row.enabled).length;
    const online=Boolean(data?.supervisor_running);
    const canControl=Boolean(data?.can_control);
    const refs=data?.references||{};
    panel.innerHTML=`
      <div class="panel-head research-component-head">
        <div>
          <p class="panel-kicker">24/7 RESEARCH NODE</p>
          <h3>데이터 수집 · 연구 구성요소</h3>
          <p class="panel-copy">매매 엔진과 분리된 연구 기능입니다. 하나가 멈춰도 가상매매는 계속됩니다.</p>
        </div>
        <span class="status-pill ${online?'good':'bad'}">${online?`정상 ${healthy}/${Math.max(enabled,1)}`:'연구 서비스 연결 안 됨'}</span>
      </div>
      <div class="research-component-summary">
        <div><span>연구 서비스</span><b>${online?'실행 중':'중지/재시작 대기'}</b><small>${data?.updated_at?`상태 ${ageText(data.updated_at)} 갱신`:'상태 파일 대기 중'}</small></div>
        <div><span>외부 레포 확인</span><b>${Number(refs.total||0).toLocaleString('ko-KR')}개</b><small>${Number(refs.updates||0)>0?`새 버전 ${refs.updates}개`:'자동 적용 안 함'}</small></div>
        <div><span>조작 범위</span><b>${canControl?'이 PC에서 가능':'조회만 가능'}</b><small>원격에서는 연구 기능을 끄거나 실행하지 못합니다.</small></div>
      </div>
      <div class="research-component-list">
        ${rows.map(row=>{
          const [label,tone]=statusMeta(row.status,row.enabled);
          return `<section class="research-component-row" data-component="${esc(row.name)}">
            <div class="research-component-copy">
              <div class="research-component-title"><b>${esc(row.label)}</b><span class="status-pill ${tone}">${label}</span></div>
              <p>${esc(row.description)}</p>
              <div class="research-component-meta">
                <span>${esc(intervalText(row.interval_seconds))}</span>
                <span>최근 성공 ${esc(ageText(row.last_success_at))}</span>
                <span>${esc(resultText(row))}</span>
              </div>
              ${row.last_error?`<div class="research-component-error">${esc(row.last_error)}</div>`:''}
            </div>
            <div class="research-component-actions">
              <button type="button" class="button secondary compact" data-action="toggle" ${canControl?'':'disabled'}>${row.enabled?'끄기':'켜기'}</button>
              <button type="button" class="button secondary compact" data-action="run" ${canControl&&row.enabled?'':'disabled'}>지금 실행</button>
            </div>
          </section>`;
        }).join('')}
      </div>
      <p class="research-component-footnote">외부 레포는 새 버전 여부만 확인합니다. 다운로드·실행·자동 교체는 하지 않습니다.</p>`;
  }

  async function sync(){
    if(busy||document.hidden)return;
    busy=true;
    try{render(await apiJson('/api/research/components'));}
    catch(_err){
      const panel=ensurePanel();if(panel&&!snapshot)panel.innerHTML='<div class="empty-state">연구 구성요소 상태를 불러오는 중입니다.</div>';
    }finally{busy=false;}
  }

  async function act(button){
    const row=button.closest('.research-component-row');if(!row||busy)return;
    const name=row.dataset.component;const action=button.dataset.action;
    const current=(snapshot?.components||[]).find(item=>item.name===name);if(!current)return;
    busy=true;button.disabled=true;
    try{
      if(action==='toggle')snapshot=await apiJson(`/api/research/components/${encodeURIComponent(name)}`,{method:'PATCH',body:{enabled:!current.enabled}});
      else if(action==='run')snapshot=await apiJson(`/api/research/components/${encodeURIComponent(name)}/run`,{method:'POST'});
      render(snapshot);
      window.setTimeout(sync,2200);
    }catch(err){
      window.alert(err?.status===403?'이 기능은 현재 로컬 PC 화면에서만 변경할 수 있습니다.':'구성요소 설정을 변경하지 못했습니다.');
    }finally{busy=false;}
  }

  function install(){
    markBuild();ensurePanel();sync();
    document.addEventListener('click',event=>{
      const button=event.target.closest?.('#researchComponentPanel [data-action]');if(button)act(button);
    });
    timer=window.setInterval(sync,10000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
