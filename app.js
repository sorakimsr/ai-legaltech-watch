// AI & Legaltech Watch v2 — 프론트엔드 로직

const state = {
  data: null,
  view: 'news',         // news | papers | legaltech | domestic | strategy | sources
  category: 'all',
  search: '',
  sort: 'date',         // date | score | source
  dateFilter: 'all',
  langFilter: 'all',    // all | ko | en
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

// ===== 초기화 =====
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
  if (bc) {
    buildInfo.textContent = `Build #${bc} · © 2026`;
  }
}

function renderStats() {
  const row = document.getElementById('stat-row');
  if (state.view !== 'news') {
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

  const backendLabel = {
    'claude-cli': 'Claude CLI',
    'anthropic': 'Anthropic SDK',
    'openai': 'OpenAI SDK',
    'none': '비활성',
  }[backend] || backend;

  row.innerHTML = `
    <div class="stat-card accent">
      <span class="stat-label">전체 항목</span>
      <span class="stat-value">${total}</span>
      <span class="stat-hint">최근 30일 수집</span>
    </div>
    <div class="stat-card success">
      <span class="stat-label">AI 분석 완료</span>
      <span class="stat-value">${enriched}</span>
      <span class="stat-hint">한국어 요약·시사점 포함</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">유사 뉴스 병합</span>
      <span class="stat-value">${withRelated}</span>
      <span class="stat-hint">중복 자동 그룹화</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">활성 소스</span>
      <span class="stat-value">${activeSrc} / ${sources.length}</span>
      <span class="stat-hint">RSS · arXiv · 국내 매체</span>
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
  if (state.view === 'strategy' || state.view === 'sources') {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';

  const counts = countByCategory();
  bar.innerHTML = CATEGORIES.map(cat => {
    const cnt = cat.id === 'all'
      ? (state.data.items || []).length
      : (counts[cat.id] || 0);
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

function countByCategory() {
  const counts = {};
  (state.data.items || []).forEach(item => {
    (item.categories || []).forEach(c => {
      counts[c] = (counts[c] || 0) + 1;
    });
  });
  return counts;
}

// ===== 메인 컨텐츠 렌더 =====
function renderContent() {
  const newsGrid = document.getElementById('news-grid');
  const stratView = document.getElementById('strategy-view');
  const sourcesView = document.getElementById('sources-view');
  const controlsRow = document.querySelector('.controls-row');
  const statRow = document.getElementById('stat-row');
  const title = document.getElementById('topbar-title');

  // 뷰별 표시 조정
  newsGrid.classList.add('hidden');
  stratView.classList.add('hidden');
  sourcesView.classList.add('hidden');
  controlsRow.style.display = 'flex';
  statRow.style.display = 'grid';

  if (state.view === 'strategy') {
    stratView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    statRow.style.display = 'none';
    title.textContent = '전략·기획 시사점';
    renderStrategy();
    return;
  }
  if (state.view === 'sources') {
    sourcesView.classList.remove('hidden');
    controlsRow.style.display = 'none';
    statRow.style.display = 'none';
    title.textContent = '소스 현황';
    renderSourcesView();
    return;
  }

  newsGrid.classList.remove('hidden');
  const titles = {
    news: '뉴스 통합 수집',
    papers: 'AI 논문 동향',
    legaltech: '리걸테크 모니터링',
    domestic: '국내 동향',
  };
  title.textContent = titles[state.view] || '뉴스 통합 수집';

  renderCategoryBar();
  renderStats();

  const filtered = filterItems();
  if (filtered.length === 0) {
    newsGrid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <div class="empty-title">조건에 맞는 항목이 없습니다</div>
        <div class="empty-desc">검색어를 바꾸거나 카테고리를 '전체'로 변경해보세요.</div>
      </div>
    `;
    return;
  }
  newsGrid.innerHTML = filtered.map(renderCard).join('');

  // related 토글
  newsGrid.querySelectorAll('.related-badge').forEach(b => {
    b.addEventListener('click', e => {
      const detail = e.currentTarget.closest('.news-card').querySelector('.related-detail');
      if (detail) detail.classList.toggle('open');
    });
  });
}

function filterItems() {
  let items = (state.data.items || []).slice();

  if (state.view === 'papers') {
    items = items.filter(i => (i.categories || []).includes('papers'));
  } else if (state.view === 'legaltech') {
    items = items.filter(i => (i.categories || []).includes('legaltech'));
  } else if (state.view === 'domestic') {
    items = items.filter(i => (i.categories || []).includes('domestic') || i.lang === 'ko');
  }

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

  if (state.sort === 'date') {
    items.sort((a, b) => new Date(b.date) - new Date(a.date));
  } else if (state.sort === 'score') {
    items.sort((a, b) => (b.score || 0) - (a.score || 0));
  } else if (state.sort === 'source') {
    items.sort((a, b) => (a.source || '').localeCompare(b.source || ''));
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

// ===== 카드 =====
function renderCard(item) {
  const score = item.score || 0;
  const scoreClass = score >= 80 ? 'high' : score >= 65 ? 'mid' : 'low';
  const scoreLabel = score > 0 ? `중요도 ${score}` : '신규';
  const dateStr = formatKoreanDate(new Date(item.date));
  const sourceInitial = (item.source || '?').charAt(0).toUpperCase();

  // 카테고리 칩 (최대 3개)
  const cats = (item.categories || []).slice(0, 3).map(c => {
    const label = (CATEGORIES.find(x => x.id === c) || { label: c }).label;
    return `<span class="card-category cat-${escapeHtml(c)}">${escapeHtml(label)}</span>`;
  }).join('');

  // 요약: 한국어 우선
  const summary = item.summary_ko || item.summary || '';
  const summaryClass = item.summary_ko ? 'has-ko' : '';

  // 시사점 (LLM 생성)
  const insightBlock = item.insight_ko ? `
    <div class="card-insight">
      <span class="insight-label">시사점</span>
      ${escapeHtml(item.insight_ko)}
    </div>
  ` : '';

  // related
  const relCount = item.related_count || 0;
  const relBadge = relCount > 0 ? `
    <span class="related-badge" title="유사 뉴스 ${relCount}건">중복 ${relCount}건 ▾</span>
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

  return `
    <article class="news-card">
      ${aiBadge}
      <div class="card-top">
        <span class="score-badge ${scoreClass}">${escapeHtml(scoreLabel)}</span>
        <div style="display:flex;gap:6px;align-items:center;">
          ${relBadge}
          <span class="date-text">${escapeHtml(dateStr)}</span>
        </div>
      </div>
      <div class="card-cats">${cats}</div>
      <h3 class="card-title">
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>
      </h3>
      ${summary ? `<div class="card-summary ${summaryClass}">${escapeHtml(summary)}</div>` : ''}
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

// ===== 전략 카드 =====
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
  root.innerHTML = items.map(s => `
    <div class="strategy-card">
      <div class="strat-tag">${escapeHtml(s.tag || 'TREND')}</div>
      <h3>${escapeHtml(s.title || '')}</h3>
      <p>${escapeHtml(s.body || '')}</p>
      <div class="strategy-action">
        <span class="action-label">ACTION</span>
        ${escapeHtml(s.action || '')}
      </div>
    </div>
  `).join('');
}

// ===== 소스 현황 =====
function renderSourcesView() {
  const root = document.getElementById('sources-table');
  const sources = state.data.sources || [];
  if (sources.length === 0) {
    root.innerHTML = '<div class="empty-state"><div class="empty-icon">🔗</div><div class="empty-title">소스 정보가 없습니다</div></div>';
    return;
  }

  // 상태별 카운트
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
          <tr><th>소스</th><th>상태</th><th>이번 빌드 수집</th><th>URL</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

// ===== 이벤트 =====
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

  document.querySelectorAll('.seg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.sort = btn.dataset.sort;
      renderContent();
    });
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

// ===== 유틸 =====
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
