(()=>{
  if(window.__viewerBestPortLoaded)return;
  window.__viewerBestPortLoaded=true;

  const q=(selector,root=document)=>root.querySelector(selector);
  const qa=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const n=value=>Number(value||0);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const won=value=>`${Math.round(n(value)).toLocaleString('ko-KR')}원`;
  const pct=(value,d=2)=>`${n(value)>=0?'+':''}${n(value).toFixed(d)}%`;
  const tone=value=>n(value)>0?'positive':n(value)<0?'negative':'';
  const stateRef=()=>typeof state!=='undefined'?state:null;
  const snapshot=()=>stateRef()?.snapshot||null;
  const pub=()=>snapshot()?.public||{};
  const rows=()=>Array.isArray(pub().leaderboard)?pub().leaderboard:[];
  const researchNode=()=>pub().research_node||{};

  function ageText(ts){
    const value=n(ts);if(!value)return'아직 없음';
    const sec=Math.max(0,Math.floor(Date.now()/1000-value));
    if(sec<10)return'방금 전';
    if(sec<60)return`${sec}초 전`;
    if(sec<3600)return`${Math.floor(sec/60)}분 전`;
    if(sec<86400)return`${Math.floor(sec/3600)}시간 전`;
    return`${Math.floor(sec/86400)}일 전`;
  }
  function intervalText(seconds){
    const sec=n(seconds);if(sec>=3600)return`${Math.round(sec/3600)}시간마다`;
    if(sec>=60)return`${Math.round(sec/60)}분마다`;
    return`${Math.round(sec)}초마다`;
  }
  function stateClass(row){return row?.state_class||(row?.has_position?'holding':n(row?.closed_trades)>0?'completed_waiting':'untraded')}
  function componentMeta(row){
    if(!row?.enabled)return['꺼짐','neutral'];
    return ({healthy:['정상','good'],running:['실행 중','good'],degraded:['확인 필요','bad'],starting:['시작 중','warn'],offline:['연결 안 됨','bad'],stopped:['꺼짐','neutral']})[row?.status]||['확인 중','warn'];
  }
  function componentResult(row,node){
    const result=row?.last_result||{};
    if(row?.name==='warehouse-export'){
      if(result.status==='waiting_for_source_db')return'가상매매 DB 생성 대기 중';
      const count=n(result.exported_rows);return count>0?`최근 ${count.toLocaleString('ko-KR')}개 기록 추가 저장`:'새로 저장할 기록 없음';
    }
    if(row?.name==='reference-version-watch'){
      const refs=node?.references||{};
      if(n(refs.failed)>0)return`${n(refs.failed)}개 확인 실패`;
      if(n(refs.updates)>0)return`${n(refs.updates)}개 새 버전 감지`;
      return n(refs.total)>0?`${n(refs.total)}개 레포 확인 완료`:'첫 확인 대기 중';
    }
    if(row?.name==='cloudflare-snapshot-publish'){
      if(result.status==='published')return`${n(result.markets).toLocaleString('ko-KR')}개 코인 웹 전송 완료`;
      if(result.status==='not_configured')return'웹 상태판 초기 연결 필요';
      return'웹 상태판 전송 대기 중';
    }
    if(row?.name==='cloudflare-market-detail-publish'){
      if(result.status==='published')return`${n(result.published).toLocaleString('ko-KR')}개 코인 상세 전송 완료`;
      if(result.status==='not_configured')return'코인 상세 전송 초기 연결 필요';
      if(result.status==='waiting_for_detail_files')return'코인 상세 데이터 생성 대기 중';
      return'코인 상세 전송 대기 중';
    }
    if(row?.name==='cloudflare-pages-deploy'){
      if(result.status==='deployed')return`새 화면 배포 완료 · ${esc(String(result.head||'').slice(0,7))}`;
      if(result.status==='up_to_date'||result.status==='no_viewer_changes')return'웹 화면 최신 상태';
      if(result.status==='not_configured')return'Cloudflare 1회 설정 필요';
      return'Git 변경 감시 중';
    }
    return'';
  }

  function researchStats(){
    const list=rows();
    return {
      holding:list.filter(row=>stateClass(row)==='holding').length,
      completed:list.filter(row=>stateClass(row)==='completed_waiting').length,
      untraded:list.filter(row=>stateClass(row)==='untraded').length,
      avg:list.length?list.reduce((sum,row)=>sum+n(row.return_pct),0)/list.length:0,
    };
  }

  function holdingsAnchors(){return '<div id="holdingsSummary" class="holding-summary best-refresh-anchor"></div><div id="holdingsList" class="holding-list best-refresh-anchor"></div>'}
  function renderHoldings(){
    const card=q('#holdingsCard');if(!card)return;
    const data=snapshot()?.private_visible?snapshot()?.private?.manual_holdings:null;
    const list=Array.isArray(data?.holdings)?data.holdings.filter(row=>n(row.volume)>0):[];
    if(!list.length){
      card.classList.remove('best-holdings-card');
      if(data)card.innerHTML=`<div class="section-head"><div><p class="kicker">내 실제 보유분</p><h3>내 코인 현황</h3></div><span class="pill neutral">로그인 전용</span></div><div class="empty">보유 수량과 평단을 입력한 코인이 없습니다.</div>${holdingsAnchors()}`;
      return;
    }
    const pnl=n(data.pnl_krw),value=n(data.value_krw),invested=n(data.invested_krw),pnlPct=invested>0?pnl/invested*100:0;
    card.classList.add('best-holdings-card');
    card.innerHTML=`
      <div class="section-head best-holdings-head"><div><p class="kicker">내 실제 보유분</p><h3>내 코인 현황</h3></div><button type="button" class="best-inline-button" data-best-open-coin="${esc(list[0]?.market||'')}">코인별 보기</button></div>
      <div class="best-holdings-body"><div class="best-holdings-total"><span>전체 평가금액</span><strong>${won(value)}</strong><small class="${tone(pnl)}">현재 손익 ${pnl>=0?'+':''}${won(pnl)} · ${pct(pnlPct)}</small></div><div class="best-holdings-list">${list.slice(0,8).map(row=>`<button type="button" class="best-holding-row" data-best-open-coin="${esc(row.market)}"><span><b>${esc(String(row.market||'').replace('KRW-',''))}</b><small>평단 ${n(row.avg_price).toLocaleString('ko-KR',{maximumFractionDigits:8})}원</small></span><span><b>${won(row.value_krw)}</b><small class="${tone(row.unrealized_pnl_krw)}">${pct(row.unrealized_pnl_pct)}</small></span></button>`).join('')}</div></div>${holdingsAnchors()}`;
  }

  function ensureHomeResearch(){
    const panel=q('[data-view-panel="home"]');if(!panel)return null;
    let section=q('#bestHomeResearch',panel);if(section)return section;
    section=document.createElement('section');section.id='bestHomeResearch';section.className='best-home-research';
    const old=q('.home-grid',panel);if(old)old.insertAdjacentElement('beforebegin',section);else panel.appendChild(section);
    return section;
  }
  function renderHomeResearch(){
    const section=ensureHomeResearch();if(!section)return;
    const data=pub(),list=rows(),stats=researchStats(),node=researchNode(),best=data.best_market||list[0]||{};
    const total=n(data.scan_total)||n(data.market_count)||list.length,scanned=n(data.scanned_count),progress=total>0?Math.max(0,Math.min(100,scanned/total*100)):0;
    const components=Array.isArray(node.components)?node.components:[],enabled=components.filter(row=>row.enabled),healthy=enabled.filter(row=>row.status==='healthy'||row.status==='running').length;
    section.innerHTML=`
      <div class="best-home-head"><div><p class="kicker">PAPER RESEARCH</p><h3>코인별 1,000만원 가상매매</h3><p>빗썸 원화마켓 전체를 같은 출발선에서 비교합니다. 실제 주문은 없습니다.</p></div><span class="pill ${node.supervisor_running?'good':'bad'}">${node.supervisor_running?'연구 중':'확인 필요'}</span></div>
      <div class="best-leader-strip"><div><span>현재 수익률 1위</span><strong>${best?.symbol?esc(best.symbol):'집계 중'}</strong><small>${esc(best?.name||best?.market||'')}</small></div><b class="${tone(best?.return_pct)}">${best?.symbol?pct(best.return_pct):'-'}</b></div>
      <div class="best-scan-progress"><i style="width:${progress.toFixed(1)}%"></i></div><div class="best-scan-meta"><span>전체 스캔 ${scanned.toLocaleString('ko-KR')} / ${total.toLocaleString('ko-KR')}</span><span>갱신 ${ageText(data.source_updated_at)}</span></div>
      <div class="best-home-metrics"><div><span>전체 연구 대상</span><b>${n(data.market_count||list.length).toLocaleString('ko-KR')}개</b><small>코인별 독립 계좌</small></div><div><span>보유 중</span><b>${stats.holding.toLocaleString('ko-KR')}개</b><small>현재 포지션 있음</small></div><div><span>매매 완료 · 대기</span><b>${stats.completed.toLocaleString('ko-KR')}개</b><small>청산 후 다음 기회 대기</small></div><div><span>아직 미진입</span><b>${stats.untraded.toLocaleString('ko-KR')}개</b><small>탐색/조건 확인 중</small></div><div><span>전체 평균 수익률</span><b class="${tone(stats.avg)}">${pct(stats.avg)}</b><small>전체 가상계좌 기준</small></div></div>
      <div class="best-home-components"><div class="best-home-components-title"><span>24시간 연구 서비스</span><b>${node.supervisor_running?`정상 ${healthy}/${Math.max(enabled.length,1)}`:'연결 확인 필요'}</b></div><div class="best-home-component-chips">${components.map(row=>{const [label,t]=componentMeta(row);return `<span class="best-component-chip ${t}"><i></i>${esc(row.label)} · ${label}</span>`}).join('')}</div></div>`;
    q('.home-grid',q('[data-view-panel="home"]'))?.classList.add('best-home-old-hidden');
  }

  function ensureResultsSummary(){
    const panel=q('[data-view-panel="results"]');if(!panel)return null;
    let section=q('#bestResultsSummary',panel);if(section)return section;
    section=document.createElement('section');section.id='bestResultsSummary';section.className='best-results-summary';
    const layout=q('#parityResearchLayout',panel)||q('.results-card',panel);if(layout)layout.insertAdjacentElement('beforebegin',section);else panel.appendChild(section);
    return section;
  }
  function renderResultsSummary(){
    const section=ensureResultsSummary();if(!section)return;
    const data=pub(),list=rows(),stats=researchStats(),best=data.best_market||list[0]||{};
    const total=n(data.scan_total)||n(data.market_count)||list.length,scanned=n(data.scanned_count),progress=total>0?Math.max(0,Math.min(100,scanned/total*100)):0;
    section.innerHTML=`<div class="best-results-top"><div><span>현재 수익률 1위</span><strong>${best?.symbol?esc(best.symbol):'집계 중'}</strong><small>${esc(best?.name||best?.market||'')}</small></div><b class="${tone(best?.return_pct)}">${best?.symbol?pct(best.return_pct):'-'}</b></div><div class="best-scan-progress"><i style="width:${progress.toFixed(1)}%"></i></div><div class="best-results-meta"><span>전체 스캔 ${scanned.toLocaleString('ko-KR')} / ${total.toLocaleString('ko-KR')}</span><span>보유 ${stats.holding} · 완료대기 ${stats.completed} · 미진입 ${stats.untraded}</span><span>갱신 ${ageText(data.source_updated_at)}</span></div>`;
  }

  function ensureResearchComponents(){
    const panel=q('[data-view-panel="settings"]');if(!panel)return null;
    let section=q('#bestResearchComponents',panel);if(section)return section;
    section=document.createElement('section');section.id='bestResearchComponents';section.className='best-research-components';
    const owner=q('#ownerPanel',panel);if(owner)owner.insertAdjacentElement('beforebegin',section);else panel.appendChild(section);
    return section;
  }
  function renderResearchComponents(){
    const section=ensureResearchComponents();if(!section)return;
    const node=researchNode(),components=Array.isArray(node.components)?node.components:[],refs=node.references||{};
    const enabled=components.filter(row=>row.enabled),healthy=enabled.filter(row=>row.status==='healthy'||row.status==='running').length;
    section.innerHTML=`
      <div class="best-component-head"><div><p class="kicker">24/7 RESEARCH NODE</p><h3>데이터 수집 · 연구 구성요소</h3><p>매매 엔진과 분리된 연구 기능입니다. Cloudflare에서는 상태만 확인하고 끄기·실행·전략 변경은 하지 않습니다.</p></div><span class="pill ${node.supervisor_running?'good':'bad'}">${node.supervisor_running?`정상 ${healthy}/${Math.max(enabled.length,1)}`:'연구 서비스 연결 안 됨'}</span></div>
      <div class="best-component-summary"><div><span>연구 서비스</span><b>${node.supervisor_running?'실행 중':'확인 필요'}</b><small>상태 ${ageText(node.updated_at)}</small></div><div><span>외부 레포 확인</span><b>${n(refs.total).toLocaleString('ko-KR')}개</b><small>${n(refs.updates)>0?`새 버전 ${n(refs.updates)}개`:'자동 적용 안 함'}</small></div><div><span>조회 범위</span><b>읽기 전용</b><small>PC 엔진 제어 기능 없음</small></div></div>
      <div class="best-component-list">${components.map(row=>{const [label,t]=componentMeta(row);const result=componentResult(row,node);return `<article class="best-component-row"><div class="best-component-copy"><div class="best-component-title"><b>${esc(row.label)}</b><span class="pill ${t}">${label}</span></div><p>${esc(row.description)}</p><div class="best-component-meta"><span>${intervalText(row.interval_seconds)}</span><span>최근 성공 ${ageText(row.last_success_at)}</span>${result?`<span>${result}</span>`:''}</div>${row.last_error?`<div class="best-component-error">${esc(row.last_error)}</div>`:''}</div></article>`}).join('')||'<div class="empty">연구 구성요소 상태를 기다리는 중입니다.</div>'}</div>
      <p class="best-component-footnote">외부 레포는 새 버전 여부만 확인하며 자동 적용하지 않습니다. 웹 배포도 조회 전용 Pages 코드만 대상으로 합니다.</p>`;
  }

  function openCoin(market){
    if(!market)return;const s=stateRef();if(!s)return;s.coinMarket=market;
    if(typeof switchView==='function')switchView('coin');
    const select=q('#coinSelect');if(select){select.value=market;select.dispatchEvent(new Event('change',{bubbles:true}))}
  }
  function bind(){document.addEventListener('click',event=>{const button=event.target.closest?.('[data-best-open-coin]');if(button){event.preventDefault();openCoin(button.dataset.bestOpenCoin)}},true)}
  function renderAll(){if(!stateRef()?.user||!snapshot())return;renderHoldings();renderHomeResearch();renderResultsSummary();renderResearchComponents()}
  function install(){
    bind();renderAll();
    if(typeof renderSnapshot==='function'){
      const before=renderSnapshot;
      renderSnapshot=function(payload){const result=before(payload);requestAnimationFrame(renderAll);return result};
    }
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)renderAll()});
    window.setInterval(()=>{if(!document.hidden)renderAll()},15000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();