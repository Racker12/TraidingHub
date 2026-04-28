const sessionTimes = [
  { name: 'Sydney', open: 23, close: 8 },
  { name: 'Asia', open: 2, close: 11 },
  { name: 'London', open: 9, close: 18 },
  { name: 'New York', open: 13.5, close: 20 }
];

let widget;
let chartIsReady = false;

function updateDeviceLayoutClass() {
  const isMobile = window.matchMedia('(max-width: 760px), (pointer: coarse)').matches;
  document.body.classList.toggle('is-mobile-layout', isMobile);
  document.body.classList.toggle('is-desktop-layout', !isMobile);
}

function updateSessions() {
  const offsetMinutes = new Date().getTimezoneOffset();
  const offsetHours = -offsetMinutes / 60;

  const now = new Date();
  const localHour = now.getUTCHours() + offsetHours;
  const localMin = now.getUTCMinutes();
  const localTime = (localHour + localMin / 60 + 24) % 24;

  const sessionsDiv = document.getElementById('sessions');
  if (!sessionsDiv) return;
  sessionsDiv.innerHTML = '';

  sessionTimes.forEach(session => {
    const open = session.open;
    const close = session.close;

    let statusColor = '#ef4444';
    let statusText = 'geschlossen';

    const timeToOpen = ((open - localTime + 24) % 24);
    const timeToClose = ((close - localTime + 24) % 24);

    const isOpen = open < close
      ? localTime >= open && localTime < close
      : localTime >= open || localTime < close;

    if (isOpen) {
      statusColor = timeToClose <= 1 ? '#f59e0b' : '#22c55e';
      statusText = timeToClose <= 1 ? 'schließt bald' : 'offen';
    } else {
      statusColor = timeToOpen <= 1 ? '#eab308' : '#ef4444';
      statusText = timeToOpen <= 1 ? 'öffnet bald' : 'geschlossen';
    }

    const span = document.createElement('span');
    span.className = 'session';
    span.title = `${session.name}: ${statusText}`;
    span.innerHTML = `
      <div class="status" style="background-color: ${statusColor}; color: ${statusColor}"></div>
      ${session.name}
    `;
    sessionsDiv.appendChild(span);
  });
}

function updateLocalTime() {
  const now = new Date();
  const hours = now.getHours().toString().padStart(2, '0');
  const minutes = now.getMinutes().toString().padStart(2, '0');
  const seconds = now.getSeconds().toString().padStart(2, '0');
  const timeString = `${hours}:${minutes}:${seconds}`;

  const timeDiv = document.getElementById('localTime');
  if (timeDiv) {
    timeDiv.textContent = timeString;
  }
}

function activateScreen(id) {
  document.body.classList.add('is-switching');

  document.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));

  const nextScreen = document.getElementById(id);
  if (nextScreen) {
    void nextScreen.offsetWidth;
    nextScreen.classList.add('active');
  }

  if (id === 'tradingApp') {
    window.setTimeout(() => initTradingViewChart(), 120);
  }

  if (id === 'seasonalityApp') {
    window.setTimeout(() => loadSeasonalityData(), 120);
  }

  window.setTimeout(() => {
    document.body.classList.remove('is-switching');
  }, 820);
}

function openApp(id) {
  activateScreen(id);
}

function goHome() {
  activateScreen('home');
}

function calculateSL() {
  const slValue = parseFloat(document.getElementById('slValue').value);
  const distance = parseFloat(document.getElementById('slDistance').value);
  const slType = document.getElementById('slType').value;
  const currency = document.getElementById('slCurrency').value;
  const resultDiv = document.getElementById('result');

  if (!resultDiv) return;

  if (isNaN(slValue) || isNaN(distance) || slValue <= 0 || distance <= 0) {
    resultDiv.textContent = 'Bitte SL-Betrag und SL-Abstand größer als 0 eingeben.';
    return;
  }

  const pipValuePerLot = 10;
  const distanceInPips = slType === 'percent' ? distance * 100 : distance;
  const riskPerLot = pipValuePerLot * distanceInPips;
  const lots = slValue / riskPerLot;

  resultDiv.innerHTML = `Empfohlene Positionsgröße: <strong>${lots.toFixed(2)} Lots</strong><span> Risiko: ${slValue.toFixed(2)} ${currency} bei ca. ${distanceInPips.toFixed(1)} Pips Abstand.</span>`;
}

function getSelectedChartSymbol() {
  const chartSelect = document.getElementById('chartPair');
  return chartSelect ? chartSelect.value : 'OANDA:EURUSD';
}

function setChartStatus(message) {
  const status = document.getElementById('chartStatus');
  if (status) status.textContent = message || '';
}

function createTradingViewWidget(symbol) {
  if (typeof TradingView === 'undefined' || !TradingView.widget) {
    setChartStatus('TradingView konnte nicht geladen werden. Prüfe deine Internetverbindung oder öffne die Seite über einen lokalen Server.');
    return;
  }

  if (widget && typeof widget.remove === 'function') {
    widget.remove();
  }

  widget = new TradingView.widget({
    container_id: 'tradingview_chart',
    autosize: true,
    symbol: symbol,
    interval: '30',
    timezone: 'Etc/UTC',
    theme: 'dark',
    style: '1',
    locale: 'de',
    toolbar_bg: '#1e1e1e',
    enable_publishing: false,
    hide_top_toolbar: false,
    hide_legend: false,
    save_image: false,
    studies: [],
  });

  chartIsReady = true;
  setChartStatus('');
}

function initTradingViewChart() {
  createTradingViewWidget(getSelectedChartSymbol());
}

function updateChartSymbol() {
  initTradingViewChart();
}

function calculateSignalCheck() {
  const trend = document.getElementById('signalTrend').value;
  const rsi = document.getElementById('signalRsi').value;
  const macd = document.getElementById('signalMacd').value;
  const news = document.getElementById('signalNews').value;
  const result = document.getElementById('signalResult');

  let score = 0;
  [trend, rsi, macd].forEach(value => {
    if (value === 'bullish') score += 1;
    if (value === 'bearish') score -= 1;
  });

  let bias = 'Neutral / abwarten';
  let detail = 'Die Signale sind gemischt. Besser auf klarere Struktur oder besseren Preis warten.';

  if (news === 'danger') {
    bias = 'Kein Trade / News-Risiko';
    detail = 'High-Impact News können Spreads und Volatilität stark erhöhen. Erst nach der News neu prüfen.';
  } else if (score >= 2) {
    bias = 'Long-Bias';
    detail = 'Mehrere Faktoren sprechen eher für Long. Trotzdem Entry, Stop Loss und R:R separat prüfen.';
  } else if (score <= -2) {
    bias = 'Short-Bias';
    detail = 'Mehrere Faktoren sprechen eher für Short. Trotzdem Entry, Stop Loss und R:R separat prüfen.';
  }

  if (news === 'medium' && bias !== 'Neutral / abwarten') {
    detail += ' Achtung: mittleres News-Risiko einplanen.';
  }

  result.innerHTML = `<strong>${bias}</strong><span>${detail}</span><small>Hinweis: Das ist eine technische Checkliste, keine Finanzberatung und keine Garantie.</small>`;
}


const SEASONALITY_FILES = [
  'ABEA10.txt','ABEA15.txt','ABEA5.txt',
  'AMZ10.txt','AMZ5.txt',
  'APC10.txt','APC15.txt','APC5.txt',
  'BTC10.txt','BTC15.txt','BTC5.txt',
  'BYD5.txt','BYD7.txt',
  'ETH10.txt','ETH5.txt',
  'EURUSD10.txt','EURUSD5.txt',
  'GBPUSD10.txt','GBPUSD5.txt',
  'MSF10.txt','MSF15.txt',
  'NASDAQ10.txt','NASDAQ15.txt','NASDAQ5.txt',
  'NVD5.txt','NVD8.txt',
  'PL10.txt','PL15.txt','PL25.txt','PL5.txt',
  'RheinmetallAG10.txt','RheinmetallAG5.txt',
  'SI10.txt','SI15.txt','SI25.txt','SI5.txt',
  'SOL5.txt',
  'Tesla10.txt','Tesla5.txt',
  'USDJPY10.txt','USDJPY5.txt',
  'VWCE5.txt',
  'XAU10.txt','XAU15.txt','XAU25.txt','XAU5.txt'
 ];

const ASSET_DISPLAY_NAMES = {
  ABEA: 'Alphabet A',
  AMZ: 'Amazon',
  APC: 'Apple',
  BTC: 'Bitcoin',
  BYD: 'BYD',
  ETH: 'Ethereum',
  EURUSD: 'Euro / US-Dollar',
  GBPUSD: 'Britisches Pfund / US-Dollar',
  MSF: 'Microsoft',
  NASDAQ: 'Nasdaq 100',
  NVD: 'Nvidia',
  PL: 'Palantir',
  RheinmetallAG: 'Rheinmetall AG',
  SI: 'Silber',
  SOL: 'Solana',
  Tesla: 'Tesla',
  USDJPY: 'US-Dollar / Yen',
  VWCE: 'Vanguard FTSE All-World',
  XAU: 'Gold'
};

function getAssetDisplayName(asset) {
  return ASSET_DISPLAY_NAMES[asset] || asset;
}

let sellRowCounter = 0;
let seasonalityData = null;

function numberValue(id) {
  const el = document.getElementById(id);
  const value = el ? parseFloat(String(el.value).replace(',', '.')) : NaN;
  return Number.isFinite(value) ? value : 0;
}

function formatMoney(value) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 }).format(value || 0);
}

function formatQty(value) {
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 6 }).format(value || 0);
}

function formatPct(value) {
  const sign = value > 0 ? '+' : '';
  return `${sign}${Number(value || 0).toFixed(2)}%`;
}

function syncOrderBuyMode() {
  const mode = document.getElementById('orderBuyMode')?.value || 'quantity';
  const quantityWrap = document.getElementById('orderQuantityWrap');
  const investWrap = document.getElementById('orderInvestWrap');
  const portfolioWrap = document.getElementById('orderPortfolioWrap');
  if (quantityWrap) quantityWrap.style.opacity = mode === 'quantity' ? '1' : '0.45';
  if (investWrap) investWrap.style.opacity = mode === 'invest' ? '1' : '0.45';
  if (portfolioWrap) portfolioWrap.style.opacity = mode === 'portfolio' ? '1' : '0.45';
}

function setOrderQuantity(qty) {
  const mode = document.getElementById('orderBuyMode');
  const quantity = document.getElementById('orderQuantity');
  if (mode) mode.value = 'quantity';
  if (quantity) quantity.value = qty;
  syncOrderBuyMode();
  calculateOrder();
}

function addSellRow(mode = 'quantity', value = '', price = '') {
  const container = document.getElementById('sellRows');
  if (!container) return;
  sellRowCounter += 1;
  const row = document.createElement('div');
  row.className = 'sell-row';
  row.dataset.sellRow = String(sellRowCounter);
  row.innerHTML = `
    <label>Verkauf über
      <select class="sell-mode" onchange="calculateOrder()">
        <option value="quantity" ${mode === 'quantity' ? 'selected' : ''}>Stückzahl</option>
        <option value="percent" ${mode === 'percent' ? 'selected' : ''}>% der Startposition</option>
        <option value="eur" ${mode === 'eur' ? 'selected' : ''}>EUR-Betrag</option>
      </select>
    </label>
    <label>Wert
      <input class="sell-value" type="number" min="0" step="0.0001" value="${value}" placeholder="z.B. 50" oninput="calculateOrder()" />
    </label>
    <label>Verkaufspreis
      <input class="sell-price" type="number" min="0" step="0.0001" value="${price}" placeholder="z.B. 125" oninput="calculateOrder()" />
    </label>
    <button class="icon-btn" title="Verkauf entfernen" onclick="removeSellRow(this)">×</button>
  `;
  container.appendChild(row);
  calculateOrder();
}

function removeSellRow(button) {
  const row = button.closest('.sell-row');
  if (row) row.remove();
  calculateOrder();
}

function getOrderQuantity() {
  const buyPrice = numberValue('orderBuyPrice');
  const mode = document.getElementById('orderBuyMode')?.value || 'quantity';
  if (buyPrice <= 0) return 0;
  if (mode === 'quantity') return numberValue('orderQuantity');
  if (mode === 'invest') return numberValue('orderInvest') / buyPrice;
  const portfolio = numberValue('orderPortfolio');
  const percent = numberValue('orderPortfolioPercent');
  return (portfolio * (percent / 100)) / buyPrice;
}

function calculateOrder() {
  const result = document.getElementById('orderResult');
  const detail = document.getElementById('orderDetail');
  if (!result || !detail) return;

  const asset = document.getElementById('orderAsset')?.value.trim() || 'Order';
  const buyPrice = numberValue('orderBuyPrice');
  const buyFeePct = numberValue('orderBuyFee') / 100;
  const sellFeePct = numberValue('orderSellFee') / 100;
  const quantity = getOrderQuantity();

  if (buyPrice <= 0 || quantity <= 0) {
    result.innerHTML = '';
    detail.innerHTML = '<strong>Order bereit</strong><span>Gib Kaufpreis und Kaufmenge / Investment ein, dann berechne ich die komplette Position.</span>';
    return;
  }

  const buyGross = quantity * buyPrice;
  const buyFee = buyGross * buyFeePct;
  const buyTotal = buyGross + buyFee;
  let remainingQty = quantity;
  let realizedGross = 0;
  let sellFees = 0;
  let soldQty = 0;
  const rows = Array.from(document.querySelectorAll('.sell-row'));
  const sellDetails = [];

  rows.forEach((row, index) => {
    const mode = row.querySelector('.sell-mode')?.value || 'quantity';
    const value = parseFloat(row.querySelector('.sell-value')?.value || '0') || 0;
    const price = parseFloat(row.querySelector('.sell-price')?.value || '0') || 0;
    if (value <= 0 || price <= 0 || remainingQty <= 0) return;

    let qty = 0;
    if (mode === 'quantity') qty = value;
    if (mode === 'percent') qty = quantity * (value / 100);
    if (mode === 'eur') qty = value / price;
    qty = Math.min(qty, remainingQty);

    const gross = qty * price;
    const fee = gross * sellFeePct;
    const costBasis = qty * buyPrice;
    const pnl = gross - fee - costBasis;

    remainingQty -= qty;
    soldQty += qty;
    realizedGross += gross;
    sellFees += fee;
    sellDetails.push(`#${index + 1}: ${formatQty(qty)} Stk. @ ${formatMoney(price)} = ${formatMoney(gross - fee)} netto | P/L ${formatMoney(pnl)}`);
  });

  const currentPrice = numberValue('orderCurrentPrice');
  const openPnl = currentPrice > 0 ? remainingQty * (currentPrice - buyPrice) : 0;
  const realizedPnl = realizedGross - sellFees - (soldQty * buyPrice) - (buyFee * (soldQty / quantity));
  const totalPnl = realizedPnl + openPnl - (currentPrice > 0 ? buyFee * (remainingQty / quantity) : 0);
  const roi = buyTotal > 0 ? (totalPnl / buyTotal) * 100 : 0;

  result.innerHTML = `
    <div class="stat-card"><span>Startposition</span><strong>${formatQty(quantity)}</strong></div>
    <div class="stat-card"><span>Invest inkl. Kaufgebühr</span><strong>${formatMoney(buyTotal)}</strong></div>
    <div class="stat-card"><span>Verkauft</span><strong>${formatQty(soldQty)}</strong></div>
    <div class="stat-card"><span>Restposition</span><strong>${formatQty(remainingQty)}</strong></div>
    <div class="stat-card"><span>Gesamt P/L</span><strong>${formatMoney(totalPnl)}</strong></div>
    <div class="stat-card"><span>ROI</span><strong>${roi.toFixed(2)}%</strong></div>
  `;

  detail.innerHTML = `
    <strong>${escapeHtml(asset)} Order-Übersicht</strong>
    <span>Kauf: ${formatQty(quantity)} Stk. × ${formatMoney(buyPrice)} = ${formatMoney(buyGross)} brutto, Kaufgebühr ${formatMoney(buyFee)}.</span>
    <span>Realisierter P/L: ${formatMoney(realizedPnl)}. Offener P/L: ${formatMoney(openPnl)}. Verkaufsgebühren: ${formatMoney(sellFees)}.</span>
    <small>${sellDetails.length ? sellDetails.map(escapeHtml).join('<br>') : 'Noch keine Teilverkäufe eingetragen. Du kannst mehrere Exits hinzufügen und je Exit Stück, %, oder EUR-Betrag nutzen.'}</small>
  `;
}

function parseSeasonalityFileName(file) {
  const clean = file.replace(/\.txt$/i, '');
  const match = clean.match(/^(.*?)(\d+)$/);
  return { file, asset: match ? match[1] : clean, years: match ? Number(match[2]) : 0 };
}

function getSeasonalityMap() {
  return SEASONALITY_FILES.map(parseSeasonalityFileName).reduce((map, item) => {
    if (!map.has(item.asset)) map.set(item.asset, []);
    map.get(item.asset).push(item);
    return map;
  }, new Map());
}

function populateSeasonalityControls() {
  const assetSelect = document.getElementById('seasonalityAsset');
  if (!assetSelect) return;
  const map = getSeasonalityMap();
  const assets = Array.from(map.keys()).sort((a, b) => a.localeCompare(b, 'de'));
  assetSelect.innerHTML = assets.map(asset => `<option value="${asset}">${escapeHtml(getAssetDisplayName(asset))} (${escapeHtml(asset)})</option>`).join('');
  assetSelect.value = assets.includes('BTC') ? 'BTC' : assets[0];
  populateSeasonalityVariants();
}

function populateSeasonalityVariants() {
  const asset = document.getElementById('seasonalityAsset')?.value;
  const variantSelect = document.getElementById('seasonalityVariant');
  if (!asset || !variantSelect) return;
  const map = getSeasonalityMap();
  const variants = (map.get(asset) || []).sort((a, b) => a.years - b.years);
  variantSelect.innerHTML = variants.map(item => `<option value="${item.file}">${item.years} Jahre</option>`).join('');
  const ten = variants.find(item => item.years === 10);
  variantSelect.value = (ten || variants[variants.length - 1] || variants[0])?.file || '';
}

function onSeasonalityAssetChange() {
  populateSeasonalityVariants();
  loadSeasonalityData();
}

function setSeasonalityStatus(message, type = '') {
  const el = document.getElementById('seasonalityStatus');
  if (!el) return;
  el.textContent = message || '';
  el.dataset.type = type;
}

async function fetchSeasonalityFile(file) {
  const candidates = [`Data/${file}`, `data/${file}`];
  let lastError = null;
  for (const url of candidates) {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`${url} nicht gefunden (HTTP ${res.status})`);
      const text = await res.text();
      return { text, url };
    } catch (error) { lastError = error; }
  }
  throw lastError || new Error('Datei konnte nicht geladen werden.');
}

async function loadSeasonalityData() {
  const file = document.getElementById('seasonalityVariant')?.value || 'BTC10.txt';
  if (!file) return;
  setSeasonalityStatus(`Lade ${file} aus Data/ ...`);
  if (window.location.protocol === 'file:') {
    seasonalityData = null;
    clearSeasonalityViews('Lokaler Doppelklick-Modus blockiert Data-Dateien. Starte die mitgelieferte start-local-server.bat oder lade es auf GitHub Pages hoch.');
    setSeasonalityStatus('Browser blockiert file://. Nutze start-local-server.bat im Projektordner.', 'error');
    return;
  }
  try {
    const loaded = await fetchSeasonalityFile(file);
    const json = JSON.parse(loaded.text.replace(/^\uFEFF/, '').trim());
    seasonalityData = json;
    seasonalityData.__file = file;
    seasonalityData.__url = loaded.url;
    setSeasonalityStatus(`Geladen: ${loaded.url}`, 'ok');
    renderSeasonality();
  } catch (error) {
    seasonalityData = null;
    clearSeasonalityViews(`${file} konnte nicht geladen werden. Prüfe, ob die Datei exakt so im Ordner Data liegt.`);
    setSeasonalityStatus(`Fehler: ${error.message}`, 'error');
  }
}

function renderSeasonality() {
  if (!seasonalityData) return;
  const labels = seasonalityData.chart?.labels || [];
  const values = seasonalityData.chart?.values || [];
  const monthly = seasonalityData.monthlyChartData || { labels: [], values: [] };
  const weekdays = seasonalityData.weekdayChartData || { labels: [], values: [] };
  const meta = seasonalityData.metrics || {};
  const title = document.getElementById('seasonalityTitle');
  const metaEl = document.getElementById('seasonalityMeta');
  if (title) { const selectedAsset = document.getElementById('seasonalityAsset')?.value || ''; const years = parseSeasonalityFileName(seasonalityData.__file || '').years; title.textContent = `${getAssetDisplayName(selectedAsset)} ${years ? years + ' Jahre' : ''}`.trim() || 'Jahresverlauf'; }
  if (metaEl) metaEl.innerHTML = `<span>${escapeHtml(meta.start || '-')} → ${escapeHtml(meta.end || '-')}</span><strong>${escapeHtml(String(meta.count || values.length))} Datenpunkte</strong>`;
  drawSeasonalityCurve(labels, values);
  renderMonthlyOverview(monthly.labels || [], monthly.values || []);
  renderWeekdayOverview(weekdays.labels || [], weekdays.values || []);
  renderSeasonalityStats(labels, values, monthly.labels || [], monthly.values || []);
}

function clearSeasonalityViews(message) {
  drawEmptySeasonality(message || 'Noch keine Daten geladen.');
  const monthly = document.getElementById('monthlyOverview');
  const weekdays = document.getElementById('weekdayOverview');
  const stats = document.getElementById('seasonalityStats');
  const insight = document.getElementById('seasonalityInsight');
  const meta = document.getElementById('seasonalityMeta');
  if (monthly) monthly.innerHTML = '';
  if (weekdays) weekdays.innerHTML = '';
  if (stats) stats.innerHTML = '';
  if (insight) insight.innerHTML = '<strong>Hinweis</strong><span>' + escapeHtml(message || '') + '</span>';
  if (meta) meta.innerHTML = '';
}

function drawEmptySeasonality(message) {
  const canvas = document.getElementById('seasonalityCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'rgba(245,247,251,0.88)';
  ctx.font = '700 21px Inter, sans-serif';
  wrapCanvasText(ctx, message, 44, 190, w - 88, 30);
}

function drawSeasonalityCurve(labels, values) {
  const canvas = document.getElementById('seasonalityCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const padL = 58, padR = 34, padT = 32, padB = 48;
  ctx.clearRect(0, 0, w, h);
  if (!values.length) return drawEmptySeasonality('Keine Jahreskurve in der Datei gefunden.');
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const zeroY = h - padB - ((100 - min) / range) * (h - padT - padB);
  ctx.strokeStyle = 'rgba(255,255,255,0.11)';
  ctx.lineWidth = 1;
  ctx.fillStyle = 'rgba(214,222,235,0.72)';
  ctx.font = '600 12px Inter, sans-serif';
  for (let i = 0; i <= 4; i++) {
    const y = padT + ((h - padT - padB) / 4) * i;
    const value = max - (range / 4) * i;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    ctx.fillText(value.toFixed(1), 8, y + 4);
  }
  if (zeroY >= padT && zeroY <= h - padB) {
    ctx.strokeStyle = 'rgba(255,255,255,0.22)'; ctx.setLineDash([6, 6]);
    ctx.beginPath(); ctx.moveTo(padL, zeroY); ctx.lineTo(w - padR, zeroY); ctx.stroke(); ctx.setLineDash([]);
  }
  const xStep = (w - padL - padR) / Math.max(values.length - 1, 1);
  const points = values.map((value, i) => ({ x: padL + i * xStep, y: h - padB - ((value - min) / range) * (h - padT - padB) }));
  const gradient = ctx.createLinearGradient(0, padT, 0, h - padB);
  gradient.addColorStop(0, 'rgba(125, 211, 252, 0.30)'); gradient.addColorStop(1, 'rgba(167, 139, 250, 0.03)');
  ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.lineTo(points.at(-1).x, h - padB); ctx.lineTo(points[0].x, h - padB); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
  ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.strokeStyle = '#7dd3fc'; ctx.lineWidth = 3.5; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
  const monthTicks = ['01-01','02-01','03-01','04-01','05-01','06-01','07-01','08-01','09-01','10-01','11-01','12-01'];
  const monthNames = ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'];
  ctx.fillStyle = 'rgba(214,222,235,0.70)'; ctx.font = '700 12px Inter, sans-serif';
  monthTicks.forEach((tick, i) => { const idx = labels.indexOf(tick); const x = idx >= 0 ? padL + idx * xStep : padL + i * ((w - padL - padR) / 12); ctx.fillText(monthNames[i], x - 10, h - 17); });
}

function renderMonthlyOverview(labels, values) {
  const el = document.getElementById('monthlyOverview');
  if (!el) return;
  if (!values.length) { el.innerHTML = '<p class="helper-text">Keine Monatsdaten vorhanden.</p>'; return; }
  const maxAbs = Math.max(...values.map(v => Math.abs(Number(v) || 0)), 1);
  el.innerHTML = labels.map((label, index) => {
    const value = Number(values[index]) || 0;
    const width = Math.max(8, Math.abs(value) / maxAbs * 100);
    const cls = value >= 0 ? 'positive' : 'negative';
    return `<div class="seasonality-bar-row ${cls}"><div class="seasonality-bar-label">${escapeHtml(label)}</div><div class="seasonality-bar-track"><span style="width:${width}%"></span></div><strong>${formatPct(value)}</strong></div>`;
  }).join('');
}

function renderWeekdayOverview(labels, values) {
  const el = document.getElementById('weekdayOverview');
  if (!el) return;
  if (!values.length) { el.innerHTML = '<p class="helper-text">Keine Wochentagsdaten vorhanden.</p>'; return; }
  const maxAbs = Math.max(...values.map(v => Math.abs(Number(v) || 0)), 1);
  el.innerHTML = labels.map((label, index) => {
    const value = Number(values[index]) || 0;
    const cls = value >= 0 ? 'positive' : 'negative';
    const height = Math.max(10, Math.abs(value) / maxAbs * 92);
    return `<div class="weekday-item ${cls}"><div class="weekday-bar"><span style="height:${height}%"></span></div><strong>${formatPct(value)}</strong><span>${escapeHtml(label)}</span></div>`;
  }).join('');
}

function renderSeasonalityStats(labels, values, monthLabels, monthValues) {
  const stats = document.getElementById('seasonalityStats');
  const insight = document.getElementById('seasonalityInsight');
  if (!stats || !insight || !values.length) return;
  const start = Number(values[0]) || 0, end = Number(values.at(-1)) || 0, change = end - start;
  const max = Math.max(...values), min = Math.min(...values);
  const bestIndex = values.indexOf(max), worstIndex = values.indexOf(min);
  const bestMonthIndex = monthValues.length ? monthValues.indexOf(Math.max(...monthValues)) : -1;
  const worstMonthIndex = monthValues.length ? monthValues.indexOf(Math.min(...monthValues)) : -1;
  stats.innerHTML = `<div><span>Jahresende</span><strong>${end.toFixed(2)}</strong></div><div><span>Veränderung</span><strong>${change >= 0 ? '+' : ''}${change.toFixed(2)}</strong></div><div><span>Stärkster Punkt</span><strong>${escapeHtml(labels[bestIndex] || '-')}</strong></div><div><span>Schwächster Punkt</span><strong>${escapeHtml(labels[worstIndex] || '-')}</strong></div>`;
  insight.innerHTML = `<strong>Seasonality-Auswertung</strong><span>Stärkster Monat: ${escapeHtml(monthLabels[bestMonthIndex] || '-')} (${bestMonthIndex >= 0 ? formatPct(monthValues[bestMonthIndex]) : '-'}). Schwächster Monat: ${escapeHtml(monthLabels[worstMonthIndex] || '-')} (${worstMonthIndex >= 0 ? formatPct(monthValues[worstMonthIndex]) : '-'}).</span><small>Historische Saisonalität ist nur Kontext und keine Kauf- oder Verkaufsempfehlung.</small>`;
}

function wrapCanvasText(ctx, text, x, y, maxWidth, lineHeight) {
  const words = String(text || '').split(' ');
  let line = '';
  words.forEach(word => {
    const test = line ? line + ' ' + word : word;
    if (ctx.measureText(test).width > maxWidth && line) { ctx.fillText(line, x, y); line = word; y += lineHeight; } else { line = test; }
  });
  if (line) ctx.fillText(line, x, y);
}

function escapeHtml(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

const TELEGRAM_STORAGE_KEY = 'forexToolsTelegramSettings';

function getTelegramSettings() {
  try {
    return JSON.parse(localStorage.getItem(TELEGRAM_STORAGE_KEY) || '{}');
  } catch (error) {
    return {};
  }
}

function setTelegramStatus(message, type = '') {
  const el = document.getElementById('telegramSettingsStatus');
  if (!el) return;
  el.textContent = message || '';
  el.dataset.type = type;
}

function loadTelegramSettings() {
  const settings = getTelegramSettings();
  const token = document.getElementById('telegramBotToken');
  const chatId = document.getElementById('telegramChatId');
  const name = document.getElementById('telegramName');
  if (token) token.value = settings.token || '';
  if (chatId) chatId.value = settings.chatId || '';
  if (name) name.value = settings.name || '';
  if (settings.token || settings.chatId) setTelegramStatus('Telegram Daten sind auf diesem Gerät gespeichert.', 'ok');
}

function saveTelegramSettings() {
  const token = document.getElementById('telegramBotToken')?.value.trim() || '';
  const chatId = document.getElementById('telegramChatId')?.value.trim() || '';
  const name = document.getElementById('telegramName')?.value.trim() || '';
  if (!token || !chatId) {
    setTelegramStatus('Bitte Bot API Token und Chat-ID eintragen. Die Daten werden nur lokal auf diesem Gerät gespeichert.', 'error');
    return;
  }
  localStorage.setItem(TELEGRAM_STORAGE_KEY, JSON.stringify({ token, chatId, name, savedAt: new Date().toISOString() }));
  setTelegramStatus('Gespeichert ✓ Nur auf diesem Browser/Gerät.', 'ok');
}

function clearTelegramSettings() {
  localStorage.removeItem(TELEGRAM_STORAGE_KEY);
  ['telegramBotToken', 'telegramChatId', 'telegramName'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  setTelegramStatus('Gespeicherte Telegram Daten wurden auf diesem Gerät gelöscht.', 'ok');
}

function toggleSecretVisibility(inputId, button) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const show = input.type === 'password';
  input.type = show ? 'text' : 'password';
  if (button) button.textContent = show ? '🙈' : '👁';
}

function getTelegramInputSettings() {
  const token = document.getElementById('telegramBotToken')?.value.trim() || getTelegramSettings().token || '';
  const chatId = document.getElementById('telegramChatId')?.value.trim() || getTelegramSettings().chatId || '';
  return { token, chatId };
}

async function findTelegramChatId() {
  const token = document.getElementById('telegramBotToken')?.value.trim() || getTelegramSettings().token || '';
  if (!token) {
    setTelegramStatus('Trage zuerst den Bot API Token ein. Danach dem Bot auf Telegram einmal eine Nachricht schreiben und erneut suchen.', 'error');
    return;
  }
  setTelegramStatus('Suche letzte Telegram Chats ...');
  try {
    const response = await fetch(`https://api.telegram.org/bot${encodeURIComponent(token)}/getUpdates`);
    const data = await response.json();
    if (!data.ok) throw new Error(data.description || 'Telegram API Fehler');
    const updates = data.result || [];
    const message = updates.map(update => update.message || update.edited_message || update.channel_post).filter(Boolean).at(-1);
    const chat = message?.chat;
    if (!chat?.id) {
      setTelegramStatus('Keine Chat-ID gefunden. Öffne Telegram, schreibe deinem Bot einmal eine Nachricht und klicke dann nochmal auf Suchen.', 'error');
      return;
    }
    const chatIdInput = document.getElementById('telegramChatId');
    const nameInput = document.getElementById('telegramName');
    if (chatIdInput) chatIdInput.value = chat.id;
    if (nameInput && !nameInput.value) nameInput.value = [chat.first_name, chat.last_name].filter(Boolean).join(' ') || chat.username || chat.title || '';
    saveTelegramSettings();
    setTelegramStatus(`Chat-ID gefunden und gespeichert: ${chat.id}`, 'ok');
  } catch (error) {
    setTelegramStatus(`Chat-ID konnte nicht gesucht werden: ${error.message}`, 'error');
  }
}

function generateTelegramTemplate() {
  const pair = document.getElementById('telegramPair')?.value.trim() || 'PAIR';
  const setup = document.getElementById('telegramSetup')?.value || 'Setup';
  const direction = document.getElementById('telegramDirection')?.value || 'Watchlist';
  const output = document.getElementById('telegramOutput');
  const text = `📊 ${pair} ${direction}\nSetup: ${setup}\nCheck: Trend + RSI + MACD + News prüfen\nRisk: max. 1% | SL/TP vor Entry festlegen\nZeit: ${new Date().toLocaleString('de-DE')}`;
  if (output) output.textContent = text;
  return text;
}

async function copyTelegramTemplate() {
  const output = document.getElementById('telegramOutput');
  let finalText = output ? output.textContent.trim() : '';
  if (!finalText) finalText = generateTelegramTemplate();
  try {
    await navigator.clipboard.writeText(finalText);
    if (output) output.textContent = `${finalText}\n\nKopiert ✓`;
  } catch (error) {
    alert('Kopieren wurde vom Browser blockiert. Du kannst den Text manuell markieren und kopieren.');
  }
}

async function sendTelegramAlert() {
  const { token, chatId } = getTelegramInputSettings();
  const output = document.getElementById('telegramOutput');
  let text = output ? output.textContent.replace(/\n\nKopiert ✓$/, '').trim() : '';
  if (!text) text = generateTelegramTemplate();
  if (!token || !chatId) {
    setTelegramStatus('Bitte Bot API Token und Chat-ID speichern, bevor du sendest.', 'error');
    return;
  }
  setTelegramStatus('Sende Telegram Alert ...');
  try {
    const response = await fetch(`https://api.telegram.org/bot${encodeURIComponent(token)}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text })
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.description || 'Telegram API Fehler');
    setTelegramStatus('Alert wurde an Telegram gesendet ✓', 'ok');
  } catch (error) {
    setTelegramStatus(`Senden fehlgeschlagen: ${error.message}`, 'error');
  }
}

window.addEventListener('resize', updateDeviceLayoutClass);

window.addEventListener('DOMContentLoaded', () => {
  updateDeviceLayoutClass();
  updateSessions();
  setInterval(updateSessions, 60000);

  updateLocalTime();
  setInterval(updateLocalTime, 1000);

  syncOrderBuyMode();
  addSellRow('percent', 50, '');
  populateSeasonalityControls();
  drawEmptySeasonality('Öffne die Seasonality-App, dann lädt BTC automatisch aus dem Data-Ordner.');
  loadTelegramSettings();
});
