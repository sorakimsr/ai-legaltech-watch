// AI & Legaltech Watch — 공통 유틸리티
// v6.0 (P2-3): app.js에서 분리. HTML escape, 마크다운 렌더, 날짜 포맷 등 순수 함수만 모음.
//
// 로드 순서: <script src="app.util.js"> 가 <script src="app.js"> 앞에 있어야 함.
// 의존성: 없음 (다른 파일을 참조하지 않음).

// ============================================================================
// HTML / 속성 escape
// ============================================================================

function escapeHtml(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function escapeAttr(s) {
  return (s || '').replace(/'/g, '&apos;').replace(/"/g, '&quot;');
}

function cssEscape(s) {
  // CSS attribute selector safe escape (simple)
  return String(s).replace(/(["\\])/g, '\\$1');
}

// ============================================================================
// 마크다운 렌더링 — LLM 출력을 안전한 HTML로 변환
// ============================================================================
// v3.10: 강조 제거 대상 — 회사명·논문명·기법명·단순 키워드 (analyze_papers.py와 동기화)
const UNBOLD_PROPER_NOUNS = [
  // AI 회사·기관
  'OpenAI', 'Anthropic', 'Sequoia Capital', 'Google', 'DeepMind', 'Meta',
  'Microsoft', 'NVIDIA', 'Apple', 'Amazon', 'AWS',
  '수출입은행', 'KB금융', '신한금융', '하나금융', '우리금융',
  // 논문 제목·프로토콜·프레임워크
  'Foundation Protocol', 'AAIA-RAG-LEGAL', 'Redrawing the AI Map',
  'MAS-Orchestra', 'EVE-Agent', 'Ontological Knowledge Blocks', 'CHRONOS',
  'Query-Adaptive Semantic Chunking', 'Latent Cache Flow', 'LFRAG', 'BOHM',
  'Energy per Successful Goal', 'AutoResearch AI',
  'Cognitive offloading', 'Inferential Privacy Leakage',
  // 단순 키워드 — 사용자 정책상 음영 부적절
  'RAG', 'RAG(검색-증강 생성)',
  '멀티에이전트 시스템', '멀티에이전트 협업 체계', '멀티에이전트(Multi-Agent System)',
  'Multi-Agent System',
  '책임 경계', '책임 경계(Accountability Boundary)', 'Accountability Boundary',
  '에이전트형 AI', '에이전트형 AI의 운영 효율화',
  '온프레미스', '온프레미스(on-premise)', 'on-premise',
  '금융 시장 모니터링', '의료 AI',
  // 금액·수치
  '40억 달러', '110억 달러', '수십억 달러', '수백억 원'
];

function _escapeRegex(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function unboldProperNouns(text) {
  if (!text) return text;
  let out = text;
  for (const name of UNBOLD_PROPER_NOUNS) {
    // **...NAME...** 전체 매칭, 강조만 풀고 이름은 보존
    const pat = new RegExp('\\*\\*([^*\\n]{0,40}?' + _escapeRegex(name) + '[^*\\n]{0,15}?)\\*\\*', 'g');
    out = out.replace(pat, '$1');
  }
  // 길이 cap — **...**가 6자 이하면 단순 키워드일 가능성 큼
  out = out.replace(/\*\*([^*\n]{1,6})\*\*/g, '$1');
  return out;
}

// v3.14: papers narrative 4개 구조 라벨 — bold만 적용 (음영 X)
const PAPERS_NARRATIVE_LABELS = [
  '한 줄 요약',
  '1) 무엇이 부상하고 있는가',
  '2) 한국 실무자에게 이 흐름이 무슨 의미인가',
  '3) 산업 적용 흐름'
];

function renderMarkdown(text, opts) {
  if (!text) return '';
  opts = opts || {};
  // v2.8.6: 빈 헤더 라인(`#` 또는 `## ` 등만 있고 텍스트 없음) 제거
  text = text.replace(/^\s*#{1,6}\s*$/gm, '');
  // v3.10: 'N) ' 패턴 (1)~9)) 앞에 빈 줄 강제 삽입 — LLM이 인라인으로 이어쓴 경우에도 단락 분리
  //   - 앞 문자가 '.', '(', '0~9' 가 아닐 때만 (3.1) / (1) / 10) 같은 케이스 회피)
  //   - papers narrative: '한 줄 요약 ... 1) 무엇이... 2) 한국 실무자에게... 3) 산업 적용 흐름...'
  text = text.replace(/([^\n.(\d])\s+([1-9]\)\s)/g, '$1\n\n$2');
  // v3.10: 회사명·논문명·단순 키워드의 **강조** 제거 (frontend 후처리 — 캐시된 데이터에도 즉시 적용)
  text = unboldProperNouns(text);
  // v3.14: papers narrative 구조 라벨 강제 bold (mark 음영 X, font-weight만 강조)
  //   - opts.inlineHeaders가 켜진 경우 (papers narrative 전용)
  //   - 'PAPERS_NARRATIVE_LABELS' 4개 라벨을 placeholder로 감싸고, escape 후 <strong class="inline-h">로 변환
  if (opts.inlineHeaders) {
    for (const label of PAPERS_NARRATIVE_LABELS) {
      const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      // 이미 placeholder 안에 있으면 다시 감싸지 않음
      text = text.replace(new RegExp('(?<!__INLINE_HEADER_OPEN__)' + escapedLabel, 'g'),
        '__INLINE_HEADER_OPEN__' + label + '__INLINE_HEADER_CLOSE__');
    }
  }
  // v3.2: inlineHeaders 옵션 — 헤더를 본문 사이즈 + bold 인라인으로 표시
  //   `## 한 줄 요약` → `<strong class="inline-h">한 줄 요약</strong>` (본문 사이즈, bold)
  //   사용자 정책: 헤더 폰트 사이즈 = 본문, 음영(mark) 외 일반 텍스트는 bold X
  if (opts.inlineHeaders || opts.stripHeaders) {
    text = text.replace(/^\s*#{1,6}\s+(.+)$/gm, (m, p) => `__INLINE_HEADER_OPEN__${p}__INLINE_HEADER_CLOSE__`);
  }
  // 매우 단순한 마크다운 → HTML (안전한 escape 후)
  let html = escapeHtml(text);
  // inline header placeholder → strong.inline-h
  html = html.replace(/__INLINE_HEADER_OPEN__/g, '<strong class="inline-h">');
  html = html.replace(/__INLINE_HEADER_CLOSE__/g, '</strong>');
  // 코드블록 ```...```
  html = html.replace(/```([\s\S]*?)```/g, (m, p) => `<pre><code>${p}</code></pre>`);
  // v2.7.9: LLM이 \n 없이 inline으로 ## 헤더를 출력한 경우 강제 줄바꿈 삽입
  html = html.replace(/([^\n])\s*(#{1,3} )/g, '$1\n\n$2');
  // 헤딩 (### / ## / #) — inlineHeaders 옵션 안 켜진 경우만
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

// v2.7.1: **text** → <mark>text</mark> (HTML escape 후 변환)
// LLM이 핵심 키워드/문구에 **굵게** 마크업을 추가하면 투명 형광색으로 강조
function escapeHtmlWithMark(text) {
  if (!text) return '';
  // v3.2: 빈 헤더 라인 제거 + inline 헤더 변환 (시사점 daily/weekly/monthly 모두 적용)
  let t = text.replace(/^\s*#{1,6}\s*$/gm, '');
  // v3.10: 회사명·논문명·단순 키워드 강조 제거 (mark 변환 전에 처리)
  t = unboldProperNouns(t);
  // `# 헤더` → __INLINE_HEADER_OPEN__텍스트__INLINE_HEADER_CLOSE__ (escapeHtml 통과 후 변환)
  t = t.replace(/^\s*#{1,6}\s+(.+)$/gm, (m, p) => `__INLINE_HEADER_OPEN__${p}__INLINE_HEADER_CLOSE__`);
  const escaped = escapeHtml(t)
    .replace(/__INLINE_HEADER_OPEN__/g, '<strong class="inline-h">')
    .replace(/__INLINE_HEADER_CLOSE__/g, '</strong>');
  // **...** 패턴 (개행 제외) → <mark>...</mark>
  return escaped.replace(/\*\*([^*\n]+?)\*\*/g, '<mark>$1</mark>');
}

// ============================================================================
// 날짜 / 기타 유틸
// ============================================================================

function formatKoreanDate(d) {
  if (!d || isNaN(d)) return '날짜 없음';
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  return `${yyyy}-${mm}-${dd} (${days[d.getDay()]})`;
}

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
