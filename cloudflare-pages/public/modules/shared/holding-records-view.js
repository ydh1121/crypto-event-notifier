import {esc} from './format.js';
import {won,number,percent,time,color} from './strategy-workbench-view.js';

export function savedPlanHtml(e,panel='plan') {
  if(!e)return '';
  const disabled=e.loading||e.busy||!e.data;
  const status=e.loading?'저장본 불러오는 중…':e.busy?'저장 중…':e.dirty?'미저장 변경':e.data?.plan?`저장됨 · ${time(e.data.plan.saved_at)}`:'저장한 계획 없음';
  return `<div class="plan-save"><span role="status">${status}</span>${panel==='plan'?`<button data-action="save-holding-plan" ${disabled?'disabled':''}>계획 저장</button>`:''}<button class="text-button" data-action="load-holding-plan" ${e.loading||e.busy?'disabled':''}>저장본 불러오기</button></div>${e.error?`<p class="notice" role="alert">${esc(e.error)}</p>`:''}`;
}
export function manualRecordsHtml(e,{closed=false}={}) {
  if(!e)return '';
  if(!e.data)return '<p class="subtle">저장 기록을 불러오는 중입니다.</p>';
  if(!e.data.plan)return `<p class="subtle">${closed?'이 전략에 저장한 계획·소액 매매 기록이 없습니다.':'매매 계획을 저장하면 이 전략의 소액 매매 기록을 시작합니다.'}</p>`;
  const d=e.data,f=e.form,s=d.summary,c=d.comparison,disabled=e.busy?'disabled':'';
  const stageRows=d.plan.draft[f.side==='buy'?'buys':'sells'];
  const field=(key,label,type='number')=>`<label>${label}<input data-record-field="${key}" data-continuity-key="manual-${key}" type="${type}" ${type==='number'?'min="0" step="any"':'step="1"'} value="${esc(f[key])}" ${disabled}></label>`;
  const value=(label,v,cls='')=>`<div><dt>${label}</dt><dd class="${cls}">${v}</dd></div>`;
  const active=new Map((s?.trades||[]).map(t=>[t.id,t]));
  return `<div class="section-heading"><h3>소액 매매 기록</h3><span>직접 입력 · 주문 전송 없음</span></div>
    <dl class="manual-totals">${value('기록 잔량',number(s?.volume,8))}${value('매수 평단 · 수수료 포함',won(s?.average))}${value('실현손익',won(s?.realized),color(s?.realized))}</dl>
    <p class="subtle">여기에 기록한 매수·매도만 계산합니다. 기존 보유자산 수량은 바뀌지 않습니다.</p>
    <details data-continuity-key="manual-entry" open><summary>체결 입력</summary>
    <fieldset class="manual-form" ${disabled}><label>종류<select data-record-field="side" data-continuity-key="manual-side"><option value="buy" ${f.side==='buy'?'selected':''}>매수</option><option value="sell" ${f.side==='sell'?'selected':''}>매도</option></select></label>
    ${field('ts','체결 시각 · 한국시간','datetime-local')}${field('price','체결가 · 원')}${field('volume','체결 수량')}${field('fee','실제 수수료 · 원')}
    <label>비교할 저장 계획<select data-record-field="stage" data-continuity-key="manual-stage"><option value="">회차 지정 안 함</option>${stageRows.map((r,i)=>r.price?`<option value="${f.side}:${i}" ${f.stage===`${f.side}:${i}`?'selected':''}>${f.side==='buy'?'매수':'익절'} ${i+1}차 · ${won(r.price)}</option>`:'').join('')}</select></label>
    <button data-action="record-manual-fill">체결 기록</button></fieldset></details>
    <div class="section-heading"><h3>같은 기간 전략 비교</h3><span>${time(c?.start)} — ${time(c?.end)}</span></div>
    <div class="table-scroll"><table><thead><tr><th></th><th>완료 거래</th><th>수익 거래 / 전체</th><th>평균 거래 수익률</th></tr></thead><tbody>${[['수동 실거래',c?.manual],['이 코인 가상계좌',c?.paper]].map(([label,v])=>`<tr><th>${label}</th><td>${v?`${v.closed}회`:'—'}</td><td>${v?.closed?`${v.wins} / ${v.closed}`:'—'}</td><td>${percent(v?.mean_return_pct)}</td></tr>`).join('')}</tbody></table></div>
    <p class="subtle">첫 입력 체결부터 마지막 입력 체결까지, 해당 기간에 매수 시작·전량 매도를 마친 거래 기준입니다.</p>
    <div class="section-heading"><h3>실제 체결 내역</h3><span>${d.records.length}건 · 수수료 합계 ${won(s?.fees)}</span></div>
    ${d.records.length?`<div class="table-scroll" data-preserve-scroll><table><thead><tr><th>체결 · 한국시간</th><th>가격 / 수량</th><th>수수료 / 입출금</th><th>실현손익</th><th></th></tr></thead><tbody>${d.records.slice().sort((a,b)=>b.ts-a.ts||b.sequence-a.sequence).map(record=>{const t=active.get(record.id)||record;return `<tr class="${t.voided?'manual-voided':''}"><td>${t.side==='buy'?'매수':'매도'}${t.voided?' · 취소':''}<small>${time(t.ts)}</small></td><td>${won(t.price)}<small>${number(t.volume,8)}개</small>${t.reference_price?`<small>계획 ${won(t.reference_price)}</small>`:''}</td><td>${won(t.fee)}<small>${t.voided?'—':won(t.net)}</small></td><td class="${color(t.realized)}">${won(t.realized)}</td><td>${t.voided?'':`<button class="text-button" data-void-record="${esc(t.id)}" ${disabled}>기록 취소</button>`}</td></tr>`;}).join('')}</tbody></table></div>`:'<p class="subtle">입력한 체결이 없습니다.</p>'}`;
}
