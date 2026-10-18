'use strict';

/* ============================================================
   日本株監視アシスタント - フロントエンドロジック
   - 公開データ（株価・財務指標）: ./data/*.json から fetch（サーバーなし）
   - 個人データ（登録銘柄・購入検討価格・メモ・監視条件）: localStorage のみ
     （この端末のブラウザ内にのみ保存され、どこにも送信されない）
   ============================================================ */

const LS_WATCHLIST = 'kabuwatch_watchlist_v1';
const LS_SEEN_DISCLOSURE = 'kabuwatch_seen_disclosure_v1';

const state = {
  snapshot: null,       // ./data/watchlist_snapshot.json
  companiesMaster: {},  // ./data/companies_master.json
  watchlist: [],        // localStorageから読み込んだ個人データ
  editingCode: null,
};

/* ---------------- localStorage ヘルパー ---------------- */

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(LS_WATCHLIST);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error('watchlist読み込み失敗', e);
    return [];
  }
}

function saveWatchlist(list) {
  localStorage.setItem(LS_WATCHLIST, JSON.stringify(list));
}

function loadSeenDisclosure() {
  try {
    const raw = localStorage.getItem(LS_SEEN_DISCLOSURE);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    return {};
  }
}

function saveSeenDisclosure(map) {
  localStorage.setItem(LS_SEEN_DISCLOSURE, JSON.stringify(map));
}

/* ---------------- データ読み込み ---------------- */

async function loadData() {
  state.watchlist = loadWatchlist();
  try {
    const [snapRes, masterRes] = await Promise.all([
      fetch('./data/watchlist_snapshot.json', { cache: 'no-store' }),
      fetch('./data/companies_master.json', { cache: 'no-store' }).catch(() => null),
    ]);
    state.snapshot = snapRes.ok ? await snapRes.json() : null;
    state.companiesMaster = masterRes && masterRes.ok ? await masterRes.json() : {};
  } catch (e) {
    console.error('データ取得失敗', e);
    state.snapshot = null;
  }
  renderAll();
}

/* ---------------- フォーマット ---------------- */

function fmtYen(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '取得不可';
  return '¥' + Math.round(v).toLocaleString('ja-JP');
}

function fmtNum(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '取得不可';
  return v.toFixed(digits);
}

function fmtPct(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '取得不可';
  return (v * 100).toFixed(digits) + '%';
}

function fmtDate(v) {
  if (!v) return '取得不可';
  return v;
}

function isNA(v) {
  return v === null || v === undefined || Number.isNaN(v);
}

/* ---------------- アラート判定 ---------------- */

function computeAlerts(item, snap) {
  const alerts = [];
  if (!snap) {
    return { alerts, earnings: null };
  }
  const a = item.alerts || {};

  if (a.priceBelowTarget && item.targetPrice != null && !isNA(snap.price) && snap.price <= item.targetPrice) {
    alerts.push(`購入検討価格（${fmtYen(item.targetPrice)}）以下です（現在 ${fmtYen(snap.price)}）`);
  }

  if (a.changePctThreshold != null && !isNA(snap.change_pct) && Math.abs(snap.change_pct) >= a.changePctThreshold) {
    const dir = snap.change_pct >= 0 ? '上昇' : '下落';
    alerts.push(`前日比 ${fmtPct(Math.abs(snap.change_pct))} ${dir}（設定: ${(a.changePctThreshold * 100).toFixed(1)}%以上）`);
  }

  if (a.perMax != null && !isNA(snap.per) && snap.per <= a.perMax) {
    alerts.push(`PERが${fmtNum(snap.per)}倍で設定条件（${a.perMax}倍以下）に該当`);
  }

  if (a.pbrMax != null && !isNA(snap.pbr) && snap.pbr <= a.pbrMax) {
    alerts.push(`PBRが${fmtNum(snap.pbr, 2)}倍で設定条件（${a.pbrMax}倍以下）に該当`);
  }

  if (a.bigFinancialChangeThreshold != null) {
    if (!isNA(snap.sales_growth_yoy) && Math.abs(snap.sales_growth_yoy) >= a.bigFinancialChangeThreshold) {
      alerts.push(`売上高が前期比 ${fmtPct(snap.sales_growth_yoy)} 変化`);
    }
    if (!isNA(snap.operating_profit_growth_yoy) && Math.abs(snap.operating_profit_growth_yoy) >= a.bigFinancialChangeThreshold) {
      alerts.push(`営業利益が前期比 ${fmtPct(snap.operating_profit_growth_yoy)} 変化`);
    }
  }

  let earnings = null;
  if (a.notifyEarningsUpdate && snap.latest_disclosure_date) {
    const seen = loadSeenDisclosure();
    if (seen[item.code] !== snap.latest_disclosure_date) {
      earnings = `決算情報が更新されました（開示日: ${snap.latest_disclosure_date}）`;
    }
  }

  return { alerts, earnings };
}

function markDisclosureSeen(code, date) {
  if (!date) return;
  const seen = loadSeenDisclosure();
  seen[code] = date;
  saveSeenDisclosure(seen);
}

/* ---------------- 一覧タブ ---------------- */

function renderList() {
  const container = document.getElementById('watch-cards');
  const emptyEl = document.getElementById('list-empty');
  container.innerHTML = '';

  if (state.watchlist.length === 0) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  const companies = (state.snapshot && state.snapshot.companies) || {};

  for (const item of state.watchlist) {
    const snap = companies[item.code] || null;
    container.appendChild(renderStockCard(item, snap));
    if (snap && snap.latest_disclosure_date) {
      markDisclosureSeen(item.code, snap.latest_disclosure_date);
    }
  }
}

function renderStockCard(item, snap) {
  const el = document.createElement('div');
  el.className = 'card stock-card';

  const name = snap ? snap.name : null;
  const isSample = snap ? !!snap.is_sample : false;
  const price = snap ? snap.price : null;
  const changePct = snap ? snap.change_pct : null;
  const change = snap ? snap.change : null;

  const { alerts, earnings } = computeAlerts(item, snap);

  const changeClass = isNA(change) ? '' : (change >= 0 ? 'up' : 'down');
  const changeSign = isNA(change) ? '' : (change >= 0 ? '+' : '');

  el.innerHTML = `
    <div class="stock-card-head">
      <div>
        <span class="stock-name">${escapeHtml(name || '（データ取得前）')}</span>
        <span class="stock-code">${escapeHtml(item.code)}</span>
        ${isSample ? '<span class="sample-tag">サンプル</span>' : ''}
      </div>
      <div>
        <div class="stock-price">${isNA(price) ? '取得不可' : fmtYen(price)}</div>
        ${snap ? `<div class="stock-change ${changeClass}">${isNA(change) ? '' : changeSign + Math.round(change).toLocaleString('ja-JP') + ' (' + changeSign + fmtPct(changePct) + ')'}</div>` : ''}
      </div>
    </div>

    <div class="metric-grid">
      ${metricHtml('PER', snap ? fmtNum(snap.per) + '倍' : null, snap && !isNA(snap.per))}
      ${metricHtml('PBR', snap ? fmtNum(snap.pbr, 2) + '倍' : null, snap && !isNA(snap.pbr))}
      ${metricHtml('ROE', snap ? fmtPct(snap.roe) : null, snap && !isNA(snap.roe))}
      ${metricHtml('売上成長率', snap ? fmtPct(snap.sales_growth_yoy) : null, snap && !isNA(snap.sales_growth_yoy))}
      ${metricHtml('営業益成長率', snap ? fmtPct(snap.operating_profit_growth_yoy) : null, snap && !isNA(snap.operating_profit_growth_yoy))}
      ${metricHtml('配当利回り', snap ? fmtPct(snap.dividend_yield) : null, snap && !isNA(snap.dividend_yield))}
    </div>

    ${item.targetPrice != null ? `<div class="target-price-row">購入検討価格: ${fmtYen(item.targetPrice)}</div>` : ''}

    <div class="alert-badges">
      ${earnings ? `<div class="earnings-badge">📢 ${escapeHtml(earnings)}</div>` : ''}
      ${alerts.map(a => `<div class="alert-badge">⚠️ ${escapeHtml(a)}</div>`).join('')}
    </div>

    ${item.memo ? `<div class="memo-text">${escapeHtml(item.memo)}</div>` : ''}

    <div class="data-updated">
      ${snap ? `データ更新日時: ${formatUpdatedAt(snap.updated_at)} / 決算基準日: ${fmtDate(snap.latest_disclosure_date)}` : 'まだデータが取得されていません（次回の自動更新をお待ちください）'}
    </div>
  `;
  return el;
}

function metricHtml(label, value, available) {
  const v = available && value ? value : '取得不可';
  return `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value ${available ? '' : 'na'}">${v}</div></div>`;
}

function formatUpdatedAt(iso) {
  if (!iso) return '取得不可';
  try {
    const d = new Date(iso);
    return d.toLocaleString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return iso;
  }
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ---------------- ヘッダー（更新情報・サンプルバナー） ---------------- */

function renderHeader() {
  const bannerEl = document.getElementById('sample-banner');
  const infoEl = document.getElementById('update-info');

  if (!state.snapshot) {
    bannerEl.hidden = true;
    infoEl.textContent = 'データを読み込めませんでした（オフライン、またはまだデータが生成されていません）';
    return;
  }

  bannerEl.hidden = state.snapshot.mode !== 'sample';
  infoEl.textContent = `データ生成日時: ${formatUpdatedAt(state.snapshot.generated_at)}`;
}

/* ---------------- 登録・管理タブ ---------------- */

function renderRegisterTab() {
  renderRegisteredList();
}

function renderRegisteredList() {
  const container = document.getElementById('registered-list');
  const emptyEl = document.getElementById('registered-empty');
  container.innerHTML = '';

  if (state.watchlist.length === 0) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  const companies = (state.snapshot && state.snapshot.companies) || {};

  for (const item of state.watchlist) {
    const snap = companies[item.code];
    const name = (snap && snap.name) || state.companiesMaster[item.code]?.name || item.code;
    const row = document.createElement('div');
    row.className = 'registered-row';
    row.innerHTML = `
      <div>${escapeHtml(name)} <span class="stock-code">${escapeHtml(item.code)}</span></div>
      <div class="registered-row-actions">
        <button type="button" data-action="edit" data-code="${escapeHtml(item.code)}">編集</button>
        <button type="button" class="danger" data-action="delete" data-code="${escapeHtml(item.code)}">削除</button>
      </div>
    `;
    container.appendChild(row);
  }

  container.querySelectorAll('[data-action="edit"]').forEach(btn => {
    btn.addEventListener('click', () => startEdit(btn.dataset.code));
  });
  container.querySelectorAll('[data-action="delete"]').forEach(btn => {
    btn.addEventListener('click', () => deleteWatchItem(btn.dataset.code));
  });
}

function deleteWatchItem(code) {
  if (!confirm('この銘柄を監視リストから削除しますか？')) return;
  state.watchlist = state.watchlist.filter(i => i.code !== code);
  saveWatchlist(state.watchlist);
  renderAll();
}

function startEdit(code) {
  const item = state.watchlist.find(i => i.code === code);
  if (!item) return;
  state.editingCode = code;

  selectCompany(code, (state.companiesMaster[code] && state.companiesMaster[code].name) || code);
  document.getElementById('target-price').value = item.targetPrice != null ? item.targetPrice : '';
  document.getElementById('memo').value = item.memo || '';

  const a = item.alerts || {};
  document.getElementById('alert-target-price').checked = a.priceBelowTarget !== false;
  document.getElementById('alert-change-pct').value = a.changePctThreshold != null ? (a.changePctThreshold * 100) : '';
  document.getElementById('alert-per-max').value = a.perMax != null ? a.perMax : '';
  document.getElementById('alert-pbr-max').value = a.pbrMax != null ? a.pbrMax : '';
  document.getElementById('alert-earnings').checked = a.notifyEarningsUpdate !== false;
  document.getElementById('alert-financial-change').value = a.bigFinancialChangeThreshold != null ? (a.bigFinancialChangeThreshold * 100) : 20;

  document.getElementById('cancel-edit-btn').hidden = false;
  document.getElementById('save-btn').textContent = '更新する';
  switchTab('register');
  document.getElementById('register-form').scrollIntoView({ behavior: 'smooth' });
}

function cancelEdit() {
  state.editingCode = null;
  document.getElementById('register-form').reset();
  document.getElementById('selected-code').value = '';
  document.getElementById('selected-company').hidden = true;
  document.getElementById('cancel-edit-btn').hidden = true;
  document.getElementById('save-btn').textContent = '保存する';
}

/* ---------------- 銘柄検索（登録用） ---------------- */

function selectCompany(code, name) {
  document.getElementById('selected-code').value = code;
  const el = document.getElementById('selected-company');
  el.hidden = false;
  el.innerHTML = `<span>${escapeHtml(name)}（${escapeHtml(code)}）</span><button type="button" id="clear-selected">変更</button>`;
  document.getElementById('clear-selected').addEventListener('click', () => {
    document.getElementById('selected-code').value = '';
    el.hidden = true;
    document.getElementById('code-search').value = '';
    document.getElementById('code-search').focus();
  });
  document.getElementById('search-results').hidden = true;
  document.getElementById('code-search').value = '';
}

function setupSearch() {
  const input = document.getElementById('code-search');
  const resultsEl = document.getElementById('search-results');

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      resultsEl.hidden = true;
      resultsEl.innerHTML = '';
      return;
    }
    const master = state.companiesMaster || {};
    const matches = Object.values(master)
      .filter(c => c.code.includes(q) || (c.name && c.name.toLowerCase().includes(q)))
      .slice(0, 20);

    if (matches.length === 0) {
      // マスタに見つからない場合でも、4桁の数字ならコード直接指定で登録できるようにする
      if (/^\d{4}$/.test(q)) {
        resultsEl.innerHTML = `<div class="search-result-item" data-code="${q}" data-name="${q}">コード ${q} で登録（企業名は未取得）</div>`;
        resultsEl.hidden = false;
        bindResultClicks();
      } else {
        resultsEl.innerHTML = `<div class="search-result-item">該当する銘柄が見つかりません</div>`;
        resultsEl.hidden = false;
      }
      return;
    }
    resultsEl.innerHTML = matches
      .map(c => `<div class="search-result-item" data-code="${escapeHtml(c.code)}" data-name="${escapeHtml(c.name)}">${escapeHtml(c.name)}（${escapeHtml(c.code)}）</div>`)
      .join('');
    resultsEl.hidden = false;
    bindResultClicks();
  });

  function bindResultClicks() {
    resultsEl.querySelectorAll('.search-result-item[data-code]').forEach(elm => {
      elm.addEventListener('click', () => selectCompany(elm.dataset.code, elm.dataset.name));
    });
  }
}

/* ---------------- 登録フォーム送信 ---------------- */

function setupRegisterForm() {
  document.getElementById('register-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const code = document.getElementById('selected-code').value.trim();
    if (!code) {
      alert('銘柄コードを選択または入力してください');
      return;
    }

    const targetPriceRaw = document.getElementById('target-price').value;
    const changePctRaw = document.getElementById('alert-change-pct').value;
    const perMaxRaw = document.getElementById('alert-per-max').value;
    const pbrMaxRaw = document.getElementById('alert-pbr-max').value;
    const finChangeRaw = document.getElementById('alert-financial-change').value;

    const item = {
      code,
      addedAt: new Date().toISOString(),
      targetPrice: targetPriceRaw ? parseFloat(targetPriceRaw) : null,
      memo: document.getElementById('memo').value.trim(),
      alerts: {
        priceBelowTarget: document.getElementById('alert-target-price').checked,
        changePctThreshold: changePctRaw ? parseFloat(changePctRaw) / 100 : null,
        perMax: perMaxRaw ? parseFloat(perMaxRaw) : null,
        pbrMax: pbrMaxRaw ? parseFloat(pbrMaxRaw) : null,
        notifyEarningsUpdate: document.getElementById('alert-earnings').checked,
        bigFinancialChangeThreshold: finChangeRaw ? parseFloat(finChangeRaw) / 100 : null,
      },
    };

    const existingIdx = state.watchlist.findIndex(i => i.code === code);
    if (existingIdx >= 0) {
      item.addedAt = state.watchlist[existingIdx].addedAt;
      state.watchlist[existingIdx] = item;
    } else {
      state.watchlist.push(item);
    }
    saveWatchlist(state.watchlist);
    state.editingCode = null;
    cancelEdit();
    renderAll();
    switchTab('list');
  });

  document.getElementById('cancel-edit-btn').addEventListener('click', cancelEdit);
}

/* ---------------- 抽出タブ ---------------- */

function renderScreenerTab() {
  const container = document.getElementById('screener-list');
  const emptyEl = document.getElementById('screener-empty');
  container.innerHTML = '';

  const companies = (state.snapshot && state.snapshot.companies) || {};
  const entries = Object.values(companies).filter(c => c.screening);

  if (entries.length === 0) {
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  entries.sort((a, b) => {
    const as = a.screening.data_sufficient ? (a.screening.score || 0) : -1;
    const bs = b.screening.data_sufficient ? (b.screening.score || 0) : -1;
    return bs - as;
  });

  entries.forEach((c, idx) => {
    const sc = c.screening;
    const el = document.createElement('div');
    el.className = 'card screener-item';
    if (!sc.data_sufficient) {
      el.innerHTML = `
        <div class="screener-rank">#${idx + 1}</div>
        <div><strong>${escapeHtml(c.name || c.code)}</strong> <span class="stock-code">${escapeHtml(c.code)}</span></div>
        <div class="data-insufficient">データ不足のため評価できません（不足項目: ${(sc.missing_fields || []).join('、') || '不明'}）</div>
      `;
    } else {
      el.innerHTML = `
        <div class="screener-rank">#${idx + 1} <span class="screener-score">${sc.score}点</span></div>
        <div><strong>${escapeHtml(c.name || c.code)}</strong> <span class="stock-code">${escapeHtml(c.code)}</span></div>
        <div class="screener-reasons">注目理由: ${sc.notable_reasons.map(escapeHtml).join(' / ')}</div>
        ${sc.concerns.length ? `<div class="screener-concerns">懸念点: ${sc.concerns.map(escapeHtml).join(' / ')}</div>` : ''}
        <div class="screener-asof">データ基準日: ${fmtDate(sc.as_of_date)}</div>
      `;
    }
    container.appendChild(el);
  });
}

/* ---------------- 設定タブ ---------------- */

function renderSettingsTab() {
  const el = document.getElementById('source-info');
  const info = state.snapshot ? state.snapshot.source_info : null;
  if (!info) {
    el.innerHTML = '<p class="note-text">データが読み込まれていません。</p>';
    return;
  }
  if (info.note) {
    el.innerHTML = `<p class="note-text">${escapeHtml(info.provider)}<br>${escapeHtml(info.note)}</p>`;
    return;
  }
  el.innerHTML = `
    <p class="note-text"><strong>提供元:</strong> ${escapeHtml(info.provider)}</p>
    <p class="note-text"><strong>株価データ:</strong> ${escapeHtml(info.price_data.kind)}<br>
      更新頻度: ${escapeHtml(info.price_data.update_frequency)}<br>
      無料枠: ${escapeHtml(info.price_data.free_tier_limit)}</p>
    <p class="note-text"><strong>財務データ:</strong> ${escapeHtml(info.financial_data.kind)}<br>
      更新頻度: ${escapeHtml(info.financial_data.update_frequency)}<br>
      無料枠: ${escapeHtml(info.financial_data.free_tier_limit)}</p>
  `;
}

function setupBackup() {
  document.getElementById('export-btn').addEventListener('click', () => {
    const payload = {
      exported_at: new Date().toISOString(),
      watchlist: state.watchlist,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const today = new Date().toISOString().slice(0, 10);
    a.href = url;
    a.download = `kabuwatch-backup-${today}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  document.getElementById('import-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    const resultEl = document.getElementById('import-result');
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const imported = Array.isArray(data) ? data : (data.watchlist || []);
      if (!Array.isArray(imported)) throw new Error('形式が正しくありません');

      const existingCodes = new Set(state.watchlist.map(i => i.code));
      let added = 0;
      for (const item of imported) {
        if (item && item.code && !existingCodes.has(item.code)) {
          state.watchlist.push(item);
          existingCodes.add(item.code);
          added++;
        }
      }
      saveWatchlist(state.watchlist);
      resultEl.textContent = `${added}件の銘柄を追加しました（重複分は除外）`;
      renderAll();
    } catch (err) {
      resultEl.textContent = '読み込みに失敗しました: ' + err.message;
    }
    e.target.value = '';
  });
}

/* ---------------- 銘柄コード同期（watchlist_codes.json 用） ---------------- */

function setupCodeCopy() {
  document.getElementById('copy-codes-btn').addEventListener('click', async () => {
    const codes = state.watchlist.map(i => i.code);
    const json = JSON.stringify(codes, null, 2);
    const resultEl = document.getElementById('copy-codes-result');
    const previewEl = document.getElementById('copy-codes-preview');

    previewEl.hidden = false;
    previewEl.textContent = json;

    try {
      await navigator.clipboard.writeText(json);
      resultEl.textContent = `コピーしました（${codes.length}銘柄）。data/watchlist_codes.json に貼り付けて保存してください。`;
    } catch (e) {
      resultEl.textContent = 'クリップボードにコピーできませんでした。下の内容を手動で選択してコピーしてください。';
    }
  });
}

/* ---------------- タブ切り替え ---------------- */

function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => { p.hidden = p.id !== `tab-${name}`; });
  document.querySelectorAll('.tab-btn').forEach(b => { b.classList.toggle('active', b.dataset.tab === name); });
  if (name === 'settings') renderSettingsTab();
  if (name === 'screener') renderScreenerTab();
  if (name === 'register') renderRegisterTab();
}

function setupTabBar() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
}

/* ---------------- 全体再描画 ---------------- */

function renderAll() {
  renderHeader();
  renderList();
  renderRegisteredList();
}

/* ---------------- 初期化 ---------------- */

function init() {
  setupTabBar();
  setupSearch();
  setupRegisterForm();
  setupBackup();
  setupCodeCopy();
  loadData();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./service-worker.js').catch(() => {});
  }
}

document.addEventListener('DOMContentLoaded', init);
