"use strict";
const $ = id => document.getElementById(id);
const verdictNames = {good:'良い', neutral:'普通', bad:'微妙', unsure:'判断困難', '':'未評価'};
let review, draft, current = 0, catalog = [], timer, toastTimer, queue = Promise.resolve(), generation = 0, savedGeneration = 0;
let conflict = false, focused = false, nativeFullscreen = false, chromeTimer, isDraggingStage = false, syncingScroll = false;
const scales = {left: 'fit', right: 'fit', focus: 'fit', 'focus-right': 'fit'};
const savedCenter = {
  left: {rx: 0.5, ry: 0.5},
  right: {rx: 0.5, ry: 0.5},
  focus: {rx: 0.5, ry: 0.5},
  'focus-right': {rx: 0.5, ry: 0.5}
};
const reviewId = new URLSearchParams(location.search).get('review');

const themeIcons = {
  auto: '<svg class="icon" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg><span>自動</span>',
  dark: '<svg class="icon" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg><span>ダーク</span>',
  light: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg><span>ライト</span>'
};

function initTheme() {
  const btn = $('theme-toggle');
  if (!btn) return;
  const apply = mode => {
    if (mode === 'light' || mode === 'dark') {
      document.documentElement.dataset.theme = mode;
    } else {
      delete document.documentElement.dataset.theme;
      mode = 'auto';
    }
    btn.innerHTML = themeIcons[mode] || themeIcons.auto;
  };
  let currentMode = localStorage.getItem('stylefork-theme') || 'auto';
  apply(currentMode);
  btn.onclick = () => {
    const order = ['auto', 'dark', 'light'];
    currentMode = order[(order.indexOf(currentMode) + 1) % order.length];
    try { localStorage.setItem('stylefork-theme', currentMode); } catch (_) {}
    apply(currentMode);
    const names = {auto: 'OS連動', dark: 'ダーク', light: 'ライト'};
    showToast(`テーマ：${names[currentMode]}`);
  };
}

function showToast(message) {
  const el = $('toast');
  if (!el) return;
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('visible'), 2200);
}

function setSaveStatus(text, state = 'saved') {
  const el = $('save-status');
  if (!el) return;
  el.textContent = text;
  el.dataset.state = state;
}

function fail(e) {
  $('error').textContent = e.message || String(e);
  $('error').hidden = false;
  setSaveStatus('保存できませんでした', 'error');
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '読み込みに失敗しました');
  return result;
}

const numberText = item => '#' + String(item.number).padStart(2, '0');
const imageUrl = item => `/image?review=${encodeURIComponent(reviewId)}&number=${item.number}`;
function rating(item) { return draft.ratings[String(item.number)] || {verdict: '', note: ''}; }

function hasUnsubmittedChanges() {
  if (!review?.submitted) return false;
  if ((draft.overall_note || '') !== (review.submitted.overall_note || '')) return true;
  return review.items.some(item => {
    const r = rating(item);
    const s = (review.submitted.items || []).find(x => x.number === item.number) || {verdict: '', note: ''};
    return (r.verdict || '') !== (s.verdict || '') || (r.note || '') !== (s.note || '');
  });
}

function markDirty() {
  generation++;
  setSaveStatus('保存待ち…', 'dirty');
  renderReceipt();
  clearTimeout(timer);
  timer = setTimeout(() => persist().catch(fail), 650);
}

function persist(submit = false) {
  clearTimeout(timer);
  const work = async () => {
    if (conflict) throw new Error('更新が競合しました。入力を控えてからページを再読み込みしてください。');
    if (!submit && generation === savedGeneration) return;
    const sentGeneration = generation;
    setSaveStatus('保存中…', 'saving');
    const payload = {revision: draft.revision, ratings: structuredClone(draft.ratings), overall_note: draft.overall_note};
    let result;
    try {
      result = await api(`/api/review/${reviewId}/${submit ? 'submit' : 'draft'}`, payload);
    } catch (e) {
      if (e.message.includes('別の画面')) conflict = true;
      throw e;
    }
    draft.revision = result.draft.revision;
    savedGeneration = sentGeneration;
    review.submitted = result.submitted;
    if (generation === savedGeneration) {
      setSaveStatus(submit ? '評価を確定しました' : '下書き保存済み', 'saved');
      if (submit) showToast('評価を確定しました');
    } else {
      setSaveStatus('保存待ち…', 'dirty');
    }
    $('error').hidden = true;
    renderReceipt();
  };
  queue = queue.catch(() => {}).then(work);
  return queue;
}

function renderCards(popCurrent = false) {
  $('cards').replaceChildren();
  review.items.forEach((item, index) => {
    const r = rating(item);
    const card = document.createElement('button');
    card.className = 'card' + (index === current ? ' selected' : '');
    card.dataset.verdict = r.verdict || '';
    card.setAttribute('aria-label', `${numberText(item)} ${item.label}`);
    card.setAttribute('aria-pressed', String(index === current));
    const img = document.createElement('img');
    img.src = imageUrl(item);
    img.alt = item.label;
    img.loading = 'lazy';
    const caption = document.createElement('span');
    caption.className = 'caption';
    const num = document.createElement('strong');
    num.textContent = numberText(item);
    const role = document.createElement('span');
    role.textContent = item.role === 'reference' ? '比較用' : '候補';
    caption.append(num, role);
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = item.label;
    const status = document.createElement('span');
    status.className = 'status' + (popCurrent && index === current ? ' pop-anim' : '');
    status.dataset.verdict = r.verdict || '';
    status.textContent = verdictNames[r.verdict] + (r.note ? ' · メモあり' : '');
    card.append(img, caption, name, status);
    card.onclick = () => select(index);
    $('cards').append(card);
  });
  const candidates = review.items.filter(i => i.role === 'candidate');
  const ratedCandidates = candidates.filter(i => rating(i).verdict || rating(i).note.trim()).length;
  $('progress').textContent = `${ratedCandidates}/${candidates.length}`;
  renderFilmstrip();
}

function renderCompareOptions() {
  const chosen = $('compare').value;
  for (const selectEl of [$('compare'), $('focus-compare')]) {
    if (!selectEl) continue;
    selectEl.replaceChildren(new Option('なし', ''));
    review.items.forEach(item => {
      selectEl.add(new Option(`${numberText(item)} ${item.label}`, String(item.number)));
    });
    selectEl.value = chosen;
  }
}

function getStageCenter(stage) {
  if (!stage || stage.dataset.mode === 'fit') return {rx: 0.5, ry: 0.5};
  const sw = Math.max(1, stage.scrollWidth);
  const sh = Math.max(1, stage.scrollHeight);
  return {
    rx: Math.min(1, Math.max(0, (stage.scrollLeft + stage.clientWidth / 2) / sw)),
    ry: Math.min(1, Math.max(0, (stage.scrollTop + stage.clientHeight / 2) / sh))
  };
}

function applyStageCenter(stage, center) {
  if (!stage || stage.dataset.mode === 'fit' || !center) {
    stage?.scrollTo(0, 0);
    return;
  }
  const left = center.rx * stage.scrollWidth - stage.clientWidth / 2;
  const top = center.ry * stage.scrollHeight - stage.clientHeight / 2;
  stage.scrollTo(Math.max(0, left), Math.max(0, top));
}

function syncScrollPosition(sourceSide, targetSide) {
  if (syncingScroll || !$('sync-compare')?.checked) return;
  const src = $(sourceSide + '-stage');
  const dst = $(targetSide + '-stage');
  if (!src || !dst || dst.hidden || dst.closest('[hidden]')) return;
  syncingScroll = true;
  try {
    if (src.dataset.mode !== 'fit' && dst.dataset.mode !== 'fit') {
      const center = getStageCenter(src);
      savedCenter[targetSide] = center;
      applyStageCenter(dst, center);
    }
  } finally {
    syncingScroll = false;
  }
}

function triggerImageTransition(img) {
  if (!img) return;
  img.classList.remove('img-enter');
  void img.offsetWidth;
  img.classList.add('img-enter');
}

function select(index) {
  const keepZoom = $('keep-zoom')?.checked;
  if (keepZoom && scales.left !== 'fit') {
    savedCenter.left = getStageCenter($('left-stage'));
  } else {
    scales.left = 'fit';
    savedCenter.left = {rx: 0.5, ry: 0.5};
  }
  if (keepZoom && scales.focus !== 'fit') {
    savedCenter.focus = getStageCenter($('focus-stage'));
  } else {
    scales.focus = 'fit';
    savedCenter.focus = {rx: 0.5, ry: 0.5};
  }

  current = (index + review.items.length) % review.items.length;
  const item = review.items[current];
  const r = rating(item);
  $('current-label').textContent = `${numberText(item)} (${current + 1}/${review.items.length})`;
  $('rating-label').textContent = `${numberText(item)} ${item.label}`;
  if ($('role-badge')) {
    $('role-badge').textContent = item.role === 'reference' ? '比較用（過去画像）' : '今回の候補';
    $('role-badge').dataset.role = item.role;
  }
  $('left-name').textContent = `${numberText(item)} ${item.label}`;
  $('left-image').src = imageUrl(item);
  $('left-image').alt = item.label;
  triggerImageTransition($('left-image'));
  $('image-note').value = r.note;
  if ($('focus-note')) $('focus-note').value = r.note;
  $('filename').textContent = item.path;
  $('hypothesis').textContent = item.hypothesis || '（生成条件の記録なし）';
  $('fork-image').hidden = !(item.run_id && item.session_id);
  renderCards();
  renderVerdicts();
  if (focused) renderFocusImage();
}

function showChrome() {
  if (!focused || isDraggingStage) return;
  $('focus-view').classList.add('ui-visible');
  clearTimeout(chromeTimer);
  chromeTimer = setTimeout(() => {
    if (document.activeElement === $('focus-note') || document.activeElement === $('focus-compare')) return;
    $('focus-view').classList.remove('ui-visible');
  }, 2400);
}

function renderFilmstrip() {
  $('filmstrip').replaceChildren();
  review.items.forEach((item, index) => {
    const r = rating(item);
    const button = document.createElement('button');
    button.className = 'film-thumb' + (index === current ? ' selected' : '');
    button.dataset.verdict = r.verdict || '';
    button.setAttribute('aria-label', `全画面 ${numberText(item)} ${item.label}`);
    button.setAttribute('aria-pressed', String(index === current));
    const img = document.createElement('img');
    img.src = imageUrl(item);
    img.alt = item.label;
    img.loading = 'lazy';
    const text = document.createElement('span');
    const badge = r.verdict ? ` [${verdictNames[r.verdict]}]` : '';
    text.textContent = `${numberText(item)} ${item.label}${badge}`;
    button.append(img, text);
    button.onclick = () => { select(index); showChrome(); };
    $('filmstrip').append(button);
  });
}

function renderFocusImage() {
  const item = review.items[current];
  $('focus-image').src = imageUrl(item);
  $('focus-image').alt = item.label;
  triggerImageTransition($('focus-image'));
  $('focus-name').textContent = `${numberText(item)} ${item.label}`;
  $('focus-counter').textContent = `${current + 1} / ${review.items.length}`;
  if ($('focus-note')) $('focus-note').value = rating(item).note;
  setZoom('focus', scales.focus, null, true);
  $('filmstrip').children[current]?.scrollIntoView({block: 'nearest', inline: 'nearest'});
  showChrome();
}

function closeFocus() {
  focused = false;
  nativeFullscreen = false;
  clearTimeout(chromeTimer);
  $('focus-view').hidden = true;
  $('workspace').inert = false;
  document.querySelector('header').inert = false;
  document.body.classList.remove('focus-open');
  $('fullscreen').focus();
}

async function exitFocus() {
  if (document.fullscreenElement === $('focus-view')) await document.exitFullscreen();
  closeFocus();
}

async function enterFocus() {
  focused = true;
  $('focus-view').hidden = false;
  document.body.classList.add('focus-open');
  $('workspace').inert = true;
  document.querySelector('header').inert = true;
  $('focus-view').focus();
  scales.focus = scales.left;
  savedCenter.focus = {...savedCenter.left};
  renderFocusImage();
  try {
    if ($('focus-view').requestFullscreen) {
      await $('focus-view').requestFullscreen();
      nativeFullscreen = true;
    }
  } catch (_) {
    nativeFullscreen = false;
  }
  setZoom('focus', scales.focus, null, true);
  showChrome();
}

function renderVerdicts(popVerdict = null) {
  const currentVerdict = rating(review.items[current]).verdict;
  document.querySelectorAll('[data-verdict]').forEach(b => {
    const active = b.dataset.verdict === currentVerdict;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
    if (popVerdict && b.dataset.verdict === popVerdict) {
      b.classList.remove('pop-anim');
      void b.offsetWidth;
      b.classList.add('pop-anim');
    }
  });
}

function setVerdict(verdict) {
  const item = review.items[current];
  const n = String(item.number);
  const cur = rating(item);
  const nextVerdict = cur.verdict === verdict ? '' : verdict;
  draft.ratings[n] = {...cur, verdict: nextVerdict};
  renderVerdicts(nextVerdict);
  renderCards(true);
  markDirty();
}

function renderReceipt() {
  const submitted = review?.submitted;
  const submitLabel = $('submit-label') || $('submit');
  $('receipt').hidden = !submitted;
  if (!submitted) {
    submitLabel.textContent = '評価を確定';
    return;
  }
  const dirtyAfterSubmit = hasUnsubmittedChanges();
  $('receipt').classList.toggle('dirty', dirtyAfterSubmit);
  if (dirtyAfterSubmit) {
    $('receipt-text').textContent = `⚠ 確定後に未反映の編集があります。もう一度「評価を確定」を押すと AI 用ファイルに反映されます。（前回確定：${new Date(submitted.submitted_at).toLocaleString('ja-JP')}）`;
    submitLabel.textContent = '評価を再確定';
  } else {
    $('receipt-text').textContent = `確定済み：${new Date(submitted.submitted_at).toLocaleString('ja-JP')}。確定後の編集は、もう一度「評価を確定」で反映できます。`;
    submitLabel.textContent = '評価を確定';
  }
}

function applySingleZoom(side, zoom, focal = null, useSavedCenter = false) {
  const img = $(side + '-image');
  const stage = $(side + '-stage');
  if (!img || !stage || stage.hidden || stage.closest('[hidden]')) return;
  const nw = img.naturalWidth || 1;
  const nh = img.naturalHeight || 1;
  const cw = stage.clientWidth || 1;
  const ch = stage.clientHeight || 1;
  const fitted = Math.min(cw / nw, ch / nh);

  const prevCenter = useSavedCenter ? (savedCenter[side] || {rx: 0.5, ry: 0.5}) : getStageCenter(stage);
  if (zoom === '+' || zoom === '-') {
    const base = scales[side] === 'fit' ? fitted : Number(scales[side]);
    zoom = Math.max(0.1, Math.min(4, base * (zoom === '+' ? 1.35 : 1 / 1.35)));
  }
  scales[side] = zoom;
  const scaleEl = $(side + '-scale');

  document.querySelectorAll(`[data-view="${side}"][data-zoom]`).forEach(btn => {
    const isFit = zoom === 'fit' && btn.dataset.zoom === 'fit';
    const isOne = zoom !== 'fit' && Math.abs(Number(zoom) - 1) < 0.01 && btn.dataset.zoom === '1';
    btn.classList.toggle('active', isFit || isOne);
  });

  if (zoom === 'fit') {
    stage.dataset.mode = 'fit';
    img.style.width = '100%';
    img.style.height = '100%';
    stage.scrollTo(0, 0);
    savedCenter[side] = {rx: 0.5, ry: 0.5};
    if (scaleEl) scaleEl.textContent = img.naturalWidth ? Math.round(fitted * 100) + '%' : '';
  } else {
    const prevWidth = stage.scrollWidth || cw;
    const prevHeight = stage.scrollHeight || ch;
    let focalRx = prevCenter.rx;
    let focalRy = prevCenter.ry;
    let offsetX = cw / 2;
    let offsetY = ch / 2;
    if (focal && stage.dataset.mode === 'zoom') {
      const rect = stage.getBoundingClientRect();
      offsetX = focal.clientX - rect.left;
      offsetY = focal.clientY - rect.top;
      focalRx = (stage.scrollLeft + offsetX) / Math.max(1, prevWidth);
      focalRy = (stage.scrollTop + offsetY) / Math.max(1, prevHeight);
    }
    stage.dataset.mode = 'zoom';
    img.style.width = Math.round(nw * Number(zoom)) + 'px';
    img.style.height = Math.round(nh * Number(zoom)) + 'px';
    if (scaleEl) scaleEl.textContent = Math.round(Number(zoom) * 100) + '%';
    if (focal && !useSavedCenter) {
      stage.scrollTo(
        Math.max(0, focalRx * stage.scrollWidth - offsetX),
        Math.max(0, focalRy * stage.scrollHeight - offsetY)
      );
    } else {
      applyStageCenter(stage, prevCenter);
    }
    savedCenter[side] = getStageCenter(stage);
  }
}

function setZoom(side, zoom, focal = null, useSavedCenter = false, skipSync = false) {
  applySingleZoom(side, zoom, focal, useSavedCenter);
  if (side === 'focus' && !$('focus-right-stage').hidden) {
    savedCenter['focus-right'] = {...savedCenter.focus};
    applySingleZoom('focus-right', scales.focus, null, true);
  }
  if (!skipSync && $('sync-compare')?.checked && !$('right-pane').hidden) {
    if (side === 'left') {
      savedCenter.right = {...savedCenter.left};
      applySingleZoom('right', scales.left, null, true);
    } else if (side === 'right') {
      savedCenter.left = {...savedCenter.right};
      applySingleZoom('left', scales.right, null, true);
    }
  }
}

function setCompare(value) {
  $('compare').value = value;
  if ($('focus-compare')) $('focus-compare').value = value;
  const item = review.items.find(i => String(i.number) === value);
  $('right-pane').hidden = !item;
  if ($('sync-compare-wrap')) $('sync-compare-wrap').hidden = !item;
  if ($('focus-right-stage')) $('focus-right-stage').hidden = !item;
  if (item) {
    $('right-image').src = imageUrl(item);
    $('right-image').alt = item.label;
    triggerImageTransition($('right-image'));
    $('right-name').textContent = `${numberText(item)} ${item.label}`;
    if ($('focus-right-image')) {
      $('focus-right-image').src = imageUrl(item);
      $('focus-right-image').alt = item.label;
    }
    const targetZoom = $('sync-compare')?.checked ? scales.left : 'fit';
    savedCenter.right = {...savedCenter.left};
    setZoom('right', targetZoom, null, true, true);
    if (focused) {
      savedCenter['focus-right'] = {...savedCenter.focus};
      applySingleZoom('focus-right', scales.focus, null, true);
    }
  }
  applySingleZoom('left', scales.left, null, true);
  if (focused) applySingleZoom('focus', scales.focus, null, true);
}

function bind() {
  $('fork-image').onclick = () => {
    $('image-style-name').value = '';
    $('image-fork-result').textContent = '';
    $('save-image-style').disabled = false;
    $('fork-image-dialog').showModal();
  };
  $('close-fork-image').onclick = () => $('fork-image-dialog').close();
  $('save-image-style').onclick = async () => {
    const item = review.items[current];
    const name = $('image-style-name').value.trim();
    if (!name) { fail(new Error('新しい絵柄の名前を入力してください。')); return; }
    $('save-image-style').disabled = true;
    try {
      const saved = await api(`/api/session/${item.session_id}/fork`, {
        style_id: 'style-' + crypto.randomUUID().slice(0, 8),
        name,
        run_id: item.run_id,
        save_intent: `User explicitly saved style from image ${numberText(item)}: ${name}`
      });
      $('image-fork-result').textContent = `「${saved.name}」を新しい絵柄として保存しました。絵柄一覧から使えます。`;
      showToast(`「${saved.name}」を保存しました`);
    } catch (e) {
      $('save-image-style').disabled = false;
      fail(e);
    }
  };

  $('fullscreen').onclick = enterFocus;
  $('exit-fullscreen').onclick = exitFocus;
  $('focus-prev').onclick = () => select(current - 1);
  $('focus-next').onclick = () => select(current + 1);
  if ($('toggle-filmstrip')) {
    $('toggle-filmstrip').onclick = () => {
      const hidden = $('focus-view').classList.toggle('filmstrip-hidden');
      $('toggle-filmstrip').textContent = hidden ? 'サムネイルを表示' : 'サムネイルを隠す';
      showChrome();
    };
  }
  $('focus-view').addEventListener('pointermove', showChrome);
  $('focus-view').addEventListener('pointerdown', showChrome);
  $('focus-view').addEventListener('wheel', showChrome, {passive: true});
  document.addEventListener('fullscreenchange', () => {
    if (nativeFullscreen && !document.fullscreenElement) closeFocus();
  });

  $('prev').onclick = () => select(current - 1);
  $('next').onclick = () => select(current + 1);

  document.querySelectorAll('[data-verdict]').forEach(b => {
    b.onclick = () => setVerdict(b.dataset.verdict);
  });

  const onNoteInput = value => {
    const n = String(review.items[current].number);
    draft.ratings[n] = {...rating(review.items[current]), note: value};
    if ($('image-note').value !== value) $('image-note').value = value;
    if ($('focus-note') && $('focus-note').value !== value) $('focus-note').value = value;
    renderCards();
    markDirty();
  };
  $('image-note').oninput = () => onNoteInput($('image-note').value);
  if ($('focus-note')) {
    $('focus-note').oninput = () => onNoteInput($('focus-note').value);
    $('focus-note').onfocus = showChrome;
  }

  $('overall-note').oninput = () => {
    draft.overall_note = $('overall-note').value;
    markDirty();
  };

  $('clear-rating').onclick = () => {
    const item = review.items[current];
    const n = String(item.number);
    const cur = rating(item);
    if (cur.note && cur.note.trim()) {
      const clearNoteToo = confirm('入力済みのメモも消去しますか？\n（「キャンセル」を選ぶとメモを残して評価ボタンのみ未評価に戻します）');
      if (!clearNoteToo) {
        draft.ratings[n] = {...cur, verdict: ''};
        renderVerdicts();
        renderCards();
        markDirty();
        return;
      }
    }
    delete draft.ratings[n];
    $('image-note').value = '';
    if ($('focus-note')) $('focus-note').value = '';
    renderVerdicts();
    renderCards();
    markDirty();
  };

  $('compare').onchange = () => setCompare($('compare').value);
  if ($('focus-compare')) $('focus-compare').onchange = () => setCompare($('focus-compare').value);
  if ($('sync-compare')) {
    $('sync-compare').onchange = () => {
      if ($('sync-compare').checked && !$('right-pane').hidden) {
        savedCenter.right = {...savedCenter.left};
        setZoom('right', scales.left, null, true, true);
      }
    };
  }

  document.querySelectorAll('[data-zoom]').forEach(b => {
    b.onclick = () => setZoom(b.dataset.view, isNaN(Number(b.dataset.zoom)) ? b.dataset.zoom : Number(b.dataset.zoom));
  });

  const stagePairs = {left: 'right', right: 'left', focus: 'focus-right', 'focus-right': 'focus'};
  for (const side of ['left', 'right', 'focus', 'focus-right']) {
    const img = $(side + '-image');
    const stage = $(side + '-stage');
    if (!img || !stage) continue;
    img.onload = () => applySingleZoom(side, scales[side], null, true);
    img.onerror = () => fail(new Error('画像を読み込めませんでした。レビューの画像ファイルを確認してください。'));
    let drag = null;
    stage.onpointerdown = e => {
      if (e.button !== 0) return;
      drag = {x: e.clientX, y: e.clientY, left: stage.scrollLeft, top: stage.scrollTop};
      isDraggingStage = true;
      stage.setPointerCapture(e.pointerId);
    };
    stage.onpointermove = e => {
      if (!drag) return;
      stage.scrollLeft = drag.left + drag.x - e.clientX;
      stage.scrollTop = drag.top + drag.y - e.clientY;
      savedCenter[side] = getStageCenter(stage);
      if (stagePairs[side]) syncScrollPosition(side, stagePairs[side]);
    };
    stage.onpointerup = stage.onpointercancel = () => {
      drag = null;
      isDraggingStage = false;
    };
    stage.addEventListener('scroll', () => {
      if (!syncingScroll && stage.dataset.mode === 'zoom') {
        savedCenter[side] = getStageCenter(stage);
        if (stagePairs[side]) syncScrollPosition(side, stagePairs[side]);
      }
    }, {passive: true});
    stage.addEventListener('wheel', e => {
      if (e.ctrlKey) {
        e.preventDefault();
        const targetSide = side === 'focus-right' ? 'focus' : side;
        setZoom(targetSide, e.deltaY < 0 ? '+' : '-', {clientX: e.clientX, clientY: e.clientY});
      }
    }, {passive: false});
  }

  window.addEventListener('resize', () => {
    for (const side of ['left', 'right', 'focus', 'focus-right']) {
      applySingleZoom(side, scales[side], null, true);
    }
  });

  const shortcutVerdicts = {'1': 'good', '2': 'neutral', '3': 'bad', '4': 'unsure'};
  document.addEventListener('keydown', e => {
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || $('library').open || $('fork-image-dialog').open) return;
    if (focused) showChrome();
    if (e.key === 'Escape' && focused) { e.preventDefault(); exitFocus(); return; }
    if (e.key === 'ArrowLeft') { e.preventDefault(); select(current - 1); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); select(current + 1); return; }
    if (e.key.toLowerCase() === 'f' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      focused ? exitFocus() : enterFocus();
      return;
    }
    if (!e.ctrlKey && !e.metaKey && !e.altKey && shortcutVerdicts[e.key]) {
      e.preventDefault();
      setVerdict(shortcutVerdicts[e.key]);
      return;
    }
    if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key === '0') {
      e.preventDefault();
      const item = review.items[current];
      const n = String(item.number);
      draft.ratings[n] = {...rating(item), verdict: ''};
      renderVerdicts();
      renderCards();
      markDirty();
    }
  });

  window.addEventListener('beforeunload', e => {
    if (generation !== savedGeneration) { e.preventDefault(); e.returnValue = ''; }
  });

  $('submit').onclick = async () => {
    const button = $('submit');
    button.disabled = true;
    try { await persist(true); }
    catch (e) { fail(e); }
    finally { button.disabled = false; }
  };

  $('copy').onclick = async () => {
    try {
      const info = await api('/api/info');
      await navigator.clipboard.writeText(`データワークスペースは「${info.workspace}」です。StyleForkの画像レビュー ${reviewId} の評価を確定しました。このレビューの提出済みフィードバックを読み取り、次の作業に反映してください。保存済みの絵柄は変更しないでください。`);
      const copyLabel = $('copy-label') || $('copy');
      copyLabel.textContent = 'コピーしました';
      showToast('AI への依頼文をコピーしました');
    } catch (e) { fail(e); }
  };

  $('add').onclick = async () => {
    try {
      if (!catalog.length) {
        catalog = await api('/api/catalog');
        const tracks = new Map();
        for (const item of catalog) {
          if (item.track_id && !tracks.has(item.track_id)) {
            tracks.set(item.track_id, item.style_name || item.track_id);
          }
        }
        tracks.forEach((label, id) => $('track-filter').add(new Option(label, id)));
        if (tracks.has(review.track_id)) $('track-filter').value = review.track_id;
      }
      renderLibrary();
      $('library').showModal();
    } catch (e) { fail(e); }
  };
  $('close-library').onclick = () => $('library').close();
  $('search').oninput = $('track-filter').onchange = renderLibrary;
}

function renderLibrary() {
  const search = $('search').value.trim().toLowerCase();
  const track = $('track-filter').value;
  $('library-items').replaceChildren();
  const seen = new Set();
  const filtered = catalog.filter(item => {
    if (seen.has(item.experiment_id)) return false;
    seen.add(item.experiment_id);
    const haystack = [
      item.label,
      item.turn_title,
      item.concept,
      item.style_name,
      item.experiment_id,
      item.batch_id,
      item.hypothesis,
      item.path,
      item.track_id
    ].filter(Boolean).join(' ').toLowerCase();
    return (!track || item.track_id === track) && (!search || haystack.includes(search));
  });

  for (const item of filtered.slice(0, 60)) {
    const button = document.createElement('button');
    const img = document.createElement('img');
    img.src = `/catalog-image?experiment=${encodeURIComponent(item.experiment_id)}&index=${item.output_index}`;
    img.alt = item.label || item.experiment_id;
    img.loading = 'lazy';
    const title = document.createElement('span');
    title.className = 'lib-title';
    title.textContent = item.label || item.turn_title || item.experiment_id;
    const meta = document.createElement('div');
    meta.className = 'lib-meta';
    const dateStr = item.created_at ? new Date(item.created_at).toLocaleDateString('ja-JP') : '';
    const subParts = [item.concept, item.turn_title && item.turn_title !== item.label ? item.turn_title : '', dateStr].filter(Boolean);
    meta.textContent = subParts.join(' · ');
    const added = review.items.some(i => i.experiment_id === item.experiment_id);
    button.disabled = added;
    const actionLabel = document.createElement('div');
    actionLabel.className = 'quiet';
    actionLabel.textContent = added ? '追加済み' : '＋ 今回のレビューへ';
    button.append(img, title, meta, actionLabel);
    button.onclick = async () => {
      button.disabled = true;
      try {
        await persist();
        const result = await api(`/api/review/${reviewId}/add`, {experiment_id: item.experiment_id, revision: draft.revision});
        review.items = result.items;
        draft.revision = result.draft.revision;
        renderCards();
        renderCompareOptions();
        renderLibrary();
        showToast(`「${title.textContent}」を比較用に追加しました`);
      } catch (e) {
        button.disabled = false;
        fail(e);
      }
    };
    $('library-items').append(button);
  }
  if (!filtered.length) {
    $('library-items').textContent = '該当する画像がありません。';
  } else if (filtered.length > 60) {
    const p = document.createElement('p');
    p.className = 'quiet';
    p.textContent = `${filtered.length}件中、新しい60件を表示しています。検索で絞り込めます。`;
    $('library-items').append(p);
  }
}

async function init() {
  initTheme();
  if (!reviewId) {
    $('landing').hidden = false;
    $('add').hidden = $('submit').hidden = $('fullscreen').hidden = true;
    setSaveStatus('', 'saved');
    const reviews = await api('/api/reviews');
    for (const item of reviews) {
      const a = document.createElement('a');
      a.className = 'review-card-link';
      a.href = '/reviews?review=' + encodeURIComponent(item.review_id);
      const infoDiv = document.createElement('div');
      const titleStrong = document.createElement('strong');
      titleStrong.textContent = item.title;
      const metaDiv = document.createElement('div');
      metaDiv.className = 'review-card-meta';
      const itemCount = item.item_count ?? 0;
      const candCount = item.candidate_count ?? itemCount;
      const ratedCount = item.rated_count ?? 0;
      metaDiv.textContent = `${new Date(item.created_at).toLocaleString('ja-JP')} · 全${itemCount}枚（候補${candCount}枚）`;
      const track = document.createElement('div');
      track.className = 'review-progress-track';
      const bar = document.createElement('div');
      bar.className = 'review-progress-bar';
      bar.style.width = Math.min(100, Math.round((ratedCount / Math.max(1, candCount)) * 100)) + '%';
      track.append(bar);
      infoDiv.append(titleStrong, metaDiv, track);

      const badge = document.createElement('span');
      if (item.submitted) {
        badge.className = 'review-badge submitted';
        badge.textContent = `確定済み (${ratedCount}/${candCount})`;
      } else if (ratedCount > 0) {
        badge.className = 'review-badge progress';
        badge.textContent = `評価中 (${ratedCount}/${candCount})`;
      } else {
        badge.className = 'review-badge';
        badge.textContent = `未評価 (0/${candCount})`;
      }
      a.append(infoDiv, badge);
      $('review-list').append(a);
    }
    if (!reviews.length) $('review-list').textContent = 'まだレビューがありません。AI が review create で今回見る画像をまとめます。';
    return;
  }
  review = await api('/api/review/' + encodeURIComponent(reviewId));
  draft = review.draft;
  $('workspace').hidden = false;
  $('title').textContent = review.title;
  document.title = review.title + ' · 画像レビュー';
  $('overall-note').value = draft.overall_note;
  setSaveStatus('下書き保存済み', 'saved');
  bind();
  renderCompareOptions();
  select(0);
  renderReceipt();
}
init().catch(fail);
