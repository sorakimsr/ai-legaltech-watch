// AI & Legaltech Watch v2.7 — 다중선택 + AI 분석 + 시계열 + 7일 추이

// 강제 HTTPS — Mixed Content 차단으로 worker fetch가 실패하는 문제 방지
// (http:// 로 접속한 사용자는 https:// 로 즉시 redirect)
if (location.protocol === 'http:' && !location.hostname.startsWith('localhost') && !location.hostname.startsWith('127.0.0.1')) {
  location.replace(location.href.replace(/^http:/, 'https:'));
}

// ============================================================================
// AI 분석 백엔드 (Cloudflare Worker)
// ============================================================================
const WORKER_ENDPOINT = "https://daibfy-ai-proxy.sora-kim-sr.workers.dev/analyze";

// 백엔드별 모델 옵션 (worker의 ALLOWED_MODELS와 동기화)
const MODELS = {
  openai: [
    { id: "gpt-4o-mini", label: "GPT-4o-mini · 빠름·저렴 (기본)", hint: "토큰당 $0.00015 / $0.00060 (입·출력)" },
    { id: "gpt-4o", label: "GPT-4o · 균형", hint: "토큰당 $0.0025 / $0.010" },
    { id: "gpt-4-turbo", label: "GPT-4 Turbo · 이전 강력형", hint: "토큰당 $0.010 / $0.030" },
    { id: "o1", label: "o1 · 깊은 추론", hint: "토큰당 $0.015 / $0.060, 느림" },
    { id: "o1-mini", label: "o1-mini · 추론·저렴", hint: "토큰당 $0.003 / $0.012" },
  ],
  claude: [
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 · 균형 (기본)", hint: "토큰당 $3 / $15 per MTok" },
    { id: "claude-opus-4-6", label: "Claude Opus 4.6 · 최강", hint: "토큰당 $15 / $75 per MTok, 가장 정확" },
    { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 · 가장 빠름", hint: "토큰당 $1 / $5 per MTok" },
    { id: "claude-3-7-sonnet-latest", label: "Claude 3.7 Sonnet · 이전 세대", hint: "이전 세대 균형 모델" },
    { id: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku · 이전 빠름", hint: "이전 세대 빠른 모델" },
  ],
};

const PROMPT_PRESETS = {
  summary:
    "다음 뉴스들의 핵심을 3~5개의 불릿 포인트로 요약해주세요. 각 포인트는 한 문장으로, 구체적 사실(회사명·금액·날짜) 중심으로.",
  insights:
    "다음 뉴스들을 한국의 전략·기획·AI 업무 담당자 관점에서 분석해주세요. (1) 흐름 정리 (2) 의미와 영향 (3) 본인 업무에 적용할 액션 가능한 시사점 3가지.",
  trends:
    "다음 뉴스들에서 반복되는 패턴·키워드·플레이어를 추출해 트렌드 분석해주세요. 강한 시그널과 약한 시그널을 구분하고, 향후 3~6개월 내 추적할 가치 있는 변수를 제시.",
  competitive:
    "다음 뉴스들에 등장하는 회사·제품·플랫폼을 경쟁 구도로 정리해주세요. 표 형식으로 비교 (강점·약점·차별화 요소), 시장 포지셔닝 분석, 잠재적 통합·M&A 가능성.",
  opportunity:
    "다음 뉴스들이 시사하는 한국 시장 진출/협업 기회를 분석해주세요. (1) 글로벌 흐름 (2) 한국 시장의 갭과 기회 (3) 진입 전략·파트너십 아이디어.",
  custom: "",
};

const state = {
  data: null,
  history: null,        // strategy_history.json
  sourceHistory: null,  // source_history.json
  view: 'latest',       // latest | top | today | strategy | sources | saved
  // 시사점 sub-state
  strategyPeriod: 'daily',  // daily | weekly | monthly
  strategyKey: null,        // 선택된 날짜·주·월 키
  // v2.7.1: 논문 흐름 sub-state
  papersPeriod: 'weekly',   // daily | weekly | monthly
  papersKey: null,          // 선택된 날짜·주·월 키
  paperTrendsHistory: null, // paper_trends_history.json
  // 소스 sub-state
  sourcesTab: 'status',     // status | trend
  sourcesPeriod: '7days',   // today | 7days | 30days | all (소스 현황 표용)
  trendView: 'source',      // source | category (7일 추이 차트 모드)
  // 필터
  category: 'all',
  search: '',
  dateFilter: 'all',
  langFilter: 'all',
  // v2.7.1: 정렬 기준 (뉴스 피드 통합 후) — latest | score | today
  sortBy: 'latest',
  // chart instance
  trendChart: null,
  // 다중 선택
  selectedUrls: new Set(),
  // 분석 모달 상태
  analyzeBackend: "openai",
  analyzeModel: "gpt-4o-mini",
  analyzePromptPreset: "summary",
  // v2.7: 사용자 저장 항목 (localStorage 동기화)
  saved: { items: {}, strategy: {} },  // {url: true}, {strategyKey: {card data}}
};

// ===== 저장(북마크) 기능 =====
const SAVED_STORAGE_KEY = 'daibfy_saved_v1';

function loadSaved() {
  try {
    const raw = localStorage.getItem(SAVED_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      state.saved = { items: parsed.items || {}, strategy: parsed.strategy || {} };
    }
  } catch (e) {}
}

function persistSaved() {
  try {
    localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(state.saved));
  } catch (e) {}
}

function isSaved(kind, key) {
  return !!(state.saved[kind] || {})[key];
}

// v2.7.4: 저장 시점(timestamp) 반환 — 이전 boolean 데이터도 호환
function getSavedAt(kind, key) {
  const entry = (state.saved[kind] || {})[key];
  if (!entry) return 0;
  if (typeof entry === 'object' && entry.savedAt) return entry.savedAt;
  return 1;  // legacy boolean → 가장 옛날로 정렬
}

function toggleSaved(kind, key, value) {
  if (!state.saved[kind]) state.saved[kind] = {};
  if (isSaved(kind, key)) {
    delete state.saved[kind][key];
  } else {
    // v2.7.4: 저장 시 timestamp 기록. value가 객체면 savedAt 추가, 아니면 {savedAt} 만 저장
    const now = Date.now();
    if (value && typeof value === 'object') {
      state.saved[kind][key] = { ...value, savedAt: now };
    } else {
      state.saved[kind][key] = { savedAt: now };
    }
  }
  persistSaved();
}

function makeStrategyKey(period, dateKey, card) {
  // 같은 일자·주기 내 카드 식별자: tag 또는 title 해시
  return `${period}|${dateKey || ''}|${(card.tag || card.title || '').slice(0, 80)}`;
}

function escapeAttr(s) {
  return (s || '').replace(/'/g, '&apos;').replace(/"/g, '&quot;');
}

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
  latest:    { title: '뉴스 피드', hint: '정렬·기간·언어 필터로 자유 탐색' },
  // 백워드 호환: 구 url/링크가 top, today를 가리킬 경우 latest로 매핑
  top:       { title: '뉴스 피드', hint: '중요도순으로 정렬됨' },
  today:     { title: '뉴스 피드', hint: '오늘 추가된 항목만' },
  strategy:  { title: '전략·기획 시사점', hint: 'Daily/Weekly/Monthly로 LLM 자동 생성' },
  papers:    { title: 'AI 논문 흐름', hint: 'Daily/Weekly/Monthly 시계열 분석' },
  sources:   { title: '소스 현황', hint: '활성·유휴·오류 + 7일 추이' },
  saved:     { title: '저장한 항목', hint: '북마크한 시사점·뉴스 카드' },
};

async function init() {
  loadSaved();  // v2.7: localStorage 북마크 복원
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
  try {
    const r = await fetch('./data/paper_trends.json?t=' + Date.now());
    state.paperTrends = await r.json();
  } catch (e) {
    state.paperTrends = null;
  }
  // v2.7.1: 논문 시계열 history (선택 사항 — 없으면 paper_trends만 표시)
  try {
    const r = await fetch('./data/paper_trends_history.json?t=' + Date.now());
    state.paperTrendsHistory = await r.json();
  } catch (e) {
    state.paperTrendsHistory = null;
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
  // v2.7.3: stat-row는 소스 현황 view에서만 표시. 다른 view에서는 숨김.
  if (state.view !== 'sources') {
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

  // v2.7.1: 카테고리 카운트는 "현재 적용된 lang/date/search 필터"까지 반영해야
  // 표시되는 카드 수와 일치한다 (category 자체만 제외).
  const pool = applyNonCategoryFilters(applyViewFilter(state.data.items || []));
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
  // v2.7.1: latest/top/today 통합 → state.sortBy로 분기
  if (state.view === 'latest') {
    switch (state.sortBy) {
      case 'score':
        arr.sort((a, b) => (b.score || 0) - (a.score || 0));
        arr = arr.slice(0, 200);  // 중요도 상위 200개
        break;
      case 'today': {
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        arr = arr.filter(i => new Date(i.first_seen || i.date) >= start);
        arr.sort((a, b) => (b.score || 0) - (a.score || 0));
        break;
      }
      case 'latest':
      default:
        arr.sort((a, b) => new Date(b.date) - new Date(a.date));
        break;
    }
  } else if (state.view === 'saved') {
    arr = arr.filter(i => isSaved('items', i.url));
    arr.sort((a, b) => (b.score || 0) - (a.score || 0));
  }
  // 'top'/'today' 구 view 이름은 백워드 호환을 위해 latest+sortBy로 매핑
  return arr;
}

function renderContent() {
  const newsGrid = document.getElementById('news-grid');
  const stratView = document.getElementById('strategy-view');
  const sourcesView = document.getElementById('sources-view');
  const papersView = document.getElementById('papers-view');
  const controlsRow = document.querySelector('.controls-row');
  const filterLabel = document.querySelector('.filter-label');
  const statRow = document.getElementById('stat-row');
  const categoryBar = document.getElementById('category-bar');
  const title = document.getElementById('topbar-title');
  const hint = document.getElementById('view-hint');

  newsGrid.classList.add('hidden');
  stratView.classList.add('hidden');
  sourcesView.classList.add('hidden');
  if (papersView) papersView.classList.add('hidden');
  controlsRow.style.display = 'flex';
  if (filterLabel) filterLabel.style.display = 'block';
  // 기본 — v2.7: stat-row는 소스 현황 view에만 표시 (다른 view에서는 숨김)
  if (statRow) statRow.style.display = 'none';
  if (categoryBar) categoryBar.style.display = '';
  // 카테고리바 우측 기간 dropdown은 sources view에서만 표시
  const periodAside = document.getElementById('category-bar-aside');
  if (periodAside) periodAside.classList.add('hidden');

  const meta = VIEW_META[state.view] || VIEW_META.latest;
  title.textContent = meta.title;
  if (hint) hint.textContent = meta.hint;

  if (state.view === 'strategy') {
    stratView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderStrategy();
    return;
  }
  if (state.view === 'sources') {
    sourcesView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    // 소스 현황에서만 stat-row + 카테고리 탭 우측 기간 dropdown 표시
    if (statRow) statRow.style.display = '';
    if (periodAside) periodAside.classList.remove('hidden');
    renderCategoryBar();
    renderSourcesView();
    renderStats();
    return;
  }
  if (state.view === 'papers') {
    if (papersView) papersView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    if (filterLabel) filterLabel.style.display = 'none';
    if (categoryBar) categoryBar.style.display = 'none';
    renderPapersView();
    return;
  }

  newsGrid.classList.remove('hidden');
  renderCategoryBar();
  renderStats();

  // v2.7: 저장한 항목 view는 시사점 + 뉴스 카드 둘 다 렌더
  if (state.view === 'saved') {
    renderSavedView(newsGrid);
    return;
  }

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

function renderSavedView(root) {
  // v2.7.4: 저장 시점(savedAt) 기준 desc 정렬 — 최근 저장한 항목이 위로
  const savedItems = (state.data.items || [])
    .filter(i => isSaved('items', i.url))
    .map(i => ({ item: i, savedAt: getSavedAt('items', i.url) }))
    .sort((a, b) => b.savedAt - a.savedAt);
  const savedStrategies = Object.entries(state.saved.strategy || {})
    .sort((a, b) => {
      const ta = (a[1] && a[1].savedAt) || 0;
      const tb = (b[1] && b[1].savedAt) || 0;
      return tb - ta;
    });

  if (savedItems.length === 0 && savedStrategies.length === 0) {
    root.innerHTML = `<div class="saved-empty"><div style="font-size:32px;margin-bottom:8px;">★</div>아직 저장한 항목이 없습니다.<br><span style="font-size:13px;color:#9ca3af;">시사점 카드나 뉴스 카드의 ☆ 별표를 눌러 저장하세요.</span></div>`;
    return;
  }

  // 저장 시점 포맷터
  const fmtSavedAt = (ts) => {
    if (!ts || ts < 100) return '';
    const d = new Date(ts);
    const yy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${yy}-${mm}-${dd} ${hh}:${mi}`;
  };

  let html = '';

  // 저장한 시사점 카드
  if (savedStrategies.length > 0) {
    html += `<h3 class="saved-section-head">⭐ 저장한 시사점 (${savedStrategies.length})</h3>`;
    html += `<div class="saved-list">`;
    html += savedStrategies.map(([k, entry]) => {
      const card = (entry && entry.card) || {};
      const period = (entry && entry.period) || '';
      const keyLabel = (entry && entry.key) || '';
      const savedAtLabel = fmtSavedAt(entry && entry.savedAt);
      return `
        <div class="strategy-card">
          <div class="strategy-card-head">
            <div>
              <div class="strat-tag">${escapeHtml(card.tag || 'TREND')} · ${escapeHtml(period)} ${escapeHtml(keyLabel)}</div>
              <h3>${escapeHtml(card.title || '')}</h3>
            </div>
            <button class="bookmark-btn is-saved" data-bookmark-strategy='${escapeAttr(JSON.stringify({k, period, key: keyLabel, card}))}' title="저장 해제">★</button>
          </div>
          <div class="strategy-card-grid">
            <p class="strategy-body">${escapeHtmlWithMark(card.body || '')}</p>
            <div class="strategy-action">
              <span class="action-label">ACTION</span>
              <div class="action-body">${escapeHtmlWithMark(card.action || '')}</div>
            </div>
          </div>
          ${savedAtLabel ? `<div class="saved-at-label">저장 ${escapeHtml(savedAtLabel)}</div>` : ''}
        </div>
      `;
    }).join('');
    html += `</div>`;  // /.saved-list
  }

  // 저장한 뉴스 카드 — savedAt desc 순서 + 저장 시점 표시
  if (savedItems.length > 0) {
    html += `<h3 class="saved-section-head">📰 저장한 뉴스 (${savedItems.length})</h3>`;
    html += `<div class="news-grid saved-news-grid">${savedItems.map(({item, savedAt}) => {
      const card = renderCard(item);
      const label = fmtSavedAt(savedAt);
      // 카드 안에 저장 시점 라벨 inject (card-bottom 위)
      return label
        ? card.replace('<div class="card-bottom">', `<div class="saved-at-label">저장 ${escapeHtml(label)}</div><div class="card-bottom">`)
        : card;
    }).join('')}</div>`;
  }

  root.innerHTML = html;
}

// v2.7.1: 카테고리 외 필터만 적용 (chip 카운트 계산용)
function applyNonCategoryFilters(items) {
  let arr = items;
  if (state.langFilter !== 'all') {
    arr = arr.filter(i => i.lang === state.langFilter);
  }
  if (state.dateFilter !== 'all') {
    const cutoff = computeDateCutoff(state.dateFilter);
    arr = arr.filter(i => new Date(i.date) >= cutoff);
  }
  if (state.search) {
    const q = state.search.toLowerCase();
    arr = arr.filter(i => {
      const blob = [i.title, i.summary, i.summary_ko, i.insight_ko, i.source, ...(i.categories || [])].filter(Boolean).join(' ').toLowerCase();
      return blob.includes(q);
    });
  }
  return arr;
}

function filterItems() {
  let items = applyNonCategoryFilters(applyViewFilter(state.data.items || []));
  if (state.category !== 'all') {
    items = items.filter(i => (i.categories || []).includes(state.category));
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
    summaryHtml = `<div class="card-summary has-ko">${escapeHtmlWithMark(summaryKo)}</div>`;
    if (isEnglish && summaryEn) {
      summaryHtml += `<details class="card-original"><summary>원문 요약 보기</summary><div class="card-original-text">${escapeHtml(summaryEn)}</div></details>`;
    }
  } else if (summaryEn) {
    summaryHtml = `<div class="card-summary ${isEnglish ? 'is-en' : ''}">${escapeHtmlWithMark(summaryEn)}</div>`;
  }

  const insightBlock = item.insight_ko ? `<div class="card-insight"><span class="insight-label">시사점</span>${escapeHtmlWithMark(item.insight_ko)}</div>` : '';

  const relCount = item.related_count || 0;
  const relBadge = relCount > 0 ? `<span class="related-badge" title="유사 뉴스 ${relCount}건">+${relCount} 매체 ▾</span>` : '';
  const relDetail = relCount > 0 && item.related ? `<div class="related-detail">${item.related.map(r => `<div class="rel-item"><span class="rel-source">${escapeHtml(r.source)}</span><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a></div>`).join('')}</div>` : '';

  // v2.7.3: ai-badge 제거 (모든 카드에 시사점이 들어가므로 의미 없음)
  const langBadge = isEnglish ? '<span class="lang-badge">EN</span>' : '';
  const newBadge = isNewToday(item) ? '<span class="new-badge">NEW</span>' : '';

  const isSelected = state.selectedUrls.has(item.url);
  const itemSaved = isSaved('items', item.url);

  return `
    <article class="news-card ${isSelected ? 'is-selected' : ''}" data-url="${escapeHtml(item.url)}">
      <label class="card-checkbox" title="AI 분석 선택">
        <input type="checkbox" class="card-check" data-url="${escapeHtml(item.url)}" ${isSelected ? 'checked' : ''} />
      </label>
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
        <button class="bookmark-btn card-bookmark ${itemSaved ? 'is-saved' : ''}" data-bookmark-item="${escapeHtml(item.url)}" title="${itemSaved ? '저장 해제' : '저장하기'}">${itemSaved ? '★' : '☆'}</button>
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
    const cardKey = makeStrategyKey(period, currentKey, s);
    const saved = isSaved('strategy', cardKey);
    return `
      <div class="strategy-card">
        <div class="strategy-card-head">
          <div>
            <div class="strat-tag">${escapeHtml(s.tag || 'TREND')}</div>
            <h3>${escapeHtml(s.title || '')}</h3>
          </div>
          <button class="bookmark-btn ${saved ? 'is-saved' : ''}" data-bookmark-strategy='${escapeAttr(JSON.stringify({k: cardKey, period, key: currentKey, card: s}))}' title="${saved ? '저장 해제' : '저장하기'}">${saved ? '★' : '☆'}</button>
        </div>
        <div class="strategy-card-grid">
          <p class="strategy-body">${escapeHtmlWithMark(s.body || '')}</p>
          <div class="strategy-action">
            <span class="action-label">ACTION</span>
            <div class="action-body">${escapeHtmlWithMark(s.action || '')}</div>
          </div>
        </div>
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

  // 선택된 기간 키 목록 생성
  const today = new Date();
  const periodDayKeys = (() => {
    const ks = [];
    const make = n => {
      for (let i = 0; i < n; i++) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        ks.push(d.toISOString().slice(0, 10));
      }
    };
    if (state.sourcesPeriod === 'today') make(1);
    else if (state.sourcesPeriod === '7days') make(7);
    else if (state.sourcesPeriod === '30days') make(30);
    else make(60); // all — source_history는 60일 보존
    return ks;
  })();

  const history = state.sourceHistory || {};

  // source_type 결정 — items에서 추정 (items의 source가 일치하는 첫 항목의 source_type)
  const itemBySource = {};
  for (const it of (state.data.items || [])) {
    if (it.source && !itemBySource[it.source]) itemBySource[it.source] = it;
  }

  // 소스별로 row 계산
  const enriched = sources.map(s => {
    const hist = history[s.name] || {};
    let periodFetched = 0;
    let periodNew = 0;
    let lastActiveDate = null;
    for (const k of periodDayKeys) {
      const entry = hist[k];
      if (entry) {
        const f = entry.fetched || 0;
        periodFetched += f;
        periodNew += entry.new || 0;
        if (f > 0 && (!lastActiveDate || k > lastActiveDate)) lastActiveDate = k;
      }
    }
    // 마지막 활성일은 전체 기간으로 따로 한 번 더 봄 (선택 기간이 짧을 때 의미 없을까봐)
    let everLastActive = null;
    for (const k of Object.keys(hist)) {
      if ((hist[k]?.fetched || 0) > 0 && (!everLastActive || k > everLastActive)) everLastActive = k;
    }
    const stype = itemBySource[s.name]?.source_type || '-';
    return {
      ...s,
      source_type: stype,
      periodFetched,
      periodNew,
      lastActive: lastActiveDate || everLastActive || '-',
    };
  });

  // 정렬: 기간 내 수집 많은 순
  enriched.sort((a, b) => b.periodFetched - a.periodFetched);

  const byStatus = enriched.reduce((a, s) => { a[s.status] = (a[s.status] || 0) + 1; return a; }, {});
  const periodTotal = enriched.reduce((sum, s) => sum + s.periodFetched, 0);

  const statusBadge = (st) => {
    const label = st === 'active' ? 'Active' : st === 'error' ? 'Error' : 'Idle';
    return `<span class="badge-${escapeHtml(st)}">${label}</span>`;
  };
  const typeBadge = (t) => {
    const labels = { rss: 'RSS', arxiv: 'arXiv', naver: 'Naver', google_news: 'Google News', semantic_scholar: 'S2', korean: 'KR', blog: 'Blog' };
    return `<span class="type-badge type-${escapeHtml(t)}">${escapeHtml(labels[t] || t || '-')}</span>`;
  };

  const periodLabel = { today: '오늘', '7days': '최근 7일', '30days': '최근 30일', all: '전체 누적' }[state.sourcesPeriod] || '';

  const rows = enriched.map(s => `
    <tr>
      <td class="src-name">${escapeHtml(s.name)}</td>
      <td>${typeBadge(s.source_type)}</td>
      <td>${statusBadge(s.status)}</td>
      <td class="num-cell">${s.periodFetched}</td>
      <td class="num-cell">${s.periodNew}</td>
      <td>${escapeHtml(s.lastActive)}</td>
      <td class="src-url">${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.url)}</a>` : '-'}</td>
    </tr>
  `).join('');

  root.innerHTML = `
    <div class="sources-table-wrap">
      <h3>소스 현황 — ${escapeHtml(periodLabel)} (총 ${enriched.length}개 · 활성 ${byStatus.active || 0}개 · 수집 ${periodTotal}건)</h3>
      <div class="sources-table-scroll">
        <table class="src-table">
          <thead>
            <tr>
              <th class="col-name">소스</th>
              <th class="col-type">유형</th>
              <th class="col-status">상태</th>
              <th class="col-num">${escapeHtml(periodLabel)} 수집</th>
              <th class="col-num">신규</th>
              <th class="col-date">마지막 활성</th>
              <th class="col-url">URL</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderSourceTrend() {
  const today = new Date();
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    days.push(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'));
  }

  const colors = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#db2777', '#65a30d', '#0ea5e9', '#a16207'];

  // 차트 제목 + view 모드별 데이터셋
  const titleEl = document.getElementById('trend-chart-title');
  let datasets = [];
  let noteHtml = '';

  if (state.trendView === 'category') {
    if (titleEl) titleEl.textContent = '최근 7일 컨텐츠 태그별 수집 추이';
    // items의 categories 별로 발행일 기준 일별 카운트
    const items = state.data.items || [];
    const catDayMap = {}; // category → { date → count }
    for (const it of items) {
      if (it.date_unknown) continue;
      const d = (it.date || '').slice(0, 10);
      if (!days.includes(d)) continue;
      const cats = it.categories || [];
      for (const c of cats) {
        if (!catDayMap[c]) catDayMap[c] = {};
        catDayMap[c][d] = (catDayMap[c][d] || 0) + 1;
      }
    }
    // 합계 큰 카테고리 상위 10
    const catTotals = Object.entries(catDayMap).map(([c, m]) =>
      [c, Object.values(m).reduce((a, b) => a + b, 0)]
    ).sort((a, b) => b[1] - a[1]).slice(0, 10);

    datasets = catTotals.map(([cat, _], idx) => ({
      label: cat,
      data: days.map(d => (catDayMap[cat][d] || 0)),
      borderColor: colors[idx % colors.length],
      backgroundColor: colors[idx % colors.length] + '20',
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 3,
    }));
    noteHtml = `<div class="trend-note">발행일 기준. 상위 ${catTotals.length}개 태그만 표시.</div>`;
  } else {
    if (titleEl) titleEl.textContent = '최근 7일 소스별 수집 추이';
    const history = state.sourceHistory || {};
    const sources = state.data.sources || [];
    const topSources = sources
      .filter(s => s.status === 'active')
      .sort((a, b) => (b.count || 0) - (a.count || 0))
      .slice(0, 8)
      .map(s => s.name);

    datasets = topSources.map((name, idx) => ({
      label: name,
      data: days.map(d => ((history[name] || {})[d]?.fetched || 0)),
      borderColor: colors[idx % colors.length],
      backgroundColor: colors[idx % colors.length] + '20',
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 3,
    }));
    noteHtml = `<div class="trend-note">수집일 기준. 활성 소스 중 수집량 상위 8개만 표시.</div>`;
  }

  const wrap = document.querySelector('.chart-canvas-wrap');
  if (state.trendChart) {
    state.trendChart.destroy();
    state.trendChart = null;
  }
  if (typeof Chart === 'undefined') {
    if (wrap) wrap.innerHTML = '<div class="empty-state">Chart.js 로드 실패</div>';
    return;
  }
  if (datasets.length === 0) {
    if (wrap) wrap.innerHTML = '<div class="empty-state">아직 데이터가 충분히 누적되지 않았습니다.</div>';
    return;
  }

  // canvas 복원 (이전 empty-state 메시지가 들어있을 수 있어서)
  if (wrap && !document.getElementById('trend-chart')) {
    wrap.innerHTML = '<canvas id="trend-chart"></canvas>';
  }

  const ctx = document.getElementById('trend-chart');
  state.trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: days.map(d => d.slice(5)),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 11 } } },
        tooltip: { mode: 'index' },
      },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 5 } } },
    },
  });

  const legend = document.getElementById('trend-legend');
  if (legend) legend.innerHTML = noteHtml;
}

// ========================= 이벤트 =========================

function bindEvents() {
  // v2.7: 북마크 버튼 (event delegation — 카드 동적 생성이므로)
  document.addEventListener('click', (e) => {
    const itemBtn = e.target.closest('[data-bookmark-item]');
    if (itemBtn) {
      e.preventDefault();
      e.stopPropagation();
      const url = itemBtn.dataset.bookmarkItem;
      toggleSaved('items', url, true);
      // 버튼 상태 토글
      const nowSaved = isSaved('items', url);
      itemBtn.classList.toggle('is-saved', nowSaved);
      itemBtn.textContent = nowSaved ? '★' : '☆';
      itemBtn.title = nowSaved ? '저장 해제' : '저장하기';
      // saved view면 다시 렌더해서 제거 반영
      if (state.view === 'saved') renderContent();
      return;
    }
    const stratBtn = e.target.closest('[data-bookmark-strategy]');
    if (stratBtn) {
      e.preventDefault();
      e.stopPropagation();
      try {
        const payload = JSON.parse(stratBtn.dataset.bookmarkStrategy);
        const { k, card, period, key } = payload;
        toggleSaved('strategy', k, { card, period, key });
        const nowSaved = isSaved('strategy', k);
        stratBtn.classList.toggle('is-saved', nowSaved);
        stratBtn.textContent = nowSaved ? '★' : '☆';
        stratBtn.title = nowSaved ? '저장 해제' : '저장하기';
        if (state.view === 'saved') renderContent();
      } catch (err) { console.error('bookmark parse', err); }
      return;
    }
  });

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

      // v2.7.1: 'top'/'today' 구 메뉴는 'latest' + sortBy로 매핑
      if (view === 'top') {
        state.view = 'latest';
        state.sortBy = 'score';
      } else if (view === 'today') {
        state.view = 'latest';
        state.sortBy = 'today';
      } else {
        state.view = view;
      }
      state.category = 'all';

      // 정렬 dropdown sync
      const sortSel = document.getElementById('sort-filter');
      if (sortSel) sortSel.value = state.sortBy;

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

  // 시사점 period 탭 (data-period 만)
  document.querySelectorAll('.period-tab[data-period]').forEach(btn => {
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

  // v2.7.1: 논문 흐름 period 탭
  document.querySelectorAll('.period-tab[data-papers-period]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.papersPeriod = btn.dataset.papersPeriod;
      state.papersKey = null;
      renderPapersView();
    });
  });
  const papersSel = document.getElementById('papers-period-select');
  if (papersSel) {
    papersSel.addEventListener('change', e => {
      state.papersKey = e.target.value;
      renderPapersView();
    });
  }

  // 일반 필터
  document.getElementById('search-input').addEventListener('input', e => {
    state.search = e.target.value.trim();
    renderContent();
    updateSelectBar();
  });
  document.getElementById('date-filter').addEventListener('change', e => {
    state.dateFilter = e.target.value;
    renderContent();
  });
  document.getElementById('lang-filter').addEventListener('change', e => {
    state.langFilter = e.target.value;
    renderContent();
  });
  // v2.7.1: 정렬 기준 dropdown
  const sortSel = document.getElementById('sort-filter');
  if (sortSel) {
    sortSel.value = state.sortBy;
    sortSel.addEventListener('change', e => {
      state.sortBy = e.target.value;
      renderContent();
    });
  }

  // 다중 선택 — 카드 체크박스 (delegation)
  document.getElementById('news-grid').addEventListener('change', e => {
    if (e.target.classList.contains('card-check')) {
      const url = e.target.dataset.url;
      if (url) toggleSelection(url);
    }
  });

  // 선택 해제
  const btnClear = document.getElementById('btn-clear-selection');
  if (btnClear) btnClear.addEventListener('click', clearSelection);

  // 소스 현황 기간 selector
  const sourcesPeriodSel = document.getElementById('sources-period');
  if (sourcesPeriodSel) {
    sourcesPeriodSel.value = state.sourcesPeriod;
    sourcesPeriodSel.addEventListener('change', e => {
      state.sourcesPeriod = e.target.value;
      renderSourcesStatus();
    });
  }

  // 추이 차트 view 토글 (소스별 / 카테고리별)
  document.querySelectorAll('.trend-view-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.trend-view-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.trendView = btn.dataset.trendView;
      renderSourceTrend();
    });
  });

  // 검색결과 전체 선택
  const btnSelectSearch = document.getElementById('btn-select-search-results');
  if (btnSelectSearch) btnSelectSearch.addEventListener('click', selectSearchResults);

  // AI 분석 버튼 → 모달 열기
  const btnAnalyze = document.getElementById('btn-ai-analyze');
  if (btnAnalyze) btnAnalyze.addEventListener('click', openAnalyzeModal);

  // 모달 닫기 (backdrop, X 버튼, 닫기 버튼)
  document.querySelectorAll('[data-close]').forEach(el => {
    el.addEventListener('click', closeAnalyzeModal);
  });

  // 모달 — 백엔드 탭
  document.querySelectorAll('.backend-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.backend-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.analyzeBackend = btn.dataset.backend;
      populateModelSelect();   // 모델 드롭다운 백엔드 따라 갱신
    });
  });

  // 모달 — 모델 선택
  const modelSel = document.getElementById('model-select');
  if (modelSel) {
    modelSel.addEventListener('change', e => {
      state.analyzeModel = e.target.value;
      updateModelHint();
    });
  }

  // 모달 — 프롬프트 프리셋
  const presetSel = document.getElementById('prompt-preset');
  if (presetSel) {
    presetSel.addEventListener('change', e => {
      state.analyzePromptPreset = e.target.value;
      applyPromptPreset();
    });
  }

  // 모달 — 선택 미리보기 토글
  const btnTogglePreview = document.getElementById('btn-toggle-preview');
  if (btnTogglePreview) {
    btnTogglePreview.addEventListener('click', () => {
      document.getElementById('analyze-preview-list').classList.toggle('hidden');
    });
  }

  // 모달 — 분석 실행
  const btnRun = document.getElementById('btn-run-analyze');
  if (btnRun) btnRun.addEventListener('click', runAnalysis);

  // 모달 — 결과 복사
  const btnCopy = document.getElementById('btn-copy-result');
  if (btnCopy) btnCopy.addEventListener('click', copyAnalyzeResult);

  // 본인 API 키 — localStorage 복원
  try {
    const saved = localStorage.getItem('daibfy_user_api_key');
    if (saved) {
      const input = document.getElementById('user-api-key');
      if (input) input.value = saved;
    }
  } catch (e) {}
}

// ========================= 논문 흐름 분석 =========================

function getPapersTrendsFor(period, key) {
  // history 우선, 없으면 paper_trends.json (= 기본 weekly) 사용
  if (state.paperTrendsHistory && state.paperTrendsHistory[period]) {
    const bucket = state.paperTrendsHistory[period];
    const keys = Object.keys(bucket).sort().reverse();
    const useKey = (key && keys.includes(key)) ? key : keys[0];
    if (useKey) return { trends: bucket[useKey], key: useKey, keys };
  }
  // fallback
  if (period === (state.paperTrends && state.paperTrends.period || 'weekly')) {
    return { trends: state.paperTrends, key: null, keys: [] };
  }
  return { trends: null, key: null, keys: [] };
}

function renderPapersControls() {
  const period = state.papersPeriod;
  // 탭 active 표시
  document.querySelectorAll('[data-papers-period]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.papersPeriod === period);
  });
  const { keys, key } = getPapersTrendsFor(period, state.papersKey);
  const sel = document.getElementById('papers-period-select');
  if (sel) {
    if (!keys || keys.length === 0) {
      sel.innerHTML = '<option>—</option>';
      sel.disabled = true;
    } else {
      sel.disabled = false;
      sel.innerHTML = keys.map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
      if (key) sel.value = key;
    }
  }
}

function renderPapersView() {
  renderPapersControls();
  const { trends: t } = getPapersTrendsFor(state.papersPeriod, state.papersKey);
  const trends = t || state.paperTrends;
  const meta = document.getElementById('papers-meta');
  if (!trends || !trends.paper_count) {
    meta.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📑</div>
        <div class="empty-title">논문 흐름 분석이 아직 없습니다</div>
        <div class="empty-desc">다음 빌드(매일 KST 06:00)부터 자동 생성됩니다.</div>
      </div>
    `;
    document.getElementById('papers-narrative').innerHTML = '';
    document.getElementById('papers-hot-topics').innerHTML = '';
    document.getElementById('papers-techniques').innerHTML = '';
    document.getElementById('papers-institutions').innerHTML = '';
    document.getElementById('papers-keywords').innerHTML = '';
    document.getElementById('papers-actionable').innerHTML = '';
    document.getElementById('papers-list').innerHTML = '';
    return;
  }

  const analyzedAt = trends.analyzed_at ? formatKoreanDate(new Date(trends.analyzed_at)) : '';
  meta.innerHTML = `
    <div class="papers-meta-row">
      <span><strong>${trends.paper_count}</strong>편 논문 · 최근 <strong>${trends.days_window}</strong>일 분석</span>
      <span class="papers-meta-time">${escapeHtml(analyzedAt)}</span>
    </div>
  `;

  // Narrative
  document.getElementById('papers-narrative').innerHTML = renderMarkdown(trends.narrative || '');

  // 관련 논문 드롭다운 헬퍼
  const renderPapersBlock = (papers) => {
    if (!Array.isArray(papers) || papers.length === 0) return '';
    return `
      <details class="topic-papers">
        <summary>관련 논문 ${papers.length}편 ▾</summary>
        <ol class="topic-paper-list">
          ${papers.map(p => `
            <li>
              <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>
              <span class="topic-paper-meta">— ${escapeHtml(p.source || 'arXiv')} · ${escapeHtml(p.date || '')}</span>
            </li>
          `).join('')}
        </ol>
      </details>
    `;
  };

  // Hot topics
  const topicsRoot = document.getElementById('papers-hot-topics');
  const topics = trends.hot_topics || [];
  topicsRoot.innerHTML = topics.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : topics.map(t => `
        <div class="topic-item">
          <div class="topic-head">
            <span class="topic-name">${escapeHtmlWithMark(t.topic || '')}</span>
            ${t.paper_count ? `<span class="topic-count">${t.paper_count}편</span>` : ''}
          </div>
          <div class="topic-desc">${escapeHtmlWithMark(t.description || '')}</div>
          ${renderPapersBlock(t.papers)}
        </div>
      `).join('');

  // Techniques
  const techRoot = document.getElementById('papers-techniques');
  const techs = trends.key_techniques || [];
  techRoot.innerHTML = techs.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : techs.map(t => `
        <div class="topic-item">
          <div class="topic-head">
            <span class="topic-name">${escapeHtmlWithMark(t.technique || '')}</span>
            ${t.paper_count ? `<span class="topic-count">${t.paper_count}편</span>` : ''}
          </div>
          <div class="topic-desc">${escapeHtmlWithMark(t.description || '')}</div>
          ${renderPapersBlock(t.papers)}
        </div>
      `).join('');

  // Institutions
  const instRoot = document.getElementById('papers-institutions');
  const insts = trends.top_institutions || [];
  instRoot.innerHTML = insts.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : `<div class="freq-list">${
        insts.map(i => `
          <div class="freq-item">
            <span class="freq-name">${escapeHtml(i.name)}</span>
            <span class="freq-bar" style="width:${Math.min(100, i.count * 10)}%"></span>
            <span class="freq-count">${i.count}</span>
          </div>
        `).join('')
      }</div>`;

  // Keywords
  const kwRoot = document.getElementById('papers-keywords');
  const kws = (trends.top_keywords || []).slice(0, 15);
  kwRoot.innerHTML = kws.length === 0
    ? '<div class="papers-empty">데이터 없음</div>'
    : `<div class="kw-cloud">${
        kws.map(k => `<span class="kw-tag" style="font-size:${Math.min(18, 11 + k.count)}px">${escapeHtml(k.keyword)} <em>${k.count}</em></span>`).join('')
      }</div>`;

  // Actionable insights — **굵게** → <mark> 하이라이트
  const actRoot = document.getElementById('papers-actionable');
  const acts = trends.actionable_insights || [];
  actRoot.innerHTML = acts.length === 0
    ? '<li class="papers-empty">데이터 없음</li>'
    : acts.map(a => `<li>${escapeHtmlWithMark(a)}</li>`).join('');

  // 논문 목록
  const listRoot = document.getElementById('papers-list');
  const papers = trends.recent_papers || [];
  listRoot.innerHTML = papers.length === 0
    ? '<div class="papers-empty">논문 없음</div>'
    : papers.map(p => `
        <div class="paper-row">
          <div class="paper-row-head">
            <span class="score-badge mid">중요도 ${p.score || 0}</span>
            <span class="date-text">${escapeHtml(p.date || '')}</span>
          </div>
          <a class="paper-row-title" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>
          ${p.summary_ko ? `<div class="paper-row-summary">${escapeHtml(p.summary_ko)}</div>` : ''}
          <div class="paper-row-source">${escapeHtml(p.source || 'arXiv')}</div>
        </div>
      `).join('');
}

// ========================= 다중 선택 + AI 분석 =========================

function toggleSelection(url) {
  if (state.selectedUrls.has(url)) {
    state.selectedUrls.delete(url);
  } else {
    state.selectedUrls.add(url);
  }
  updateSelectBar();
  // 카드 시각 업데이트
  const card = document.querySelector(`.news-card[data-url="${cssEscape(url)}"]`);
  if (card) card.classList.toggle('is-selected', state.selectedUrls.has(url));
}

function clearSelection() {
  state.selectedUrls.clear();
  document.querySelectorAll('.news-card.is-selected').forEach(c => c.classList.remove('is-selected'));
  document.querySelectorAll('.card-check:checked').forEach(c => c.checked = false);
  updateSelectBar();
}

function selectSearchResults() {
  const visible = filterItems();
  visible.forEach(it => state.selectedUrls.add(it.url));
  renderContent();   // 카드 재렌더해서 체크 표시
  updateSelectBar();
}

function updateSelectBar() {
  const bar = document.getElementById('select-bar');
  const count = state.selectedUrls.size;
  document.getElementById('selected-count').textContent = `${count}개 선택`;
  if (count > 0) {
    bar.classList.remove('hidden');
  } else {
    bar.classList.add('hidden');
  }

  // 검색결과 전체 선택 버튼 — 검색어 있을 때만 표시
  const btnSelectSearch = document.getElementById('btn-select-search-results');
  if (btnSelectSearch) {
    btnSelectSearch.classList.toggle('hidden', !state.search);
  }
}

function openAnalyzeModal() {
  if (state.selectedUrls.size === 0) {
    alert('먼저 카드를 선택해주세요.');
    return;
  }
  const modal = document.getElementById('analyze-modal');
  modal.classList.remove('hidden');

  // 선택 항목 미리보기
  const items = (state.data.items || []).filter(i => state.selectedUrls.has(i.url));
  document.getElementById('analyze-count').textContent = `${items.length}개 항목 선택`;
  const list = document.getElementById('analyze-preview-list');
  list.innerHTML = items.map(i => `<li>${escapeHtml(i.title)} <span class="rel-source">— ${escapeHtml(i.source)}</span></li>`).join('');

  // 모델 드롭다운 채우기
  populateModelSelect();

  // 프롬프트 기본값
  applyPromptPreset();

  // 결과 영역 초기화
  const resultWrap = document.getElementById('analyze-result-wrap');
  resultWrap.classList.add('hidden');
  document.getElementById('analyze-result').innerHTML = '';
  document.getElementById('analyze-meta').textContent = '';
}

function populateModelSelect() {
  const sel = document.getElementById('model-select');
  if (!sel) return;
  const models = MODELS[state.analyzeBackend] || [];
  sel.innerHTML = models.map(m => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.label)}</option>`).join('');

  // state.analyzeModel이 현재 백엔드에 없으면 기본값 (첫 모델)로
  const ids = models.map(m => m.id);
  if (!ids.includes(state.analyzeModel)) {
    state.analyzeModel = ids[0];
  }
  sel.value = state.analyzeModel;
  updateModelHint();
}

function updateModelHint() {
  const hintEl = document.getElementById('model-hint');
  if (!hintEl) return;
  const m = (MODELS[state.analyzeBackend] || []).find(x => x.id === state.analyzeModel);
  hintEl.textContent = m ? m.hint : '';
}

function closeAnalyzeModal() {
  document.getElementById('analyze-modal').classList.add('hidden');
}

function applyPromptPreset() {
  const preset = state.analyzePromptPreset;
  const input = document.getElementById('prompt-input');
  if (preset !== 'custom') {
    input.value = PROMPT_PRESETS[preset] || '';
  }
}

async function runAnalysis() {
  const items = (state.data.items || []).filter(i => state.selectedUrls.has(i.url));
  if (items.length === 0) {
    alert('선택된 항목이 없습니다.');
    return;
  }

  const promptInstruction = document.getElementById('prompt-input').value.trim();
  if (!promptInstruction) {
    alert('분석 요청을 입력해주세요.');
    return;
  }

  // 데이터 묶어서 프롬프트 구성
  const newsBlob = items.slice(0, 60).map((it, i) => {
    const ko = it.summary_ko || it.summary || '';
    return `${i + 1}. [${it.source}, ${(it.date || '').slice(0,10)}] ${it.title}\n   ${ko.slice(0, 300)}\n   URL: ${it.url}`;
  }).join('\n\n');

  const fullPrompt = `${promptInstruction}\n\n[분석 대상 뉴스 ${items.length}건]\n\n${newsBlob}`;

  // 본인 API 키 (옵션)
  const userKey = document.getElementById('user-api-key').value.trim();
  if (userKey) {
    try { localStorage.setItem('daibfy_user_api_key', userKey); } catch (e) {}
  }

  const headers = { 'Content-Type': 'application/json' };
  if (userKey) {
    headers['X-User-Api-Key'] = userKey;
    headers['X-User-Backend'] = state.analyzeBackend;
  }

  const runBtn = document.getElementById('btn-run-analyze');
  const resultWrap = document.getElementById('analyze-result-wrap');
  const resultEl = document.getElementById('analyze-result');
  const metaEl = document.getElementById('analyze-meta');

  runBtn.disabled = true;
  runBtn.textContent = '분석 중...';
  resultWrap.classList.remove('hidden');
  resultEl.innerHTML = '<div class="analyze-loading">🤖 모델 연결 중<span class="dots"></span></div>';
  metaEl.textContent = '';

  // v2.7.2: SSE 스트리밍 — 첫 글자가 1~2초 안에 도착, 타이핑하듯 누적
  try {
    const t0 = Date.now();
    let firstByteTime = null;
    const r = await fetch(WORKER_ENDPOINT, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        backend: state.analyzeBackend,
        model: state.analyzeModel,
        prompt: fullPrompt,
        max_tokens: 2500,
        stream: true,  // ← 스트리밍 요청
      }),
    });
    if (!r.ok) {
      // 비-스트리밍 에러 응답
      let data;
      try { data = await r.json(); } catch (e) { data = { error: `HTTP ${r.status}` }; }
      const msg = data.error || `HTTP ${r.status}`;
      if (data.limit_reached) {
        resultEl.innerHTML = `
          <div class="analyze-error">
            <strong>${escapeHtml(msg)}</strong>
            <p>본인 API 키를 입력하시면 한도 제한 없이 사용할 수 있습니다.</p>
          </div>
        `;
      } else {
        resultEl.innerHTML = `<div class="analyze-error"><strong>분석 실패</strong><p>${escapeHtml(msg)}</p></div>`;
      }
      return;
    }

    // 스트리밍 응답 처리
    const contentType = r.headers.get('Content-Type') || '';
    if (!contentType.includes('text/event-stream')) {
      // Worker가 옛 버전이면 JSON으로 폴백
      const data = await r.json();
      resultEl.innerHTML = renderMarkdown(data.result || '');
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      const usage = data.usage || {};
      metaEl.textContent = `${data.backend} · ${data.model} · ${elapsed}초 · 입력 ${usage.input_tokens || usage.prompt_tokens || '?'}토큰 / 출력 ${usage.output_tokens || usage.completion_tokens || '?'}토큰`;
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let accumulated = '';
    let meta = { backend: state.analyzeBackend, model: state.analyzeModel, used_user_key: false };
    let usage = {};
    let streamErr = null;

    resultEl.innerHTML = '<div class="analyze-stream"></div>';
    const streamEl = resultEl.querySelector('.analyze-stream');

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const evt of events) {
        const dataLine = evt.split('\n').find(l => l.startsWith('data:'));
        if (!dataLine) continue;
        const payload = dataLine.slice(5).trim();
        if (!payload) continue;
        try {
          const parsed = JSON.parse(payload);
          if (parsed.type === 'meta') {
            meta = { ...meta, ...parsed };
            if (firstByteTime === null) firstByteTime = Date.now();
            metaEl.textContent = `${meta.backend} · ${meta.model} · 응답 수신 시작…`;
          } else if (parsed.type === 'delta' && parsed.text) {
            if (firstByteTime === null) {
              firstByteTime = Date.now();
              const ttfb = ((firstByteTime - t0) / 1000).toFixed(1);
              metaEl.textContent = `${meta.backend} · ${meta.model} · TTFB ${ttfb}초 · 생성 중…`;
            }
            accumulated += parsed.text;
            streamEl.innerHTML = renderMarkdown(accumulated) + '<span class="stream-cursor">▌</span>';
            // 자동 스크롤
            resultEl.scrollTop = resultEl.scrollHeight;
          } else if (parsed.type === 'done') {
            usage = parsed.usage || {};
            meta.model = parsed.model || meta.model;
          } else if (parsed.type === 'error') {
            streamErr = parsed.error;
          }
        } catch (e) { /* incomplete chunk */ }
      }
    }

    // 완료
    streamEl.innerHTML = renderMarkdown(accumulated);
    if (streamErr) {
      streamEl.innerHTML += `<div class="analyze-error"><strong>스트림 오류</strong><p>${escapeHtml(streamErr)}</p></div>`;
    }
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    const ttfb = firstByteTime ? ((firstByteTime - t0) / 1000).toFixed(1) : '?';
    const inT = usage.input_tokens || usage.prompt_tokens || '?';
    const outT = usage.output_tokens || usage.completion_tokens || '?';
    metaEl.textContent = `${meta.backend} · ${meta.model} · 첫 응답 ${ttfb}초 / 전체 ${elapsed}초 · 입력 ${inT}토큰 / 출력 ${outT}토큰` + (meta.used_user_key ? ' · 본인 키' : '');
  } catch (e) {
    resultEl.innerHTML = `<div class="analyze-error"><strong>네트워크 오류</strong><p>${escapeHtml(e.message || String(e))}</p><p>Worker URL이 살아있는지, CORS가 허용되는지 확인하세요.</p></div>`;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = '분석 실행';
  }
}

function renderMarkdown(text) {
  if (!text) return '';
  // 매우 단순한 마크다운 → HTML (안전한 escape 후)
  let html = escapeHtml(text);
  // 코드블록 ```...```
  html = html.replace(/```([\s\S]*?)```/g, (m, p) => `<pre><code>${p}</code></pre>`);
  // 헤딩 (### / ## / #)
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // v2.7.1: 굵게 **text** → <mark> (투명 형광색 + bold)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<mark>$1</mark>');
  // 인라인 코드 `text`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 리스트 라인 (- item)
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*?<\/li>(\n|$))+/g, m => `<ul>${m}</ul>`);
  // 줄바꿈
  html = html.replace(/\n\n+/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // 빈 p, ul 안의 p 정리
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/<p>(<h\d>)/g, '$1');
  html = html.replace(/(<\/h\d>)<\/p>/g, '$1');
  html = html.replace(/<p>(<ul>)/g, '$1');
  html = html.replace(/(<\/ul>)<\/p>/g, '$1');
  html = html.replace(/<p>(<pre>)/g, '$1');
  html = html.replace(/(<\/pre>)<\/p>/g, '$1');
  return html;
}

function copyAnalyzeResult() {
  const result = document.getElementById('analyze-result').innerText;
  if (!result) return;
  navigator.clipboard.writeText(result).then(() => {
    const btn = document.getElementById('btn-copy-result');
    const orig = btn.textContent;
    btn.textContent = '✓ 복사됨';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

function cssEscape(s) {
  // CSS attribute selector safe escape (simple)
  return String(s).replace(/(["\\])/g, '\\$1');
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

// v2.7.1: **text** → <mark>text</mark> (HTML escape 후 변환)
// LLM이 핵심 키워드/문구에 **굵게** 마크업을 추가하면 투명 형광색으로 강조
function escapeHtmlWithMark(text) {
  const escaped = escapeHtml(text);
  // **...** 패턴 (개행 제외) → <mark>...</mark>
  return escaped.replace(/\*\*([^*\n]+?)\*\*/g, '<mark>$1</mark>');
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
