let installed=false;
export function installSectorImeGuard(){
  if(installed)return;installed=true;
  const composing=new WeakSet();
  document.addEventListener('compositionstart',event=>{const target=event.target;if(target instanceof HTMLInputElement&&target.matches('[data-sector-search]'))composing.add(target)},true);
  document.addEventListener('input',event=>{const target=event.target;if(!(target instanceof HTMLInputElement)||!target.matches('[data-sector-search]'))return;if(event.isComposing||composing.has(target))event.stopImmediatePropagation()},true);
  document.addEventListener('compositionend',event=>{const target=event.target;if(!(target instanceof HTMLInputElement)||!target.matches('[data-sector-search]'))return;composing.delete(target);setTimeout(()=>{if(target.isConnected)target.dispatchEvent(new Event('input',{bubbles:true}))},0)},true);
}
