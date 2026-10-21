# ✈️ TripPilot (트립파일럿) — 글로벌 여행지 추천 및 일정 생성 RAG 서비스

> **SSAFY AI 코어 프로젝트 2회차** — 전 세계 인기 여행지 100곳 메타데이터(`travel_meta`)와 한국어 위키백과 백과사전 문서(`travel_wiki`)를 결합한 **LangGraph 기반 이중 컬렉션 RAG 도메인 지식 서비스**

---

## 1. 프로젝트 개요 및 도메인 선정 이유

### 왜 글로벌 여행 & 일정 도메인에서 RAG가 필수적인가? (`근거 없이 답하면 무엇이 문제가 되는가`)
1. **가짜 관광지(Hallucination) 및 타 지역 랜드마크 혼동 방지**: 순수 LLM이 근거 없이 2박 3일 여행 일정을 생성하면 수백 km 떨어진 다른 도시의 명소를 하루 코스에 섞거나 존재하지 않는 장소를 지어내어 현지에서 여행자의 시간·비용 손실 및 조난 위험을 초래합니다.
2. **지역별 건기/우기·몬순·남반구 계절 역전 오안내 방지**: 같은 동남아라도 다낭(건기 2~5월), 방콕(건기 11~2월), 발리(건기 4~10월)는 우기·태풍 시기가 완전히 다르며, 우유니 소금사막처럼 우기(12~3월)에 '하늘 거울'을 볼 수 있는 특수 지형은 정확한 문서 근거 없이는 안내가 틀리기 쉽습니다.
3. **고산병 위험 고도(마추픽추 2,430m, 우유니 3,656m) 및 예산 규모의 정확한 검증**: 건강 안전 및 여행 경비 규모(`100만원 이하` vs `300만원 이상`)를 메타데이터와 위키백과 원문 근거(`[근거 N]`)로 투명하게 제시합니다.

---

## 2. 디렉터리 구조 및 산출물 안내

```text
ai_pjt_2_trippilot/
├── app.py                            # [UI 영역] Streamlit 메인 웹 애플리케이션 (F2009 ~ F2012, F2014)
├── requirements.txt                  # 필수 패키지 버전 명세
├── .env.example                      # 환경변수 설정 템플릿 (NF2003)
├── .gitignore                        # .venv/, .env, chroma_db/, __pycache__/ 제외
├── data/
│   ├── travel_metadata.json          # [F2001] 글로벌 인기 여행지 100곳 메타데이터
│   └── wiki_cache.json               # [NF2002] 위키백과 검색어·문서 수집 캐시
├── src/
│   ├── config.py                     # [NF2005] 경로, 모델, 청크 크기(1000/200), Top-k(3), MMR 설정
│   ├── make_data.py                  # [F2001] 100곳 여행지 메타데이터 JSON 생성 스크립트
│   ├── index_metadata.py             # [F2001~F2002] travel_meta 컬렉션 임베딩·색인 (ID: TRIP_{id})
│   ├── collect_and_index_wiki.py     # [F2003~F2005] 프롬프트 1·2 위키 수집 및 travel_wiki 청킹·색인
│   └── core_rag.py                   # [F2006~F2008, F2010~F2011] LangGraph(retrieve->generate) 및 특화 기능
└── docs/
    ├── 1_요구사항정의서.md            # [산출물 1] 필수·심화·비기능 요구사항 표 및 도메인 선정 근거
    ├── 2_RAG_파이프라인_설계문서.md   # [산출물 2] 컬렉션 설계, 청킹(1000/200), 프롬프트 3종, Top-k 분석
    ├── 3_검증결과_및_품질비교.md      # [산출물 3] 요구사항 대조표, 테스트 결과표, RAG 전후 비교(F2015)
    └── 4_셀프체크리스트.md            # [산출물 5] 명세서 4장 기준 자체 점검 완료 체크리스트
```

---

## 3. 프로젝트 실행 방법

### 1) 가상환경 생성 및 필수 라이브러리 설치
```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2) 환경변수(`.env`) 설정
`.env.example`을 참고하여 `.env` 파일에 SSAFY GMS API 키와 위키백과 연락처 이메일을 설정합니다.
```env
GMS_KEY=your_gms_api_key_here
OPENAI_BASE_URL=https://gms.ssafy.io/api/v1
WIKI_CONTACT=ssafy_travel@example.com
```

### 3) 여행지 메타데이터 100건 생성 및 `travel_meta` 색인 (F2001 ~ F2002)
```bash
python src/make_data.py
python src/index_metadata.py
```

### 4) (선택) 위키백과 수집·색인 및 LangGraph RAG 단독 검증 (F2003 ~ F2008)
```bash
python src/collect_and_index_wiki.py
python src/core_rag.py
```

### 5) Streamlit 웹 서비스 실행 (F2009 ~ F2012)
```bash
streamlit run app.py
```

---

## 4. 주요 기능 요약 (필수 및 심화 기능)

- **메타데이터 색인 및 중복 방지 (`F2001`, `F2002`)**: 전 세계 여행지 100곳을 단일 검색 텍스트로 포맷팅하여 ChromaDB `travel_meta` 컬렉션에 `TRIP_{id}` 식별자로 적재합니다.
- **프롬프트 기반 위키백과 수집 및 청킹 색인 (`F2003` ~ `F2005`, `NF2002`)**:
  - **프롬프트 1**: 여행 큐레이터 역할로 질문에서 검색 키워드 3~5개 추출 (여행지명 첫 번째 필수 포함)
  - **프롬프트 2**: 후보 문서 중 동음이의어를 배제하고 유효 문서만 선별해 본문과 원문 URL 수집 (여행지 본체 문서 최우선 포함)
  - **청킹 및 색인**: `1,000자` 청크 / `200자` 중복으로 분할하여 `travel_wiki` 컬렉션에 `{trip_id}:{doc_title}:{chunk_index}` ID로 색인
- **LangGraph 2-노드 RAG 파이프라인 (`F2006` ~ `F2008`)**:
  - `retrieve` 노드: `travel_meta` 기본 청크(`[근거 1]`) + `travel_wiki` 검색 결과(`Top-k=3`) 병합 및 중복 제거
  - `generate` 노드: 프롬프트 3을 통해 문서 근거만으로 답변을 생성하고 실제 인용된 `[근거 N]`만 파싱하여 하단 `st.expander`에 원문 링크와 함께 표시
- **도메인 특화 기능 (`F2010`)**:
  - **🗓️ 맞춤 2박 3일 여행 일정표 생성**: 위키백과 문서와 메타데이터를 근거로 1~3일차 시간대별(오전/오후/저녁) 여행 일정표를 마크다운 표(Table)로 생성하고 `[근거 N]`을 함께 제시
  - **⚖️ 여행지 정보 팩트체크**: 여행 관련 주장의 사실 여부를 색인된 문서 근거로 판정
- **조건 기반 자연어 여행지 탐색 (`F2011`)**: `"예산 100만원 이하 휴양지"` 등 자연어 조건 입력 시 `travel_meta` 검색 후 LLM이 조건 부합 여행지만 선별해 카드로 추천하고 원클릭으로 해당 여행지 대화로 연결
- **심화 기능 (`F2014`, `F2015`, `F2016`)**:
  - 유사도 검색(`similarity`)과 **MMR 다양성 검색(`mmr`)** 실시간 전환 및 비교
  - 대표 질문 5종에 대한 **RAG 사용 전후 답변 품질 비교 문서화** (`docs/3_검증결과_및_품질비교.md`)
  - 다중 출처(`여행지 메타데이터` vs `한국어 위키백과`) 결합 및 태그 구분 표시

---

## 5. 데이터 출처 및 라이선스 이용 조건 안내 (NF2006, NF2007)

1. **외부 문서 출처**: [한국어 위키백과 (Korean Wikipedia)](https://ko.wikipedia.org/) — MediaWiki Action API (`https://ko.wikipedia.org/w/api.php`)
2. **라이선스 및 이용 조건 (CC BY-SA 4.0)**:
   - 위키백과에서 수집한 모든 문서 텍스트는 **크리에이티브 커먼즈 저작자표시-동일조건변경허락 4.0 국제 라이선스 (CC BY-SA 4.0)** 및 GFDL에 따라 이용됩니다.
   - 본 서비스는 라이선스 조건을 준수하여 답변 및 일정표에 인용된 모든 위키백과 문서의 **문서 제목과 원문 URL 하이퍼링크**를 화면 하단 인용 출처 영역(`st.expander`)에 명시합니다.
3. **API 호출 예절 (User-Agent 정책 준수)**:
   - Wikimedia Foundation의 User-Agent 정책에 따라 모든 API 요청 헤더에 연락처 정보(`User-Agent: TripPilotApp/1.0 ({WIKI_CONTACT}) python-requests`)를 포함하며, 호출 간격(`0.25s`) 및 `429 Too Many Requests` 지수 백오프 재시도 규칙을 준수합니다.
