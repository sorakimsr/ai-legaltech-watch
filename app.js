// AI & Legaltech Watch v2.4 — 시계열 시사점 + 7일 추이 차트

const state = {
  data: null,
  history: null,        // strategy_history.json
  sourceHistory: null,  // source_history.json
  view: 'latest',       // latest | top | today | strategy | sources
  // 시사점 sub-state
  strategyPeriod: 'daily',  // daily | weekly | monthly
  strategyKey: null,        // 선택된 날짜·주·월 키
  // 소스 sub-state
  sourcesTab: 'status',     // status | trend
  // 필터
  category: 'all',
  search: '',
  dateFilter: 'all',
  langFilter: 'all',
  // chart instance
  trendChart: null,
};

const CATEGORIES = [
  { id: 'all', label: '전체' },
  { id: 'ai-industry', label: 'AI 산업' },
  { id: 'legaltech', label: '리걸테크' },
  { id: 'papers', label: 'AI 논문' },
  { id: 'product', label: '제품·기능' },
  { id: 'funding', label: '투자·M&A' },
  { id: 'adoption', label: '도입사례' },
  { id: 'domestic', label: '국내' },
  { id: 'policy', label: '정책·규제' },
];

const VIEW_META = {
  latest:    { title: '최신순', hint: '최근 30일 · 발행일 최신순' },
  top:       { title: '중요도 TOP', hint: 'AI 중요도 점수 상위 100개 항목' },
  today:     { title: '오늘 추가됨', hint: '오늘(KST) 신규 수집' },
  strategy:  { title: '전략·기획 시사점', hint: 'Daily/Weekly/Monthly로 LLM 자동 생성' },
  sources:   { title: '소스 현황', hint: '활성·유휴·오류 + 7일 추이' },
};

async function init() {
  try {
    const res = await fetch('./data/news.json?t=' + Date.now());
    state.data = await res.json();
  } catch (e) {
    console.error('news.json 로드 실패:', e);
    state.data = { items: [], strategy: [], sources: [], stats: {} };
  }

  // 보조 데이터 (옵션)
  try {
    const r = await fetch('./data/strategy_history.json?t=' + Date.now());
    state.history = await r.json();
  } catch (e) {
    state.history = { daily: {}, weekly: {}, monthly: {} };
  }
  try {
    const r = await fetch('./data/source_history.json?t=' + Date.now());
    state.sourceHistory = await r.json();
  } catch (e) {
    state.sourceHistory = {};
  }

  renderTopbar();
  renderStats();
  renderCategoryBar();
  renderContent();
  bindEvents();
}

function renderTopbar() {
  const last = state.data.last_updated;
  const el = document.getElementById('last-updated-text');
  if (last) {
    el.textContent = `최근 갱신: ${formatKoreanDate(new Date(last))} · 매일 KST 06:00 자동`;
  }
  const buildInfo = document.getElementById('last-build-info');
  if (state.data.build_count) {
    buildInfo.textContent = `Build #${state.data.build_count} · © 2026`;
  }
}

function renderStats() {
  const row = document.getElementById('stat-row');
  if (state.view === 'strategy' || state.view === 'sources') {
    row.style.display = 'none';
    return;
  }
  row.style.display = 'grid';

  const stats = state.data.stats || {};
  const total = stats.total_items || (state.data.items || []).length;
  const enriched = stats.enriched_items || 0;
  const withRelated = stats.with_related || 0;
  const sources = state.data.sources || [];
  const activeSrc = sources.filter(s => s.status === 'active').length;
  const backend = state.data.llm_backend || 'none';
  const newToday = (state.data.items || []).filter(isNewToday).length;

  const backendLabel = {
    'claude-cli': 'Claude CLI', 'anthropic': 'Anthropic SDK',
    'openai': 'OpenAI SDK', 'none': '비활성',
  }[backend] || backend;

  row.innerHTML = `
    <div class="stat-card accent">
      <span class="stat-label">전체 항목</span>
      <span class="stat-value">${total}</span>
      <span class="stat-hint">최근 30일 수집</span>
    </div>
    <div class="stat-card highlight">
      <span class="stat-label">오늘 신규</span>
      <span class="stat-value">${newToday}</span>
      <span class="stat-hint">today 첫 수집</span>
    </div>
    <div class="stat-card success">
      <span class="stat-label">AI 분석 완료</span>
      <span class="stat-value">${enriched}</span>
      <span class="stat-hint">한국어 요약/시사점</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">유사 뉴스 병합</span>
      <span class="stat-value">${withRelated}</span>
      <span class="stat-hint">중복 자동 그룹화</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">활성 소스</span>
      <span class="stat-value">${activeSrc} / ${sources.length}</span>
      <span class="stat-hint">RSS·arXiv·Naver</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">LLM 백엔드</span>
      <span class="stat-value" style="font-size:16px;">${escapeHtml(backendLabel)}</span>
      <span class="stat-hint">이번 빌드</span>
    </div>
  `;
}

function renderCategoryBar() {
  const bar = document.getElementById('category-bar');
  const label = document.querySelector('.filter-label');
  if (state.view === 'strategy' || state.view === 'sources') {
    bar.style.display = 'none';
    if (label) label.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  if (label) label.style.display = 'block';

  const pool = applyViewFilter(state.data.items || []);
  const counts = {};
  pool.forEach(item => (item.categories || []).forEach(c => counts[c] = (counts[c] || 0) + 1));

  bar.innerHTML = CATEGORIES.map(cat => {
    const cnt = cat.id === 'all' ? pool.length : (counts[cat.id] || 0);
    const active = cat.id === state.category ? 'active' : '';
    return `<button class="cat-chip ${active}" data-category="${cat.id}"><span>${escapeHtml(cat.label)}</span><span class="cat-count">${cnt}</span></button>`;
  }).join('');

  bar.querySelectorAll('.cat-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      state.category = chip.dataset.category;
      renderCategoryBar();
      renderContent();
    });
  });
}

function applyViewFilter(items) {
  let arr = items.slice();
  switch (state.view) {
    case 'latest':
      arr.sort((a, b) => new Date(b.date) - new Date(a.date));
      break;
    case 'top':
      arr.sort((a, b) => (b.score || 0) - (a.score || 0));
      arr = arr.slice(0, 100);
      break;
    case 'today':
      const now = new Date();
      const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      arr = arr.filter(i => new Date(i.first_seen || i.date) >= start);
      arr.sort((a, b) => new Date(b.date) - new Date(a.date));
      break;
  }
  return arr;
}

function renderContent() {
  const newsGrid = document.getElementById('news-grid');
  const stratView = document.getElementById('strategy-view');
  const sourcesView = document.getElementById('sources-view');
  const controlsRow = document.querySelector('.controls-row');
  const filterLabel = document.querySelector('.filter-label');
  const title = document.getElementById('topbar-title');
  const hint = document.getElementById('view-hint');

  newsGrid.classList.add('hidden');
  stratView.classList.add('hidden');
  sourcesView.classList.add('hidden');
  controlsRow.style.display = 'flex';
  if (filterLabel) filterLabel.style.display = 'block';

  const meta = VIEW_META[state.view] || VIEW_META.latest;
  title.textContent = meta.title;
  if (hint) hint.textContent = meta.hint;

  if (state.view === 'strategy') {
    stratView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    renderStrategy();
    renderStats();
    return;
  }
  if (state.view === 'sources') {
    sourcesView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    renderSourcesView();
    renderStats();
    return;
  }

  newsGrid.classList.remove('hidden');
  renderCategoryBar();
  renderStats();

  const filtered = filterItems();
  if (filtered.length === 0) {
    newsGrid.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-title">조건에 맞는 항목이 없습니다</div></div>`;
    return;
  }
  newsGrid.innerHTML = filtered.map(renderCard).join('');
  newsGrid.querySelectorAll('.related-badge').forEach(b => {
    b.addEventListener('click', e => {
      const detail = e.currentTarget.closest('.news-card').querySelector('.related-detail');
      if (detail) detail.classList.toggle('open');
    });
  });
}

function filterItems() {
  let items = applyViewFilter(state.data.items || []);
  if (state.category !== 'all') {
    items = items.filter(i => (i.categories || []).includes(state.category));
  }
  if (state.langFilter !== 'all') {
    items = items.filter(i => i.lang === state.langFilter);
  }
  if (state.dateFilter !== 'all') {
    const cutoff = computeDateCutoff(state.dateFilter);
    items = items.filter(i => new Date(i.date) >= cutoff);
  }
  if (state.search) {
    const q = state.search.toLowerCase();
    items = items.filter(i => {
      const blob = [i.title, i.summary, i.summary_ko, i.insight_ko, i.source, ...(i.categories || [])].filter(Boolean).join(' ').toLowerCase();
      return blob.includes(q);
    });
  }
  return items;
}

function computeDateCutoff(key) {
  const now = new Date();
  const d = new Date(now);
  switch (key) {
    case 'today': d.setHours(0, 0, 0, 0); break;
    case '3days': d.setDate(d.getDate() - 3); break;
    case 'week': d.setDate(d.getDate() - 7); break;
    case 'month': d.setMonth(d.getMonth() - 1); break;
  }
  return d;
}

function renderCard(item) {
  const score = item.score || 0;
  const scoreClass = score >= 80 ? 'high' : score >= 65 ? 'mid' : 'low';
  const scoreLabel = score > 0 ? `중요도 ${score}` : '신규';
  const dateStr = formatKoreanDate(new Date(item.date));
  const sourceInitial = (item.source || '?').charAt(0).toUpperCase();

  const cats = (item.categories || []).slice(0, 2).map(c => {
    const label = (CATEGORIES.find(x => x.id === c) || { label: c }).label;
    return `<span class="card-category cat-${escapeHtml(c)}">${escapeHtml(label)}</span>`;
  }).join('');

  const isEnglish = item.lang === 'en';
  const summaryKo = item.summary_ko;
  const summaryEn = item.summary;
  let summaryHtml = '';
  if (summaryKo) {
    summaryHtml = `<div class="card-summary has-ko">${escapeHtml(summaryKo)}</div>`;
    if (isEnglish && summaryEn) {
      summaryHtml += `<details class="card-original"><summary>원문 요약 보기</summary><div class="card-original-text">${escapeHtml(summaryEn)}</div></details>`;
    }
  } else if (summaryEn) {
    summaryHtml = `<div class="card-summary ${isEnglish ? 'is-en' : ''}">${escapeHtml(summaryEn)}</div>`;
  }

  const insightBlock = item.insight_ko ? `<div class="card-insight"><span class="insight-label">시사점</span>${escapeHtml(item.insight_ko)}</div>` : '';

  const relCount = item.related_count || 0;
  const relBadge = relCount > 0 ? `<span class="related-badge" title="유사 뉴스 ${relCount}건">+${relCount} 매체 ▾</span>` : '';
  const relDetail = relCount > 0 && item.related ? `<div class="related-detail">${item.related.map(r => `<div class="rel-item"><span class="rel-source">${escapeHtml(r.source)}</span><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a></div>`).join('')}</div>` : '';

  const aiBadge = item.llm_enriched ? '<span class="ai-badge">AI 분석</span>' : '';
  const langBadge = isEnglish ? '<span class="lang-badge">EN</span>' : '';
  const newBadge = isNewToday(item) ? '<span class="new-badge">NEW</span>' : '';

  return `
    <article class="news-card">
      ${aiBadge}
      <div class="card-top">
        <div style="display:flex;gap:6px;align-items:center;">
          <span class="score-badge ${scoreClass}">${escapeHtml(scoreLabel)}</span>
          ${newBadge}
        </div>
        <div style="display:flex;gap:6px;align-items:center;">${langBadge}${relBadge}<span class="date-text">${escapeHtml(dateStr)}</span></div>
      </div>
      <div class="card-cats">${cats}</div>
      <h3 class="card-title"><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h3>
      ${summaryHtml}
      ${insightBlock}
      ${relDetail}
      <div class="card-bottom">
        <span class="card-source"><span class="card-source-icon">${escapeHtml(sourceInitial)}</span>${escapeHtml(item.source || '')}</span>
        <div class="card-actions"><a class="icon-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" title="원문">↗</a></div>
      </div>
    </article>
  `;
}

// ========================= 시사점 (시계열) =========================

function getStrategyKeys(period) {
  if (!state.history || !state.history[period]) return [];
  return Object.keys(state.history[period]).sort().reverse();
}

function getCurrentStrategyKey(period) {
  // state.strategyKey가 명시되어 있고 해당 period에 있으면 사용
  const keys = getStrategyKeys(period);
  if (state.strategyKey && keys.includes(state.strategyKey)) {
    return state.strategyKey;
  }
  return keys[0] || null;
}

function renderStrategy() {
  // period 셀렉트
  const select = document.getElementById('strategy-period-select');
  const period = state.strategyPeriod;

  // 탭 active 표시
  document.querySelectorAll('.period-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.period === period);
  });

  const keys = getStrategyKeys(period);

  if (period === 'daily') {
    // Daily는 보통 최신만 보여주지만, 셀렉트로 과거 일자 선택 가능
    select.classList.remove('hidden');
    select.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  } else if (period === 'weekly') {
    select.classList.remove('hidden');
    select.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  } else if (period === 'monthly') {
    select.classList.remove('hidden');
    select.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  }

  const currentKey = getCurrentStrategyKey(period);
  if (currentKey) select.value = currentKey;

  // 카드 렌더
  const root = document.getElementById('strategy-cards');
  let cards = [];
  if (currentKey && state.history && state.history[period]) {
    cards = state.history[period][currentKey] || [];
  }
  // history에 아무것도 없으면 news.json의 strategy로 fallback (daily)
  if (cards.length === 0 && period === 'daily') {
    cards = state.data.strategy || [];
  }

  if (cards.length === 0) {
    root.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎯</div>
        <div class="empty-title">${escapeHtml(period === 'weekly' ? '아직 주간 시사점이 없습니다' : period === 'monthly' ? '아직 월간 시사점이 없습니다' : '시사점이 없습니다')}</div>
        <div class="empty-desc">매일 빌드가 누적되면서 점차 채워집니다.</div>
      </div>
    `;
    return;
  }

  root.innerHTML = cards.map(s => {
    const citations = Array.isArray(s.citations) ? s.citations : [];
    const citationsBlock = citations.length > 0 ? `
      <details class="strategy-citations">
        <summary>근거 ${citations.length}건 ▾</summary>
        <ol class="citation-list">
          ${citations.map(c => `<li><a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.title)}</a><span class="citation-meta">— ${escapeHtml(c.source)} · ${escapeHtml(c.date)}</span></li>`).join('')}
        </ol>
      </details>` : '';
    return `
      <div class="strategy-card">
        <div class="strat-tag">${escapeHtml(s.tag || 'TREND')}</div>
        <h3>${escapeHtml(s.title || '')}</h3>
        <p>${escapeHtml(s.body || '')}</p>
        <div class="strategy-action"><span class="action-label">ACTION</span>${escapeHtml(s.action || '')}</div>
        ${citationsBlock}
      </div>
    `;
  }).join('');
}

// ========================= 소스 현황 (status / trend) =========================

function renderSourcesView() {
  const statusTab = document.getElementById('sources-tab-status');
  const trendTab = document.getElementById('sources-tab-trend');

  // 사이드바 nav-sub active 상태 반영 (이미 bindEvents에서 처리)

  if (state.sourcesTab === 'trend') {
    statusTab.classList.add('hidden');
    trendTab.classList.remove('hidden');
    renderSourceTrend();
  } else {
    statusTab.classList.remove('hidden');
    trendTab.classList.add('hidden');
    renderSourcesStatus();
  }
}

function renderSourcesStatus() {
  const root = document.getElementById('sources-table');
  const sources = state.data.sources || [];
  if (sources.length === 0) {
    root.innerHTML = '<div class="empty-state"><div class="empty-icon">🔗</div><div class="empty-title">소스 정보 없음</div></div>';
    return;
  }
  const byStatus = sources.reduce((a, s) => { a[s.status] = (a[s.status] || 0) + 1; return a; }, {});
  const total = sources.reduce((sum, s) => sum + (s.count || 0), 0);
  const rows = sources.map(s => `
    <tr>
      <td class="src-name">${escapeHtml(s.name)}</td>
      <td><span class="badge-${escapeHtml(s.status)}">${escapeHtml(s.status === 'active' ? 'Active' : s.status === 'error' ? 'Error' : 'Idle')}</span></td>
      <td>${s.count || 0}</td>
      <td style="color:#6b7280;font-size:11px;">${escapeHtml(s.url || '')}</td>
    </tr>
  `).join('');
  root.innerHTML = `
    <div class="sources-table-wrap">
      <h3>소스 현황 (총 ${sources.length}개 · 활성 ${byStatus.active || 0}개 · 수집 ${total}건)</h3>
      <table class="src-table">
        <thead><tr><th>소스</th><th>상태</th><th>이번 빌드</th><th>URL</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderSourceTrend() {
  const history = state.sourceHistory || {};
  const sources = state.data.sources || [];
  // 최근 7일 키 (오늘 포함)
  const today = new Date();
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    days.push(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'));
  }

  // 활성 소스 상위 (수집량 기준 top 8) — 너무 많으면 라인 가독성 떨어짐
  const topSources = sources
    .filter(s => s.status === 'active')
    .sort((a, b) => (b.count || 0) - (a.count || 0))
    .slice(0, 8)
    .map(s => s.name);

  const colors = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#db2777', '#65a30d'];

  const datasets = topSources.map((name, idx) => {
    const series = days.map(d => {
      const entry = (history[name] || {})[d];
      return entry ? (entry.fetched || 0) : 0;
    });
    return {
      label: name,
      data: series,
      borderColor: colors[idx % colors.length],
      backgroundColor: colors[idx % colors.length] + '20',
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 3,
      pointHoverRadius: 5,
    };
  });

  const ctx = document.getElementById('trend-chart');
  if (!ctx) return;

  if (state.trendChart) {
    state.trendChart.destroy();
  }

  if (typeof Chart === 'undefined') {
    document.querySelector('.chart-canvas-wrap').innerHTML = '<div class="empty-state">Chart.js 로드 실패. 새로고침해주세요.</div>';
    return;
  }

  if (datasets.length === 0) {
    document.querySelector('.chart-canvas-wrap').innerHTML = '<div class="empty-state">7일 추이 데이터가 아직 누적되지 않았습니다. 며칠 후 확인해주세요.</div>';
    return;
  }

  state.trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: days.map(d => d.slice(5)),  // MM-DD만
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 } } },
        tooltip: { mode: 'index' },
      },
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 5 } },
      },
    },
  });

  // 사용자에게 안내 — 전체 소스 라인 보고 싶으면
  const legend = document.getElementById('trend-legend');
  legend.innerHTML = `<div class="trend-note">활성 소스 중 수집량 상위 8개만 표시. 전체 소스 데이터는 source_history.json에 누적되어 있습니다.</div>`;
}

// ========================= 이벤트 =========================

function bindEvents() {
  // 사이드바 nav (parent + sub 통합)
  document.querySelectorAll('.nav-item, .nav-sub').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const view = item.dataset.view;
      if (!view) return;

      // active 표시
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelectorAll('.nav-sub').forEach(n => n.classList.remove('active'));
      // parent: 자신 + 첫 sub를 active로
      // sub: parent도 active로
      const parentItem = item.closest('.nav-group')?.querySelector('.nav-parent');
      if (parentItem) parentItem.classList.add('active');
      item.classList.add('active');

      state.view = view;
      state.category = 'all';

      if (view === 'strategy') {
        const period = item.dataset.period;
        if (period) state.strategyPeriod = period;
        state.strategyKey = null;  // 항상 최신 키부터
      }
      if (view === 'sources') {
        const tab = item.dataset.tab;
        if (tab) state.sourcesTab = tab;
      }

      renderContent();
    });
  });

  // 시사점 period 탭
  document.querySelectorAll('.period-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      state.strategyPeriod = btn.dataset.period;
      state.strategyKey = null;
      renderStrategy();
    });
  });

  // 시사점 period 셀렉트 (날짜·주·월 선택)
  const select = document.getElementById('strategy-period-select');
  if (select) {
    select.addEventListener('change', e => {
      state.strategyKey = e.target.value;
      renderStrategy();
    });
  }

  // 일반 필터
  document.getElementById('search-input').addEventListener('input', e => {
    state.search = e.target.value.trim();
    renderContent();
  });
  document.getElementById('date-filter').addEventListener('change', e => {
    state.dateFilter = e.target.value;
    renderContent();
  });
  document.getElementById('lang-filter').addEventListener('change', e => {
    state.langFilter = e.target.value;
    renderContent();
  });
}

// ========================= 유틸 =========================

function isNewToday(item) {
  const fs = item.first_seen || item.date;
  if (!fs) return false;
  try {
    const dt = new Date(fs);
    if (isNaN(dt)) return false;
    const now = new Date();
    const todayKey = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0');
    const fsKey = dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0') + '-' + String(dt.getDate()).padStart(2,'0');
    return todayKey === fsKey;
  } catch (e) { return false; }
}
function escapeHtml(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
function formatKoreanDate(d) {
  if (!d || isNaN(d)) return '날짜 없음';
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  return `${yyyy}-${mm}-${dd} (${days[d.getDay()]})`;
}

document.addEventListener('DOMContentLoaded', init);
