import {createPaperPage} from './paper.js?v=legacy-preserved-1';
import {getMarketDetail} from '../services/market-detail.js';
import {getStrategyJournal} from '../services/strategy-journal.js';
import {accountModel, importPlan} from '../shared/strategy-workbench-model.js';
import {esc} from '../shared/format.js';
import {patchPreservingUi} from '../shared/ui-continuity.js';
import {accountHtml,planHtml,journalHtml,calculatorHtml,calculationHtml,priceChart,relativeHtml,freshnessHtml,won,percent} from '../shared/strategy-workbench-view.js';
import {eventsHtml,eventKey} from '../shared/event-workbench-view.js';

/** One coin stays selected while independent strategy accounts change beneath it. */
export function createPaperWorkbench({store, allowOverview=true}) {
  let root,view,legacy,unsub,detail=null,journal=null,journalError='',detailError='',loading=false,requestId=0,journalId=0;
  let selected='',currentRevision='',selectedEvent='',search='',section='strategy',range='7d',calculatorOpen=false;
  const drafts=new Map();
  const ui=()=>store.get().ui;
  const exchange=()=>ui().paperExchange==='upbit'?'upbit':'bithumb';
  const market=()=>String(ui().paperMarket||'');
  const identity=()=>`${exchange()}|${market()}`;
  const draftKey=()=>`${identity()}|${selected}`;
  const account=()=>accountModel(detail,exchange(),market(),selected);
  function coins() {
    const pub=store.get().snapshot?.public||{};
    const source=pub.exchanges?.[exchange()]||(String(pub.exchange||'bithumb')===exchange()?pub:null);
    return [...(source?.leaderboard||[])].sort((a,b)=>String(a.symbol||a.market).localeCompare(String(b.symbol||b.market)));
  }
  function pickMarket() {
    const rows=coins();
    if(!rows.some(r=>r.market===market()))store.setUi({paperMarket:rows.find(r=>r.market==='KRW-B3')?.market||rows[0]?.market||''},{scope:'paper-workbench'});
  }
  const el=id=>view?.getElementById(id);
  const set=(id,html)=>{const node=el(id);if(node)node.innerHTML=html;};
  const syncTheme=()=>{if(view)view.host.dataset.theme=document.documentElement.dataset.theme||'light';};
  function render() {
    if(!root)return;
    legacy?.destroy();legacy=null;requestId++;journalId++;
    pickMarket();
    root.innerHTML='<crypto-paper-workbench data-raw-text></crypto-paper-workbench>';
    view=root.firstElementChild.attachShadow({mode:'open'});
    syncTheme();
    view.innerHTML=`<link rel="stylesheet" href="/modules/styles/strategy-workbench.css?v=2">
      <main><header class="workbench-header"><h1>가상매매</h1>${allowOverview?'<nav aria-label="전체 가상매매"><button data-overview="summary">전체 계좌</button><button data-overview="compare">거래소 비교</button></nav>':''}</header>
      <div class="workspace"><aside aria-label="코인 선택"><div class="exchange-picker" role="group" aria-label="거래소"><button data-exchange="bithumb" aria-pressed="${exchange()==='bithumb'}">빗썸</button><button data-exchange="upbit" aria-pressed="${exchange()==='upbit'}">업비트</button></div><label class="search-label">코인 검색<input id="coin-search" type="search" placeholder="이름 또는 티커" value="${esc(search)}"></label><div id="coin-list" class="coin-list" data-preserve-scroll></div><label class="mobile-picker">코인 선택<select id="mobile-coin"></select></label></aside>
      <div class="coin-detail"><header id="coin-heading" class="coin-heading"></header><nav class="section-tabs" aria-label="코인 분석"><button data-section="strategy" aria-current="page">전략</button><button data-section="relative">BTC·ETH</button><button data-section="events">이벤트</button></nav><div id="coin-content"></div></div></div></main>`;
    view.addEventListener('click',click);view.addEventListener('input',input);view.addEventListener('change',change);
    renderCoins();renderHeading();void loadDetail();
  }
  function renderCoins() {
    const rows=coins(),q=search.trim().toLocaleLowerCase(),filtered=rows.filter(r=>`${r.market} ${r.symbol||''} ${r.name||''}`.toLocaleLowerCase().includes(q));
    set('coin-list',filtered.map(r=>`<button data-coin="${esc(r.market)}" aria-pressed="${r.market===market()}"><span><b>${esc(r.symbol||r.market.replace('KRW-',''))}</b><small>${esc(r.name||'')}</small></span><strong>${won(r.price)}</strong></button>`).join('')||'<p>검색 결과 없음</p>');
    set('mobile-coin',rows.map(r=>`<option value="${esc(r.market)}" ${market()===r.market?'selected':''}>${esc(r.symbol||r.market)} · ${esc(r.name||'')}</option>`).join(''));
  }
  function renderHeading() {
    const row=coins().find(r=>r.market===market()),a=account();
    set('coin-heading',`<div><span>${exchange()==='upbit'?'업비트':'빗썸'} · KRW</span><h2>${esc(row?.symbol||market().replace('KRW-','')||'코인 선택')} <small>${esc(row?.name||'')}</small></h2></div><div class="coin-price"><b>${won(row?.price??a?.last_price)}</b>${freshnessHtml({source_ts:row?.signal_ts||a?.source_ts})}</div>`);
  }
  async function loadDetail(force=false) {
    if(!view||legacy||!market())return;
    const key=identity(),id=++requestId;
    if(!detail||detail.exchange!==exchange()||detail.market!==market()) {
      detail=null;journal=null;currentRevision='';set('coin-content','<p class="placeholder">코인별 가상계좌를 불러오는 중…</p>');
    }
    try {
      const result=await getMarketDetail(exchange(),market(),{force});
      if(id!==requestId||identity()!==key||legacy)return;
      detail=result;detailError='';
      const accounts=detail?.data?.strategy_lab?.experiments||[];
      if(!accounts.some(a=>a.experiment_id===selected))selected=accounts.find(a=>a.style===ui().paperLabStyle)?.experiment_id||accounts.find(a=>a.style==='aggressive')?.experiment_id||accounts[0]?.experiment_id||'';
      const a=account();
      if(!a){renderContent();return;}
      renderHeading();
      if(a?.revision!==currentRevision||!el('strategy-content')) {
        journal=null;currentRevision=a?.revision||'';
        renderContent();if(section==='strategy'&&a)void loadJournal(0);
      }
    } catch(err) {
      if(id!==requestId)return;
      detailError=err.message;
      set('coin-content',`<p class="notice">${esc(detailError)}</p><button data-action="retry-detail">다시 불러오기</button>`);
    }
  }
  function renderContent() {
    view?.querySelectorAll('[data-section]').forEach(b=>b.setAttribute('aria-current',b.dataset.section===section?'page':'false'));
    if(section==='relative') {set('coin-content',relativeHtml(detail?.data?.market_memory,detail?.data?.strategy_lab?.relative));return;}
    if(section==='events') {renderEvents();return;}
    const accounts=detail?.data?.strategy_lab?.experiments||[],a=account();
    if(!a) {
      const lab=detail?.data?.strategy_lab;
      const message=lab?.status==='read_error'?'전략 계좌를 읽지 못했습니다.':lab?.status==='no_account'?'이 코인의 전략 계좌가 없습니다.':'전략별 원장 전송이 아직 반영되지 않았습니다.';
      set('coin-content',`<p class="placeholder">${message}</p>${allowOverview?'<button data-overview="coins">기존 기본 전략 기록</button>':''}<button data-action="retry-detail">다시 불러오기</button>`);
      return;
    }
    patchPreservingUi(view,()=>set('coin-content',`<nav class="strategy-tabs" role="tablist" aria-label="전략 선택" data-preserve-scroll>${accounts.map(e=>`<button role="tab" aria-selected="${e.experiment_id===selected}" data-experiment="${esc(e.experiment_id)}"><b>${esc(e.label)}</b><span>${percent(e.return_pct)} · 완료 ${e.closed_trades}회</span></button>`).join('')}</nav>
      <section id="strategy-content"><div id="account-summary">${accountHtml(a)}</div><div class="account-asof">${freshnessHtml(a)}${allowOverview?'<button class="text-button" data-overview="coins">기본 전략 기록</button>':''}</div>
      <div class="analysis-layout"><div><section class="chart-section"><div class="section-heading"><h3>가격 · 체결</h3><div class="range-picker">${[['24h','24시간'],['7d','7일'],['all','전체']].map(([value,label])=>`<button data-range="${value}" aria-pressed="${range===value}">${label}</button>`).join('')}</div></div><div id="price-chart"></div></section><section id="journal" class="journal"></section></div><aside class="plan-column"><section id="current-plan">${planHtml(a)}</section><section id="calculator" ${calculatorOpen?'':'hidden'}>${calculatorOpen&&drafts.has(draftKey())?calculatorHtml(drafts.get(draftKey())):''}</section></aside></div></section>`));
    renderChart();set('journal',journalHtml(journal,{loading,error:journalError}));
    if(calculatorOpen)calculate();
  }
  function renderChart() {
    const source=detail?.data||{},history=source.strategy_lab?.price_history||source.market_memory?.map(r=>({ts:r.signal_ts||r.ts,price:r.price}))||[];
    set('price-chart',priceChart(history,journal?.trades||[],range));
  }
  async function loadJournal(offset=0) {
    const a=account();if(!a?.revision)return;
    const key=draftKey(),id=++journalId;loading=true;journalError='';set('journal',journalHtml(journal,{loading:true}));
    try {
      const result=await getStrategyJournal(exchange(),market(),selected,{revision:a.revision,offset});
      if(id!==journalId||key!==draftKey()||legacy)return;
      journal=result;loading=false;set('journal',journalHtml(journal));renderChart();
    } catch(err) {
      if(id!==journalId)return;loading=false;
      journalError=err.code==='JOURNAL_CHANGED'?'계좌가 갱신되었습니다. 새 원장을 불러오세요.':err.message;
      set('journal',journalHtml(null,{error:journalError}));
    }
  }
  function renderCalculator() {
    const draft=drafts.get(draftKey());if(!draft)return;
    const box=el('calculator');if(!box)return;box.hidden=!calculatorOpen;
    patchPreservingUi(view,()=>{box.innerHTML=calculatorHtml(draft);});calculate();
  }
  function calculate() { const draft=drafts.get(draftKey());if(draft)set('calculation-result',calculationHtml(draft,{exchange:exchange(),market:market()})); }
  function renderEvents() {
    const events=detail?.data?.strategy_lab?.events;
    if(Array.isArray(events)&&!events.some(e=>eventKey(e)===selectedEvent))selectedEvent=events[0]?eventKey(events[0]):'';
    patchPreservingUi(view,()=>set('coin-content',eventsHtml(events,selectedEvent)));
  }
  function openOverview(tab) {
    if(!allowOverview)return;
    requestId++;journalId++;legacy?.destroy();
    store.setUi({paperTab:tab},{scope:'paper-workbench-overview'});
    root.innerHTML='<button type="button" data-return-workbench>← 코인별 전략</button><div data-paper-overview></div>';
    root.querySelector('[data-return-workbench]').addEventListener('click',render);
    legacy=createPaperPage({store});legacy.mount(root.querySelector('[data-paper-overview]'));legacy.render();
    view=null;
  }
  function chooseCoin(value) {
    requestId++;journalId++;store.setUi({paperMarket:value},{scope:'paper-workbench'});
    detail=null;journal=null;currentRevision='';selectedEvent='';calculatorOpen=false;renderCoins();renderHeading();void loadDetail();
  }
  function click(event) {
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.overview) {openOverview(b.dataset.overview);return;}
    if(b.dataset.exchange) {store.setUi({paperExchange:b.dataset.exchange,paperMarket:''},{scope:'paper-workbench'});detail=null;journal=null;calculatorOpen=false;render();return;}
    if(b.dataset.coin) {chooseCoin(b.dataset.coin);return;}
    if(b.dataset.section) {section=b.dataset.section;renderContent();if(section==='strategy'&&!journal)void loadJournal(0);return;}
    if(b.dataset.experiment) {selected=b.dataset.experiment;store.setUi({paperLabStyle:account()?.style},{scope:'paper-workbench'});currentRevision=account()?.revision||'';journal=null;journalError='';calculatorOpen=drafts.has(draftKey());renderContent();void loadJournal(0);return;}
    if(b.dataset.range) {range=b.dataset.range;view.querySelectorAll('[data-range]').forEach(n=>n.setAttribute('aria-pressed',n.dataset.range===range));renderChart();return;}
    const action=b.dataset.action;
    if(action==='retry-detail'||action==='retry-journal') {currentRevision='';void loadDetail(true);return;}
    if(action==='next'&&journal?.next_offset!==null) {void loadJournal(journal.next_offset);return;}
    if(action==='previous'&&journal) {void loadJournal(Math.max(0,journal.offset-journal.limit));return;}
    if(action==='import-plan') {drafts.set(draftKey(),importPlan(account()));calculatorOpen=true;renderCalculator();return;}
    if(action==='close-calculator') {calculatorOpen=false;el('calculator').hidden=true;return;}
    const draft=drafts.get(draftKey());if(!draft)return;
    if(action==='add-buy'&&draft.buys.length<20)draft.buys.push({price:'',amount:''});
    else if(action==='add-sell'&&draft.sells.length<20)draft.sells.push({price:'',weight:''});
    else if(b.hasAttribute('data-remove-buy'))draft.buys.splice(Number(b.dataset.removeBuy),1);
    else if(b.hasAttribute('data-remove-sell'))draft.sells.splice(Number(b.dataset.removeSell),1);
    else return;
    renderCalculator();
  }
  function input(event) {
    const t=event.target;
    if(t.id==='coin-search') {search=t.value;renderCoins();return;}
    const draft=drafts.get(draftKey());if(!draft)return;
    if(t.dataset.draft)draft[t.dataset.draft]=t.value;
    else if(t.hasAttribute('data-buy-price'))draft.buys[Number(t.dataset.buyPrice)].price=t.value;
    else if(t.hasAttribute('data-buy-amount'))draft.buys[Number(t.dataset.buyAmount)].amount=t.value;
    else if(t.hasAttribute('data-sell-price'))draft.sells[Number(t.dataset.sellPrice)].price=t.value;
    else if(t.hasAttribute('data-sell-weight'))draft.sells[Number(t.dataset.sellWeight)].weight=t.value;
    else return;
    calculate();
  }
  function change(event) {
    if(event.target.id==='mobile-coin')chooseCoin(event.target.value);
    if(event.target.id==='event-picker'){selectedEvent=event.target.value;renderEvents();}
  }
  return {mount(node){root=node;document.addEventListener('viewer-theme-change',syncTheme);unsub=store.subscribe((_,meta)=>{if(['snapshot','snapshot-live'].includes(meta.type)&&!legacy) {pickMarket();renderHeading();void loadDetail();}});},render,
    destroy(){requestId++;journalId++;document.removeEventListener('viewer-theme-change',syncTheme);unsub?.();legacy?.destroy();root=null;view=null;}};
}
