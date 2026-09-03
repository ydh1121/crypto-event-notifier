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
    return`<section class="viewer-scope viewer-scope-shadow"><div><span>SHADOW STRATEGY LAB</span><strong>전략 연구는 독립 Shadow PAPER 실험계좌입니다.</strong><p>PAPER 메뉴의 실행 계좌와 자금·체결·수익률 범위가 다릅니다. experiment_id가 같은 데이터끼리만 직접 비교합니다.</p></div><em>연구 전용 · 실행전략 미변경</em></section>`;
  }
  const label=strategyLabel(strategy);
  return`<section class="viewer-scope viewer-scope-paper"><div><span>EXECUTION PAPER</span><strong>${esc(label)} 실행 PAPER 계좌</strong><p>이 화면의 계좌·체결·수익은 현재 실행 PAPER 전략 기준입니다. 전략 연구의 Shadow 실험계좌와는 별도입니다.</p></div><em>${esc(label)} · PAPER ONLY</em></section>`;
}
