const $=id=>document.getElementById(id);
const state={user:null,snapshot:null,filter:'all',sort:'return_desc',search:'',inviteToken:'',listSignature:'',activeView:'home',coinMarket:''};
const won=v=>`${Math.round(Number(v||0)).toLocaleString('ko-KR')}원`;
const pct=(v,d=2)=>`${Number(v||0)>=0?'+':''}${Number(v||0).toFixed(d)}%`;
const price=v=>{const n=Number(v||0);if(!n)return'-';return `${n.toLocaleString('ko-KR',{maximumFractionDigits:n<1?8:n<100?4:2})}원`};
const tone=v=>Number(v||0)>0?'positive':Number(v||0)<0?'negative':'';
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const dateTime=ts=>{const n=Number(ts||0);return n?new Date(n*1000).toLocaleString('ko-KR'):'-'};

async function request(path,options={}){
  const headers={...(options.headers||{})};
  if(options.body&&typeof options.body!=='string'){headers['content-type']='application/json';options.body=JSON.stringify(options.body)}
  const response=await fetch(path,{...options,headers,credentials:'same-origin',cache:'no-store'});
  let body={};try{body=await response.json()}catch{}
  if(!response.ok){const err=new Error(body?.error?.message||`요청 실패 ${response.status}`);err.status=response.status;err.code=body?.error?.code;throw err}
  return body;
}
function show(id,visible=true){$(id)?.classList.toggle('hidden',!visible)}
function clearFragment(){if(location.hash)history.replaceState(null,'',`${location.pathname}${location.search}`)}
function readInvite(){const match=location.hash.match(/^#invite=(.+)$/);if(!match)return'';try{return decodeURIComponent(match[1])}catch{return''}}
function authMode(mode){show('loginCard',mode==='login');show('bootstrapCard',mode==='bootstrap');show('inviteCard',mode==='invite')}
function showAuth(){show('authView',true);show('viewerView',false);show('viewerNav',false);show('logoutBtn',false);authMode(state.inviteToken?'invite':'login')}
function showViewer(){show('authView',false);show('viewerView',true);show('viewerNav',true);show('logoutBtn',true);$('userName').textContent=state.user?.display_name||state.user?.email||'-';$('userRole').textContent=state.user?.role==='owner'?'관리자':'조회 사용자';show('ownerPanel',state.user?.role==='owner');renderAccount();switchView(state.activeView)}
function ageSeconds(ts){return Math.max(0,Date.now()/1000-Number(ts||0))}
function updateFreshness(receivedAt,sourceTs){
  const pill=$('freshnessPill');const basis=Number(sourceTs||receivedAt||0);if(!basis){pill.className='pill neutral';pill.textContent='데이터 대기';return}
  const sec=Math.floor(ageSeconds(basis));
  if(sec<60){pill.className='pill good';pill.textContent=`최신 · ${sec}초 전`}
  else if(sec<180){pill.className='pill warn';pill.textContent=`${Math.floor(sec/60)}분 전`}
  else{pill.className='pill bad';pill.textContent=`PC 갱신 지연 · ${Math.floor(sec/60)}분 전`}
}
function switchView(view){
  state.activeView=view;
  document.querySelectorAll('[data-view-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.viewPanel===view));
  document.querySelectorAll('#viewerNav button[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
  if(view==='coin')renderCoin();
  if(view==='results')renderMarkets(true);
}
function stateLabel(row){if(row?.state_label)return row.state_label;if(row?.has_position)return'보유 중';if(Number(row?.closed_trades)>0)return'매매 완료 · 대기';return'미진입'}
function scoreGrade(value){const n=Number(value||0);if(n<40)return'매우 나쁨';if(n<55)return'좋지 않음';if(n<65)return'보통';if(n<75)return'좋음';return'매우 좋음'}
function intentLabel(row){
  const raw=String(row?.trade_intent||'').toLowerCase();
  if(row?.has_position)return'보유 상태 관리 중';
  if(raw.includes('buy')||raw.includes('enter'))return'매수 후보';
  if(raw.includes('pullback'))return'가격이 내려오길 기다림';
  if(raw.includes('risk')||raw.includes('block'))return'지금은 매수하지 않음';
  return'조금 더 지켜보기';
}
function renderCapital(pub){
  const start=Number(pub.aggregate_virtual_capital_krw||0),equity=Number(pub.equity_krw||0),pnl=Number(pub.pnl_krw??equity-start);
  $('startCapital').textContent=won(start);$('currentCapital').textContent=won(equity);$('currentCapital').className=tone(pnl);
  $('marketCount').textContent=`${Number(pub.market_count||0).toLocaleString('ko-KR')}개 코인 · 코인별 독립 가상계좌`;
  $('totalPnl').textContent=`${pnl>=0?'+':''}${won(pnl)}`;$('totalPnl').className=tone(pnl);$('totalReturn').textContent=`원금 대비 ${pct(pub.return_pct)}`;$('totalReturn').className=tone(pub.return_pct);
  $('totalCash').textContent=won(pub.cash_krw);$('activePositions').textContent=`${Number(pub.active_positions||0).toLocaleString('ko-KR')}개`;
  $('scanProgress').textContent=Number(pub.scan_total||0)>0?`최근 순회 ${Number(pub.scanned_count||0).toLocaleString('ko-KR')} / ${Number(pub.scan_total||0).toLocaleString('ko-KR')}`:'수집 상태 확인 중';
  const best=pub.best_market;$('leaderText').textContent=best?.symbol?`현재 1위 ${best.symbol} ${pct(best.return_pct)}`:'아직 순위 계산 중';
}
function renderHome(pub){
  const best=pub.best_market||{};
  $('homeLeader').innerHTML=best?.symbol?`<div class="summary-line"><span>코인</span><b>${esc(best.symbol)}</b></div><div class="summary-line"><span>수익률</span><b class="${tone(best.return_pct)}">${pct(best.return_pct)}</b></div><div class="summary-line"><span>현재 상태</span><b>${esc(stateLabel(best))}</b></div><button class="inline-link" type="button" data-open-market="${esc(best.market||'')}">코인 상세 보기</button>`:'<div class="empty">아직 순위 계산 중입니다.</div>';
  renderNode(pub.research_node,'homeNode');
}
function nodeEntries(node){
  if(!node||typeof node!=='object')return[];
  const components=Array.isArray(node.components)?node.components:Array.isArray(node.component_status)?node.component_status:[];
  const online=node.online??node.supervisor_online??node.running;
  const entries=[];
  if(online!==undefined)entries.push(['연구 Supervisor',online?'정상 실행':'확인 필요']);
  if(components.length)entries.push(['구성요소',`${components.length}개`]);
  if(node.reference_updates!==undefined)entries.push(['외부 레포 업데이트',`${Number(node.reference_updates||0)}건`]);
  if(node.reference_failures!==undefined)entries.push(['외부 레포 오류',`${Number(node.reference_failures||0)}건`]);
  if(!entries.length)entries.push(['24시간 연구 노드','스냅샷 수신 중']);
  return entries;
}
function renderNode(node,id){const box=$(id);if(!box)return;box.innerHTML=nodeEntries(node).map(([label,value])=>`<div class="summary-line"><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join('')}
function filteredRows(){
  const rows=[...(state.snapshot?.public?.leaderboard||[])];const q=state.search.toLowerCase();
  let result=rows.filter(row=>!q||`${row.symbol||''} ${row.market||''} ${row.name||''}`.toLowerCase().includes(q));
  if(state.filter==='holding')result=result.filter(row=>row.has_position);
  else if(state.filter==='completed')result=result.filter(row=>!row.has_position&&Number(row.closed_trades||0)>0);
  else if(state.filter==='profit')result=result.filter(row=>Number(row.return_pct||0)>0);
  else if(state.filter==='loss')result=result.filter(row=>Number(row.return_pct||0)<0);
  const sorters={
    return_desc:(a,b)=>Number(b.return_pct||0)-Number(a.return_pct||0),return_asc:(a,b)=>Number(a.return_pct||0)-Number(b.return_pct||0),
    position_desc:(a,b)=>Number(b.position_value_krw||0)-Number(a.position_value_krw||0),pnl_desc:(a,b)=>Number(b.unrealized_pnl_krw||0)-Number(a.unrealized_pnl_krw||0),
    trades_desc:(a,b)=>Number(b.closed_trades||0)-Number(a.closed_trades||0),opportunity_desc:(a,b)=>Number(b.opportunity_score||0)-Number(a.opportunity_score||0),
  };result.sort(sorters[state.sort]||sorters.return_desc);return result;
}
function renderMarkets(force=false){
  const rows=filteredRows();const sig=`${state.filter}|${state.sort}|${state.search}|${rows.map(r=>`${r.market}:${r.signal_ts}:${r.return_pct}:${r.position_value_krw}`).join(';')}`;
  if(!force&&sig===state.listSignature)return;state.listSignature=sig;const box=$('marketList');const scroll=box.scrollTop;
  if(!rows.length){box.innerHTML='<div class="empty">조건에 맞는 코인이 없습니다.</div>';return}
  box.innerHTML=rows.map((row,index)=>`<button type="button" class="market-row" data-open-market="${esc(row.market||'')}">
    <div class="rank">${index+1}</div>
    <div class="market-name"><b>${esc(row.symbol||row.market)}</b><i>${esc(stateLabel(row))}</i><small>${esc(row.name||row.market||'')}</small></div>
    <div class="market-metric"><span>현재가</span><b>${price(row.price)}</b><small>${row.position_avg_price?`평단 ${price(row.position_avg_price)}`:'평단 없음'}</small></div>
    <div class="market-metric"><span>보유금액</span><b>${won(row.position_value_krw)}</b><small>미실현 ${Number(row.unrealized_pnl_krw||0)>=0?'+':''}${won(row.unrealized_pnl_krw)}</small></div>
    <div class="market-metric market-return"><span>수익률</span><b class="${tone(row.return_pct)}">${pct(row.return_pct)}</b><small>${Number(row.closed_trades||0)}회 · 승률 ${Number(row.win_rate_pct||0).toFixed(1)}%</small></div>
  </button>`).join('');box.scrollTop=Math.max(0,Math.min(scroll,box.scrollHeight-box.clientHeight));
}
function renderHoldings(privateData,visible){
  const data=privateData?.manual_holdings;const has=visible&&data&&Array.isArray(data.holdings);show('holdingsCard',Boolean(has));if(!has)return;
  $('holdingsSummary').innerHTML=`<div><span>투입 원금</span><b>${won(data.invested_krw)}</b></div><div><span>현재 평가액</span><b>${won(data.value_krw)}</b></div><div><span>평가 손익</span><b class="${tone(data.pnl_krw)}">${Number(data.pnl_krw||0)>=0?'+':''}${won(data.pnl_krw)}</b></div>`;
  $('holdingsList').innerHTML=data.holdings.length?data.holdings.map(row=>`<div class="holding-row"><div><span>${esc(row.market)}</span><b>${Number(row.volume||0).toLocaleString('ko-KR',{maximumFractionDigits:8})}</b></div><div><span>평단</span><b>${price(row.avg_price)}</b></div><div><span>현재가</span><b>${price(row.current_price)}</b></div><div><span>손익</span><b class="${tone(row.unrealized_pnl_krw)}">${pct(row.unrealized_pnl_pct)}</b></div></div>`).join(''):'<div class="empty">등록된 자산정보가 없습니다.</div>';
}
function marketRows(){return state.snapshot?.public?.leaderboard||[]}
function populateCoinSelect(){
  const select=$('coinSelect');if(!select)return;const rows=[...marketRows()].sort((a,b)=>String(a.symbol||a.market).localeCompare(String(b.symbol||b.market)));
  if(!rows.length){select.innerHTML='<option>데이터 대기</option>';return}
  if(!state.coinMarket||!rows.some(row=>row.market===state.coinMarket))state.coinMarket=state.snapshot?.public?.best_market?.market||rows[0].market;
  const signature=rows.map(row=>row.market).join('|');
  if(select.dataset.signature!==signature){select.dataset.signature=signature;select.innerHTML=rows.map(row=>`<option value="${esc(row.market)}">${esc(row.symbol||row.market)} · ${esc(row.name||row.market||'')}</option>`).join('')}
  select.value=state.coinMarket;
}
function scoreCard(label,value){const n=Number(value||0);return `<div class="score-card"><span>${esc(label)}</span><b>${scoreGrade(n)}</b><strong>${n.toFixed(1)} / 100</strong><i><em style="width:${Math.max(0,Math.min(100,n))}%"></em></i></div>`}
function renderCoin(){
  populateCoinSelect();const row=marketRows().find(item=>item.market===state.coinMarket);const box=$('coinDetailCard');if(!box)return;
  if(!row){box.innerHTML='<div class="empty">코인 데이터를 기다리는 중입니다.</div>';return}
  const account=Number(row.equity_krw||0),cash=Number(row.cash_krw||0),position=Number(row.position_value_krw||0);
  box.innerHTML=`<div class="coin-hero"><div><p class="kicker">${esc(row.market||'')}</p><h3>${esc(row.symbol||row.market)}</h3><p>${esc(intentLabel(row))}</p></div><div class="coin-price"><span>현재가</span><b>${price(row.price)}</b><strong class="${tone(row.return_pct)}">${pct(row.return_pct)}</strong></div></div>
    <div class="coin-account-grid"><div><span>가상계좌 평가액</span><b>${won(account)}</b></div><div><span>남은 현금</span><b>${won(cash)}</b></div><div><span>현재 보유금액</span><b>${won(position)}</b></div><div><span>평균 매수가</span><b>${row.position_avg_price?price(row.position_avg_price):'보유 없음'}</b></div><div><span>미실현 손익</span><b class="${tone(row.unrealized_pnl_krw)}">${Number(row.unrealized_pnl_krw||0)>=0?'+':''}${won(row.unrealized_pnl_krw)}</b></div><div><span>완료 거래</span><b>${Number(row.closed_trades||0)}회 · 승률 ${Number(row.win_rate_pct||0).toFixed(1)}%</b></div></div>
    <div class="score-grid">${scoreCard('전체 시장 분위기',row.regime_score)}${scoreCard('지금 매수 타이밍',row.entry_score)}${scoreCard('현재 기회점수',row.opportunity_score)}</div>
    <div class="coin-note"><span>현재 상태</span><b>${esc(stateLabel(row))}</b><small>권장 가상 투입비중 ${Number(row.suggested_weight_pct||0).toFixed(1)}%</small></div>`;
}
function renderRecords(pub){
  const rows=marketRows(),completed=rows.filter(row=>Number(row.closed_trades||0)>0),trades=rows.reduce((sum,row)=>sum+Number(row.closed_trades||0),0),winners=completed.filter(row=>Number(row.return_pct||0)>0).length;
  $('recordSnapshot').innerHTML=`<div class="summary-line"><span>PC 데이터 시각</span><b>${dateTime(pub.source_updated_at)}</b></div><div class="summary-line"><span>Cloudflare 수신</span><b>${dateTime(state.snapshot?.received_at)}</b></div><div class="summary-line"><span>시장 수</span><b>${Number(pub.market_count||0)}개</b></div>`;
  $('recordTrades').innerHTML=`<div class="summary-line"><span>완료 거래 누적</span><b>${trades.toLocaleString('ko-KR')}회</b></div><div class="summary-line"><span>거래 경험 있는 코인</span><b>${completed.length}개</b></div><div class="summary-line"><span>현재 원금보다 높은 코인</span><b>${winners}개</b></div>`;
}
function renderAccount(){const box=$('settingsAccount');if(!box||!state.user)return;box.innerHTML=`<div class="summary-line"><span>이름</span><b>${esc(state.user.display_name||'-')}</b></div><div class="summary-line"><span>권한</span><b>${state.user.role==='owner'?'관리자':'조회 사용자'}</b></div><div class="summary-line"><span>내 자산정보</span><b>${state.user.can_view_holdings||state.user.role==='owner'?'볼 수 있음':'권한 없음'}</b></div>`}
function renderSettings(pub){renderNode(pub.research_node,'settingsNode');renderAccount()}
function renderSnapshot(payload){
  state.snapshot=payload?.snapshot||null;if(!state.snapshot){$('viewerSub').textContent='PC에서 첫 데이터를 보내면 이 화면이 자동으로 채워집니다.';updateFreshness(0,0);return}
  const pub=state.snapshot.public||{};$('viewerSub').textContent='PC 원본 DB는 외부에 공개하지 않고 조회용 스냅샷만 표시합니다.';updateFreshness(state.snapshot.received_at,pub.source_updated_at||state.snapshot.source_ts);renderCapital(pub);renderHoldings(state.snapshot.private,state.snapshot.private_visible);renderHome(pub);renderMarkets();populateCoinSelect();renderCoin();renderRecords(pub);renderSettings(pub);
}
async function loadSnapshot(){if(!state.user)return;try{const data=await request('/api/snapshot');if(data.user)state.user=data.user;renderSnapshot(data)}catch(err){if(err.status===401){state.user=null;showAuth()}}}
async function bootstrap(event){event.preventDefault();const email=$('bootstrapEmail').value.trim(),password=$('bootstrapPassword').value,name=$('bootstrapName').value.trim(),token=$('bootstrapToken').value;try{await request('/api/auth/bootstrap',{method:'POST',headers:{Authorization:`Bearer ${token}`},body:{email,password,display_name:name}});await doLogin(email,password)}catch(err){alert(err.message)}}
async function doLogin(email,password){const data=await request('/api/auth/login',{method:'POST',body:{email,password}});state.user=data.user;showViewer();await loadSnapshot()}
async function login(event){event.preventDefault();try{await doLogin($('loginEmail').value.trim(),$('loginPassword').value)}catch(err){alert(err.message)}}
async function activateInvite(event){event.preventDefault();try{const data=await request('/api/invites/activate',{method:'POST',body:{token:state.inviteToken,password:$('invitePassword').value,display_name:$('inviteName').value.trim()}});state.user=data.user;state.inviteToken='';clearFragment();showViewer();await loadSnapshot()}catch(err){alert(err.message)}}
async function logout(){try{await request('/api/auth/logout',{method:'POST'})}catch{}state.user=null;state.snapshot=null;showAuth()}
async function createInvite(event){event.preventDefault();try{const data=await request('/api/invites/create',{method:'POST',body:{email:$('inviteEmail').value.trim(),can_view_holdings:$('inviteHoldings').checked}});const link=`${location.origin}/#invite=${encodeURIComponent(data.invite.token)}`;const result=$('inviteResult');result.classList.remove('hidden');result.innerHTML=`<b>초대 링크가 만들어졌습니다.</b><code>${esc(link)}</code><div style="margin-top:8px">이 링크의 초대 토큰은 이 화면에서 한 번만 보여줍니다.</div>`;$('inviteEmail').value=''}catch(err){alert(err.message)}}
async function boot(){
  state.inviteToken=readInvite();if(state.inviteToken){clearFragment();showAuth();authMode('invite');return}
  try{const me=await request('/api/auth/me');state.user=me.user;showViewer();await loadSnapshot()}catch{showAuth()}
  setInterval(()=>{if(state.user&&!document.hidden)loadSnapshot()},15000);
}
$('loginForm').addEventListener('submit',login);$('bootstrapForm').addEventListener('submit',bootstrap);$('inviteForm').addEventListener('submit',activateInvite);$('logoutBtn').addEventListener('click',logout);$('inviteCreateForm').addEventListener('submit',createInvite);
$('showBootstrapBtn').addEventListener('click',()=>authMode('bootstrap'));$('showLoginBtn').addEventListener('click',()=>authMode('login'));
$('viewerNav').addEventListener('click',event=>{const button=event.target.closest('button[data-view]');if(button)switchView(button.dataset.view)});
$('searchInput').addEventListener('input',event=>{state.search=event.target.value.trim();renderMarkets(true)});$('sortSelect').addEventListener('change',event=>{state.sort=event.target.value;renderMarkets(true)});$('filterRow').addEventListener('click',event=>{const btn=event.target.closest('button[data-filter]');if(!btn)return;state.filter=btn.dataset.filter;document.querySelectorAll('#filterRow button').forEach(item=>item.classList.toggle('active',item===btn));renderMarkets(true)});
$('coinSelect').addEventListener('change',event=>{state.coinMarket=event.target.value;renderCoin()});
document.addEventListener('click',event=>{const target=event.target.closest('[data-open-market]');if(!target)return;state.coinMarket=target.dataset.openMarket;switchView('coin')});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.user)loadSnapshot()});boot();
