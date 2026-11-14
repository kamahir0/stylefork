"use strict";
const $ = id => document.getElementById(id);
let styles = [], session, allRuns = [], allTurns = [], allReviews = [], info;
const tokens = text => text.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);

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

async function refreshLibrary() {
  [styles, allRuns, allTurns, allReviews] = await Promise.all([
    api('/api/styles'),
    api('/api/runs'),
    api('/api/turns').catch(() => []),
    api('/api/reviews').catch(() => [])
  ]);
  const sessions = await api('/api/sessions');
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

  $('session-list').replaceChildren();
  for (const item of sessions) {
    const sessionRuns = allRuns.filter(r => r.session_id === item.session_id);
    const label = sessionRuns.length ? `${item.title} (${sessionRuns.length}枚)` : item.title;
    $('session-list').append(button(label, async () => {
      showSession(await api('/api/session/' + encodeURIComponent(item.session_id)));
    }));
  }
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
});

$('copy-request').onclick = handle(async () => {
  await saveSession();
  const turn = await api('/api/turn', {session_id: session.session_id, title: session.title});
  await navigator.clipboard.writeText(`データワークスペース「${info.workspace}」のセッション ${session.session_id} とターン ${turn.turn_id} を使い、今回の要件に沿って画像を生成してください。最初に AGENTS.md と stylefork-project スキルを確認し、保存済み絵柄 ${session.base_style_id} は変更しないでください。調整はこのセッション内だけに置き、生成後はこのターンの画像と必要な過去画像を番号付きレビューにまとめてください。`);
  $('copy-request').textContent = '依頼文をコピーしました';
});

(async () => {
  info = await api('/api/info');
  await refreshLibrary();
  const id = new URLSearchParams(location.search).get('session');
  if (id) showSession(await api('/api/session/' + encodeURIComponent(id)));
})().catch(error);
