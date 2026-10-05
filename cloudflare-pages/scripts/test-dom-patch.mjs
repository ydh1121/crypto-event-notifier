import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {updateHtml} from '../public/modules/shared/dom-patch.js';
import {patchPreservingUi} from '../public/modules/shared/ui-continuity.js';

const dom=new JSDOM('<div id="root"></div>',{pretendToBeVisual:true});
for(const name of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element'])globalThis[name]=dom.window[name];
globalThis.CSS={escape:String};let frames=[],x=0,y=0,scrolls=0;
globalThis.requestAnimationFrame=fn=>frames.push(fn);
Object.defineProperties(window,{scrollX:{get:()=>x},scrollY:{get:()=>y}});
window.scrollTo=({left,top})=>{x=left;y=top;scrolls++;};
const root=document.getElementById('root'),patch=html=>patchPreservingUi(root,()=>updateHtml(root,html));
test.beforeEach(()=>{root.replaceChildren();frames=[];x=0;y=700;scrolls=0;});
test.after(()=>dom.window.close());

test('quote ticks mutate existing text and color, without detaching any element',()=>{
  updateHtml(root,'<section><b class="gain">1,200원</b><span>+2%</span></section>');
  const nodes=[root.firstChild,root.querySelector('b'),root.querySelector('b').firstChild,root.querySelector('span')];
  const observer=new dom.window.MutationObserver(()=>{});observer.observe(root,{subtree:true,attributes:true,characterData:true,childList:true});
  patch('<section><b class="loss">1,100원</b><span>−1%</span></section>');
  assert.deepEqual([root.firstChild,root.querySelector('b'),root.querySelector('b').firstChild,root.querySelector('span')],nodes);
  const changes=observer.takeRecords();assert.equal(changes.filter(c=>c.type==='childList').length,0);
  assert.equal(changes.filter(c=>c.type==='characterData').length,2);assert.equal(root.querySelector('b').className,'loss');
  assert.equal(y,700);assert.equal(scrolls,0);assert.equal(frames.length,0);observer.disconnect();
});
test('keyed additions and reordering retain coin identity, focus, listeners and rail position',()=>{
  const html=coins=>`<div id="rail" data-preserve-scroll>${coins.map(c=>`<button data-coin="${c}" data-continuity-key="coin-${c}">${c}</button>`).join('')}</div>`;
  updateHtml(root,html(['B3','DEXE']));const coin=root.querySelector('[data-coin=DEXE]'),rail=root.firstChild;
  let clicks=0;coin.addEventListener('click',()=>clicks++);coin.focus();rail.scrollLeft=50;
  patch(html(['A','DEXE','B3']));assert.equal(root.querySelector('[data-coin=DEXE]'),coin);assert.equal(document.activeElement,coin);
  assert.equal(rail.scrollLeft,50);coin.click();assert.equal(clicks,1);assert.equal(y,700);
});
test('open and closed disclosures, focused editor and caret remain owned by the user',()=>{
  const html=value=>`<details data-continuity-key="rules" open><summary>조건</summary><input id="amount" value="${value}"></details>`;
  updateHtml(root,html('12345'));const details=root.firstChild,input=root.querySelector('input');details.open=false;input.focus();input.setSelectionRange(2,4);
  patch(html('12345'));assert.equal(details.open,false);assert.equal(input.selectionStart,2);assert.equal(input.selectionEnd,4);assert.equal(root.querySelector('input'),input);
  details.open=true;patch(html('12345'));assert.equal(details.open,true);assert.equal(document.activeElement,input);
});
test('controlled form values and flags apply explicit zero, reset, select and checkbox changes',()=>{
  updateHtml(root,'<input id="qty" type="number" value="10"><input id="check" type="checkbox" checked><select id="market"><option value="a" selected>A</option><option value="b">B</option></select><textarea id="note">old</textarea>');
  const qty=root.querySelector('#qty'),select=root.querySelector('select');qty.value='9';select.value='b';
  patch('<input id="qty" type="number" value="0" disabled><input id="check" type="checkbox"><select id="market"><option value="b" selected>B</option><option value="a">A</option></select><textarea id="note">new</textarea>');
  assert.equal(qty.value,'0');assert.equal(qty.disabled,true);assert.equal(root.querySelector('#check').checked,false);assert.equal(select.value,'b');assert.equal(root.querySelector('textarea').value,'new');
  patch('<input id="qty" type="number" value="">');assert.equal(qty.value,'');assert.equal(qty.disabled,false);
});
test('table rows and SVG points keep their actual DOM identity and namespace',()=>{
  const html=v=>`<table><tbody><tr data-render-key="fill-1"><td>${v}원</td></tr></tbody></table><svg><polyline points="0,${v} 10,20"/></svg>`;
  updateHtml(root,html(1));const row=root.querySelector('tr'),line=root.querySelector('polyline');patch(html(2));
  assert.equal(root.querySelector('tr'),row);assert.equal(root.querySelector('polyline'),line);assert.equal(line.namespaceURI,'http://www.w3.org/2000/svg');assert.equal(line.getAttribute('points'),'0,2 10,20');
});
test('loading preserves height through parent renders, then releases it after data arrives',()=>{
  updateHtml(root,'<section id="result" style="min-height:12px"><table><tr><td>row</td></tr></table></section>');
  const box=root.firstChild;box.getBoundingClientRect=()=>({height:650});
  updateHtml(box,'<p>불러오는 중</p>',{busy:true});assert.equal(box.style.minHeight,'650px');
  updateHtml(root,'<section id="result"><p>불러오는 중</p></section>');assert.equal(box.style.minHeight,'650px');
  updateHtml(box,'<p>결과</p>');assert.equal(box.style.minHeight,'12px');
});
test('a synchronous layout correction never queues an old scroll position over later user scrolling',()=>{
  updateHtml(root,'<button id="load">불러오기</button>');const button=root.firstChild;button.focus();
  patchPreservingUi(root,()=>{y=0;updateHtml(root,'<button id="load">완료</button>');});
  assert.equal(y,700);assert.equal(scrolls,1);assert.equal(frames.length,0);
  y=950;frames.forEach(f=>f());assert.equal(y,950);assert.equal(root.firstChild,button);
});
