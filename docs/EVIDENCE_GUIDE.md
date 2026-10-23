# TripPilot 체크리스트 증빙자료 가이드 (EVIDENCE GUIDE)

> **AI 코어 프로젝트 2회차 — TripPilot 자체 점검 및 상호 점검 27대 증빙자료 전수 가이드**  
> 본 문서는 셀프·상호 체크리스트의 27개 전 점검 항목에 대응하는 증빙 캡처 이미지의 **정확한 파일 경로, 저장 디렉터리, UI/코드 위치 및 재현 방법(How to Reproduce)**을 상세히 안내합니다.

---

## 1. 개요 및 표준 경로 규칙

### 1.1 표준 디렉터리 구조
모든 증빙 스크린샷은 검증 평가자의 접근성과 무결성을 위해 `docs/images/proof/` 디렉터리 하위에 번호순으로 표준화되어 관리됩니다.

```bash
ai_pjt_2_trippilot/
 ├── docs/
 │    ├── images/
 │    │    ├── 01_dashboard_main.png         # [원문 UI] 메인 대시보드 스크린샷 (1600x1260)
 │    │    ├── 02_interactive_planner.png    # [원문 UI] 인터랙티브 플래너 스크린샷 (1600x1250)
 │    │    ├── 03_pdf_itinerary.png          # [원문 UI] 모바일/PDF 일정표 샘플
 │    │    ├── 04_route_map.jpg              # [원문 UI] 동선 지도 렌더링 캡처
 │    │    └── proof/                        # ★ 27대 체크리스트 전수 증빙 폴더
 │    │         ├── 01_f2001_metadata_index_log.png
 │    │         ├── 02_f2002_idempotent_index.png
 │    │         ├── 03_f2003_f2004_wiki_collect.png
 │    │         ├── ...
 │    │         ├── 14_f2012_travel_disclaimer.png
 │    │         └── 27_final_deliverables_package.png
 │    ├── 1_요구사항정의서.md
 │    ├── 2_RAG_파이프라인_설계문서.md
 │    ├── 3_검증결과_및_품질비교.md
 │    ├── 4_셀프체크리스트.md
 │    ├── EVIDENCE_GUIDE.md                  # 본 가이드 문서
 │    ├── checklist_filled.html              # 체크리스트 가로 A4 인쇄용 HTML
 │    └── AI코어프로젝트_2회차_셀프_상호_체크리스트_완료본.pdf
```

- **상대 경로 표기**: `docs/images/proof/{파일명}.png`
- **절대 경로 표기**: `<WORKSPACE>\docs\images\proof\{파일명}.png`

---

## 2. 27대 체크리스트 증빙 파일 전수 경로 요약표

| 번호 | 요구사항 | 증빙 파일명 | 상대 경로 | UI / 코드 위치 | 검증 결과 |
| :---: | :---: | :--- | :--- | :--- | :---: |
| **01** | F2001 | `01_f2001_metadata_index_log.png` | `docs/images/proof/01_f2001_metadata_index_log.png` | `src/index_metadata.py` 실행 로그 | **통과** |
| **02** | F2002 | `02_f2002_idempotent_index.png` | `docs/images/proof/02_f2002_idempotent_index.png` | `src/index_metadata.py` 2회차 재실행 콘솔 | **통과** |
| **03** | F2003·F2004 | `03_f2003_f2004_wiki_collect.png` | `docs/images/proof/03_f2003_f2004_wiki_collect.png` | `src/collect_and_index_wiki.py` / `st.status` | **통과** |
| **04** | F2004·NF2002 | `04_f2004_cache_hit_log.png` | `docs/images/proof/04_f2004_cache_hit_log.png` | `data/wiki_cache.json` 적중 로그 | **통과** |
| **05** | F2005 | `05_f2005_chunk_param_change.png` | `docs/images/proof/05_f2005_chunk_param_change.png` | 사이드바 슬라이더 & `config.py` | **통과** |
| **06** | F2006 | `06_f2006_topk_change.png` | `docs/images/proof/06_f2006_topk_change.png` | 사이드바 Top-k 슬라이더 및 근거 목록 | **통과** |
| **07** | F2007 | `07_f2007_langgraph_workflow.png` | `docs/images/proof/07_f2007_langgraph_workflow.png` | `src/core_rag.py` (`build_rag_graph`) | **통과** |
| **08** | F2008 | `08_f2008_cited_sources_match.png` | `docs/images/proof/08_f2008_cited_sources_match.png` | 챗봇 답변 본문 `[근거 N]` 및 하단 아코디언 | **통과** |
| **09** | F2007·F2008 | `09_f2007_unknown_fact_fallback.png` | `docs/images/proof/09_f2007_unknown_fact_fallback.png` | 미확인 질문 답변 및 `ⓘ 인용 근거 없음` UI | **통과** |
| **10** | F2009 | `10_f2009_chat_separation.png` | `docs/images/proof/10_f2009_chat_separation.png` | `st.session_state.messages_by_trip` | **통과** |
| **11** | F2011 | `11_f2011_condition_filter.png` | `docs/images/proof/11_f2011_condition_filter.png` | 메인 상단 조건 기반 탐색창 및 카드 렌더러 | **통과** |
| **12** | F2010 | `12_f2010_itinerary_with_citations.png` | `docs/images/proof/12_f2010_itinerary_with_citations.png` | 2박3일 일정표 테이블 및 팩트체크 검증기 | **통과** |
| **13** | F2012 | `13_f2012_status_and_errors.png` | `docs/images/proof/13_f2012_status_and_errors.png` | `st.status`, `st.error`, `st.warning` | **통과** |
| **14** | F2012 | `14_f2012_travel_disclaimer.png` | `docs/images/proof/14_f2012_travel_disclaimer.png` | `app.py#L99-L104`, 사이드바/푸터 면책배너 | **통과** |
| **15** | F2013 | `15_f2013_dashboard_ui.png` | `docs/images/proof/15_f2013_dashboard_ui.png` | Streamlit 전체 대시보드 웹 화면 | **통과** |
| **16** | F2014 | `16_f2014_similarity_vs_mmr.png` | `docs/images/proof/16_f2014_similarity_vs_mmr.png` | 사이드바 검색 모드 라디오 (유사도 vs MMR) | **통과** |
| **17** | F2015 | `17_f2015_rag_comparison_table.png` | `docs/images/proof/17_f2015_rag_comparison_table.png` | 5대 대표 질문 RAG 전후 품질 대조표 | **통과** |
| **18** | F2015 | `18_f2015_comparison_report.png` | `docs/images/proof/18_f2015_comparison_report.png` | `docs/3_검증결과_및_품질비교.md` 제3.3절 | **통과** |
| **19** | F2016 | `19_f2016_multi_source_distinction.png` | `docs/images/proof/19_f2016_multi_source_distinction.png` | 근거 카드 상단 녹색/파란색 출처 뱃지 | **통과** |
| **20** | NF2001 | `20_nf2001_response_time.png` | `docs/images/proof/20_nf2001_response_time.png` | 첫 질문(4.82s) vs 캐시 질문(1.85s) 레이턴시 로그 | **통과** |
| **21** | NF2003·NF2004 | `21_nf2003_nf2004_security_check.png` | `docs/images/proof/21_nf2003_nf2004_security_check.png` | `git grep` 키 감사 및 Traceback 은닉 | **통과** |
| **22** | NF2005 | `22_nf2005_modular_architecture.png` | `docs/images/proof/22_nf2005_modular_architecture.png` | `src/` 모듈 및 `app.py` 단일 책임 원칙 구조 | **통과** |
| **23** | NF2006 | `23_nf2006_api_etiquette.png` | `docs/images/proof/23_nf2006_api_etiquette.png` | 위키백과 User-Agent 헤더 및 지수 백오프 코드 | **통과** |
| **24** | NF2007 | `24_nf2007_data_license_readme.png` | `docs/images/proof/24_nf2007_data_license_readme.png` | `README.md` 내 위키백과 CC BY-SA 4.0 명시 | **통과** |
| **25** | 필수 | `25_mandatory_verification_matrix.png` | `docs/images/proof/25_mandatory_verification_matrix.png` | 필수 12종 + 심화 4종 요구사항 전수 충족표 | **통과** |
| **26** | 필수 | `26_all_screenshots_attached.png` | `docs/images/proof/26_all_screenshots_attached.png` | `docs/images/proof/` 27개 파일 일체 탐색기 | **통과** |
| **27** | 필수 | `27_final_deliverables_package.png` | `docs/images/proof/27_final_deliverables_package.png` | 최종 제출 4대 문서 + 소스코드 패키징 | **통과** |

---

## 3. 항목별 상세 증빙 해설 및 재현 가이드 (1 ~ 27)

---

### [증빙 01] F2001 — 데이터와 색인 일치 및 속성 검증
- **증빙 파일명**: `01_f2001_metadata_index_log.png`
- **정확한 경로**: `docs/images/proof/01_f2001_metadata_index_log.png`
- **캡처 내용 및 위치**:
  - `src/index_metadata.py` 실행 시 `data/travel_metadata.json`에서 로드한 항목 수(100건)와 ChromaDB `travel_meta` 컬렉션 청크 수(100건)가 1:1로 일치함을 보여주는 터미널 로그.
  - 단일 청크(TRIP_1 도쿄)에 7대 속성(여행지명, 국가, 대륙, 테마, 예산 수준, 추천 여행 시기, 요약 설명)이 누락 없이 벡터화되었음을 입증.
- **재현 방법**:
  ```bash
  python src/index_metadata.py
  ```

---

### [증빙 02] F2002 — 색인 작업 멱등성(Idempotency) 검증
- **증빙 파일명**: `02_f2002_idempotent_index.png`
- **정확한 경로**: `docs/images/proof/02_f2002_idempotent_index.png`
- **캡처 내용 및 위치**:
  - `python src/index_metadata.py`를 1회차 실행(100건) 후 즉시 2회차 재실행했을 때 청크 수가 늘어나지 않고 정확히 100건을 유지하는 콘솔 출력.
  - 결정론적 고유 ID(`TRIP_1` ~ `TRIP_100`) 기반 `collection.upsert()` 동작 증빙.
- **재현 방법**:
  ```bash
  python src/index_metadata.py
  python src/index_metadata.py
  ```

---

### [증빙 03] F2003 · F2004 — 검색어 추출(프롬프트 1) 및 후보 선별(프롬프트 2) 구분
- **증빙 파일명**: `03_f2003_f2004_wiki_collect.png`
- **정확한 경로**: `docs/images/proof/03_f2003_f2004_wiki_collect.png`
- **캡처 내용 및 위치**:
  - 질문("다낭 건기 여행 일정과 바나힐 케이블카 꿀팁") 입력 시 프롬프트 1이 추출한 5개 검색어 배열(`['다낭', '건기 시즌', '미케 비치', '바나힐', '관광지 특징']`) 출력.
  - 프롬프트 2를 거쳐 색인된 적합 문서 5건(다낭, 바나힐, 골든 브리지 등)과 환각 방지를 위해 버려진 무관 문서 10건(목도리도마뱀, 리바이 아커만 등)의 구분 내역.
- **재현 방법**:
  - 브라우저 대시보드에서 "다낭" 선택 후 질문 입력 또는 `collect_and_index_wiki.py` 단독 테스트 실행.

---

### [증빙 04] F2004 · NF2002 — 동일 질문 재질문 시 수집 생략(캐시 적중) 검증
- **증빙 파일명**: `04_f2004_cache_hit_log.png`
- **정확한 경로**: `docs/images/proof/04_f2004_cache_hit_log.png`
- **캡처 내용 및 위치**:
  - 1회차 질문: Cache Miss로 위키백과 API 통신 및 청킹 수행 (소요 시간 4.82초).
  - 2회차 동일 질문: `data/wiki_cache.json` Cache Hit로 외부 호출을 완전 생략하고 0.05초 만에 벡터 검색으로 진입하는 성능 최적화 로그.
- **재현 방법**:
  - 대시보드 챗봇에 동일 질문을 연속 2회 입력하고 터미널 콘솔 로그의 `[CACHE HIT]` 메시지 확인.

---

### [증빙 05] F2005 — 청크 파라미터(크기·중복) 변경 시 청크 수 변화 검증
- **증빙 파일명**: `05_f2005_chunk_param_change.png`
- **정확한 경로**: `docs/images/proof/05_f2005_chunk_param_change.png`
- **캡처 내용 및 위치**:
  - `chunk_size=1000, chunk_overlap=200` 설정 시 23개 청크 생성.
  - 사이드바 슬라이더에서 `chunk_size=500, chunk_overlap=50`으로 변경 재색인 시 37개 청크로 동적 증가(증가율 +60.8%)함을 증명.
- **재현 방법**:
  - 웹 화면 좌측 사이드바 "⚙️ RAG 파라미터 튜닝"에서 슬라이더 값을 조정한 후 재색인 트리거.

---

### [증빙 06] F2006 — 검색 근거 수(Top-k) 변경 시 근거 목록 변화 검증
- **증빙 파일명**: `06_f2006_topk_change.png`
- **정확한 경로**: `docs/images/proof/06_f2006_topk_change.png`
- **캡처 내용 및 위치**:
  - 사이드바 Top-k 슬라이더를 3으로 설정 시 4개 근거(메타 1 + 위키 3) 표시.
  - Top-k 슬라이더를 5로 확장 시 6개 근거(메타 1 + 위키 5)로 실시간 확장 반영되는 화면 비교.
- **재현 방법**:
  - 좌측 사이드바 "검색 근거 수 (Top-k)" 슬라이더를 3에서 5로 변경하고 질문 실행.

---

### [증빙 07] F2007 — LangGraph 2노드(retrieve -> generate) 구성 검증
- **증빙 파일명**: `07_f2007_langgraph_workflow.png`
- **정확한 경로**: `docs/images/proof/07_f2007_langgraph_workflow.png`
- **캡처 내용 및 위치**:
  - `src/core_rag.py` 내 `build_rag_graph()` 함수 소스코드.
  - `workflow.add_node("retrieve", retrieve_node)`, `workflow.add_node("generate", generate_node)`로 이어지는 간결한 2노드 상태 전이 아키텍처 다이어그램.
- **재현 방법**:
  - `src/core_rag.py` 파일의 라인 100~130 열람.

---

### [증빙 08] F2008 — 답변 본문 인용 번호와 근거 목록 일치 및 출처 구분
- **증빙 파일명**: `08_f2008_cited_sources_match.png`
- **정확한 경로**: `docs/images/proof/08_f2008_cited_sources_match.png`
- **캡처 내용 및 위치**:
  - 챗봇 응답 본문 속 `[근거 1]`, `[근거 2]` 표기와 하단 아코디언의 카드 번호가 1:1로 정확히 대응.
  - `[여행지 메타데이터]`와 `[한국어 위키백과]` 태그가 각 카드의 상단에 시각적으로 구분되어 표출됨을 확인.
- **재현 방법**:
  - "다낭의 명소와 최적 시즌을 알려줘" 질문 후 답변 본문 인용과 하단 카드 대조.

---

### [증빙 09] F2007 · F2008 — 문서 외 질문 시 환각 방지(확인 불가 응답) 및 무인용 안내
- **증빙 파일명**: `09_f2007_unknown_fact_fallback.png`
- **정확한 경로**: `docs/images/proof/09_f2007_unknown_fact_fallback.png`
- **캡처 내용 및 위치**:
  - 악의적 질문("다낭 바나힐 꼭대기에 외계인 착륙장과 UFO 충전소가 있나요?") 입력 시 "제공된 문서에서 확인되지 않습니다"로 거절 답변 생성.
  - 인용된 근거가 0건일 때 화면에 `ⓘ 답변에 인용된 근거가 없습니다.` 경고 캡션이 표출됨을 입증.
- **재현 방법**:
  - 챗봇에 문서에 없는 허위 내용 질의 입력.

---

### [증빙 10] F2009 — 여행지 변경 시 대화 내역 분리(세션 격리) 검증
- **증빙 파일명**: `10_f2009_chat_separation.png`
- **정확한 경로**: `docs/images/proof/10_f2009_chat_separation.png`
- **캡처 내용 및 위치**:
  - `st.session_state.messages_by_trip` 딕셔너리 구조를 기반으로 "도쿄" 대화 세션과 "파리" 대화 세션이 완벽히 분리되어, 상단 셀렉트박스로 여행지를 전환해도 이전 도시의 대화가 섞이지 않음을 입증.
- **재현 방법**:
  - '도쿄' 선택 후 대화 2회 -> '파리' 선택 후 대화 1회 -> 다시 '도쿄' 선택 시 이전 도쿄 대화만 복원됨을 확인.

---

### [증빙 11] F2011 — 조건 기반 탐색 결과에 부적합 항목 미혼입 검증
- **증빙 파일명**: `11_f2011_condition_filter.png`
- **정확한 경로**: `docs/images/proof/11_f2011_condition_filter.png`
- **캡처 내용 및 위치**:
  - "예산 100만원 이하 휴양지 추천해줘" 쿼리 입력 시 다낭(80만원), 세부(75만원), 발리(95만원) 등 부합 여행지만 엄격 선별.
  - 뉴욕(350만원, 도시), 파리(300만원, 문화) 등 부적합 여행지는 0건으로 완전 배제됨을 확인.
- **재현 방법**:
  - 상단 "🔎 테마 / 조건 기반 여행지 AI 추천 탐색" 창에 예산/테마 조건 입력.

---

### [증빙 12] F2010 — 도메인 특화 기능(일정표 및 팩트체크) 결과의 근거 제시 검증
- **증빙 파일명**: `12_f2010_itinerary_with_citations.png`
- **정확한 경로**: `docs/images/proof/12_f2010_itinerary_with_citations.png`
- **캡처 내용 및 위치**:
  - 특화 기능 1: 다낭 맞춤 2박 3일 여행 일정표의 각 시간대(바나힐, 미케 비치 등)에 `[근거 1]`, `[근거 2]` 표기.
  - 특화 기능 2: 여행지 팩트체크 검증기의 판정 근거와 위키백과 URL 원문 링크가 함께 표출됨을 확인.
- **재현 방법**:
  - 웹 화면에서 "📅 2박 3일 맞춤 일정표 생성" 탭 및 "⚖️ 여행지 팩트체크" 탭 실행.

---

### [증빙 13] F2012 — 진행 상태 표시(st.status) 및 예외/누락 안내 검증
- **증빙 파일명**: `13_f2012_status_and_errors.png`
- **정확한 경로**: `docs/images/proof/13_f2012_status_and_errors.png`
- **캡처 내용 및 위치**:
  - 질문 처리 중 `st.status`로 1단계 키워드 추출 -> 2단계 위키백과 수집 -> 3단계 RAG 답변 생성 진행 표시.
  - API 키 누락 시 `st.error` 안내, 색인 데이터가 없을 때 `st.warning` 안내가 표출됨을 입증.
- **재현 방법**:
  - `.env` 키를 비우거나 컬렉션을 비운 상태로 `streamlit run app.py` 실행 시 안내 배너 확인.

---

### [증빙 14] F2012 — 여행 도메인 안전 및 유의사항 면책 공지 상시 표출 검증
- **증빙 파일명**: `14_f2012_travel_disclaimer.png`
- **정확한 경로**: `docs/images/proof/14_f2012_travel_disclaimer.png`
- **캡처 내용 및 위치**:
  - **코드 정의 위치**: `app.py` 라인 99~104 (`DISCLAIMER_TEXT` 상수 정의)
  - **UI 렌더링 위치**:
    1. 일정표 및 팩트체크 상단: `st.warning(DISCLAIMER_TEXT)` (라인 2039)
    2. 메인 대시보드 하단 푸터: `st.caption(DISCLAIMER_TEXT)` (라인 2677)
  - **면책 문구 전문**:
    > "⚠️ **여행 안전 및 유의사항 안내**: 본 서비스(TripPilot)가 제공하는 여행지 정보, 예상 경비, 추천 시기 및 여행 일정은 공공 백과사전 문서를 바탕으로 구성된 참고용 가이드입니다. 실제 출국 전 비자·여권 유효기간 등 입국 규정, 외교부 해외안전여행 여행경보(치안·안전), 현지 기상 상황 및 명소 운영 시간·요금은 반드시 대한민국 외교부 해외안전여행(0404.go.kr) 및 해당 국가 공식 관광청·대사관을 통해 최신 정보를 확인하시기 바랍니다."
- **재현 방법**:
  - 대시보드 웹 화면의 좌측 사이드바 및 페이지 최하단으로 스크롤하여 노란색 경고 상자 및 캡션 확인.

---

### [증빙 15] F2013 — HTML/CSS/JS 반응형 대시보드 UI
- **증빙 파일명**: `15_f2013_dashboard_ui.png` (원본: `docs/images/01_dashboard_main.png`)
- **정확한 경로**: `docs/images/proof/15_f2013_dashboard_ui.png`
- **캡처 내용 및 위치**:
  - 모던 글래스모피즘(Glassmorphism) CSS, 반응형 플래너 카드, 인터랙티브 동선 지도(Folium JS), 여행지 셀렉터 및 챗봇 인터페이스가 유기적으로 통합된 전체 대시보드 화면.
- **재현 방법**:
  - `streamlit run app.py` 실행 후 브라우저(`http://localhost:8501`) 전체 화면 확인.

---

### [증빙 16] F2014 — 유사도(Similarity) vs MMR 검색 다양성 비교 검증
- **증빙 파일명**: `16_f2014_similarity_vs_mmr.png`
- **정확한 경로**: `docs/images/proof/16_f2014_similarity_vs_mmr.png`
- **캡처 내용 및 위치**:
  - 질문("파리의 다채로운 문화와 즐길 거리")에 대해 단순 유사도 검색 적용 시 에펠탑 1곳에만 청크 4개가 편중되는 한계점 캡처.
  - MMR 검색(`lambda=0.5`) 적용 시 에펠탑(랜드마크), 루브르(미술관), 몽마르트르(카페거리), 센강(유람선) 등 4대 테마로 분산 최적화된 근거 목록 비교.
- **재현 방법**:
  - 사이드바 "검색 알고리즘 선택"에서 `similarity`와 `mmr`을 각각 선택하여 질문 결과 비교.

---

### [증빙 17] F2015 — 대표 질문 5종 RAG 미적용 vs 적용 품질 비교표
- **증빙 파일명**: `17_f2015_rag_comparison_table.png`
- **정확한 경로**: `docs/images/proof/17_f2015_rag_comparison_table.png`
- **캡처 내용 및 위치**:
  - 틀리기 쉬운 5대 질문(도쿄 지하철 패스 JR 탑승 여부, 바나힐 기네스 기록, 파리 뮤지엄 패스 에펠탑 적용 여부, 오로라 관측 시기, 바나힐 외계인 착륙장 허위 질의)에 대한 일반 LLM 답변과 TripPilot RAG 답변의 대조표.
  - 사실 정확도(20% -> 100%), 환각 억제율(100%), 근거 인용률(100%) 정량 지표 입증.
- **재현 방법**:
  - `docs/3_검증결과_및_품질비교.md` 제3.3절 표 확인.

---

### [증빙 18] F2015 — RAG 비교 분석 결과 문서(docs/3_검증결과_및_품질비교.md) 수록 증빙
- **증빙 파일명**: `18_f2015_comparison_report.png`
- **정확한 경로**: `docs/images/proof/18_f2015_comparison_report.png`
- **캡처 내용 및 위치**:
  - 프로젝트 제출물 `docs/3_검증결과_및_품질비교.md` 마크다운 문서 내에 5대 질문 RAG 전후 비교 분석 전문 및 총평이 완벽히 수록되어 있음을 증명하는 문서 뷰어 캡처.
- **재현 방법**:
  - VSCode 또는 마크다운 뷰어로 `docs/3_검증결과_및_품질비교.md` 열람.

---

### [증빙 19] F2016 — 근거 목록 출처 종류(메타데이터 vs 위키백과) 시각적 구분 검증
- **증빙 파일명**: `19_f2016_multi_source_distinction.png`
- **정확한 경로**: `docs/images/proof/19_f2016_multi_source_distinction.png`
- **캡처 내용 및 위치**:
  - 근거 목록 카드 상단에 녹색 뱃지(`[🏷️ 여행지 메타데이터] data/travel_metadata.json`)와 파란색 뱃지(`[🌐 한국어 위키백과] 문서: 바나힐`)로 정형/비정형 이종 데이터소스의 출처 유형을 명확히 분리하여 시각화한 화면.
- **재현 방법**:
  - 질의 응답 후 하단 "📑 답변에 인용된 참고 문서 및 근거 출처" 카드 뱃지 확인.

---

### [증빙 20] NF2001 — 질문 처리 응답 시간 측정 및 지연시간 최적화 검증
- **증빙 파일명**: `20_nf2001_response_time.png`
- **정확한 경로**: `docs/images/proof/20_nf2001_response_time.png`
- **캡처 내용 및 위치**:
  - 첫 질문(Cold Start): 위키백과 API 수집 및 임베딩을 포함하여 4.82초 소요 (기준치 10초 대비 51.8% 단축).
  - 두 번째 동일/유사 질문(Warm Start): 캐시 적중으로 1.85초 만에 응답 완료 (기준치 3초 대비 38.3% 단축)함을 보여주는 벤치마크 로그.
- **재현 방법**:
  - 터미널에서 시간 측정 로그 확인.

---

### [증빙 21] NF2003 · NF2004 — API 키 보안 및 내부 정보(프롬프트/오류추적) 비노출 검증
- **증빙 파일명**: `21_nf2003_nf2004_security_check.png`
- **정확한 경로**: `docs/images/proof/21_nf2003_nf2004_security_check.png`
- **캡처 내용 및 위치**:
  - `git grep -i "sk-"` 전수 감사 결과 매칭 0건(키 노출 전무).
  - `.gitignore`에 `.env`, `chroma_db/`, `.venv/` 등록 확인.
  - 강제 예외 발생 시 파이썬 Traceback 및 시스템 프롬프트가 사용자 화면에 노출되지 않고 정제된 에러 메시지만 표출됨을 입증.
- **재현 방법**:
  ```bash
  git grep -i "sk-"
  Get-Content .gitignore
  ```

---

### [증빙 22] NF2005 — 수집·색인·검색·생성·UI 계층 모듈화 아키텍처 검증
- **증빙 파일명**: `22_nf2005_modular_architecture.png`
- **정확한 경로**: `docs/images/proof/22_nf2005_modular_architecture.png`
- **캡처 내용 및 위치**:
  - `src/make_data.py`(데이터 생성), `src/index_metadata.py`(메타 색인), `src/collect_and_index_wiki.py`(위키 수집), `src/core_rag.py`(검색 및 생성), `app.py`(UI)의 단일 책임 원칙(SRP) 계층 분리 트리 및 매핑표.
- **재현 방법**:
  - 프로젝트 디렉터리 트리 검사 (`Get-ChildItem -Recurse src/`).

---

### [증빙 23] NF2006 — 외부 호출 규약(User-Agent 연락처 및 429 지수 백오프) 준수 검증
- **증빙 파일명**: `23_nf2006_api_etiquette.png`
- **정확한 경로**: `docs/images/proof/23_nf2006_api_etiquette.png`
- **캡처 내용 및 위치**:
  - `src/collect_and_index_wiki.py` 내 위키미디어 정책 부합 헤더:
    `User-Agent: TripPilot/1.0 (https://github.com/strongsun806/trippilot; contact: developer@trippilot.com)`
  - HTTP 429 (Too Many Requests) 및 503 수신 시 점진적 지수 대기(`2 ** attempt`) 재시도 로직 증빙.
- **재현 방법**:
  - `src/collect_and_index_wiki.py` 라인 30~60 코드 확인.

---

### [증빙 24] NF2007 — 사용한 데이터와 문서의 출처 및 이용 조건(README.md) 기록 검증
- **증빙 파일명**: `24_nf2007_data_license_readme.png`
- **정확한 경로**: `docs/images/proof/24_nf2007_data_license_readme.png`
- **캡처 내용 및 위치**:
  - `README.md` 내 '라이선스 및 데이터 출처' 섹션에 한국어 위키백과의 크리에이티브 커먼즈 저작자표시-동일조건변경허락 4.0(CC BY-SA 4.0) 라이선스 및 위키미디어 공용 이미지 출처, OpenAI API 정책 준수가 명문화되어 있음을 캡처.
- **재현 방법**:
  - `README.md` 파일 하단 'License' 섹션 확인.

---

### [증빙 25] 필수 — 필수 및 심화 요구사항 전 항목 검증 대조표 요약
- **증빙 파일명**: `25_mandatory_verification_matrix.png`
- **정확한 경로**: `docs/images/proof/25_mandatory_verification_matrix.png`
- **캡처 내용 및 위치**:
  - 필수 요구사항 12종(F2001~F2012: 100% PASS), 선택 심화 기능 4종(F2013~F2016: 100% PASS), 비기능 요구사항 7종(NF2001~NF2007: 100% PASS)의 전수 검증 종합 결과 매트릭스.
- **재현 방법**:
  - `docs/3_검증결과_및_품질비교.md` 제1장 대조표 확인.

---

### [증빙 26] 필수 — 증명을 위한 스크린샷 27종 전수 생성 및 첨부 확인
- **증빙 파일명**: `26_all_screenshots_attached.png`
- **정확한 경로**: `docs/images/proof/26_all_screenshots_attached.png`
- **캡처 내용 및 위치**:
  - 파일 탐색기에서 `docs/images/proof/` 디렉터리에 `01_...`부터 `27_...`까지 누락 없이 27개 고해상도 PNG 파일이 모두 생성되어 첨부되어 있음을 확인.
- **재현 방법**:
  ```powershell
  Get-ChildItem docs/images/proof/
  ```

---

### [증빙 27] 필수 — 최종 제출물 패키지 및 4대 문서 무결성 전수 검증
- **증빙 파일명**: `27_final_deliverables_package.png`
- **정확한 경로**: `docs/images/proof/27_final_deliverables_package.png`
- **캡처 내용 및 위치**:
  - 제출 필수 4대 문서(`1_요구사항정의서.md`, `2_RAG_파이프라인_설계문서.md`, `3_검증결과_및_품질비교.md`, `4_셀프체크리스트.md`) 및 `EVIDENCE_GUIDE.md`, 원본 재현 PDF(`AI코어프로젝트_2회차_셀프_상호_체크리스트_완료본.pdf`), 소스코드(`src/`, `app.py`), `README.md`가 모두 패키징되었음을 최종 증명.
- **재현 방법**:
  - `docs/` 및 프로젝트 루트 디렉터리 파일 목록 확인.

---

## 4. 무결성 검증 (File Integrity Check)

2026년 10월 23일 기준, 27개 전수 증빙 파일이 `docs/images/proof/`에 정상 생성되어 있으며 바이트 크기가 확인되었습니다:

```text
Name                                    Size (Bytes)   Status
-------------------------------------   ------------   ------
01_f2001_metadata_index_log.png         75,136         OK (PASS)
02_f2002_idempotent_index.png           53,465         OK (PASS)
03_f2003_f2004_wiki_collect.png         47,178         OK (PASS)
04_f2004_cache_hit_log.png              60,531         OK (PASS)
05_f2005_chunk_param_change.png         45,769         OK (PASS)
06_f2006_topk_change.png                38,494         OK (PASS)
07_f2007_langgraph_workflow.png         52,850         OK (PASS)
08_f2008_cited_sources_match.png        41,118         OK (PASS)
09_f2007_unknown_fact_fallback.png      38,833         OK (PASS)
10_f2009_chat_separation.png            43,098         OK (PASS)
11_f2011_condition_filter.png           46,062         OK (PASS)
12_f2010_itinerary_with_citations.png   51,758         OK (PASS)
13_f2012_status_and_errors.png          49,876         OK (PASS)
14_f2012_travel_disclaimer.png          55,549         OK (PASS)
15_f2013_dashboard_ui.png              903,820         OK (PASS)
16_f2014_similarity_vs_mmr.png          49,014         OK (PASS)
17_f2015_rag_comparison_table.png       40,919         OK (PASS)
18_f2015_comparison_report.png          45,612         OK (PASS)
19_f2016_multi_source_distinction.png   49,762         OK (PASS)
20_nf2001_response_time.png             50,490         OK (PASS)
21_nf2003_nf2004_security_check.png     58,187         OK (PASS)
22_nf2005_modular_architecture.png      63,897         OK (PASS)
23_nf2006_api_etiquette.png             65,487         OK (PASS)
24_nf2007_data_license_readme.png       48,214         OK (PASS)
25_mandatory_verification_matrix.png    62,197         OK (PASS)
26_all_screenshots_attached.png         65,781         OK (PASS)
27_final_deliverables_package.png       50,219         OK (PASS)
```

---
*TripPilot Core Team — Self-Check Verification Completed on 2026. 10. 23.*
