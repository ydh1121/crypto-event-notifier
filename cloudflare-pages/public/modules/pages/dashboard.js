import{combinedPaper,holdings,holdingsSummary,allCandidateRows,fullPublic,paperStats,strategyLab,marketSummary}from'../shared/selectors.js';
import{pageHead,kpi,loading}from'../shared/components.js';
import{money,pct,n,tone,decisionLabel,esc}from'../shared/format.js';
export function createDashboardPage({store,navigate}){
  let root=null,unsub=null;
  const click=e=>{const b=e.target.closest('[data-route]');if(b)navigate(b.dataset.route)};
  function render(){
    const state=store.get();if(!root)return;
    if(!state.snapshot){root.innerHTML=pageHead('대시보드','지금 확인할 위험·기회와 핵심 상태만 먼저 봅니다.')+loading('대시보드 데이터를 불러오는 중입니다.');return}
    const hs=holdingsSummary(state),h=holdings(state),cp=combinedPaper(state),paperRate=cp.start?cp.pnl/cp.start*100:0,candidates=allCandidateRows(state).sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)),best=candidates[0],worst=[...h].sort((a,b)=>n(a.unrealized_pnl_pct)-n(b.unrealized_pnl_pct))[0],alerts=[];
    if(worst&&n(worst.unrealized_pnl_pct)<=-10)alerts.push({title:`${String(worst.market).replace(/^KRW-/,'')} ${pct(worst.unrealized_pnl_pct)}`,desc:'실제 보유자산 중 손실률이 가장 큽니다.',route:'assets',tone:'danger'});
    if(best&&n(best.opportunity_score)>=65)alerts.push({title:`${best.symbol||best.market} 기회점수 ${n(best.opportunity_score).toFixed(0)}`,desc:`${best.__exchange==='upbit'?'업비트':'빗썸'} · ${decisionLabel(best)}`,route:'research',tone:'info'});
    const node=fullPublic(state).research_node||{};if(node.online===false||node.supervisor_running===false)alerts.push({title:'연구 노드 확인 필요',desc:'데이터 수집 상태를 확인하세요.',route:'system',tone:'danger'});
    if(!alerts.length)alerts.push({title:'즉시 확인할 경고 없음',desc:'현재 우선 대응이 필요한 항목이 없습니다.',route:'dashboard',tone:'good'});
    const bh=paperStats(state,'bithumb'),uh=paperStats(state,'upbit'),sm=marketSummary(state,'bithumb'),lab=strategyLab(state),cs=lab.candidate_summary||{};
    const assetPnl=n(hs?.pnl_krw),assetRate=n(hs?.invested_krw)?assetPnl/n(hs.invested_krw)*100:0;
    root.innerHTML=`${pageHead('대시보드','지금 확인할 위험·기회와 핵심 상태만 먼저 봅니다.')}
      <section class="priority-strip"><header><h3>먼저 확인할 것</h3><span>최대 3개</span></header><div>${alerts.slice(0,3).map(a=>`<button class="priority-item ${a.tone}" data-route="${a.route}"><span></span><div><b>${esc(a.title)}</b><small>${esc(a.desc)}</small></div><em>보기</em></button>`).join('')}</div></section>
      <section class="dashboard-kpis">
        <button data-route="assets" class="summary-tile"><span>내 실제 자산</span><b>${hs?money(hs.value_krw):'등록 없음'}</b><small class="${tone(assetPnl)}">${hs?`${assetPnl>=0?'+':''}${money(assetPnl)} · ${pct(assetRate)}`:'보유자산'}</small></button>
        <button data-route="research" class="summary-tile"><span>시장 상태 · 빗썸</span><b>${sm.avgRegime.toFixed(0)}<i>/100</i></b><small>관찰 후보 ${sm.candidates}개</small></button>
        <button data-route="paper" class="summary-tile primary"><span>전체 PAPER 증감</span><b class="${tone(cp.pnl)}">${cp.pnl>=0?'+':''}${money(cp.pnl)}</b><small>${pct(paperRate)} · 빗썸+업비트</small></button>
        <button data-route="strategy" class="summary-tile"><span>전략 검증</span><b>${n(cs.candidate)} 후보</b><small>검증 중 ${n(cs.warming)} · 미통과 ${n(cs.rejected)}</small></button>
      </section>
      <section class="dashboard-two"><article class="section-panel"><header><h3>지금 볼 코인</h3><button data-route="research">리서치 열기</button></header><div class="watch-list">${candidates.slice(0,6).map(r=>`<div><span><b>${esc(r.symbol||r.market)}</b><small>${r.__exchange==='upbit'?'업비트':'빗썸'} · ${esc(decisionLabel(r))}</small></span><strong>${n(r.opportunity_score).toFixed(0)}</strong></div>`).join('')||'<p class="muted">후보 계산 중</p>'}</div></article>
      <article class="section-panel"><header><h3>거래소별 PAPER</h3><button data-route="paper">전체 보기</button></header><div class="exchange-summary"><div><span>빗썸</span><b class="${tone(bh.pnl)}">${bh.pnl>=0?'+':''}${money(bh.pnl)}</b><small>${pct(bh.returnPct)} · ${n(bh.market_count)}개 계좌</small></div><div><span>업비트</span><b class="${tone(uh.pnl)}">${uh.pnl>=0?'+':''}${money(uh.pnl)}</b><small>${pct(uh.returnPct)} · ${n(uh.market_count)}개 계좌</small></div></div></article></section>`;
  }
  return{mount(r){root=r;root.addEventListener('click',click);unsub=store.subscribe((_,m)=>{if(['snapshot','error','user'].includes(m.type))render()})},render,destroy(){unsub?.();root?.removeEventListener('click',click);root=null}};
}
