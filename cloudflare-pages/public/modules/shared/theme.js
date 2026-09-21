const STORAGE_KEY='crypto-viewer-theme';
const THEMES=new Set(['light','dark']);

function savedTheme(){
  try{
    const value=localStorage.getItem(STORAGE_KEY);
    return THEMES.has(value)?value:'';
  }catch{return''}
}

function systemTheme(){
  try{return window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}catch{return'light'}
}

function currentTheme(){
  const value=document.documentElement.dataset.theme;
  return THEMES.has(value)?value:(savedTheme()||systemTheme());
}

function updateMeta(theme){
  const meta=document.querySelector('meta[name="theme-color"]');
  if(meta)meta.setAttribute('content',theme==='dark'?'#111214':'#ffffff');
}

function updateButtons(theme){
  const dark=theme==='dark';
  for(const button of document.querySelectorAll('[data-theme-toggle]')){
    button.textContent=dark?'밝게':'어둡게';
    button.setAttribute('aria-label',dark?'밝은 화면으로 바꾸기':'어두운 화면으로 바꾸기');
    button.setAttribute('aria-pressed',dark?'true':'false');
    button.dataset.themeState=theme;
  }
}

export function applyTheme(theme,{persist=false}={}){
  const next=THEMES.has(theme)?theme:'light';
  document.documentElement.dataset.theme=next;
  document.documentElement.style.colorScheme=next;
  updateMeta(next);
  updateButtons(next);
  if(persist){try{localStorage.setItem(STORAGE_KEY,next)}catch{}}
  return next;
}

export function installThemeToggle(){
  applyTheme(savedTheme()||systemTheme());
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-theme-toggle]');
    if(!button)return;
    applyTheme(currentTheme()==='dark'?'light':'dark',{persist:true});
  });
  try{
    const media=window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change',event=>{
      if(savedTheme())return;
      applyTheme(event.matches?'dark':'light');
    });
  }catch{}
}
