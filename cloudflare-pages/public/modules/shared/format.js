import{decisionLabel}from'./decision.js';
export const n=v=>Number(v||0);
export const money=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
export const pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
export const price=v=>{const x=n(v);if(!x)return'-';const d=x>=1000?0:x>=100?1:x>=1?3:x>=.1?5:8;return`${x.toLocaleString('ko-KR',{maximumFractionDigits:d})}원`};
export const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const dt=ts=>n(ts)?new Date(n(ts)*1000).toLocaleString('ko-KR'):'-';
export function age(ts){const x=n(ts);if(!x)return'데이터 대기';const sec=Math.max(0,Math.floor(Date.now()/1000-x));if(sec<60)return`${sec}초 전`;if(sec<3600)return`${Math.floor(sec/60)}분 전`;return`${Math.floor(sec/3600)}시간 전`}
export function scoreGrade(v){const x=n(v);if(x<40)return'매우 나쁨';if(x<55)return'좋지 않음';if(x<65)return'보통';if(x<75)return'좋음';return'매우 좋음'}
export function normalizeCapital(start,equity,base=10000000,fallbackReturnPct=0){const s=n(start),e=n(equity),b=Math.max(0,n(base)),returnPct=s?(e-s)/s*100:n(fallbackReturnPct),normalizedEquity=b*(1+returnPct/100);return{base:b,equity:normalizedEquity,pnl:normalizedEquity-b,returnPct}}
export{decisionLabel};
export function stateLabel(row){if(row?.state_label)return row.state_label;if(row?.has_position)return'보유 중';if(n(row?.closed_trades)>0)return'매매 완료 · 대기';return'미진입'}