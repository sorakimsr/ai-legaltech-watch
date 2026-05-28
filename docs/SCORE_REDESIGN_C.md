# Score Function 재설계 — Plan C (다단계 점수)

작성일: 2026-05-28
작성자: 사용자 + Claude 협업
배경: 사용자 지적 — "강제 조정(SUPER_BOOST·floor·키워드 추가)이 끝도 없다. 애초에 중요도 산정 기준 자체를 보완해야 한다."

---

## 1. 현재 (v6.15.22 = A) 구조 한계

### A 구조 (LLM dominant)
```
base 30
+ keyword hit signals (DECISION/REGULATORY/MARKET/LEGAL × strength × 가중치)  → ~30점
+ 카테고리 보너스 (legaltech +16, models +10 ...)                            → 0~30점
+ recency (24h +10 / 72h +5 / 168h +2)                                       → 0~10점
+ 본문 깊이/제목 길이 등 micro                                                → ±3점
+ persona_score × 8 (LLM 0~10)                                               → 0~80점 (dominant)
+ bookmark_bonus                                                              → 0~12점
+ SUPER_BOOST_FLOOR 85 / 법령 78 (hybrid 안전망)
- NEGATIVE caps / PR caps
─────────────────────────────────────────
최종 score = max(0, min(150, sum))
```

### A의 남은 문제
1. **단계 책임이 섞여 있음** — keyword가 1차 cut도 하고 score에도 기여. LLM 평가와 keyword 점수가 단순 합산되어 디버깅 어려움.
2. **enrich 못 받은 기사 fallback이 keyword 의존** — keyword 미흡한 짧은 본문은 SUPER_BOOST에 안 잡히면 cut-off 못 넘음.
3. **카테고리 보너스 + persona 가산이 중복** — legaltech 카테고리(+16)도 받고 persona 9점(+72)도 받으면 같은 신호 이중 가산.
4. **점수 cap 150이 점수 의미 불투명화** — 130점도 150점도 시각적으로 비슷.

---

## 2. C 구조 — 다단계 점수

### 핵심 원칙
- **단계별 책임 명확 분리**
  - 1단계 = noise filter (PR·광고·연예·정치 drop)
  - 2단계 = persona 평가 (LLM이 사용자 가치 판단)
  - 3단계 = bookmark/SUPER_BOOST 검증 보정 (LLM 변동성 안전망)
- **각 단계의 출력은 다음 단계 입력일 뿐 합산 X**
- **점수 의미를 사용자가 직관적으로 해석 가능하게**

### 구조도
```
[1단계 — Filter (keyword 기반, 빠른 cut)]
   ├─ PR pattern detect → drop
   ├─ NEGATIVE_SIGNALS 매칭 + total_signal < 0.5 → drop
   ├─ AI gate (ai_mentions=0 + no AI 카테고리 + no SUPER_BOOST) → drop
   ├─ Filter score 20점 (PASS) / 0점 (FAIL → drop)
   └─ output: filter_passed: bool

[2단계 — Persona Evaluation (LLM dominant)]
   ├─ enrich_with_llm.py가 Haiku 4.5로 평가 (이미 운영 중)
   ├─ persona_score (0~10), persona_reason (1문장)
   ├─ persona_score × 10 = persona_value (0~100)
   ├─ persona_score = N/A (enrich 못 받음) → keyword 보조 점수로 fallback
   │     · keyword signal 강도 기반 추정 persona (0~6, dominant cap)
   └─ output: persona_value (0~100)

[3단계 — Verification & Adjustment]
   ├─ bookmark_match: 사용자 북마크 ENTITIES/KEYWORDS/SOURCES 매칭
   │     · 매칭 시 persona_value +0~+12 가산 (검증 보너스)
   ├─ SUPER_BOOST (사용자 명시 어젠다 매칭)
   │     · 매칭 시 persona_value floor 85 보장 (LLM이 평가 못한 경우 보호)
   ├─ 법령 매칭 (AI 기본법·정보통신망법·개인정보보호법)
   │     · 매칭 시 floor 78
   ├─ 시간 가중치 (24h 이내만 +5, 그 외 0) — 보조
   └─ output: final_score (0~120)

[최종]
   score = filter_passed ? final_score : 0
   cut-off: TOP_DAILY=30 / TOP_WEEKLY=50 / TOP_MONTHLY=80 (현행 유지)
```

### 점수 의미 (사용자 직관적 해석)
- **90~120**: 의사결정 직접 영향 — 시사점 카드 1-3번 후보 (LLM 9-10점 + 보너스)
- **70~89**: 검토·논의 가치 — 시사점 카드 4-10번 (LLM 7-8점)
- **40~69**: 참고 (LLM 4-6점)
- **20~39**: 약한 관련성 — 후보 풀 진입 가능하나 카드화 우선순위 낮음
- **0~19 / drop**: noise filter 거름

---

## 3. 단계별 상세 설계

### 1단계 Filter
**파일**: `scripts/common.py` `filter_item(title, summary, categories, source)`

```python
def filter_item(title, summary, categories, source) -> bool:
    # PR detector
    pr_verdict, _ = classify_pr_pattern(title, summary)
    if pr_verdict == 'block': return False
    
    # AI gate (AI 무관 기사 drop, papers/legaltech 등 + SUPER_BOOST 면제)
    text = _normalize_text_for_match(title + " " + summary)
    ai_mentions = count_ai_mentions(text)
    ai_intrinsic = {"papers", "legaltech", "models", "coding", "infra"}
    if ai_mentions == 0:
        if not any(c in ai_intrinsic for c in categories) and not _has_super_boost(text):
            return False
    
    # NEGATIVE strong cap
    neg_hits = count_signal_hits(text, NEGATIVE_SIGNALS)
    total_sig = sum_signal_strength(text)
    if neg_hits >= 1 and total_sig < 0.3:
        return False
    
    return True
```

**의도**: 1단계는 0/1 결정만. score 점수에 기여하지 않음.

### 2단계 Persona Evaluation
**파일**: `scripts/enrich_with_llm.py` (이미 운영 중 — Phase A에서 강화한 prompt 사용)

- persona_score: 0~10 정수 (Haiku 4.5 평가)
- persona_value = persona_score × 10 (0~100)
- enrich 못 받은 기사 fallback:
  - keyword signal 기반 추정 (LEGAL/REGULATORY/DECISION/MARKET 강도 → 0~6 추정 persona)
  - Why 6 cap: enrich 받은 기사의 LLM 평가보다 낮게 평가해야 LLM 통과 기사가 우선

### 3단계 Verification
**파일**: `scripts/common.py` `compute_final_score(persona_value, text, categories, bookmark_match, ...)`

```python
def compute_final_score(persona_value, text, categories, bookmark_match, super_boost, has_law):
    score = persona_value
    
    # bookmark 검증 보너스
    if bookmark_match:
        score += min(12, bookmark_match)
    
    # SUPER_BOOST floor (LLM 평가 못한 경우 안전망)
    if super_boost and score < 85:
        score = 85
    
    # 법령 floor
    if has_law and score < 78:
        score = 78
    
    # recency (보조)
    if recent_24h:
        score += 5
    
    return max(0, min(120, score))
```

---

## 4. 마이그레이션 계획

### Phase A 운영 (현재 → 1주)
- v6.15.22 운영 중 (LLM ×8, SUPER_BOOST, 법령 floor 등 hybrid)
- 관찰 지표 수집:
  - persona_score 분포 (실제 LLM 출력 0~10 히스토그램)
  - persona_score=9-10 받은 기사 vs cut-off 통과 기사 일치율
  - 사용자 북마크 추가 패턴 (Phase A의 LLM 평가가 잘 맞는가)

### Phase B 시뮬레이션 (1주차 후반)
- 수집된 persona_score 분포로 C의 cut-off/floor 숫자 결정
  - persona_value × 10이 적절한가? × 12로 더 spread?
  - bookmark cap +12가 적절한가?
- 기존 빌드 데이터로 C 함수 계산 → 시사점 카드 변화 확인

### Phase C 마이그레이션 (1.5주차)
- score_item 함수를 filter_item + persona_value + compute_final_score 3단계 분리
- 기존 score_item은 deprecated, 한 빌드 동시 출력 (A 점수 vs C 점수 diff 로그)
- 시사점 카드 1-2회 빌드 확인 후 C 단독 전환

### Phase D 정리 (2주차)
- 키워드 BLACKLIST 외 SCORE_LEGAL_SIGNALS·DECISION_SIGNALS 등 다수 시그널 리스트 정리
- 카테고리 보너스 제거 (LLM 평가에 통합됨)
- SUPER_BOOST는 floor 안전망으로만 유지

---

## 5. 관찰 지표 (A 운영 중 수집)

### 매 빌드 로그 추가 항목 (`enrich_with_llm.py`)
```python
print(f"[persona] {len(enriched)} items, "
      f"persona_score dist: {Counter(it['persona_score'] for it in enriched)}")
```

### 1주 후 분석 query
```python
# 1. persona_score 분포
ps_dist = Counter(it.get('persona_score') for it in items if it.get('persona_score') is not None)
print(ps_dist)

# 2. persona_score 9-10 받은 기사 중 시사점 카드 진입 비율
ps_high = [it for it in items if it.get('persona_score', 0) >= 9]
card_urls = set(c['url'] for card in strategy_cards for c in card.get('citations', []))
in_card = sum(1 for it in ps_high if it.get('url') in card_urls)
print(f"persona 9-10: {len(ps_high)} 중 카드 진입 {in_card}")

# 3. AI×법조 어젠다 카드 비율
ai_legal_cards = [c for c in strategy_cards 
                  if _has_super_boost(c.get('title','').lower() + c.get('body','').lower())]
print(f"AI×법조 카드: {len(ai_legal_cards)} / 전체 {len(strategy_cards)}")
```

---

## 6. 결정해야 할 숫자 (1주 후)

| 항목 | A (현재) | C 후보 | 결정 근거 |
|---|---|---|---|
| persona_value 가중치 | ×8 = max +80 | ×10 = max +100 | persona_score 분포 보고 결정 |
| keyword filter 점수 | 0~50점 가산 | 0/1 binary | C는 점수 기여 X |
| SUPER_BOOST floor | 85 | 85 또는 90 | persona 9점 비율 보고 결정 |
| 법령 floor | 78 | 78 | 유지 |
| 점수 cap | 150 | 120 | 의미 직관성 위해 낮춤 |
| AI gate | 카테고리 면제 + SUPER_BOOST | 동일 | 유지 |

---

## 7. 리스크 & 대비

| 리스크 | 대비 |
|---|---|
| LLM 변동성 — 같은 기사 ±1점 차이 | SUPER_BOOST floor + 법령 floor를 안전망으로 유지 |
| enrich 못 받은 기사 fallback 약함 | keyword 기반 추정 persona (0~6 cap) 적용 |
| 빌드 1-2회 시사점 품질 일시 저하 | A·C 동시 출력 단계(Phase C)에서 diff 로그로 사전 검증 |
| 마이그레이션 중 카테고리 보너스 제거로 점수 분포 변동 | Phase C에서 점수 분포 비교 → cut-off 조정 |

---

## 8. 다음 작업 (이 문서 작성 후)

- [x] Phase A 적용 — v6.15.22 push (persona ×8 + prompt 강화)
- [ ] 1주 운영 (2026-05-28 ~ 2026-06-04)
- [ ] persona_score 분포 분석 → C 숫자 결정
- [ ] Phase B 시뮬레이션 (기존 데이터로 C 점수 산출, 시사점 카드 변화 확인)
- [ ] Phase C 마이그레이션 (A·C 동시 출력 → C 단독 전환)
- [ ] Phase D 정리 (불필요 키워드 리스트 정리, 카테고리 보너스 제거)
