import {createPaperPage} from './paper.js?v=legacy-preserved-1';
import {getMarketDetail} from '../services/market-detail.js';
import {getStrategyJournal} from '../services/strategy-journal.js';
import {accountModel, importPlan} from '../shared/strategy-workbench-model.js';
import {esc} from '../shared/format.js';
import {patchPreservingUi} from '../shared/ui-continuity.js';
import {updateHtml} from '../shared/dom-patch.js';
import {accountHtml,planHtml,journalHtml,calculatorHtml,calculationHtml,priceChart,relativeHtml,freshnessHtml,won,percent} from '../shared/strategy-workbench-view.js';
import {eventsHtml,eventKey} from '../shared/event-workbench-view.js';
import {createEventStudy} from '../shared/event-study-workbench.js';
import {createStrategyPeriod} from '../shared/strategy-period-workbench.js';

/** One coin stays selected while independent strategy accounts change beneath it. */
export function createPaperWorkbench({store, allowOverview=true}) {
  let root,view,legacy,unsub,detail=null,journal=null,journalError='',detailError='',loading=false,requestId=0,journalId=0;
  let selected='',currentRevision='',reactionSection='relative',reactionMode='events',strategyMode='account',eventHorizon='15m',search='',section='strategy',range='7d',calculatorOpen=false;
  const drafts=new Map(),selectedEvents=new Map();
  const ui=()=>store.get().ui;
  const exchange=()=>ui().paperExchange==='upbit'?'upbit':'bithumb';
  const market=()=>String(ui().paperMarket||'');
  const identity=()=>`${exchange()}|${market()}`;
  const draftKey=()=>`${identity()}|${selected}`;
  const account=()=>accountModel(detail,exchange(),market(),selected);
  function openJournal(experiment){
    selected=experiment;section='strategy';strategyMode='account';journal=null;calculatorOpen=false;
    store.setUi({paperLabStyle:account()?.style},{scope:'paper-workbench'});
    currentRevision=account()?.revision||'';renderContent();void loadJournal(0);
  }
  const eventStudy=createEventStudy({openJournal});
  const periodReview=createStrategyPeriod({openJournal});
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
  const set=(id,html,options)=>{const node=el(id);if(node)patchPreservingUi(view,()=>updateHtml(node,html,options));};
  const syncTheme=()=>{if(view)view.host.dataset.theme=document.documentElement.dataset.theme||'light';};
  function render() {
    if(!root)return;
    legacy?.destroy();legacy=null;requestId++;journalId++;
    pickMarket();
    if(!view||!root.contains(view.host)) {
    root.innerHTML='<crypto-paper-workbench data-raw-text></crypto-paper-workbench>';
    view=root.firstElementChild.attachShadow({mode:'open'});
    syncTheme();
    view.innerHTML=`<link rel="stylesheet" href="/modules/styles/strategy-workbench.css?v=7">
      <main><header class="workbench-header"><h1>가상매매</h1>${allowOverview?'<nav aria-label="전체 가상매매"><button data-overview="summary">전체 계좌</button><button data-overview="compare">거래소 비교</button></nav>':''}</header>
      <div class="workspace"><aside aria-label="코인 선택"><div class="exchange-picker" role="group" aria-label="거래소"><button data-exchange="bithumb" aria-pressed="${exchange()==='bithumb'}">빗썸</button><button data-exchange="upbit" aria-pressed="${exchange()==='upbit'}">업비트</button></div><label class="search-label">코인 검색<input id="coin-search" type="search" placeholder="이름 또는 티커" value="${esc(search)}"></label><div id="coin-list" class="coin-list" data-preserve-scroll></div><label class="mobile-picker">코인 선택<select id="mobile-coin"></select></label></aside>
      <div class="coin-detail"><header id="coin-heading" class="coin-heading"></header><nav class="section-tabs" aria-label="코인 분석"><button data-section="strategy" aria-current="page">전략</button><button data-section="reaction">반응도</button></nav><div id="coin-content"></div></div></div></main>`;
    view.addEventListener('click',click);view.addEventListener('input',input);view.addEventListener('change',change);
    }
    view.querySelectorAll('[data-exchange]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.exchange===exchange())));
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
      detail=null;journal=null;currentRevision='';set('coin-content','<p class="placeholder">코인별 가상계좌를 불러오는 중…</p>',{busy:true});
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
      const reload=a.revision!==currentRevision||!journal;
      if(journal?.account?.experiment_id!==selected)journal=null;
      const offset=journal?.offset||0;currentRevision=a.revision||'';
      if(reload&&section==='strategy'&&strategyMode==='account')loading=true;
      renderContent();
      if(reload&&section==='strategy'&&strategyMode==='account')void loadJournal(offset);
    } catch(err) {
      if(id!==requestId)return;
      detailError=err.message;
      set('coin-content',`<p class="notice">${esc(detailError)}</p><button data-action="retry-detail">다시 불러오기</button>`,{busy:true});
    }
  }
  function renderContent() {
    view?.querySelectorAll('[data-section]').forEach(b=>b.setAttribute('aria-current',b.dataset.section===section?'page':'false'));
    if(section==='reaction') {renderReaction();return;}
    const accounts=detail?.data?.strategy_lab?.experiments||[],a=account();
    if(!a) {
      const lab=detail?.data?.strategy_lab;
      const message=lab?.status==='read_error'?'전략 계좌를 읽지 못했습니다.':lab?.status==='no_account'?'이 코인의 전략 계좌가 없습니다.':'전략별 원장 전송이 아직 반영되지 않았습니다.';
      set('coin-content',`<p class="placeholder">${message}</p>${allowOverview?'<button data-overview="coins">기존 기본 전략 기록</button>':''}<button data-action="retry-detail">다시 불러오기</button>`);
      return;
    }
    const canCompare=detail?.data?.strategy_lab?.period_review_available===true;
    const modes=canCompare?`<nav class="reaction-modes" aria-label="전략 보기">${[['account','계좌·매매'],['compare','기간별 비교']].map(([key,label])=>`<button data-strategy-mode="${key}" data-continuity-key="strategy-mode-${key}" aria-pressed="${strategyMode===key}">${label}</button>`).join('')}</nav>`:'';
    if(canCompare&&strategyMode==='compare') {
      const scope={exchange:exchange(),market:market(),style:a.style};
      patchPreservingUi(view,()=>set('coin-content',`${modes}<section id="strategy-period">${periodReview.html(scope)}</section>`));
      periodReview.mount(el('strategy-period'),scope);return;
    }
    patchPreservingUi(view,()=>set('coin-content',`${modes}<nav class="strategy-tabs" role="tablist" aria-label="전략 선택" data-preserve-scroll>${accounts.map(e=>`<button role="tab" aria-selected="${e.experiment_id===selected}" data-experiment="${esc(e.experiment_id)}"><b>${esc(e.label)}</b><span>${percent(e.return_pct)} · 완료 ${e.closed_trades}회</span></button>`).join('')}</nav>
      <section id="strategy-content"><div id="account-summary">${accountHtml(a)}</div><div class="account-asof">${freshnessHtml(a)}${allowOverview?'<button class="text-button" data-overview="coins">기본 전략 기록</button>':''}</div>
      <div class="analysis-layout"><div><section class="chart-section"><div class="section-heading"><h3>가격 · 체결</h3><div class="range-picker">${[['24h','24시간'],['7d','7일'],['all','전체']].map(([value,label])=>`<button data-range="${value}" aria-pressed="${range===value}">${label}</button>`).join('')}</div></div><div id="price-chart">${chartHtml()}</div></section><section id="journal" class="journal">${journalHtml(journal,{loading,error:journalError})}</section></div><aside class="plan-column"><section id="current-plan">${planHtml(a)}</section><section id="calculator" ${calculatorOpen?'':'hidden'}>${calculatorOpen&&drafts.has(draftKey())?calculatorHtml(drafts.get(draftKey()),{identity:{exchange:exchange(),market:market()}}):''}</section></aside></div></section>`,{busy:loading&&!journal||Boolean(journalError)}));
    if(calculatorOpen)calculate();
  }
  function chartHtml() {
    const source=detail?.data||{},history=source.strategy_lab?.price_history||source.market_memory?.map(r=>({ts:r.signal_ts||r.ts,price:r.price}))||[];
    return priceChart(history,journal?.trades||[],range);
  }
  function renderChart() {set('price-chart',chartHtml());}
  async function loadJournal(offset=0) {
    const a=account();if(!a?.revision)return;
    const key=draftKey(),id=++journalId;loading=true;journalError='';set('journal',journalHtml(journal,{loading:true}));
    try {
      const result=await getStrategyJournal(exchange(),market(),selected,{revision:a.revision,offset});
      if(id!==journalId||key!==draftKey()||legacy)return;
      journal=result;loading=false;renderContent();
    } catch(err) {
      if(id!==journalId)return;loading=false;
      journalError=err.code==='JOURNAL_CHANGED'?'계좌가 갱신되었습니다. 새 원장을 불러오세요.':err.message;
      set('journal',journalHtml(null,{error:journalError}));
    }
  }
  function renderCalculator() {
    const draft=drafts.get(draftKey());if(!draft)return;
    const box=el('calculator');if(!box)return;box.hidden=!calculatorOpen;
    patchPreservingUi(view,()=>updateHtml(box,calculatorHtml(draft,{identity:{exchange:exchange(),market:market()}})));calculate();
  }
  function calculate() { const draft=drafts.get(draftKey());if(draft)set('calculation-result',calculationHtml(draft,{exchange:exchange(),market:market()})); }
  function renderReaction() {
    const all=detail?.data?.strategy_lab?.events;
    const events=Array.isArray(all)?all.filter(e=>(e.category||'news')===reactionSection):all;
    const key=`${identity()}|${reactionSection}`;
    if(Array.isArray(events)&&!events.some(e=>eventKey(e)===selectedEvents.get(key)))selectedEvents.set(key,events[0]?eventKey(events[0]):'');
    const label=reactionSection==='economic'?'경제지표':'정책·뉴스';
    const canStudy=reactionSection!=='relative'&&detail?.data?.strategy_lab?.event_study_available===true;
    const scope={exchange:exchange(),market:market(),category:reactionSection,style:account()?.style||'aggressive'};
    const showStudy=canStudy&&reactionMode==='study';
    const content=reactionSection==='relative'
      ?relativeHtml(detail?.data?.market_memory,detail?.data?.strategy_lab?.relative,market().replace('KRW-',''))
      :showStudy?`<div id="event-study">${eventStudy.html(scope)}</div>`:eventsHtml(events,selectedEvents.get(key),eventHorizon,label);
    patchPreservingUi(view,()=>set('coin-content',`<nav class="reaction-tabs" aria-label="반응도 분야" data-preserve-scroll>${[['relative','BTC·ETH'],['economic','경제지표'],['news','정책·뉴스']].map(([key,label])=>`<button data-reaction="${key}" data-continuity-key="reaction-${key}" aria-pressed="${key===reactionSection}">${label}</button>`).join('')}</nav>${canStudy?`<nav class="reaction-modes" aria-label="반응도 보기">${[['events','발표별'],['study','종류별 누적']].map(([k,l])=>`<button data-reaction-mode="${k}" data-continuity-key="reaction-mode-${k}" aria-pressed="${reactionMode===k}">${l}</button>`).join('')}</nav>`:''}<section class="reaction-content">${content}</section>`));
    if(showStudy)eventStudy.mount(el('event-study'),scope);
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
    detail=null;journal=null;currentRevision='';calculatorOpen=false;renderCoins();renderHeading();void loadDetail();
  }
  function click(event) {
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.reaction){reactionSection=b.dataset.reaction;renderReaction();return;}
    if(b.dataset.reactionMode){reactionMode=b.dataset.reactionMode;renderReaction();return;}
    if(b.dataset.strategyMode){strategyMode=b.dataset.strategyMode;renderContent();if(strategyMode==='account'&&!journal)void loadJournal(0);return;}
    if(b.dataset.event){selectedEvents.set(`${identity()}|${reactionSection}`,b.dataset.event);renderReaction();return;}
    if(b.dataset.eventHorizon){eventHorizon=b.dataset.eventHorizon;renderReaction();return;}
    if(b.dataset.overview) {openOverview(b.dataset.overview);return;}
    if(b.dataset.exchange) {store.setUi({paperExchange:b.dataset.exchange,paperMarket:''},{scope:'paper-workbench'});detail=null;journal=null;calculatorOpen=false;render();return;}
    if(b.dataset.coin) {chooseCoin(b.dataset.coin);return;}
    if(b.dataset.section) {section=b.dataset.section;renderContent();if(section==='strategy'&&strategyMode==='account'&&!journal)void loadJournal(0);return;}
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
  }
  return {mount(node){root=node;document.addEventListener('viewer-theme-change',syncTheme);unsub=store.subscribe((_,meta)=>{if(['snapshot','snapshot-live'].includes(meta.type)&&!legacy) {pickMarket();renderCoins();renderHeading();void loadDetail();}});},render,
    openAccount(exchange,market,style){selected='';section='strategy';strategyMode='account';detail=null;journal=null;currentRevision='';calculatorOpen=false;store.setUi({paperExchange:exchange,paperMarket:market,paperLabStyle:style},{scope:'paper-workbench'});render();},
    destroy(){requestId++;journalId++;eventStudy.destroy();periodReview.destroy();document.removeEventListener('viewer-theme-change',syncTheme);unsub?.();legacy?.destroy();root=null;view=null;}};
}
