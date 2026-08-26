const ROUTES=new Set(['dashboard','research','assets','paper','strategy','sectors','records','system']);
export function createRouter({store,root,nav,pages}){
  let current=null,currentName='';
  function syncNav(name){nav?.querySelectorAll('[data-route]').forEach(b=>b.classList.toggle('active',b.dataset.route===name))}
  function go(name,{replace=false}={}){if(!ROUTES.has(name))name='dashboard';if(currentName===name){current?.render?.();syncNav(name);return}current?.destroy?.();currentName=name;store.setUi({route:name},{scope:'router'});syncNav(name);root.innerHTML='';current=pages[name]?.();if(!current)throw new Error(`unknown page ${name}`);current.mount(root);current.render();if(!replace)window.scrollTo({top:0,left:0,behavior:'auto'})}
  nav?.addEventListener('click',e=>{const b=e.target.closest('[data-route]');if(b)go(b.dataset.route)});
  return{go,current:()=>currentName,render:()=>current?.render?.()};
}
