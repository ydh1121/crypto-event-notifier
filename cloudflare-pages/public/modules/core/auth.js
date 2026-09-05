import{request}from'./http.js';
function show(el,on=true){el?.classList.toggle('hidden',!on)}
export function createAuth({store,onReady,onLogout}){
  const auth=document.getElementById('authView'),app=document.getElementById('appShell');
  const loginCard=document.getElementById('loginCard'),bootstrapCard=document.getElementById('bootstrapCard'),inviteCard=document.getElementById('inviteCard');
  let inviteToken='';
  const mode=name=>{show(loginCard,name==='login');show(bootstrapCard,name==='bootstrap');show(inviteCard,name==='invite')};
  const showAuth=()=>{show(auth,true);show(app,false);mode(inviteToken?'invite':'login')};
  const showApp=user=>{store.setUser(user);show(auth,false);show(app,true);onReady?.()};
  async function login(email,password){const data=await request('/api/auth/login',{method:'POST',body:{email,password}});showApp(data.user);return data.user}
  async function boot(){
    const m=location.hash.match(/^#invite=(.+)$/);if(m){try{inviteToken=decodeURIComponent(m[1])}catch{}history.replaceState(null,'',location.pathname+location.search);showAuth();mode('invite');return}
    try{const me=await request('/api/auth/me');showApp(me.user)}catch{showAuth()}
  }
  document.getElementById('loginForm')?.addEventListener('submit',async e=>{e.preventDefault();try{await login(document.getElementById('loginEmail').value.trim(),document.getElementById('loginPassword').value)}catch(err){alert(err.message)}});
  document.getElementById('bootstrapForm')?.addEventListener('submit',async e=>{e.preventDefault();try{const email=document.getElementById('bootstrapEmail').value.trim(),password=document.getElementById('bootstrapPassword').value;await request('/api/auth/bootstrap',{method:'POST',headers:{Authorization:`Bearer ${document.getElementById('bootstrapToken').value}`},body:{email,password,display_name:document.getElementById('bootstrapName').value.trim()}});await login(email,password)}catch(err){alert(err.message)}});
  document.getElementById('inviteForm')?.addEventListener('submit',async e=>{e.preventDefault();try{const data=await request('/api/invites/activate',{method:'POST',body:{token:inviteToken,password:document.getElementById('invitePassword').value,display_name:document.getElementById('inviteName').value.trim()}});inviteToken='';showApp(data.user)}catch(err){alert(err.message)}});
  document.getElementById('showBootstrapBtn')?.addEventListener('click',()=>mode('bootstrap'));
  document.getElementById('showLoginBtn')?.addEventListener('click',()=>mode('login'));
  document.getElementById('logoutBtn')?.addEventListener('click',async()=>{try{await request('/api/auth/logout',{method:'POST'})}catch{}store.resetSession();showAuth();onLogout?.()});
  return{boot,showAuth,showApp};
}
