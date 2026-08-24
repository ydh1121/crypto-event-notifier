const $=id=>document.getElementById(id);
const state={user:null,snapshot:null,filter:'all',sort:'return_desc',search:'',inviteToken:'',listSignature:''};
const won=v=>`${Math.round(Number(v||0)).toLocaleString('ko-KR')}원`;
const pct=(v,d=2)=>`${Number(v||0)>=0?'+':''}${Number(v||0).toFixed(d)}%`;
const price=v=>{const n=Number(v||0);if(!n)return'-';return `${n.toLocaleString('ko-KR',{maximumFractionDigits:n<1?8:n<100?4:2})}원`};
const tone=v=>Number(v||0)>0?'positive':Number(v||0)<0?'negative':'';
const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

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
function showAuth(){show('authView',true);show('viewerView',false);show('logoutBtn',false);authMode(state.inviteToken?'invite':'login')}
function showViewer(){show('authView',false);show('viewerView',true);show('logoutBtn',true);$('userName').textContent=state.user?.display_name||state.user?.email||'-';$('userRole').textContent=state.user?.role==='owner'?'관리자':'조회 사용자';show('ownerPanel',state.user?.role==='owner')}
function ageSeconds(ts){return Math.max(0,Date.now()/1000-Number(ts||0))}
function updateFreshness(receivedAt,sourceTs){
  const pill=$('freshnessPill');const basis=Number(sourceTs||receivedAt||0);if(!basis){pill.className='pill neutral';pill.textContent='데이터 대기';return}
  const sec=Math.floor(ageSeconds(basis));
  if(sec<60){pill.className='pill good';pill.textContent=`최신 · ${sec}초 전`}
  else if(sec<180){pill.className='pill warn';pill.textContent=`${Math.floor(sec/60)}분 전`}
  else{pill.className='pill bad';pill.textContent=`PC 갱신 지연 · ${Math.floor(sec/60)}분 전`}
}
function stateLabel(row){if(row.state_label)return row.state_label;if(row.has_position)return'보유 중';if(Number(row.closed_trades)>0)return'매매 완료 · 대기';return'미진입'}
function renderCapital(pub){
  const start=Number(pub.aggregate_virtual_capital_krw||0),equity=Number(pub.equity_krw||0),pnl=Number(pub.pnl_krw??equity-start);
  $('startCapital').textContent=won(start);$('currentCapital').textContent=won(equity);$('currentCapital').className=tone(pnl);
  $('marketCount').textContent=`${Number(pub.market_count||0).toLocaleString('ko-KR')}개 코인 · 코인별 독립 가상계좌`;
  $('totalPnl').textContent=`${pnl>=0?'+':''}${won(pnl)}`;$('totalPnl').className=tone(pnl);$('totalReturn').textContent=`원금 대비 ${pct(pub.return_pct)}`;$('totalReturn').className=tone(pub.return_pct);
  $('totalCash').textContent=won(pub.cash_krw);$('activePositions').textContent=`${Number(pub.active_positions||0).toLocaleString('ko-KR')}개`;
  $('scanProgress').textContent=Number(pub.scan_total||0)>0?`최근 순회 ${Number(pub.scanned_count||0).toLocaleString('ko-KR')} / ${Number(pub.scan_total||0).toLocaleString('ko-KR')}`:'수집 상태 확인 중';
  const best=pub.best_market;$('leaderText').textContent=best?.symbol?`현재 1위 ${best.symbol} ${pct(best.return_pct)}`:'아직 순위 계산 중';
}
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
  box.innerHTML=rows.map((row,index)=>`<div class="market-row">
    <div class="rank">${index+1}</div>
    <div class="market-name"><b>${esc(row.symbol||row.market)}</b><i>${esc(stateLabel(row))}</i><small>${esc(row.name||row.market||'')}</small></div>
    <div class="market-metric"><span>현재가</span><b>${price(row.price)}</b><small>${row.position_avg_price?`평단 ${price(row.position_avg_price)}`:'평단 없음'}</small></div>
    <div class="market-metric"><span>보유금액</span><b>${won(row.position_value_krw)}</b><small>미실현 ${row.unrealized_pnl_krw>=0?'+':''}${won(row.unrealized_pnl_krw)}</small></div>
    <div class="market-metric market-return"><span>수익률</span><b class="${tone(row.return_pct)}">${pct(row.return_pct)}</b><small>${Number(row.closed_trades||0)}회 · 승률 ${Number(row.win_rate_pct||0).toFixed(1)}%</small></div>
  </div>`).join('');box.scrollTop=Math.min(scroll,box.scrollHeight-box.clientHeight);
}
function renderHoldings(privateData,visible){
  const data=privateData?.manual_holdings;const has=visible&&data&&Array.isArray(data.holdings);show('holdingsCard',Boolean(has));if(!has)return;
  $('holdingsSummary').innerHTML=`<div><span>투입 원금</span><b>${won(data.invested_krw)}</b></div><div><span>현재 평가액</span><b>${won(data.value_krw)}</b></div><div><span>평가 손익</span><b class="${tone(data.pnl_krw)}">${Number(data.pnl_krw||0)>=0?'+':''}${won(data.pnl_krw)}</b></div>`;
  $('holdingsList').innerHTML=data.holdings.length?data.holdings.map(row=>`<div class="holding-row"><div><span>${esc(row.market)}</span><b>${Number(row.volume||0).toLocaleString('ko-KR',{maximumFractionDigits:8})}</b></div><div><span>평단</span><b>${price(row.avg_price)}</b></div><div><span>현재가</span><b>${price(row.current_price)}</b></div><div><span>손익</span><b class="${tone(row.unrealized_pnl_krw)}">${pct(row.unrealized_pnl_pct)}</b></div></div>`).join(''):'<div class="empty">등록된 자산정보가 없습니다.</div>';
}
function renderSnapshot(payload){
  state.snapshot=payload?.snapshot||null;if(!state.snapshot){$('viewerSub').textContent='PC에서 첫 데이터를 보내면 이 화면이 자동으로 채워집니다.';updateFreshness(0,0);return}
  const pub=state.snapshot.public||{};$('viewerSub').textContent='PC 원본 DB는 외부에 공개하지 않고 조회용 스냅샷만 표시합니다.';updateFreshness(state.snapshot.received_at,pub.source_updated_at||state.snapshot.source_ts);renderCapital(pub);renderHoldings(state.snapshot.private,state.snapshot.private_visible);renderMarkets();
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
$('searchInput').addEventListener('input',event=>{state.search=event.target.value.trim();renderMarkets(true)});$('sortSelect').addEventListener('change',event=>{state.sort=event.target.value;renderMarkets(true)});$('filterRow').addEventListener('click',event=>{const btn=event.target.closest('button[data-filter]');if(!btn)return;state.filter=btn.dataset.filter;document.querySelectorAll('#filterRow button').forEach(item=>item.classList.toggle('active',item===btn));renderMarkets(true)});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.user)loadSnapshot()});boot();
