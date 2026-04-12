/* ═══════════════════════════════════════════════════════════════
   交易工作站前端邏輯 v4
   ═══════════════════════════════════════════════════════════════ */
console.log('=== APP JS v7 LOADED ===');

const API = 'http://localhost:8000';
const WS  = 'ws://localhost:8000/ws';

// ── WebSocket ──────────────────────────────────────────────────
const priceData = {};

function connectWS() {
  const ws  = new WebSocket(WS);
  const dot = document.getElementById('ws-status');
  ws.onopen  = () => dot.classList.add('connected');
  ws.onclose = () => { dot.classList.remove('connected'); setTimeout(connectWS, 3000); };
  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.type === 'tick') updatePriceBar(msg.symbol, msg.price);
  };
  setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 15000);
}

// ── 報價欄 ─────────────────────────────────────────────────────
function updatePriceBar(symbol, price) {
  const prev = priceData[symbol];
  priceData[symbol] = price;
  const el = document.querySelector(`[data-symbol="${symbol}"]`);
  if (!el) return;
  el.querySelector('.value').textContent = price.toLocaleString();
  if (prev !== undefined) {
    const diff = price - prev;
    const pct  = ((diff / prev) * 100).toFixed(2);
    const ch   = el.querySelector('.change');
    ch.textContent = `${diff >= 0 ? '+' : ''}${diff.toFixed(2)} (${pct}%)`;
    ch.className   = `change ${diff >= 0 ? 'price-up' : 'price-down'}`;
  }
}

// ── 即時報價輪詢 ───────────────────────────────────────────────
async function loadPrices() {
  try {
    const data = await fetch(`${API}/prices`).then(r => r.json());
    console.log('[Prices]', data);
    Object.entries(data).forEach(([symbol, price]) => {
      console.log(`updatePriceBar(${symbol}, ${price})`);
      updatePriceBar(symbol, price);
    });
  } catch(e) { console.error('[Prices] 錯誤:', e); }
}

// ── 財經新聞 ───────────────────────────────────────────────────
async function loadNews() {
  try {
    const items = await fetch(`${API}/news`).then(r => r.json());
    document.getElementById('news-inner').innerHTML = items.map(n =>
      `<a href="${n.link}" target="_blank">[${n.source}] ${n.title}</a>`
    ).join('');
  } catch (e) { console.warn('新聞載入失敗', e); }
}

// ── YouTube ────────────────────────────────────────────────────
let playlist    = [];
let currentIndex = 0;

function playAt(index) {
  if (!playlist.length) return;
  currentIndex = (index + playlist.length) % playlist.length;
  const item = playlist[currentIndex];
  const iframe = document.getElementById('yt-iframe');
  iframe.src = `https://www.youtube.com/embed/${item.videoId}?autoplay=0&rel=0&enablejsapi=1`;
  document.getElementById('now-playing').textContent = item.title;
  document.querySelectorAll('.playlist-item').forEach((el, i) =>
    el.classList.toggle('active', i === currentIndex));
}
function playNext() { playAt(currentIndex + 1); }
function playPrev() { playAt(currentIndex - 1); }
let _paused = false;
function playPause() {
  const iframe = document.getElementById('yt-iframe');
  const btn = document.getElementById('btn-playpause');
  if (_paused) {
    iframe.contentWindow?.postMessage('{"event":"command","func":"playVideo","args":""}', '*');
    btn.textContent = '⏸';
    _paused = false;
  } else {
    iframe.contentWindow?.postMessage('{"event":"command","func":"pauseVideo","args":""}', '*');
    btn.textContent = '▶';
    _paused = true;
  }
}

async function loadPlaylist() {
  const status = await fetch(`${API}/youtube/status`).then(r => r.json()).catch(() => ({ authorized: false }));
  const authPrompt  = document.getElementById('auth-prompt');
  const wrap        = document.getElementById('yt-iframe-wrap');
  const controls    = document.getElementById('player-controls');
  const plContainer = document.getElementById('playlist-container');

  if (!status.authorized) {
    authPrompt.style.display = 'flex';
    wrap.style.display       = 'none';
    controls.style.display   = 'none';
    return;
  }

  authPrompt.style.display = 'none';
  wrap.style.display       = 'block';
  controls.style.display   = 'flex';

  try {
    playlist = await fetch(`${API}/youtube/playlist`).then(r => r.json());
    plContainer.innerHTML = playlist.map((item, i) => `
      <div class="playlist-item" onclick="playAt(${i})">
        <img src="${item.thumbnail}" alt="">
        <div class="title">${escHtml(item.title)}</div>
      </div>`).join('');
    if (playlist.length) { currentIndex = 0; document.querySelectorAll('.playlist-item')[0]?.classList.add('active'); }
  } catch (e) { console.error('播放清單載入失敗', e); }
}

function openYTAuth() {
  const win = window.open(`${API}/youtube/auth`, '_blank', 'width=500,height=600');
  const t = setInterval(() => { if (win.closed) { clearInterval(t); loadPlaylist(); } }, 1000);
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── 恐貪指數 ───────────────────────────────────────────────────
const FNG_LABELS = {
  'Extreme Fear': '極度恐懼', 'Fear': '恐懼',
  'Neutral': '中性', 'Greed': '貪婪', 'Extreme Greed': '極度貪婪'
};
const FNG_COLORS = {
  'Extreme Fear': '#e74c3c', 'Fear': '#e67e22',
  'Neutral': '#f1c40f', 'Greed': '#2ecc71', 'Extreme Greed': '#27ae60'
};

async function loadFng() {
  try {
    const d = await fetch(`${API}/fng`).then(r => r.json());
    if (d.error) return;
    const v = d.value;
    const color = FNG_COLORS[d.label] || '#f1c40f';
    const deg = (v / 100) * 180 - 90;
    document.getElementById('fng-needle').style.transform = `rotate(${deg}deg)`;
    document.getElementById('fng-value').textContent = v;
    document.getElementById('fng-value').style.color = color;
    document.getElementById('fng-label').textContent = FNG_LABELS[d.label] || d.label;
    document.getElementById('fng-label').style.color = color;
    const fmt = n => n != null ? n : '--';
    document.getElementById('fng-yesterday').textContent =
      `昨日：${fmt(d.yesterday)} ｜ 上週：${fmt(d.last_week)} ｜ 上月：${fmt(d.last_month)}`;
  } catch(e) {}
}

// ══════════════════════════════════════════════════════════════
// ── 超簡單策略機 ──────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════

let selectedLight = null;   // 'red' | 'yellow' | 'green' | null
let selectedSub   = null;   // 'bull' | 'bear' | null  (黃燈子策略)
let selectedZibao = null;   // 'green' | 'red' | null  (紫爆選項)

// ── localStorage 持久化 ────────────────────────────────────────
const STRATEGY_INPUTS = [
  'inp-entry','inp-bull-big','inp-bear-big',
  'inp-bull-horn','inp-bear-claw','inp-purple',
  'inp-product','inp-point-val'
];
const LEVERAGE_INPUTS = [
  'lev-taiex','lev-margin-tx','lev-margin-mtx','lev-margin-mxf','lev-target'
];

function saveState() {
  const state = {
    light: selectedLight,
    sub:   selectedSub,
    zibao: selectedZibao,
  };
  STRATEGY_INPUTS.forEach(id => {
    state[id] = document.getElementById(id)?.value ?? '';
  });
  LEVERAGE_INPUTS.forEach(id => {
    state[id] = document.getElementById(id)?.value ?? '';
  });
  localStorage.setItem('trading_state', JSON.stringify(state));
}

function loadState() {
  try {
    const state = JSON.parse(localStorage.getItem('trading_state') || '{}');
    selectedLight = state.light || null;
    selectedSub   = state.sub   || null;
    selectedZibao = state.zibao || null;
    STRATEGY_INPUTS.forEach(id => {
      const el = document.getElementById(id);
      if (el && state[id]) el.value = state[id];
    });
    LEVERAGE_INPUTS.forEach(id => {
      const el = document.getElementById(id);
      if (el && state[id]) el.value = state[id];
    });
  } catch(e) {}
}

function getNum(id) {
  const val = parseFloat(document.getElementById(id)?.value);
  return isNaN(val) ? 0 : val;
}

function setEl(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// 格式化停損距離
function fmtStop(pts, ptVal) {
  if (!pts && pts !== 0) return '--';
  const abs  = Math.abs(pts).toFixed(0);
  const warn = pts < 0 ? ' ⚠逆向' : '';
  if (!ptVal) return `${abs}點(請填每點價格)${warn}`;
  const money = (Math.abs(pts) * ptVal).toLocaleString();
  return `${abs}點(${money}元)${warn}`;
}

function initStrategy() {
  // 燈號按鈕
  document.querySelectorAll('.light-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const light = btn.dataset.light;
      selectedLight = selectedLight === light ? null : light;
      if (selectedLight !== 'yellow') selectedSub = null;
      updateStrategy();
      saveState();
    });
  });

  // 子策略按鈕
  document.querySelectorAll('.sub-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const sub = btn.dataset.sub;
      selectedSub = selectedSub === sub ? null : sub;
      updateStrategy();
      saveState();
    });
  });

  // 紫爆按鈕
  document.querySelectorAll('.zibao-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const z = btn.dataset.zibao;
      selectedZibao = selectedZibao === z ? null : z;
      updateStrategy();
      saveState();
    });
  });

  // 輸入框即時重算 + 儲存
  document.querySelectorAll('#strategy-panel input').forEach(inp => {
    inp.addEventListener('input', () => { updateStrategy(); saveState(); });
  });

  // 目前價格輸入
  document.getElementById('inp-current-price')?.addEventListener('input', calcPnl);

  updateStrategy();
}

function updateStrategy() {
  // ── 燈號狀態 ──────────────────────────────────────────────
  document.querySelectorAll('.light-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.light === selectedLight);
  });

  // ── 策略項目亮暗 ──────────────────────────────────────────
  document.getElementById('strat-red').classList.toggle('active',    selectedLight === 'red');
  document.getElementById('strat-yellow').classList.toggle('active', selectedLight === 'yellow');
  document.getElementById('strat-green').classList.toggle('active',  selectedLight === 'green');

  // ── 子策略顯示（黃燈時） ──────────────────────────────────
  const subArea = document.getElementById('sub-strat');
  subArea.classList.toggle('show', selectedLight === 'yellow');
  document.querySelectorAll('.sub-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.sub === selectedSub);
  });

  // ── 停損區顯示 ────────────────────────────────────────────
  document.getElementById('sl-long').classList.toggle('sl-hidden',  selectedLight !== 'red');
  document.getElementById('sl-range').classList.toggle('sl-hidden', selectedLight !== 'yellow');
  document.getElementById('sl-short').classList.toggle('sl-hidden', selectedLight !== 'green');

  // 區間子列暗度
  const bearRow = document.getElementById('sl-range-bear-row');
  const bullRow = document.getElementById('sl-range-bull-row');
  bearRow.classList.toggle('dimmed', selectedSub !== null && selectedSub !== 'bull');
  bullRow.classList.toggle('dimmed', selectedSub !== null && selectedSub !== 'bear');

  // 紫爆二選一暗度
  document.querySelectorAll('.zibao-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.zibao === selectedZibao);
  });
  const zRow1 = document.getElementById('sl-zibao-row-green');
  const zRow2 = document.getElementById('sl-zibao-row-red');
  zRow1.classList.toggle('dimmed', selectedZibao !== null && selectedZibao !== 'green');
  zRow2.classList.toggle('dimmed', selectedZibao !== null && selectedZibao !== 'red');

  calcStopLoss();
  calcPnl();
}


function calcPnl() {
  const section = document.getElementById('pnl-section');
  const pnlPts  = document.getElementById('pnl-pts');
  const pnlMoney = document.getElementById('pnl-money');

  // 黃燈不顯示
  if (!selectedLight || selectedLight === 'yellow') {
    section.classList.remove('show');
    return;
  }
  section.classList.add('show');

  const entry   = getNum('inp-entry');
  const current = parseFloat(document.getElementById('inp-current-price')?.value) || 0;
  const ptVal   = parseFloat(document.getElementById('inp-point-val')?.value) || 0;

  if (!entry || !current) {
    pnlPts.textContent   = '--';
    pnlMoney.textContent = '--';
    pnlPts.className     = '';
    pnlMoney.className   = 'pnl-money';
    return;
  }

  // 紅燈做多：current - entry；綠燈做空：entry - current
  const pts = selectedLight === 'red' ? current - entry : entry - current;
  const isProfit = pts >= 0;
  const cls = isProfit ? 'pnl-loss' : 'pnl-profit';  // 台灣：紅=獲利 綠=虧損
  const sign = isProfit ? '+' : '';

  pnlPts.textContent   = `${sign}${pts.toFixed(0)} 點`;
  pnlPts.className     = cls;
  pnlMoney.className   = `pnl-money ${cls}`;
  pnlMoney.textContent = ptVal ? `(${sign}${(pts * ptVal).toLocaleString()} 元)` : '';
}

function calcStopLoss() {
  const entry    = getNum('inp-entry');
  const bullBig  = getNum('inp-bull-big');
  const bearBig  = getNum('inp-bear-big');
  const bullHorn = getNum('inp-bull-horn');
  const bearClaw = getNum('inp-bear-claw');
  const purple   = getNum('inp-purple');
  const ptVal    = parseFloat(document.getElementById('inp-point-val')?.value) || 0;

  const fmt = (pts) => (entry && pts) ? fmtStop(pts, ptVal) : '--';

  // 做多（紅燈）：紫線需小於買進才顯示
  setEl('sl-long-purple', (entry && purple && purple < entry) ? fmt(entry - purple) : '--');
  setEl('sl-long-claw',   fmt(entry - bearClaw));

  // 區間盤整（黃燈）：以買進價格計算距離
  setEl('sl-range-bear', fmt(entry - bearBig));   // 低接牛：守大熊
  setEl('sl-range-bull', fmt(entry - bullBig));   // 高空熊：守大牛

  // 做空（綠燈）：紫線需大於賣出才顯示
  setEl('sl-short-purple', (entry && purple && purple > entry) ? fmt(purple - entry) : '--');
  setEl('sl-short-horn',   fmt(bullHorn - entry));

  // 紫爆（恆亮）
  setEl('sl-zibao-bear',   fmt(purple - bearBig));  // 態度紅：紫線 - 大熊
  setEl('sl-zibao-purple', fmt(entry  - purple));   // 態度綠：買進/賣出 - 紫線
}

// ══════════════════════════════════════════════════════════════
// ── 加權槓桿計算機 ────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════

function initLeverage() {
  LEVERAGE_INPUTS.forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => { calcLeverage(); saveState(); });
  });
  calcLeverage();
}

function calcLeverage() {
  const taiex     = parseFloat(document.getElementById('lev-taiex')?.value)      || 0;
  const marginTx  = parseFloat(document.getElementById('lev-margin-tx')?.value)  || 0;
  const marginMtx = parseFloat(document.getElementById('lev-margin-mtx')?.value) || 0;
  const marginMxf = parseFloat(document.getElementById('lev-margin-mxf')?.value) || 0;
  const target    = parseFloat(document.getElementById('lev-target')?.value)      || 0;

  const s = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  // 單口槓桿
  const ratioTx  = taiex && marginTx  ? taiex * 200 / marginTx  : null;
  const ratioMtx = taiex && marginMtx ? taiex * 50  / marginMtx : null;
  const ratioMxf = taiex && marginMxf ? taiex * 10  / marginMxf : null;
  s('lev-ratio-tx',  ratioTx  ? ratioTx.toFixed(1)  : '--');
  s('lev-ratio-mtx', ratioMtx ? ratioMtx.toFixed(1) : '--');
  s('lev-ratio-mxf', ratioMxf ? ratioMxf.toFixed(1) : '--');

  // 單口槓桿 ÷ 目標槓桿 = 所需口數（降槓桿：目標越低 → 口數越多 → 保證金越高）
  const calc = (ratio, margin) => {
    if (!ratio || !margin) return { lots: '--', oneLot: '', cap: '--' };
    const lots   = ratio / target;
    const lotsUp = Math.ceil(lots);
    return {
      lots:   `必須 ${lotsUp} 口`,
      oneLot: `做一口 → ${ratio.toFixed(1)}倍`,
      cap:    (lotsUp * margin).toLocaleString() + ' 元'
    };
  };

  if (target) {
    const tx  = calc(ratioTx,  marginTx);
    const mtx = calc(ratioMtx, marginMtx);
    const mxf = calc(ratioMxf, marginMxf);

    s('lev-lots-tx',  tx.lots);  s('lev-one-tx',  tx.oneLot);  s('lev-capital-tx',  tx.cap);
    s('lev-lots-mtx', mtx.lots); s('lev-one-mtx', mtx.oneLot); s('lev-capital-mtx', mtx.cap);
    s('lev-lots-mxf', mxf.lots); s('lev-one-mxf', mxf.oneLot); s('lev-capital-mxf', mxf.cap);
  } else {
    ['lev-lots-tx','lev-lots-mtx','lev-lots-mxf',
     'lev-capital-tx','lev-capital-mtx','lev-capital-mxf'].forEach(id => s(id, '--'));
    ['lev-one-tx','lev-one-mtx','lev-one-mxf'].forEach(id => s(id, ''));
  }
}

// ── 啟動 ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  connectWS();
  loadPrices();
  setInterval(loadPrices, 30 * 1000);
  loadNews();
  setInterval(loadNews, 5 * 60 * 1000);
  loadPlaylist();
  loadFng();
  setInterval(loadFng, 10 * 60 * 1000);
  loadState();
  initStrategy();
  initLeverage();
});
