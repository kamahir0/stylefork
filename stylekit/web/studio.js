"use strict";
const $ = id => document.getElementById(id);
let styles = [], session, allRuns = [], allTurns = [], allReviews = [], allSessions = [], info, toastTimer;
const tokens = text => text.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);

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

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作できませんでした');
  return result;
}

function error(e) {
  $('error').textContent = e.message || String(e);
  $('error').hidden = false;
}

function handle(fn) {
  return async () => {
    try {
      $('error').hidden = true;
      await fn();
    } catch (e) {
      error(e);
    }
  };
}

function button(text, callback) {
  const b = document.createElement('button');
  b.textContent = text;
  b.onclick = handle(callback);
  return b;
}

function showSession(value) {
  session = value;
  $('welcome').hidden = true;
  $('session-panel').hidden = false;
  $('session-title').textContent = value.title;
  const base = styles.find(s => s.style_id === value.base_style_id);
  $('base-style').textContent = `使用する絵柄：${base?.name || value.base_style_id} · 保存済みの設定は変更されません`;
  for (const field of ['requirements', 'negative-extra']) {
    $(field).value = value[field.replaceAll('-', '_')] || '';
  }
  for (const field of ['positive-add', 'negative-add', 'negative-remove']) {
    $(field).value = (value.adjustments[field.replaceAll('-', '_')] || []).join(', ');
  }
  $('working-status').textContent = Object.values(value.adjustments).some(v => Array.isArray(v) ? v.length : Object.keys(v).length)
    ? 'セッション内の調整あり'
    : '保存済みの絵柄を使用中';
  $('recipe-preview').textContent = JSON.stringify(value.working_recipe, null, 2);
  $('session-save-status').textContent = '読み込み済み';
  $('fork-result').textContent = '';
  history.replaceState(null, '', '/?session=' + encodeURIComponent(value.session_id));
  renderSessionList();
  renderRuns();
  renderLineage(base);
}

function renderLineage(style) {
  $('lineage').replaceChildren();
  const seen = new Set();
  while (style && !seen.has(style.style_id)) {
    seen.add(style.style_id);
    const p = document.createElement('p');
    p.textContent = style.name;
    $('lineage').append(p);
    style = styles.find(s => s.style_id === style.parent_style_id);
    if (style) {
      const arrow = document.createElement('span');
      arrow.className = 'quiet';
      arrow.textContent = '↑ 派生元';
      $('lineage').append(arrow);
    }
  }
}

function renderRuns() {
  $('run-list').replaceChildren();
  const runs = allRuns.filter(r => r.session_id === session.session_id);
  if (!runs.length) {
    const p = document.createElement('p');
    p.className = 'quiet';
    p.textContent = '生成結果が登録されると、ここからレビューを開けます。';
    $('run-list').append(p);
    return;
  }

  const byTurn = new Map();
  for (const run of runs) {
    if (!byTurn.has(run.turn_id)) byTurn.set(run.turn_id, []);
    byTurn.get(run.turn_id).push(run);
  }

  for (const [turnId, turnRuns] of byTurn.entries()) {
    const firstRun = turnRuns[0];
    const turnRecord = allTurns.find(t => t.turn_id === turnId);
    const existingReview = allReviews.find(rv => rv.batch_id === turnId);

    const card = document.createElement('div');
    card.className = 'run-card';

    const firstLabel = firstRun.outputs?.[0]?.label || firstRun.label;
    const title = document.createElement('div');
    title.className = 'run-card-title';
    title.textContent = turnRecord?.title || firstLabel || turnId;

    const meta = document.createElement('div');
    meta.className = 'run-card-meta';
    const dateStr = new Date(turnRecord?.created_at || firstRun.created_at).toLocaleString('ja-JP');
    const themePart = turnRecord?.theme && turnRecord.theme !== turnRecord.title ? ` · ${turnRecord.theme}` : '';
    meta.textContent = `${dateStr} · ${turnRuns.length}枚${themePart}`;

    const thumbs = document.createElement('div');
    thumbs.className = 'turn-thumbs';
    for (const r of turnRuns.slice(0, 4)) {
      const rLabel = r.outputs?.[0]?.label || r.label || r.run_id;
      const img = document.createElement('img');
      img.src = `/catalog-image?experiment=${encodeURIComponent(r.run_id)}&index=0`;
      img.alt = rLabel;
      img.title = rLabel;
      img.loading = 'lazy';
      thumbs.append(img);
    }

    const actionText = existingReview
      ? (existingReview.submitted ? 'このターンのレビューを開く（確定済み）' : 'このターンのレビューを開く')
      : 'このターンの画像をレビュー';

    const actionBtn = button(actionText, async () => {
      if (existingReview) {
        location.href = '/reviews?review=' + encodeURIComponent(existingReview.review_id);
        return;
      }
      const reviewTitle = turnRecord?.title
        ? `${session.title} · ${turnRecord.title}`
        : `${session.title} · 画像レビュー`;
      const created = await api('/api/review', {turn_id: turnId, title: reviewTitle});
      location.href = '/reviews?review=' + encodeURIComponent(created.review_id);
    });

    card.append(title, meta, thumbs, actionBtn);
    $('run-list').append(card);
  }
}

function renderSessionList() {
  $('session-list').replaceChildren();
  for (const item of allSessions) {
    const sessionRuns = allRuns.filter(r => r.session_id === item.session_id);
    const label = sessionRuns.length ? `${item.title} (${sessionRuns.length}枚)` : item.title;
    const btn = button(label, async () => {
      showSession(await api('/api/session/' + encodeURIComponent(item.session_id)));
    });
    if (session && session.session_id === item.session_id) btn.classList.add('active');
    $('session-list').append(btn);
  }
}

async function refreshLibrary() {
  [styles, allRuns, allTurns, allReviews, allSessions] = await Promise.all([
    api('/api/styles'),
    api('/api/runs'),
    api('/api/turns').catch(() => []),
    api('/api/reviews').catch(() => []),
    api('/api/sessions')
  ]);
  $('style-list').replaceChildren();
  for (const style of styles) {
    const card = document.createElement('div');
    card.className = 'style-card';
    const title = document.createElement('strong');
    title.textContent = style.name;
    const p = document.createElement('p');
    p.className = 'quiet';
    const parent = styles.find(s => s.style_id === style.parent_style_id);
    p.textContent = parent ? '派生元：' + parent.name : '保存済みの絵柄';
    card.append(title, p, button('この絵柄で新しく始める', async () => {
      showSession(await api('/api/session', {style_id: style.style_id}));
      await refreshLibrary();
    }));
    $('style-list').append(card);
  }
  if (!styles.length) $('style-list').textContent = 'まだ絵柄がありません。右上から登録できます。';
  renderSessionList();
}

async function saveSession() {
  session = await api('/api/session/' + session.session_id + '/update', {
    revision: session.revision,
    requirements: $('requirements').value,
    negative_extra: $('negative-extra').value,
    adjustments: {
      positive_add: tokens($('positive-add').value),
      negative_add: tokens($('negative-add').value),
      negative_remove: tokens($('negative-remove').value)
    }
  });
  $('working-status').textContent = Object.values(session.adjustments).some(v => Array.isArray(v) ? v.length : Object.keys(v).length)
    ? 'セッション内の調整あり'
    : '保存済みの絵柄を使用中';
  $('session-save-status').textContent = '作業内容を保存しました';
  $('recipe-preview').textContent = JSON.stringify(session.working_recipe, null, 2);
  showToast('セッションの作業内容を保存しました');
}

$('new-style').onclick = () => { $('register-style').showModal(); };
$('close-register').onclick = () => $('register-style').close();
$('register-submit').onclick = handle(async () => {
  const name = $('style-name').value.trim();
  const checkpoint = $('checkpoint').value.trim();
  if (!name || !checkpoint) throw new Error('名前とチェックポイント名を入力してください。');
  const style = await api('/api/style', {
    style_id: 'style-' + crypto.randomUUID().slice(0, 8),
    name,
    recipe: {
      style_config: {
        checkpoint,
        loras: [],
        clip_stop_at_clip_layer: null,
        base_resolution: [832, 1216],
        sampler: {steps: 28, cfg: 4.5, sampler_name: 'euler_ancestral', scheduler: 'karras', denoise: 1},
        hires: {enabled: false},
        detailer: {enabled: false}
      },
      prompt_template: {
        style_prefix: tokens($('root-tokens').value),
        style_suffix: [],
        default_negative: 'low quality, bad anatomy, bad hands',
        detailer_positive_template: ''
      }
    }
  });
  $('register-style').close();
  await refreshLibrary();
  showSession(await api('/api/session', {style_id: style.style_id}));
  await refreshLibrary();
  showToast(`絵柄「${style.name}」を登録しました`);
});

$('update-session').onclick = handle(saveSession);
$('fork-style').onclick = handle(async () => {
  const name = $('fork-name').value.trim();
  if (!name) throw new Error('新しい絵柄の名前を入力してください。');
  await saveSession();
  const child = await api('/api/session/' + session.session_id + '/fork', {
    style_id: 'style-' + crypto.randomUUID().slice(0, 8),
    name,
    save_intent: 'User clicked 新しい絵柄として保存: ' + name
  });
  await refreshLibrary();
  $('fork-result').textContent = `「${child.name}」を別の絵柄として保存しました。元の絵柄と、このセッションの使用元はそのままです。`;
  $('fork-name').value = '';
  showToast(`新しい絵柄「${child.name}」を保存しました`);
});

$('copy-request').onclick = handle(async () => {
  await saveSession();
  const turn = await api('/api/turn', {session_id: session.session_id, title: session.title});
  await navigator.clipboard.writeText(`データワークスペース「${info.workspace}」のセッション ${session.session_id} とターン ${turn.turn_id} を使い、今回の要件に沿って画像を生成してください。最初に AGENTS.md と stylefork-project スキルを確認し、保存済み絵柄 ${session.base_style_id} は変更しないでください。調整はこのセッション内だけに置き、生成後はこのターンの画像と必要な過去画像を番号付きレビューにまとめてください。`);
  const label = $('copy-request-label') || $('copy-request');
  label.textContent = '依頼文をコピーしました';
  showToast('エージェントへの依頼文をコピーしました');
});

(async () => {
  initTheme();
  info = await api('/api/info');
  await refreshLibrary();
  const id = new URLSearchParams(location.search).get('session');
  if (id) showSession(await api('/api/session/' + encodeURIComponent(id)));
})().catch(error);
