// AI & Legaltech Watch v2.1 — 관점·뷰 + 주제 필터 분리

const state = {
  data: null,
  // view = 사이드바 (관점·뷰)
  view: 'latest',       // latest | top | insights | today | strategy | sources
  // category = 카테고리 탭 (주제)
  category: 'all',
  search: '',
  dateFilter: 'all',
  langFilter: 'all',
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
  latest:    { title: '최신순 뉴스', hint: '최근 30일 · 발행일 최신순' },
  top:       { title: '중요도 TOP', hint: 'AI 중요도 점수 상위 항목 (회사·금액·신선도·카테고리)' },
  insights:  { title: '시사점 있는 항목', hint: 'Claude가 전략·기획·AI 업무 관점 시사점을 도출한 항목' },
  today:     { title: '오늘 추가됨', hint: '오늘(KST) 발행/업데이트된 항목' },
  strategy:  { title: '전략·기획 시사점', hint: '오늘 흐름을 종합한 LLM 자동 생성 카드' },
  sources:   { title: '소스 현황', hint: '활성·유휴·오류 상태' },
};

async function init() {
  try {
    const res = await fetch('./data/news.json?t=' + Date.now());
    state.data = await res.json();
  } catch (e) {
    console.error('데이터 로드 실패:', e);
    state.data = { items: [], strategy: [], sources: [], stats: {}, last_updated: null };
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
    const d = new Date(last);
    el.textContent = `최근 갱신: ${formatKoreanDate(d)} · 매일 오전 6시(KST) 자동 갱신`;
  } else {
    el.textContent = '아직 갱신 정보 없음';
  }
  const buildInfo = document.getElementById('last-build-info');
  const bc = state.data.build_count;
  if (bc) buildInfo.textContent = `Build #${bc} · © 2026`;
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
  // 오늘 신규 카운트 (first_seen이 오늘인 항목)
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
      <span class="stat-hint">RSS · arXiv · 국내</span>
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

  // 뷰 적용된 전체 풀에서 카운트 계산
  const pool = applyViewFilter(state.data.items || []);
  const counts = {};
  pool.forEach(item => {
    (item.categories || []).forEach(c => {
      counts[c] = (counts[c] || 0) + 1;
    });
  });

  bar.innerHTML = CATEGORIES.map(cat => {
    const cnt = cat.id === 'all' ? pool.length : (counts[cat.id] || 0);
    const active = cat.id === state.category ? 'active' : '';
    return `
      <button class="cat-chip ${active}" data-category="${cat.id}">
        <span>${escapeHtml(cat.label)}</span>
        <span class="cat-count">${cnt}</span>
      </button>
    `;
  }).join('');

  bar.querySelectorAll('.cat-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      state.category = chip.dataset.category;
      renderCategoryBar();
      renderContent();
    });
  });
}

// 사이드바 뷰별 필터링 (카테고리·검색·기타 무관)
function applyViewFilter(items) {
  let arr = items.slice();
  switch (state.view) {
    case 'latest':
      arr.sort((a, b) => new Date(b.date) - new Date(a.date));
      break;
    case 'top':
      arr.sort((a, b) => (b.score || 0) - (a.score || 0));
      // 상위 100개로 제한해서 진짜 중요한 것만
      arr = arr.slice(0, 100);
      break;
    case 'insights':
      arr = arr.filter(i => i.insight_ko);
      arr.sort((a, b) => new Date(b.date) - new Date(a.date));
      break;
    case 'today':
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      arr = arr.filter(i => new Date(i.date) >= todayStart);
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
    newsGrid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <div class="empty-title">조건에 맞는 항목이 없습니다</div>
        <div class="empty-desc">사이드바·카테고리·검색어를 바꿔보세요.</div>
      </div>
    `;
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
      const blob = [
        i.title, i.summary, i.summary_ko, i.insight_ko, i.source,
        ...(i.categories || []),
      ].filter(Boolean).join(' ').toLowerCase();
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

  // 카테고리 최대 2개만 표시 (UI 정돈)
  const cats = (item.categories || []).slice(0, 2).map(c => {
    const label = (CATEGORIES.find(x => x.id === c) || { label: c }).label;
    return `<span class="card-category cat-${escapeHtml(c)}">${escapeHtml(label)}</span>`;
  }).join('');

  // 영문 표시: 영문 카드인데 한국어 요약 없으면 영문 그대로
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

  const insightBlock = item.insight_ko ? `
    <div class="card-insight">
      <span class="insight-label">시사점</span>
      ${escapeHtml(item.insight_ko)}
    </div>
  ` : '';

  const relCount = item.related_count || 0;
  const relBadge = relCount > 0 ? `
    <span class="related-badge" title="유사 뉴스 ${relCount}건">+${relCount} 매체 ▾</span>
  ` : '';
  const relDetail = relCount > 0 && item.related ? `
    <div class="related-detail">
      ${item.related.map(r => `
        <div class="rel-item">
          <span class="rel-source">${escapeHtml(r.source)}</span>
          <a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>
        </div>
      `).join('')}
    </div>
  ` : '';

  const aiBadge = item.llm_enriched ? '<span class="ai-badge">AI 분석</span>' : '';
  const langBadge = isEnglish ? '<span class="lang-badge">EN</span>' : '';

  // 오늘 신규 배지 — first_seen이 오늘(KST)인 항목
  const newBadge = isNewToday(item) ? '<span class="new-badge">NEW</span>' : '';

  return `
    <article class="news-card">
      ${aiBadge}
      <div class="card-top">
        <div style="display:flex;gap:6px;align-items:center;">
          <span class="score-badge ${scoreClass}">${escapeHtml(scoreLabel)}</span>
          ${newBadge}
        </div>
        <div style="display:flex;gap:6px;align-items:center;">
          ${langBadge}
          ${relBadge}
          <span class="date-text">${escapeHtml(dateStr)}</span>
        </div>
      </div>
      <div class="card-cats">${cats}</div>
      <h3 class="card-title">
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>
      </h3>
      ${summaryHtml}
      ${insightBlock}
      ${relDetail}
      <div class="card-bottom">
        <span class="card-source">
          <span class="card-source-icon">${escapeHtml(sourceInitial)}</span>
          ${escapeHtml(item.source || '')}
        </span>
        <div class="card-actions">
          <a class="icon-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" title="원문 보기">↗</a>
        </div>
      </div>
    </article>
  `;
}

function renderStrategy() {
  const root = document.getElementById('strategy-cards');
  const items = state.data.strategy || [];
  if (items.length === 0) {
    root.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎯</div>
        <div class="empty-title">전략 시사점이 아직 없습니다</div>
        <div class="empty-desc">매일 수집된 뉴스를 바탕으로 LLM이 자동 생성합니다.</div>
      </div>
    `;
    return;
  }
  root.innerHTML = items.map(s => {
    const citations = Array.isArray(s.citations) ? s.citations : [];
    const citationsBlock = citations.length > 0 ? `
      <details class="strategy-citations">
        <summary>근거 ${citations.length}건 ▾</summary>
        <ol class="citation-list">
          ${citations.map(c => `
            <li>
              <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">
                ${escapeHtml(c.title)}
              </a>
              <span class="citation-meta">— ${escapeHtml(c.source)} · ${escapeHtml(c.date)}</span>
            </li>
          `).join('')}
        </ol>
      </details>
    ` : '';

    return `
      <div class="strategy-card">
        <div class="strat-tag">${escapeHtml(s.tag || 'TREND')}</div>
        <h3>${escapeHtml(s.title || '')}</h3>
        <p>${escapeHtml(s.body || '')}</p>
        <div class="strategy-action">
          <span class="action-label">ACTION</span>
          ${escapeHtml(s.action || '')}
        </div>
        ${citationsBlock}
      </div>
    `;
  }).join('');
}

function renderSourcesView() {
  const root = document.getElementById('sources-table');
  const sources = state.data.sources || [];
  if (sources.length === 0) {
    root.innerHTML = '<div class="empty-state"><div class="empty-icon">🔗</div><div class="empty-title">소스 정보가 없습니다</div></div>';
    return;
  }

  const byStatus = sources.reduce((acc, s) => {
    acc[s.status] = (acc[s.status] || 0) + 1;
    return acc;
  }, {});

  const totalCount = sources.reduce((sum, s) => sum + (s.count || 0), 0);

  const rows = sources.map(s => {
    const statusBadge = `<span class="badge-${escapeHtml(s.status)}">${escapeHtml(s.status === 'active' ? 'Active' : s.status === 'error' ? 'Error' : 'Idle')}</span>`;
    return `
      <tr>
        <td class="src-name">${escapeHtml(s.name)}</td>
        <td>${statusBadge}</td>
        <td>${s.count || 0}</td>
        <td style="color:#6b7280;font-size:11px;">${escapeHtml(s.url || '')}</td>
      </tr>
    `;
  }).join('');

  root.innerHTML = `
    <div class="sources-table-wrap">
      <h3>소스 현황 (총 ${sources.length}개 · 활성 ${byStatus.active || 0}개 · 수집 ${totalCount}건)</h3>
      <table class="src-table">
        <thead>
          <tr><th>소스</th><th>상태</th><th>이번 빌드</th><th>URL</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function bindEvents() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      state.view = item.dataset.view;
      state.category = 'all';
      renderContent();
    });
  });

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

function isNewToday(item) {
  const fs = item.first_seen || item.date;
  if (!fs) return false;
  try {
    const dt = new Date(fs);
    if (isNaN(dt)) return false;
    const now = new Date();
    // KST 기준 오늘
    const todayKey = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0');
    const fsKey = dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0') + '-' + String(dt.getDate()).padStart(2,'0');
    return todayKey === fsKey;
  } catch (e) {
    return false;
  }
}

function escapeHtml(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
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
