import{combinedPaper,holdings,holdingsSummary,allCandidateRows,marketSummary,recordsData}from'../../shared/selectors.js';
import{money,pct,n,tone,price,esc,dt}from'../../shared/format.js';
import{decisionKind}from'../../shared/decision.js';
import{getMarketQuotes}from'../../services/market-quotes.js?v=1';

function exchangeLabel(value){return String(value||'').toLowerCase()==='upbit'?'업비트':'빗썸'}
function symbol(row){return String(row?.symbol||row?.market||'').replace(/^KRW-/,'')||'-'}
function stateLabel(row){const kind=decisionKind(row);if(kind==='buy')return'매수 관심';if(kind==='wait')return'가격 대기';if(kind==='risk')return'주의';if(kind==='holding')return'보유 중';return'관심'}
function recentTrades(state){const rows=[];for(const exchange of['bithumb','upbit']){const data=recordsData(state,exchange);for(const row of Array.isArray(data.fills)?data.fills:[])rows.push({...row,exchange,kind:row.side==='sell'?'매도':'매수'})}return rows.sort((a,b)=>n(b.ts)-n(a.ts)).slice(0,8)}
function sectionHead(title,route,label){return`<header class="mainstream-section-head"><h2>${esc(title)}</h2>${route?`<button type="button" data-home-route="${route}">${esc(label||'전체보기')}</button>`:''}</header>`}
function finite(value){if(value===null||value===undefined||value==='')return null;const parsed=Number(value);return Number.isFinite(parsed)?parsed:null}
function signedPct(value){return value===null?'—':`${value>0?'+':''}${value.toFixed(2)}%`}

export function createHomePage({store,navigate}){
  let root=null,unsub=null,quoteMaps={bithumb:new Map(),upbit:new Map()},quoteSeq=0;
  function candidateRows(){return allCandidateRows(store.get()).filter(row=>row?.market).sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score))}
  function quoteFor(row){const ex=String(row?.__exchange||'bithumb').toLowerCase(),cached=quoteMaps[ex]?.get(String(row?.market||''))||null;return{price:finite(cached?.price)??finite(row?.price),change:finite(cached?.change_24h_pct)??finite(row?.change_24h_pct)}}
  function coinRowsHtml(candidates){return candidates.length?candidates.slice(0,8).map(row=>{const quote=quoteFor(row);return`<button class="mainstream-table-row home-market-row" data-home-market="${esc(row.market)}" data-home-exchange="${esc(row.__exchange||'bithumb')}"><span><b>${esc(symbol(row))}</b><small>${esc(row.name||'')} · ${exchangeLabel(row.__exchange)}</small></span><span class="home-market-price">${quote.price===null?'—':price(quote.price)}</span><span class="${quote.change===null?'muted':tone(quote.change)} home-market-change">${signedPct(quote.change)}</span><span>${esc(stateLabel(row))}</span></button>`}).join(''):'<div class="mainstream-empty">표시할 코인이 없습니다.</div>'}
  function renderCoinTable(){const box=root?.querySelector('#homeCoinTable');if(!box)return;box.innerHTML=`<div class="mainstream-table-head home-market-head"><span>코인</span><span>현재가</span><span>24h</span><span>판단</span></div>${coinRowsHtml(candidateRows())}`}
  async function loadQuotes(){const seq=++quoteSeq;const [b,u]=await Promise.allSettled([getMarketQuotes('bithumb'),getMarketQuotes('upbit')]);if(seq!==quoteSeq||!root)return;if(b.status==='fulfilled')quoteMaps.bithumb=b.value;if(u.status==='fulfilled')quoteMaps.upbit=u.value;renderCoinTable()}
  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){root.innerHTML='<div class="mainstream-loading">최신 정보를 불러오는 중입니다.</div>';return}
    const assets=holdings(state),assetSummary=holdingsSummary(state),paper=combinedPaper(state),candidates=candidateRows(),b=marketSummary(state,'bithumb'),u=marketSummary(state,'upbit'),trades=recentTrades(state);
    const assetPnl=n(assetSummary?.pnl_krw);
    root.innerHTML=`<div class="mainstream-page home-v4">
      <header class="mainstream-page-head"><h1>홈</h1></header>

      <section class="mainstream-summary" aria-label="내 현황">
        <div><span>내 자산</span><b>${assetSummary?money(assetSummary.value_krw):'등록 없음'}</b></div>
        <div><span>평가손익</span><b class="${tone(assetPnl)}">${assetSummary?`${assetPnl>=0?'+':''}${money(assetPnl)}`:'-'}</b></div>
        <div><span>모의투자 손익</span><b class="${tone(paper.pnl)}">${n(paper.pnl)>=0?'+':''}${money(paper.pnl)}</b></div>
      </section>

      <div class="home-dashboard-grid">
        <div class="home-dashboard-column">
          <section class="mainstream-section home-market-section">
            ${sectionHead('시장현황','dashboard-detail','자세히')}
            <div class="market-summary-table">
              <div class="market-summary-row head"><span>거래소</span><span>상승</span><span>매수 관심</span><span>상태</span></div>
              <button class="market-summary-row" data-home-route="research"><span>빗썸</span><span>${n(b.up)}개</span><span>${n(b.buyCandidates)}개</span><span>${n(b.avgRegime)>=50?'보통 이상':'약한 편'}</span></button>
              <button class="market-summary-row" data-home-route="research"><span>업비트</span><span>${n(u.up)}개</span><span>${n(u.buyCandidates)}개</span><span>${n(u.avgRegime)>=50?'보통 이상':'약한 편'}</span></button>
            </div>
          </section>

          <section class="mainstream-section home-assets-section">
            ${sectionHead('내 자산','assets','전체보기')}
            <div class="mainstream-table asset-table">
              <div class="mainstream-table-head"><span>코인</span><span>평균 매수가</span><span>현재가</span><span>손익</span></div>
              ${assets.length?[...assets].sort((a,b)=>n(b.value_krw)-n(a.value_krw)).slice(0,8).map(row=>`<button class="mainstream-table-row" data-home-asset="${esc(row.market)}"><span><b>${esc(symbol(row))}</b><small>${money(row.value_krw)}</small></span><span>${price(row.avg_price)}</span><span>${price(row.current_price)}</span><span class="${tone(row.unrealized_pnl_pct)}">${pct(row.unrealized_pnl_pct)}</span></button>`).join(''):'<div class="mainstream-empty">등록된 자산이 없습니다.</div>'}
            </div>
          </section>
        </div>

        <div class="home-dashboard-column">
          <section class="mainstream-section home-coins-section">
            ${sectionHead('코인','research','전체보기')}
            <div id="homeCoinTable" class="mainstream-table home-market-table"><div class="mainstream-table-head home-market-head"><span>코인</span><span>현재가</span><span>24h</span><span>판단</span></div>${coinRowsHtml(candidates)}</div>
          </section>

          <section class="mainstream-section home-trades-section">
            ${sectionHead('최근 거래','records','전체보기')}
            <div class="trade-list">${trades.length?trades.map(row=>`<div class="trade-row"><span><b>${esc(symbol(row))}</b><small>${exchangeLabel(row.exchange)}</small></span><span>${row.kind}</span><span>${price(row.price)}</span><time>${row.ts?dt(row.ts):'-'}</time></div>`).join(''):'<div class="mainstream-empty">최근 거래가 없습니다.</div>'}</div>
          </section>
        </div>
      </div>

      <nav class="home-shortcuts" aria-label="바로가기">
        <button data-home-route="sectors">테마</button>
        <button data-home-route="strategy">매매방법 비교</button>
        <button data-home-route="system">더보기</button>
      </nav>
    </div>`;
    loadQuotes();
  }
  function go(route,{exchange='',market=''}={}){
    const patch={};
    if(route==='research'){if(exchange)patch.researchExchange=exchange;if(market)patch.researchMarket=market;patch.researchSearch='';patch.researchFilter='all'}
    if(route==='assets'&&market)patch.assetMarket=market;
    if(Object.keys(patch).length)store.setUi(patch,{scope:'home-v4'});
    navigate?.(route);
  }
  const click=event=>{
    const market=event.target.closest('[data-home-market]');
    if(market){go('research',{exchange:market.dataset.homeExchange,market:market.dataset.homeMarket});return}
    const asset=event.target.closest('[data-home-asset]');
    if(asset){go('assets',{market:asset.dataset.homeAsset});return}
    const route=event.target.closest('[data-home-route]');
    if(route)go(route.dataset.homeRoute);
  };
  return{mount(node){root=node;root.addEventListener('click',click);unsub=store.subscribe((_,meta)=>{if(meta.type==='snapshot')render()})},render,destroy(){quoteSeq++;unsub?.();root?.removeEventListener('click',click);root=null}};
}