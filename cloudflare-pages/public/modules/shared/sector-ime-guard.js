let installed=false;
const SEARCH_SELECTOR='input[type="search"],[data-sector-search]';
export function installSectorImeGuard(){
  if(installed)return;installed=true;
  const composing=new WeakSet();
  document.addEventListener('compositionstart',event=>{const target=event.target;if(target instanceof HTMLInputElement&&target.matches(SEARCH_SELECTOR))composing.add(target)},true);
  document.addEventListener('input',event=>{const target=event.target;if(!(target instanceof HTMLInputElement)||!target.matches(SEARCH_SELECTOR))return;if(event.isComposing||composing.has(target))event.stopImmediatePropagation()},true);
  document.addEventListener('compositionend',event=>{const target=event.target;if(!(target instanceof HTMLInputElement)||!target.matches(SEARCH_SELECTOR))return;composing.delete(target);setTimeout(()=>{if(target.isConnected)target.dispatchEvent(new Event('input',{bubbles:true}))},0)},true);
}
