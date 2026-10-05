/** Update rendered values without replacing live controls, lists or scroll owners.
 * Templates are the same escaped application HTML used on the initial render. */
const keys=['data-render-key','data-continuity-key','id','data-holding','data-coin','data-experiment','data-strategy','data-event','data-period-experiment','data-study-experiment','data-action'];
const key=node=>node.nodeType===1?keys.map(name=>node.hasAttribute(name)?`${name}:${node.getAttribute(name)}`:'').find(Boolean)||'':'';
const compatible=(a,b)=>a.nodeType===b.nodeType&&a.nodeName===b.nodeName&&a.namespaceURI===b.namespaceURI;
const pendingSizes=new WeakMap();

function syncNode(current,next) {
  if(current.nodeType!==1){if(current.nodeValue!==next.nodeValue)current.nodeValue=next.nodeValue;return;}
  const disclosure=current.localName==='details';
  const reserved=pendingSizes.has(current)?current.style.minHeight:null;
  for(const attr of [...current.attributes]) {
    if(disclosure&&attr.name==='open')continue;
    if(!next.hasAttributeNS(attr.namespaceURI,attr.localName))current.removeAttributeNS(attr.namespaceURI,attr.localName);
  }
  for(const attr of next.attributes) {
    if(disclosure&&attr.name==='open')continue;
    if(current.getAttributeNS(attr.namespaceURI,attr.localName)!==attr.value)current.setAttributeNS(attr.namespaceURI,attr.name,attr.value);
  }
  if(reserved!==null)current.style.minHeight=reserved;
  syncChildren(current,next);
  if(['input','textarea','select'].includes(current.localName)) {
    if(current.type!=='file'&&current.value!==next.value)current.value=next.value;
    if(current.localName==='input'&&current.checked!==next.checked)current.checked=next.checked;
  }
}

function syncChildren(parent,nextParent) {
  const previous=[...parent.childNodes],keyed=new Map(previous.map(node=>[key(node),node]).filter(([id])=>id)),used=new Set();
  let cursor=parent.firstChild;
  for(const next of nextParent.childNodes) {
    const id=key(next);
    let current=id?keyed.get(id):cursor&&!key(cursor)&&compatible(cursor,next)?cursor:previous.find(node=>!used.has(node)&&!key(node)&&compatible(node,next));
    if(!current||used.has(current)||!compatible(current,next)) {
      current=next.cloneNode(true);parent.insertBefore(current,cursor);
    } else {
      if(current!==cursor)parent.insertBefore(current,cursor);
      syncNode(current,next);
    }
    used.add(current);cursor=current.nextSibling;
  }
  for(const node of previous)if(!used.has(node))node.remove();
}

export function updateHtml(node,html,{busy=false}={}) {
  if(!node)return;
  if(busy&&!pendingSizes.has(node)) {
    pendingSizes.set(node,node.style.minHeight);
    const height=node.getBoundingClientRect().height;
    if(height>0)node.style.minHeight=`${height}px`;
  }
  // Contextual fragments preserve table/SVG parsing rules and never detach the owner.
  const range=node.ownerDocument.createRange();range.selectNodeContents(node);
  syncChildren(node,range.createContextualFragment(html));
  if(!busy&&pendingSizes.has(node)){node.style.minHeight=pendingSizes.get(node);pendingSizes.delete(node);}
}
