import{age,dt,esc,n}from'../shared/format.js';
import{lifecycleMeta}from'../shared/market-lifecycle.js';

const EXCHANGE_LABEL={bithumb:'빗썸',upbit:'업비트'};

function safeUrl(value){
  const text=String(value||'').trim();
  return/^https?:\/\//i.test(text)?text:'';
}

function sourceLabel(value){
  const key=String(value||'').toLowerCase();
  if(key.includes('bithumb'))return'빗썸 공식 공지';
  if(key.includes('upbit'))return'업비트 공식 공지';
  return value?'공식 공지':'자동 감지';
}

function scheduleText(row,state){
  if(['LISTING_ANNOUNCED','NEW_LISTING'].includes(state)){
    if(Number(row?.trade_open_at||0)>0)return`거래 시작 ${dt(row.trade_open_at)}`;
    if(Number(row?.deposit_at||0)>0)return`입금 시작 ${dt(row.deposit_at)}`;
  }
  if(['TERMINATION_SCHEDULED','TERMINATED'].includes(state)&&Number(row?.termination_at||0)>0){
    return`거래 종료 ${dt(row.termination_at)}`;
  }
  const announced=Number(row?.announcement_at||row?.effective_at||0);
  return announced>0?`공지 ${dt(announced)}`:'';
}

function lifecycleRow(row){
  const meta=lifecycleMeta(row?.state),market=String(row?.market||''),symbol=market.replace(/^KRW-/,'')||'-',title=String(row?.title||''),url=safeUrl(row?.url),effective=Number(row?.effective_at||0),schedule=scheduleText(row,meta.state);
  return`<article class="market-lifecycle-row ${meta.className}"><div class="market-lifecycle-identity"><b>${esc(symbol)}</b><span>${esc(market)}</span></div><div class="market-lifecycle-event"><strong>${esc(meta.label||'상태 변경')}</strong><small>${title?esc(title):esc(sourceLabel(row?.source))}</small>${schedule?`<em>${esc(schedule)}</em>`:''}</div><div class="market-lifecycle-meta"><span>${effective?age(effective):'시각 확인 중'}</span>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">공식 공지</a>`:''}</div></article>`;
}

export function renderMarketLifecyclePanel(lifecycle,{exchange='bithumb',limit=8}={}){
  const attention=Array.isArray(lifecycle?.attention)?lifecycle.attention:[],noticeOnly=Array.isArray(lifecycle?.notice_only)?lifecycle.notice_only:[];
  const seen=new Set(),rows=[];
  for(const row of [...noticeOnly,...attention]){
    const key=`${String(row?.market||'')}|${String(row?.state||'')}|${String(row?.notice_id||'')}`;
    if(!row?.market||seen.has(key))continue;
    seen.add(key);rows.push(row);
  }
  const announced=rows.filter(row=>lifecycleMeta(row?.state).state==='LISTING_ANNOUNCED').length;
  const caution=rows.filter(row=>lifecycleMeta(row?.state).state==='CAUTION').length;
  const ending=rows.filter(row=>['TERMINATION_SCHEDULED','TERMINATED'].includes(lifecycleMeta(row?.state).state)).length;
  const visible=rows.slice(0,Math.max(1,Number(limit)||8));
  const exchangeName=EXCHANGE_LABEL[String(exchange||'').toLowerCase()]||String(exchange||'거래소');
  return`<section class="market-lifecycle-panel" data-market-lifecycle-panel><header><div><span>거래지원 상태</span><h3>${esc(exchangeName)} 상장 · 유의 · 종료 감지</h3><p>공식 공지와 실제 KRW 마켓 변화를 분리 수집한 shadow 정보입니다.</p></div><div class="market-lifecycle-kpis"><span><small>상장예정</small><b>${n(announced)}</b></span><span><small>유의</small><b class="market-lifecycle-caution">${n(caution)}</b></span><span><small>종료</small><b class="market-lifecycle-terminated">${n(ending)}</b></span></div></header>${visible.length?`<div class="market-lifecycle-list">${visible.map(lifecycleRow).join('')}</div>${rows.length>visible.length?`<small class="market-lifecycle-more">외 ${rows.length-visible.length}건의 상태 변경이 기록되어 있습니다.</small>`:''}`:`<div class="market-lifecycle-empty"><b>현재 표시할 거래지원 경보가 없습니다.</b><span>신규 상장·유의·거래종료 공지가 감지되면 이 영역에 자동 표시됩니다.</span></div>`}</section>`;
}

export function refreshMarketLifecyclePanel(root,lifecycle,options={}){
  const current=root?.querySelector?.('[data-market-lifecycle-panel]');
  if(!current)return false;
  const template=document.createElement('template');
  template.innerHTML=renderMarketLifecyclePanel(lifecycle,options).trim();
  const next=template.content.firstElementChild;
  if(!next)return false;
  current.replaceWith(next);
  return true;
}
