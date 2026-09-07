import{marketSummary,rowsFor,findMarket}from'../../shared/selectors.js';
import{n,pct,price,tone,esc}from'../../shared/format.js';

const exchangeLabel=value=>value==='upbit'?'업비트':'빗썸';
const symbol=row=>String(row?.symbol||row?.market||'').replace(/^KRW-/,'')||'-';
const marketState=value=>{const x=n(value);if(x>=70)return'강한 편';if(x>=55)return'조금 강한 편';if(x>=45)return'중립';if(x>=30)return'약한 편';return'매우 약한 편'};

function majorCard(state,exchange,market,label){
  const row=findMarket(state,exchange,market);
  return`<button type="button" class="v5-major-card" data-v5-market="${esc(market)}" data-v5-exchange="${exchange}"><span>${label}<small>${exchangeLabel(exchange)}</small></span><b>${row?price(row.price):'-'}</b><strong class="${tone(row?.return_pct)}">${row?pct(row.return_pct):'-'}</strong></button>`;
}

function exchangePanel(state,exchange){
  const summary=marketSummary(state,exchange),rows=rowsFor(state,exchange),up=rows.filter(row=>n(row.return_pct)>0).length,down=rows.filter(row=>n(row.return_pct)<0).length,flat=Math.max(0,rows.length-up-down);
  return`<article class="v5-market-exchange"><header><div><span>${exchangeLabel(exchange)}</span><h2>${marketState(summary.avgRegime)}</h2></div><b>${n(summary.avgRegime).toFixed(0)}<small>/100</small></b></header><div class="v5-market-facts"><span><small>상승</small><b>${up}개</b></span><span><small>하락</small><b>${down}개</b></span><span><small>보합</small><b>${flat}개</b></span><span><small>매수 관심</small><b>${n(summary.buyCandidates)}개</b></span><span><small>강한 후보</small><b>${n(summary.opportunityCandidates)}개</b></span><span><small>매수 타이밍</small><b>${n(summary.avgEntry).toFixed(0)}</b></span></div></article>`;
}

function moverRows(state){
  const rows=[];
  for(const exchange of['bithumb','upbit'])for(const row of rowsFor(state,exchange))rows.push({...row,__exchange:exchange});
  return rows.filter(row=>row?.market).sort((a,b)=>Math.abs(n(b.return_pct))-Math.abs(n(a.return_pct))).slice(0,12);
}

export function createMarketPage({store,navigate}){
  let root=null,unsub=null;
  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){root.innerHTML='<div class="mainstream-loading">시장현황을 불러오는 중입니다.</div>';return}
    const movers=moverRows(state);
    root.innerHTML=`<div class="v5-market-page">
      <header class="mainstream-page-head"><div><h1>시장현황</h1><p>개별 코인 판단과 분리해 시장 전체 방향과 주요 움직임만 봅니다.</p></div></header>
      <section class="v5-market-majors"><header><h2>비트코인 · 이더리움</h2><p>시장 기준이 되는 두 코인의 현재 움직임입니다.</p></header><div>${majorCard(state,'bithumb','KRW-BTC','비트코인')}${majorCard(state,'bithumb','KRW-ETH','이더리움')}${majorCard(state,'upbit','KRW-BTC','비트코인')}${majorCard(state,'upbit','KRW-ETH','이더리움')}</div></section>
      <section class="v5-market-status"><header><h2>거래소별 시장 상태</h2><p>상승·하락 종목 분포와 현재 매수 타이밍을 함께 봅니다.</p></header><div>${exchangePanel(state,'bithumb')}${exchangePanel(state,'upbit')}</div></section>
      <section class="v5-market-movers"><header><h2>변동이 큰 코인</h2><p>현재 시장에서 움직임이 큰 종목만 추려 봅니다. 코인을 누르면 상세 판단으로 이동합니다.</p></header><div class="v5-market-mover-table"><div class="v5-market-mover-row head"><span>코인</span><span>거래소</span><span>등락</span><span>현재 판단</span></div>${movers.map(row=>`<button type="button" class="v5-market-mover-row" data-v5-market="${esc(row.market)}" data-v5-exchange="${row.__exchange}"><span><b>${esc(symbol(row))}</b><small>${esc(row.name||'')}</small></span><span>${exchangeLabel(row.__exchange)}</span><span class="${tone(row.return_pct)}">${pct(row.return_pct)}</span><span>${esc(row.state_label||'확인')}</span></button>`).join('')}</div></section>
      <section class="v5-data-pending"><b>대외 이벤트 반응</b><span>이벤트별 반응도 행렬은 아직 현재 백엔드에 연결되지 않았습니다. PHASE 2~5에서 실제 데이터 계약과 계산기가 준비된 뒤 이 위치에 연결합니다.</span></section>
    </div>`;
  }
  const click=event=>{const row=event.target.closest('[data-v5-market]');if(!row)return;store.setUi({researchExchange:row.dataset.v5Exchange||'bithumb',researchMarket:row.dataset.v5Market||'',researchSearch:'',researchFilter:'all'},{scope:'v5-market-to-coin'});navigate?.('research')};
  return{mount(node){root=node;root.addEventListener('click',click);unsub=store.subscribe((_,meta)=>{if(meta.type==='snapshot')render()})},render,destroy(){unsub?.();root?.removeEventListener('click',click);root=null}};
}
