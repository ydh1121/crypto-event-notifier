import{combinedPaper,holdings,allCandidateRows,marketSummary,recordsData}from'../shared/selectors.js';
import{money,pct,n,tone,esc,dt}from'../shared/format.js';
import{decisionKind}from'../shared/decision.js';

function exchangeLabel(exchange){return exchange==='upbit'?'업비트':'빗썸'}
function marketName(row){return String(row?.symbol||row?.market||'').replace(/^KRW-/,'')||'-'}
function marketMood(score){const x=n(score);if(x>=68)return'강한 편';if(x>=52)return'보통';if(x>=40)return'약한 편';return'조심할 구간'}
function plainDecision(row){const kind=decisionKind(row);if(kind==='buy')return'지금 살펴보기';if(kind==='wait')return'가격을 더 기다리기';if(kind==='risk')return'지금은 조심하기';if(kind==='holding')return'보유 중';return'계속 지켜보기'}
function candidateRows(state){return allCandidateRows(state).filter(row=>row?.market).sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score))}
function recentChanges(state){const out=[];for(const exchange of['bithumb','upbit']){const data=recordsData(state,exchange),label=exchangeLabel(exchange);for(const row of Array.isArray(data.fills)?data.fills:[])out.push({ts:n(row.ts),market:row.market||'',label,text:row.side==='sell'?'가상매매에서 팔았음':'가상매매에서 샀음'});for(const row of Array.isArray(data.feedback)?data.feedback:[])out.push({ts:n(row.ts),market:row.market||'',label,text:'판단 기준이 바뀜'})}return out.sort((a,b)=>b.ts-a.ts).slice(0,6)}

function sectionHead(title,desc,route,label){return`<header class="v2-section-head"><div><h2>${esc(title)}</h2>${desc?`<p>${esc(desc)}</p>`:''}</div>${route?`<button type="button" data-home-route="${route}">${esc(label||'전체 보기')}</button>`:''}</header>`}

function renderCandidates(rows){const primary=rows.filter(row=>decisionKind(row)==='buy').slice(0,5),waiting=rows.filter(row=>decisionKind(row)==='wait').slice(0,2),list=[...primary,...waiting].slice(0,7);if(!list.length)return`<div class="v2-empty">지금 바로 살펴볼 코인이 없습니다.</div>`;return`<div class="v2-table" role="table" aria-label="지금 볼 코인"><div class="v2-table-head" role="row"><span>코인</span><span>거래소</span><span>현재 판단</span><span>참고점수</span></div>${list.map(row=>`<button class="v2-table-row" data-home-market="${esc(row.market)}" data-home-exchange="${esc(row.__exchange||'bithumb')}"><span><b>${esc(marketName(row))}</b><small>${esc(row.name||'')}</small></span><span>${exchangeLabel(row.__exchange)}</span><span>${esc(plainDecision(row))}</span><span>${n(row.opportunity_score).toFixed(0)}</span></button>`).join('')}</div>`}

function renderHoldings(list,total){if(!list.length)return`<div class="v2-empty">등록된 보유 코인이 없습니다.</div>`;return`<div class="v2-table" role="table" aria-label="내 코인"><div class="v2-table-head" role="row"><span>코인</span><span>평가액</span><span>손익</span><span>비중</span></div>${[...list].sort((a,b)=>n(b.value_krw)-n(a.value_krw)).slice(0,7).map(row=>{const weight=total?n(row.value_krw)/total*100:0;return`<button class="v2-table-row" data-home-route="assets" data-home-asset="${esc(row.market)}"><span><b>${esc(marketName(row))}</b><small>${exchangeLabel(String(row.exchange||'bithumb').toLowerCase())}</small></span><span>${money(row.value_krw)}</span><span class="${tone(row.unrealized_pnl_pct)}">${pct(row.unrealized_pnl_pct)}</span><span>${weight.toFixed(1)}%</span></button>`}).join('')}</div>`}

function renderChanges(rows){if(!rows.length)return`<div class="v2-empty">최근에 새로 바뀐 내용이 없습니다.</div>`;return`<div class="v2-change-list">${rows.map(row=>`<div><span><b>${esc(marketName(row))}</b><small>${esc(row.label)}</small></span><strong>${esc(row.text)}</strong><time>${row.ts?dt(row.ts):'-'}</time></div>`).join('')}</div>`}

export function createHomePage({store,navigate}){
  let root=null,unsub=null;
  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){root.innerHTML='<div class="v2-loading">최신 자료를 불러오는 중입니다.</div>';return}
    const b=marketSummary(state,'bithumb'),u=marketSummary(state,'upbit'),marketScore=(n(b.avgRegime)+n(u.avgRegime))/2,rows=candidateRows(state),my=holdings(state),total=my.reduce((sum,row)=>sum+n(row.value_krw),0),paper=combinedPaper(state),changes=recentChanges(state),buyCount=rows.filter(row=>decisionKind(row)==='buy').length;
    root.innerHTML=`<div class="v2-page v2-home">
      <header class="v2-page-title"><div><h1>홈</h1><p>지금 확인할 내용만 한 화면에 모았습니다.</p></div></header>
      <section class="v2-status-strip" aria-label="오늘 요약">
        <div><span>시장 흐름</span><b>${esc(marketMood(marketScore))}</b><small>${marketScore.toFixed(0)}점</small></div>
        <div><span>지금 볼 코인</span><b>${buyCount}개</b><small>두 거래소 기준</small></div>
        <div><span>내 보유 금액</span><b>${money(total)}</b><small>${my.length}종목</small></div>
        <div><span>가상매매 손익</span><b class="${tone(paper.pnl)}">${paper.pnl>=0?'+':''}${money(paper.pnl)}</b><small>현재 ${n(paper.active)}종목 보유</small></div>
      </section>

      <div class="v2-home-grid">
        <section class="v2-section">${sectionHead('지금 볼 코인','먼저 확인할 코인만 추렸습니다.','research','코인 찾기')}${renderCandidates(rows)}</section>
        <section class="v2-section">${sectionHead('내 코인','보유 금액과 손익을 바로 확인합니다.','assets','내 코인 보기')}${renderHoldings(my,total)}</section>
      </div>

      <div class="v2-home-grid v2-home-grid-bottom">
        <section class="v2-section">${sectionHead('가상매매 결과','실제 주문 없이 계산한 결과입니다.','paper','결과 보기')}<dl class="v2-summary-list"><div><dt>처음 금액</dt><dd>${money(paper.start)}</dd></div><div><dt>현재 금액</dt><dd>${money(paper.equity)}</dd></div><div><dt>손익</dt><dd class="${tone(paper.pnl)}">${paper.pnl>=0?'+':''}${money(paper.pnl)}</dd></div><div><dt>현재 들고 있는 코인</dt><dd>${n(paper.active)}개</dd></div></dl></section>
        <section class="v2-section">${sectionHead('최근 기록','최근에 사고팔거나 판단이 바뀐 내용입니다.','records','기록 보기')}${renderChanges(changes)}</section>
      </div>

      <nav class="v2-more-links" aria-label="추가 화면">
        <button data-home-route="sectors">종류별 보기</button>
        <button data-home-route="strategy">방법 비교</button>
        <button data-home-route="dashboard-detail">시장 자세히 보기</button>
      </nav>
    </div>`;
  }
  function jump(route,{exchange='',market=''}={}){const patch={};if(route==='research'){if(exchange)patch.researchExchange=exchange;if(market)patch.researchMarket=market;patch.researchSearch='';patch.researchFilter='all'}if(route==='assets'&&market)patch.assetMarket=market;if(Object.keys(patch).length)store.setUi(patch,{scope:'home-jump'});navigate?.(route)}
  const click=e=>{const market=e.target.closest('[data-home-market]');if(market){jump('research',{exchange:market.dataset.homeExchange,market:market.dataset.homeMarket});return}const route=e.target.closest('[data-home-route]');if(route)jump(route.dataset.homeRoute,{market:route.dataset.homeAsset||''})};
  return{mount(r){root=r;root.addEventListener('click',click);unsub=store.subscribe((_,meta)=>{if(meta.type==='snapshot')render()})},render,destroy(){unsub?.();root?.removeEventListener('click',click);root=null}};
}
