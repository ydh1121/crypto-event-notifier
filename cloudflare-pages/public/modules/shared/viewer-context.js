import{esc}from'./format.js';

export function strategyLabel(value){
  const raw=String(value||'adaptive').trim();
  const key=raw.toLowerCase();
  if(key==='adaptive')return'Adaptive';
  if(key==='baseline')return'Baseline';
  if(key==='conservative')return'Conservative';
  if(key==='aggressive')return'Aggressive';
  if(key==='scalping')return'Scalping';
  if(!raw)return'Adaptive';
  return raw.replace(/[_-]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
}

export function scopeBanner(kind,{strategy='adaptive'}={}){
  if(kind==='strategy'){
    return`<section class="viewer-scope viewer-scope-shadow"><div><span>전략 비교용 가상계좌</span><strong>전략마다 따로 시험한 결과입니다.</strong><p>‘가상매매’ 메뉴의 현재 실행 계좌와는 다른 계좌입니다. 이 화면 안에서 같은 전략·같은 실험끼리만 비교합니다.</p></div><em>연구용 · 실제 주문 없음</em></section>`;
  }
  const label=strategyLabel(strategy);
  return`<section class="viewer-scope viewer-scope-paper"><div><span>현재 실행 가상매매</span><strong>${esc(label)} 방식 성적</strong><p>이 화면은 현재 실행 중인 가상매매 방식의 계좌·체결·수익을 보여줍니다. 전략 비교용 시험계좌와는 별도입니다.</p></div><em>${esc(label)} · 가상매매</em></section>`;
}
