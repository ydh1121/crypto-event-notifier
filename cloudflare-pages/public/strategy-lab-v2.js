(()=>{
  if(window.__strategyLabViewerV2Loaded)return;
  window.__strategyLabViewerV2Loaded=true;
  const q=(s,r=document)=>r.querySelector(s),n=v=>Number(v||0),pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  const lab=()=>typeof state!=='undefined'?state.snapshot?.public?.strategy_lab||{}:{};
  const viewerExchange=()=>{const x=window.cryptoResearchExchange?.mode||((typeof state!=='undefined'&&state.snapshot?.public?.exchange)||'bithumb');return x==='upbit'?'upbit':'bithumb'};
  function candidate(row,criteria){const c=row?.candidate||{};if(row?.status==='paused'||c.status==='paused')return['일시정지','paused'];if(c.status==='candidate')return['후보 통과','candidate'];if(c.status==='rejected')return['게이트 미통과','rejected'];return[`검증 ${n(c.closed_trades||row.closed_trades).toFixed(0)}/${n(criteria?.min_closed_trades)||30}`,'warming']}
  function render(force=false){
    const root=q('#strategyLabCard');if(!root)return;
    const data=lab(),all=Array.isArray(data.experiments)?data.experiments:[],ex=viewerExchange(),criteria=data.candidate_criteria||{},rows=all.filter(r=>r.exchange===ex).sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    if(!rows.length){root.classList.remove('hidden');root.innerHTML='<div class="strategy-table-state">전략 비교 데이터를 불러오는 중입니다.</div>';return}
    root.classList.remove('hidden');
    root.innerHTML=`<div class="strategy-table-head"><div><p class="kicker">전략 비교</p><h3>${ex==='upbit'?'업비트':'빗썸'} · 같은 시장 데이터에서 전략 성과 비교</h3><p>수익률뿐 아니라 낙폭·Profit Factor·거래 표본·검증 게이트를 함께 봅니다.</p></div><span>${rows.length}개 전략</span></div><div class="strategy-table-wrap"><div class="strategy-table-row strategy-table-columns"><span>전략</span><span>수익률</span><span>최대 DD</span><span>PF</span><span>거래</span><span>승률</span><span>검증</span></div>${rows.map((r,i)=>{const [label,status]=candidate(r,criteria),pf=n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2);return`<div class="strategy-table-row ${i===0?'leader':''}"><span class="strategy-name"><i>${i+1}</i><b>${esc(r.label||r.style)}</b><small>${esc(r.description||'')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${pf}</span><span>${n(r.closed_trades).toFixed(0)}회</span><span>${n(r.win_rate_pct).toFixed(1)}%</span><span><em class="strategy-status ${status}">${esc(label)}</em><small>게이트 ${n(r.candidate?.passed_gates).toFixed(0)}/${n(r.candidate?.total_gates).toFixed(0)}</small></span></div>`}).join('')}</div><p class="strategy-table-note">후보 통과는 PAPER 연구 검증을 통과했다는 뜻이며 실제 주문 전략으로 자동 승격되지 않습니다.</p>`;
  }
  window.strategyLabV2={render};
  document.addEventListener('phase3exchangechange',()=>setTimeout(()=>render(true),80));
  document.addEventListener('viewer:snapshot',()=>setTimeout(()=>render(false),0));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>render(true),{once:true});else render(true);
})();