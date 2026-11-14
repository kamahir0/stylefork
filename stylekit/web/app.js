"use strict";
const $ = id => document.getElementById(id);
const verdictNames = {good:'良い', neutral:'普通', bad:'微妙', unsure:'判断困難', '':'未評価'};
let review, draft, current = 0, catalog = [], timer, queue = Promise.resolve(), generation = 0, savedGeneration = 0;
let conflict = false, focused = false, nativeFullscreen = false, chromeTimer;
const scales = {left: 'fit', right: 'fit', focus: 'fit'};
const reviewId = new URLSearchParams(location.search).get('review');
function fail(e) { $('error').textContent = e.message || String(e); $('error').hidden = false; $('save-status').textContent = '保存できませんでした'; }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '読み込みに失敗しました');
  return result;
}
const numberText = item => '#' + String(item.number).padStart(2,'0');
const imageUrl = item => `/image?review=${encodeURIComponent(reviewId)}&number=${item.number}`;
function rating(item) { return draft.ratings[String(item.number)] || {verdict:'',note:''}; }
function markDirty() {
  generation++; $('save-status').textContent = '保存待ち…'; clearTimeout(timer);
  timer = setTimeout(() => persist().catch(fail), 650);
}
function persist(submit = false) {
  clearTimeout(timer);
  const work = async () => {
    if (conflict) throw new Error('更新が競合しました。入力を控えてからページを再読み込みしてください。');
    if (!submit && generation === savedGeneration) return;
    const sentGeneration = generation;
    $('save-status').textContent = '保存中…';
    const payload = {revision:draft.revision, ratings:structuredClone(draft.ratings), overall_note:draft.overall_note};
    let result;
    try { result = await api(`/api/review/${reviewId}/${submit?'submit':'draft'}`, payload); }
    catch (e) { if (e.message.includes('別の画面')) conflict = true; throw e; }
    draft.revision = result.draft.revision;
    savedGeneration = sentGeneration;
    review.submitted = result.submitted;
    $('save-status').textContent = generation === savedGeneration ? (submit?'評価を確定しました':'下書き保存済み') : '保存待ち…';
    $('error').hidden = true; renderReceipt();
  };
  queue = queue.catch(() => {}).then(work);
  return queue;
}
function renderCards() {
  $('cards').replaceChildren();
  review.items.forEach((item, index) => {
    const card = document.createElement('button'); card.className = 'card' + (index===current?' selected':'');
    card.setAttribute('aria-label',`${numberText(item)} ${item.label}`); card.setAttribute('aria-pressed',String(index===current));
    const img = document.createElement('img'); img.src = imageUrl(item); img.alt = item.label; img.loading = 'lazy';
    const caption = document.createElement('span'); caption.className = 'caption';
    const num = document.createElement('strong'); num.textContent = numberText(item);
    const role = document.createElement('span'); role.textContent = item.role==='reference'?'比較用':'候補';
    caption.append(num,role);
    const name = document.createElement('span'); name.className='name'; name.textContent=item.label;
    const status = document.createElement('span'); status.className='status'; status.textContent=verdictNames[rating(item).verdict] + (rating(item).note?' · メモあり':'');
    card.append(img,caption,name,status); card.onclick = () => select(index); $('cards').append(card);
  });
  const candidates = review.items.filter(i=>i.role==='candidate');
  $('progress').textContent = `${candidates.filter(i=>rating(i).verdict || rating(i).note.trim()).length}/${candidates.length}`;
  renderFilmstrip();
}
function renderCompareOptions() {
  const chosen = $('compare').value; $('compare').replaceChildren(new Option('なし',''));
  review.items.forEach(item => $('compare').add(new Option(`${numberText(item)} ${item.label}`,String(item.number))));
  $('compare').value=chosen;
}
function select(index) {
  current = (index+review.items.length)%review.items.length; const item=review.items[current];
  $('current-label').textContent=numberText(item); $('rating-label').textContent=`${numberText(item)} ${item.label}`;
  $('left-name').textContent=`${numberText(item)} ${item.label}`;
  $('left-image').src=imageUrl(item); $('left-image').alt=item.label; setZoom('left','fit');
  $('image-note').value=rating(item).note; $('filename').textContent=item.path; $('hypothesis').textContent=item.hypothesis;
  $('fork-image').hidden=!(item.run_id&&item.session_id);
  renderCards(); renderVerdicts();
  if(focused) renderFocusImage();
}
function showChrome() {
  if(!focused) return;
  $('focus-view').classList.add('ui-visible'); clearTimeout(chromeTimer);
  chromeTimer=setTimeout(()=>$('focus-view').classList.remove('ui-visible'),2400);
}
function renderFilmstrip() {
  $('filmstrip').replaceChildren();
  review.items.forEach((item,index)=>{
    const button=document.createElement('button');button.className='film-thumb'+(index===current?' selected':'');
    button.setAttribute('aria-label',`全画面 ${numberText(item)} ${item.label}`);button.setAttribute('aria-pressed',String(index===current));
    const img=document.createElement('img');img.src=imageUrl(item);img.alt=item.label;img.loading='lazy';
    const text=document.createElement('span');text.textContent=`${numberText(item)} ${item.label}`;
    button.append(img,text);button.onclick=()=>{select(index);showChrome();};$('filmstrip').append(button);
  });
}
function renderFocusImage() {
  const item=review.items[current];$('focus-image').src=imageUrl(item);$('focus-image').alt=item.label;
  $('focus-name').textContent=`${numberText(item)} ${item.label}`;$('focus-counter').textContent=`${current+1} / ${review.items.length}`;
  setZoom('focus','fit');
  $('filmstrip').children[current]?.scrollIntoView({block:'nearest',inline:'nearest'});showChrome();
}
function closeFocus() {
  focused=false;nativeFullscreen=false;clearTimeout(chromeTimer);$('focus-view').hidden=true;
  $('workspace').inert=false;document.querySelector('header').inert=false;document.body.classList.remove('focus-open');$('fullscreen').focus();
}
async function exitFocus() {
  if(document.fullscreenElement===$('focus-view')) await document.exitFullscreen();
  closeFocus();
}
async function enterFocus() {
  focused=true;$('focus-view').hidden=false;document.body.classList.add('focus-open');
  $('workspace').inert=true;document.querySelector('header').inert=true;$('focus-view').focus();renderFocusImage();
  // Embedded browsers may disallow native fullscreen; the viewport-filling viewer still works.
  try {if($('focus-view').requestFullscreen){await $('focus-view').requestFullscreen();nativeFullscreen=true;}}catch(_){nativeFullscreen=false;}
  setZoom('focus','fit');showChrome();
}
function renderVerdicts() { document.querySelectorAll('[data-verdict]').forEach(b=>{const active=b.dataset.verdict===rating(review.items[current]).verdict; b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}); }
function renderReceipt() {
  const submitted=review.submitted; $('receipt').hidden=!submitted;
  if(submitted) $('receipt-text').textContent=`確定済み：${new Date(submitted.submitted_at).toLocaleString('ja-JP')}。確定後の編集は、もう一度「評価を確定」で反映できます。`;
}
function setZoom(side, zoom) {
  const img=$(side+'-image'), stage=$(side+'-stage');
  let fitted = Math.min(stage.clientWidth/(img.naturalWidth||1),stage.clientHeight/(img.naturalHeight||1));
  if(zoom==='+' || zoom==='-') zoom=Math.max(.1,Math.min(4,(scales[side]==='fit'?fitted:scales[side])*(zoom==='+'?1.35:1/1.35)));
  scales[side]=zoom;
  if(zoom==='fit') { img.style.width='100%';img.style.height='100%';stage.scrollTo(0,0);$(side+'-scale').textContent=''; }
  else { img.style.width=(img.naturalWidth*Number(zoom))+'px';img.style.height=(img.naturalHeight*Number(zoom))+'px';$(side+'-scale').textContent=Math.round(Number(zoom)*100)+'%'; }
}
function bind() {
  $('fork-image').onclick=()=>{$('image-style-name').value='';$('image-fork-result').textContent='';$('save-image-style').disabled=false;$('fork-image-dialog').showModal();};
  $('close-fork-image').onclick=()=>$('fork-image-dialog').close();
  $('save-image-style').onclick=async()=>{
    const item=review.items[current],name=$('image-style-name').value.trim();
    if(!name){fail(new Error('新しい絵柄の名前を入力してください。'));return;}
    $('save-image-style').disabled=true;
    try{const saved=await api(`/api/session/${item.session_id}/fork`,{style_id:'style-'+crypto.randomUUID().slice(0,8),name,run_id:item.run_id,save_intent:`User explicitly saved style from image ${numberText(item)}: ${name}`});$('image-fork-result').textContent='「'+saved.name+'」を新しい絵柄として保存しました。絵柄一覧から使えます。';}
    catch(e){$('save-image-style').disabled=false;fail(e);}
  };
  $('fullscreen').onclick=enterFocus;$('exit-fullscreen').onclick=exitFocus;
  $('focus-prev').onclick=()=>select(current-1);$('focus-next').onclick=()=>select(current+1);
  $('focus-view').addEventListener('pointermove',showChrome);$('focus-view').addEventListener('pointerdown',showChrome);
  $('focus-view').addEventListener('wheel',showChrome,{passive:true});
  document.addEventListener('fullscreenchange',()=>{if(nativeFullscreen&&!document.fullscreenElement)closeFocus();});
  $('prev').onclick=()=>select(current-1);$('next').onclick=()=>select(current+1);
  document.querySelectorAll('[data-verdict]').forEach(b=>b.onclick=()=>{
    const n=String(review.items[current].number); draft.ratings[n]={...rating(review.items[current]),verdict:b.dataset.verdict};
    renderVerdicts();renderCards();markDirty();
  });
  $('image-note').oninput=()=>{const n=String(review.items[current].number);draft.ratings[n]={...rating(review.items[current]),note:$('image-note').value};renderCards();markDirty();};
  $('overall-note').oninput=()=>{draft.overall_note=$('overall-note').value;markDirty();};
  $('clear-rating').onclick=()=>{delete draft.ratings[String(review.items[current].number)];$('image-note').value='';renderVerdicts();renderCards();markDirty();};
  $('compare').onchange=()=>{
    const item=review.items.find(i=>String(i.number)===$('compare').value);$('right-pane').hidden=!item;
    if(item){$('right-image').src=imageUrl(item);$('right-name').textContent=`${numberText(item)} ${item.label}`;setZoom('right','fit');}
  };
  document.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>setZoom(b.dataset.view,isNaN(Number(b.dataset.zoom))?b.dataset.zoom:Number(b.dataset.zoom)));
  for(const side of ['left','right','focus']) {
    $(side+'-image').onload=()=>setZoom(side,scales[side]);
    $(side+'-image').onerror=()=>fail(new Error('画像を読み込めませんでした。レビューの画像ファイルを確認してください。'));
    const stage=$(side+'-stage');let drag;
    stage.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,left:stage.scrollLeft,top:stage.scrollTop};stage.setPointerCapture(e.pointerId);};
    stage.onpointermove=e=>{if(drag){stage.scrollLeft=drag.left+drag.x-e.clientX;stage.scrollTop=drag.top+drag.y-e.clientY;}};
    stage.onpointerup=stage.onpointercancel=()=>{drag=null;};
    stage.addEventListener('wheel',e=>{if(e.ctrlKey){e.preventDefault();setZoom(side,e.deltaY<0?'+':'-');}},{passive:false});
  }
  document.addEventListener('keydown',e=>{if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||$('library').open||$('fork-image-dialog').open)return;if(focused)showChrome();if(e.key==='Escape'&&focused){e.preventDefault();exitFocus();}if(e.key==='ArrowLeft'){e.preventDefault();select(current-1);}if(e.key==='ArrowRight'){e.preventDefault();select(current+1);}if(e.key.toLowerCase()==='f'&&!e.ctrlKey&&!e.metaKey){e.preventDefault();focused?exitFocus():enterFocus();}});
  window.addEventListener('beforeunload',e=>{if(generation!==savedGeneration){e.preventDefault();e.returnValue='';}});
  $('submit').onclick=async()=>{const button=$('submit');button.disabled=true;try{await persist(true);}catch(e){fail(e);}finally{button.disabled=false;}};
  $('copy').onclick=async()=>{
    try {const info=await api("/api/info");await navigator.clipboard.writeText(`データワークスペースは「${info.workspace}」です。StyleForkの画像レビュー ${reviewId} の評価を確定しました。このレビューの提出済みフィードバックを読み取り、次の作業に反映してください。保存済みの絵柄は変更しないでください。`);$('copy').textContent='コピーしました';}catch(e){fail(e);}
  };
  $('add').onclick=async()=>{try{if(!catalog.length){catalog=await api('/api/catalog');const ids=[...new Set(catalog.map(i=>i.track_id).filter(Boolean))];ids.forEach(id=>$('track-filter').add(new Option(id,id)));if(ids.includes(review.track_id))$('track-filter').value=review.track_id;}renderLibrary();$('library').showModal();}catch(e){fail(e);}};
  $('close-library').onclick=()=>$('library').close();$('search').oninput=$('track-filter').onchange=renderLibrary;
}
function renderLibrary() {
  const search=$('search').value.toLowerCase(),track=$('track-filter').value;
  $('library-items').replaceChildren();
  const seen=new Set();
  const filtered=catalog.filter(item=>{if(seen.has(item.experiment_id))return false;seen.add(item.experiment_id);return (!track||item.track_id===track)&&[item.label,item.experiment_id,item.hypothesis].join(' ').toLowerCase().includes(search);});
  for(const item of filtered.slice(0,40)) {
    const button=document.createElement('button');const img=document.createElement('img');img.src=`/catalog-image?experiment=${encodeURIComponent(item.experiment_id)}&index=${item.output_index}`;img.alt=item.label;img.loading='lazy';
    const name=document.createElement('span');name.textContent=item.label;
    const added=review.items.some(i=>i.experiment_id===item.experiment_id);button.disabled=added;
    const label=document.createElement('div');label.className='quiet';label.textContent=added?'追加済み':'＋ 今回のレビューへ';button.append(img,name,label);
    button.onclick=async()=>{button.disabled=true;try{await persist();const result=await api(`/api/review/${reviewId}/add`,{experiment_id:item.experiment_id,revision:draft.revision});review.items=result.items;draft.revision=result.draft.revision;renderCards();renderCompareOptions();renderLibrary();}catch(e){button.disabled=false;fail(e);}};
    $('library-items').append(button);
  }
  if(!filtered.length)$('library-items').textContent='該当する画像がありません。';
  else if(filtered.length>40){const p=document.createElement('p');p.className='quiet';p.textContent=`${filtered.length}件中、新しい40件を表示しています。検索で絞り込めます。`;$('library-items').append(p);}
}
async function init() {
  if(!reviewId) {
    $('landing').hidden=false;$('add').hidden=$('submit').hidden=$('fullscreen').hidden=true;$('save-status').textContent='';
    const reviews=await api('/api/reviews');for(const item of reviews){const a=document.createElement('a');a.href='/reviews?review='+encodeURIComponent(item.review_id);a.textContent=item.title+' · '+new Date(item.created_at).toLocaleString('ja-JP');$('review-list').append(a);}
    if(!reviews.length)$('review-list').textContent='まだレビューがありません。AI が review create で今回見る画像をまとめます。';return;
  }
  review=await api('/api/review/'+encodeURIComponent(reviewId));draft=review.draft;
  $('workspace').hidden=false;$('title').textContent=review.title;document.title=review.title+' · 画像レビュー';
  $('overall-note').value=draft.overall_note;$('save-status').textContent='下書き保存済み';
  bind();renderCompareOptions();select(0);renderReceipt();
}
init().catch(fail);
