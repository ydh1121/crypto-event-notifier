import {esc} from './format.js';
import {number,time,color} from './strategy-workbench-view.js';

const labels={buy:'추가매수',sell:'매도',adjust:'수량·평단 수정',close:'목록에서 정리',history:'변경 내역'};
const money=(n,q)=>n===null||n===undefined?'—':`${number(n,8)}${q==='KRW'?'원':' BTC'}`;
function historyHtml(s,h) {
  if(!s.data)return '';
  const rows=s.data.history;
  return `<div class="holding-history"><h4>보유 변경 내역</h4>${rows.length?`<div class="holding-history-scroll" tabindex="0" aria-label="보유 변경 내역 가로 스크롤"><table><thead><tr><th>기록 시각</th><th>구분</th><th>체결가</th><th>체결 수량</th><th>수수료</th><th>실현손익</th><th>반영 후 수량</th><th>반영 후 평단</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${time(r.applied_ts)}${r.fill?`<small>체결 ${time(r.fill.ts)}</small>`:''}</td><td>${labels[r.action]||'변경'}</td><td>${money(r.fill?.price,h.quote_currency)}</td><td>${r.fill?number(r.fill.volume,8):'—'}</td><td>${money(r.fill?.fee,h.quote_currency)}</td><td class="${color(r.realized_quote)}">${r.realized_quote==null?(r.action==='buy'?'—':'미확인'):money(r.realized_quote,h.quote_currency)}</td><td>${number(r.after.volume,8)}</td><td>${money(r.after.avg_price,h.quote_currency)}</td></tr>`).join('')}</tbody></table></div><p class="subtle">${s.data.has_more?'최근 100건 · 이전 내역도 DB에 보관':'현재 보유정보에 반영된 순서'} · 손익은 기록 당시 평단 기준</p>`:'<p class="subtle">아직 기록한 보유 변경이 없습니다.</p>'}</div>`;
}
export function holdingManagementHtml(h,s,enabled) {
  if(!enabled||!h.management_available)return '';
  const actions=[['buy',h.closed?'다시 매수':'추가매수'],...(!h.closed?[['sell','매도'],['adjust','수량·평단 수정'],['close','목록에서 정리']]:[]),['history','변경 내역']];
  const busy=s?.busy?'disabled':'';
  const toolbar=`<div class="holding-manage-actions" aria-label="실제 보유자산 관리">${actions.map(([a,l])=>`<button type="button" data-manage-open="${a}" ${busy}>${l}</button>`).join('')}</div><p class="holding-manage-notice" role="status">${esc(s?.notice||'')}</p>`;
  if(!s?.open)return `<section class="holding-management">${toolbar}</section>`;
  const f=s.form,q=h.quote_currency==='BTC'?'BTC':'원';
  const input=(label,name,type='number',value=f[name])=>`<label>${label}<input type="${type}" ${type==='number'?'step="any" min="0"':'step="1"'} data-manage-field="${name}" data-continuity-key="manage-${esc(h.key)}-${name}" value="${esc(value)}" required></label>`;
  const fields=s.action==='close'?'<p>보유수량을 0으로 바꾸고 완료 목록으로 옮깁니다. 매도 가격·손익은 미확인으로 남습니다.</p>':s.action==='adjust'?`${input('현재 보유수량','volume')}${input('평균 매수가 · '+q,'avg_price')}<p class="subtle">매매 기록 없이 현재 수량·평단을 바로잡습니다.</p>`:
    `${input('체결 시각 · 한국시간','ts','datetime-local')}${input('실제 체결가 · '+q,'price')}<div>${input('체결 수량','volume')}${s.action==='sell'?`<button type="button" class="text-button" data-manage-action="all" ${!s.data?'disabled':''}>전량 ${s.data?number(s.data.current.volume,8):''}</button>`:''}</div>${input('실제 수수료 · '+q,'fee')}<p class="subtle">이미 체결한 거래를 입력하세요. 수수료가 없으면 0을 입력합니다.</p>`;
  const p=s.preview;
  const preview=p?`<div class="holding-change-preview" role="status"><h4>반영할 보유정보</h4><dl><div><dt>보유수량</dt><dd>${number(p.before.volume,8)} → <strong>${number(p.after.volume,8)}</strong></dd></div><div><dt>평균 매수가</dt><dd>${money(p.before.avg_price,h.quote_currency)} → <strong>${money(p.after.avg_price,h.quote_currency)}</strong></dd></div>${s.action==='sell'?`<div><dt>실현손익 · 수수료 반영</dt><dd class="${color(p.realized_quote)}">${money(p.realized_quote,h.quote_currency)}</dd></div>`:''}</dl><button type="button" data-manage-action="apply" ${busy}>보유정보에 반영</button></div>`:'';
  return `<section class="holding-management">${toolbar}<div class="holding-manage-editor"><div class="section-heading"><h3>${h.closed&&s.action==='buy'?'다시 매수':labels[s.action]}</h3><button type="button" data-manage-action="close" ${busy}>닫기</button></div>${s.action==='history'?'':`<form id="holding-manage-form" data-continuity-key="manage-form-${esc(h.key)}"><fieldset class="holding-manage-fields" ${busy?'disabled':''}>${fields}<div><button type="submit" ${!s.data?'disabled':''}>${s.busy?'확인 중…':'변경 내용 확인'}</button></div></fieldset></form>${preview}`}<p class="notice" role="alert">${esc(s.error||'')}</p>${s.error?`<button type="button" data-manage-action="reload" ${busy}>최신 보유정보 다시 불러오기</button>`:''}${s.busy&&!s.data?'<p role="status">보유 기록 불러오는 중…</p>':''}${historyHtml(s,h)}</div></section>`;
}
