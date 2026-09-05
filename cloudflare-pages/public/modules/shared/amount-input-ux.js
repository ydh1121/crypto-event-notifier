const PRESETS=[
  [1_000_000,'100만원'],
  [5_000_000,'500만원'],
  [10_000_000,'1,000만원'],
  [50_000_000,'5,000만원'],
  [100_000_000,'1억원']
];

function presetButtons(kind,index=''){
  return`<div class="amount-quick-buttons" data-amount-quick-for="${kind}${index}"><span>빠른 금액</span>${PRESETS.map(([value,label])=>`<button type="button" data-amount-preset="${value}" data-amount-target="${kind}"${index!==''?` data-amount-index="${index}"`:''}>${label}</button>`).join('')}<small>직접 입력은 1억원을 넘겨도 가능합니다.</small></div>`;
}

function decorateDirect(root){
  const input=root.querySelector('[data-direct-amount]');
  if(!input||input.dataset.amountUx==='1')return;
  input.dataset.amountUx='1';
  input.removeAttribute('max');
  input.setAttribute('inputmode','numeric');
  input.setAttribute('step','10000');
  input.setAttribute('placeholder','예: 10000000');
  const fields=input.closest('.calculator-fields');
  if(fields&&!fields.parentElement?.querySelector('[data-amount-quick-for="direct"]'))fields.insertAdjacentHTML('afterend',presetButtons('direct'));
}

function decorateAveraging(root){
  for(const row of root.querySelectorAll('[data-avg-row]')){
    const input=row.querySelector('[data-avg-amount]');
    if(!input||input.dataset.amountUx==='1')continue;
    input.dataset.amountUx='1';
    input.removeAttribute('max');
    input.setAttribute('inputmode','numeric');
    input.setAttribute('step','10000');
    input.setAttribute('placeholder','예: 10000000');
    const field=input.closest('.calculator-field');
    const index=row.dataset.avgRow||'0';
    if(field&&!row.querySelector(`[data-amount-quick-for="avg${index}"]`))field.insertAdjacentHTML('afterend',presetButtons('avg',index));
  }
}

function decorate(root){decorateDirect(root);decorateAveraging(root)}

export function installAmountInputUx(root){
  if(!root||root.dataset.amountInputUx==='1')return;
  root.dataset.amountInputUx='1';
  decorate(root);
  const observer=new MutationObserver(()=>decorate(root));
  observer.observe(root,{childList:true,subtree:true});
  root.addEventListener('click',event=>{
    const button=event.target.closest('[data-amount-preset]');
    if(!button||!root.contains(button))return;
    const value=Number(button.dataset.amountPreset||0);
    if(!Number.isFinite(value)||value<=0)return;
    let input=null;
    if(button.dataset.amountTarget==='direct')input=root.querySelector('[data-direct-amount]');
    else{
      const row=root.querySelector(`[data-avg-row="${button.dataset.amountIndex||'0'}"]`);
      input=row?.querySelector('[data-avg-amount]')||null;
    }
    if(!input)return;
    input.value=String(value);
    input.dispatchEvent(new Event('input',{bubbles:true}));
    input.focus({preventScroll:true});
  });
}
