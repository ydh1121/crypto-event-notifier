(()=>{
  if(window.__strategyLabViewerV1Loaded)return;
  window.__strategyLabViewerV1Loaded=true;

  const q=(s,r=document)=>r.querySelector(s);
  const n=v=>Number(v||0);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const won=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
  const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  const STORE='strategyLabViewerV1';
  let exchange='bithumb';
  let lastSignature='';

  try{
    const saved=JSON.parse(localStorage.getItem(STORE)||'{}');
    if(['bithumb','upbit'].includes(saved.exchange))exchange=saved.exchange;
  }catch{}

  function save(){try{localStorage.setItem(STORE,JSON.stringify({exchange}))}catch{}}
  function lab(){return typeof state!=='undefined'?state.snapshot?.public?.strategy_lab||{}:{}}
  function root(){return q('#strategyLabCard')}
  function exchangeLabel(x){return x==='upbit'?'업비트':'빗썸'}

  function render(force=false){
    const el=root();if(!el)return;
    const data=lab(),all=Array.isArray(data.experiments)?data.experiments:[];
    if(!all.length){el.classList.add('hidden');return}
    const rows=all.filter(r=>r.exchange===exchange).sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    if(!rows.length){el.classList.add('hidden');return}
    const signature=`${exchange}|${n(data.updated_at)}|${rows.map(r=>`${r.style}:${n(r.return_pct)}:${n(r.closed_trades)}:${n(r.active_positions)}`).join('|')}`;
    if(!force&&signature===lastSignature)return;
    lastSignature=signature;
    el.classList.remove('hidden');
    const leader=rows[0];
    const enough=rows.filter(r=>n(r.closed_trades)>=20).length;
    el.innerHTML=`<div class="strategy-lab-head"><div><p class="kicker">STRATEGY LAB · PHASE 4</p><h3>같은 시장 데이터로 6가지 전략을 동시에 비교합니다.</h3><p>거래소 API를 추가 호출하지 않고 기존 시장 기억을 재사용합니다. 각 전략은 별도 PAPER 계좌와 학습상태를 가집니다.</p></div><div class="strategy-lab-switch"><button type="button" data-lab-exchange="bithumb" class="${exchange==='bithumb'?'active':''}">빗썸</button><button type="button" data-lab-exchange="upbit" class="${exchange==='upbit'?'active':''}">업비트</button></div></div><div class="strategy-lab-summary"><div><span>현재 1위</span><b>${esc(leader.label||leader.style)}</b><small class="${tone(leader.return_pct)}">${pct(leader.return_pct)} 누적</small></div><div><span>비교 전략</span><b>${rows.length}개</b><small>동일 원천 데이터</small></div><div><span>표본 20회 이상</span><b>${enough}개</b><small>표본이 적으면 순위 해석 주의</small></div><div><span>실행 모델</span><b>PAPER</b><small>수수료·슬리피지 포함</small></div></div><div class="strategy-lab-grid">${rows.map((r,i)=>{const trades=n(r.closed_trades),sample=trades>=20?'표본 형성':'초기 표본';return`<article class="strategy-lab-style ${i===0?'leader':''}"><div class="strategy-lab-style-head"><span><i>${i+1}</i><b>${esc(r.label||r.style)}</b></span><strong class="${tone(r.return_pct)}">${pct(r.return_pct)}</strong></div><p>${esc(r.description||'')}</p><div class="strategy-lab-metrics"><div><span>최대 낙폭</span><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></div><div><span>승률</span><b>${n(r.win_rate_pct).toFixed(1)}%</b></div><div><span>기대값</span><b class="${tone(r.expectancy_pct)}">${pct(r.expectancy_pct)}</b></div><div><span>완료 거래</span><b>${trades.toLocaleString('ko-KR')}</b></div><div><span>현재 보유</span><b>${n(r.active_positions).toLocaleString('ko-KR')}</b></div><div><span>Profit Factor</span><b>${n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2)}</b></div></div><footer><span>${exchangeLabel(exchange)}</span><span class="${trades>=20?'ready':'warming'}">${sample}</span></footer></article>`}).join('')}</div>`;
  }

  document.addEventListener('click',event=>{
    const btn=event.target.closest?.('[data-lab-exchange]');if(!btn)return;
    const next=btn.dataset.labExchange;if(!['bithumb','upbit'].includes(next)||next===exchange)return;
    exchange=next;save();render(true);
  });
  document.addEventListener('phase3exchangechange',event=>{
    const next=event.detail?.exchange;if(['bithumb','upbit'].includes(next)){exchange=next;save();render(true)}
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)render(true)});

  function install(){render(true);setInterval(()=>{if(!document.hidden&&typeof state!=='undefined'&&state.user)render(false)},15000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
