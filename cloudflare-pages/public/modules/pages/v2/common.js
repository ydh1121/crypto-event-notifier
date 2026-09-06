import{n,esc}from'../../shared/format.js';
import{decisionKind}from'../../shared/decision.js';
export const EXCHANGES=['bithumb','upbit'];
export function exchangeLabel(value){return String(value||'').toLowerCase()==='upbit'?'업비트':'빗썸'}
export function marketSymbol(value){return String(value?.symbol||value?.market||value||'').replace(/^KRW-/,'')||'-'}
export function plainDecision(row){const kind=decisionKind(row);if(kind==='buy')return'지금 살펴보기';if(kind==='wait')return'가격 더 기다리기';if(kind==='risk')return'지금은 조심';if(kind==='holding')return'보유 중';return'계속 지켜보기'}
export function marketMood(value){const x=n(value);if(x>=70)return'강한 편';if(x>=55)return'조금 강한 편';if(x>=45)return'보통';if(x>=35)return'약한 편';return'조심할 구간'}
export function pageTitle(title,desc='',aside=''){return`<header class="v2-page-title"><div><h1>${esc(title)}</h1>${desc?`<p>${esc(desc)}</p>`:''}</div>${aside||''}</header>`}
export function sectionTitle(title,desc='',action=''){return`<header class="v2-section-head"><div><h2>${esc(title)}</h2>${desc?`<p>${esc(desc)}</p>`:''}</div>${action||''}</header>`}
export function emptyState(title,desc=''){return`<div class="v2-empty"><b>${esc(title)}</b>${desc?`<span>${esc(desc)}</span>`:''}</div>`}
export function loadingState(text='자료를 불러오는 중입니다.'){return`<div class="v2-loading">${esc(text)}</div>`}
export function exchangeSwitch(current,attr){return`<div class="v2-segment" role="group" aria-label="거래소 선택"><button type="button" ${attr}="bithumb" class="${current==='bithumb'?'active':''}">빗썸</button><button type="button" ${attr}="upbit" class="${current==='upbit'?'active':''}">업비트</button></div>`}
export function details(title,body,open=false){return`<details class="v2-details" ${open?'open':''}><summary>${esc(title)}</summary><div class="v2-details-body">${body}</div></details>`}
export function statusPill(text,tone=''){return`<span class="v2-status ${esc(tone)}">${esc(text)}</span>`}
export function methodLabel(value,index=0){const key=String(value||'').toLowerCase();const mapped={adaptive:'기본 방식',balanced:'균형 방식',conservative:'안정 방식',aggressive:'적극 방식'}[key];return mapped||`비교 방식 ${index+1}`}
export function statusKorean(value){const key=String(value||'').toLowerCase();return{healthy:'정상',running:'실행 중',starting:'시작 중',stopped:'중지',offline:'연결 안 됨',degraded:'확인 필요',ok:'정상',ready:'준비됨',error:'확인 필요',candidate:'기준 통과',rejected:'기준 미충족',paused:'일시정지'}[key]||'확인 중'}
export function safeKoreanText(value,fallback=''){const text=String(value||'').trim();if(!text)return fallback;return/[A-Za-z]{2,}/.test(text)?fallback:text}
export function pctNumber(value,digits=1){const x=n(value);return`${x>=0?'+':''}${x.toFixed(digits)}%`}
