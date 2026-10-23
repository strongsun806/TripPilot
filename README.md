<div align="center">

# ✈️ TripPilot (트립파일럿)
### AI 여행 코파일럿 '토리'와 함께하는 인텔리전트 글로벌 여행 플래너

<img src="assets/pilot_tori.jpg" width="180" alt="Pilot Tori Mascot" style="border-radius: 50%; box-shadow: 0 4px 15px rgba(0,0,0,0.15);" />

<br/>

**전 세계 인기 여행지 메타데이터(`travel_meta`)와 한국어 위키백과 백과사전 문서(`travel_wiki`)를 결합한<br/>LangGraph 기반 이중 컬렉션 RAG 도메인 지식 여행 비서**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](#)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B.svg?logo=streamlit&logoColor=white)](#)
[![LangChain](https://img.shields.io/badge/LangGraph-RAG%20Workflow-green.svg?logo=langchain&logoColor=white)](#)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-orange.svg)](#)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--5.4--Mini-412991.svg?logo=openai&logoColor=white)](#)
[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)

</div>

---

## 📸 서비스 시연 화면 (Demonstration)

### 1. 메인 대시보드 & 자연 공감 뷰파인더
> 여행지 메타데이터 카드, 4대 공간 감성 테마, 고화질 힐링 명소 뷰파인더 및 실시간 현지 물가·환율 시뮬레이터
<div align="center">
  <img src="docs/images/01_dashboard_main.png" width="95%" alt="TripPilot Main Dashboard" />
</div>

<br/>

### 2. 파일럿 토리와의 여행 라운지 & 실시간 동선 플래너
> 백그라운드 병렬 추론 기반의 대화형 일정 수정(원클릭 프리셋), 인터랙티브 지도, 동행자 올인원 공유 허브
<div align="center">
  <img src="docs/images/02_interactive_planner.png" width="95%" alt="TripPilot Interactive Planner" />
</div>

<br/>

### 3. 일자별(Day-by-Day) 분할 동선 지도 & PDF 리포트
> 전체 일정이 뭉쳐 보이던 핀 겹침 현상을 해결하고, Day별 독립 경로선과 마커를 렌더링하는 고해상도 PDF 내보내기
<div align="center">
  <table width="100%">
    <tr>
      <td width="60%" align="center">
        <b>🗺️ 일자별 최적화 동선 지도 (Day 1~2 코스)</b><br/>
        <img src="docs/images/04_route_map.jpg" width="100%" alt="Route Map" />
      </td>
      <td width="40%" align="center">
        <b>📄 맞춤형 한글 PDF 일정표 출력</b><br/>
        <img src="docs/images/03_pdf_itinerary.png" width="85%" alt="PDF Export" />
      </td>
    </tr>
  </table>
</div>

---

## 🌟 핵심 기능 (Key Highlights)

1. **🕊️ 전담 마스코트 '파일럿 토리' & 웜 오트밀/바이오필릭 UI**
   - 귀여운 3D 룩 병아리 비행 조종사 토리가 여행 코치로 동행
   - 자연 친화적인 웜 오트밀 & 포레스트 그린 컬러 팔레트로 시각적 피로도 최소화

2. **⚡ 무중단 백그라운드 병렬 추론 엔진 (`src/background_inference.py`)**
   - Streamlit의 UI 렌더링 생명주기와 AI 추론 루프를 스레드 워커로 분리
   - 사용자가 탭을 전환하거나 다른 옵션을 클릭해도 백그라운드에서 추론이 끊김 없이 지속

3. **🗓️ 자유로운 여행 기간 설정 (당일치기 ~ 30일 한달살기)**
   - 2박 3일 고정 일정을 넘어 `1박 2일 ~ 최대 29박 30일(한달살기)`까지 슬라이더로 맞춤 기간 설정 지원

4. **🗺️ Day-by-Day 독립 동선 지도 생성 (`src/pdf_route_map.py`)**
   - 다일정 여행 시 장소 핀과 선이 한 지도에 뭉치지 않도록 일자별로 깔끔하게 분리 렌더링

5. **📱 모바일 QR 웹 일정표 & 올인원 내보내기 (`src/publish_mobile_itinerary.py`)**
   - 스마트폰 기본 카메라로 QR 코드를 스캔하면 반응형 모바일 웹 일정표로 바로 연결
   - PDF 일정표, 웹 가이드북(HTML), 캘린더 등록(.ics), 마크다운(.md) 내보내기 지원

6. **🧠 LangGraph 기반 이중 컬렉션 RAG (F2001 ~ F2016)**
   - **travel_meta**: 전 세계 100개 주요 도시 메타데이터 벡터 색인
   - **travel_wiki**: 한국어 위키백과 실시간 수집 및 청킹(1,000자 / 200자 중복) 색인
   - **가드레일 & 팩트체크**: 허위 관광지(Hallucination) 방지 및 근거 출처(`[근거 N]`) 표기

---

## 🏗️ 시스템 아키텍처

```mermaid
flowchart TD
    User([사용자 / 여행자]) --> UI[Streamlit 웹 애플리케이션 app.py]
    
    subgraph UI_Features [사용자 인터페이스 & 편의 기능]
        UI --> Viewfinder[자연 공감 뷰파인더 & 물가 시뮬레이터]
        UI --> Lounge[파일럿 토리 라운지 & 실시간 플래너]
        UI --> ExportHub[올인원 내보내기 PDF / QR / ICS / MD]
    end

    subgraph Async_Engine [병렬 추론 워커]
        Lounge --> BgWorker[Background Inference Worker src/background_inference.py]
    end

    subgraph LangGraph_RAG [LangGraph RAG 파이프라인]
        BgWorker --> RetrieveNode[Retrieve 노드]
        RetrieveNode --> ChromaMeta[(ChromaDB: travel_meta)]
        RetrieveNode --> ChromaWiki[(ChromaDB: travel_wiki)]
        RetrieveNode --> MergeFilter[중복 제거 및 MMR 다양성 재순위화]
        MergeFilter --> GenerateNode[Generate 노드: GPT-5.4 Nano]
        GenerateNode --> Guardrail[가드레일 검증 및 근거 표기 파싱]
    end

    Guardrail --> ItineraryPlan[구조화된 맞춤 여행 일정 데이터]
    ItineraryPlan --> RouteMapGen[일자별 분할 지도 렌더러 src/pdf_route_map.py]
    ItineraryPlan --> MobileWebPub[모바일 웹 퍼블리셔 src/publish_mobile_itinerary.py]
    RouteMapGen --> PDF[최종 한글 PDF 생성]
```

---

## 📂 프로젝트 디렉터리 구조

```text
ai_pjt_2_trippilot/
├── app.py                            # Streamlit 메인 애플리케이션
├── requirements.txt                  # 의존성 패키지 명세
├── .env.example                      # 환경변수 설정 예시
├── .gitignore                        # Git 추적 제외 파일 목록
├── assets/
│   └── pilot_tori.jpg                # 공식 마스코트 '파일럿 토리' 이미지
├── data/
│   ├── travel_metadata.json          # 전 세계 100개 주요 여행지 메타데이터
│   └── wiki_cache.json               # 위키백과 문서 수집 로컬 캐시
├── docs/
│   ├── images/                       # 시연 및 README용 스크린샷 에셋
│   ├── 1_요구사항정의서.md            # 기능/비기능 요구사항 정의서
│   ├── 2_RAG_파이프라인_설계문서.md   # 이중 컬렉션 RAG 및 청킹 설계서
│   ├── 3_검증결과_및_품질비교.md      # RAG 전후 정량/정성 품질 비교
│   └── 4_셀프체크리스트.md            # 요구사항 구현 점검표
└── src/
    ├── config.py                     # 모델, 경로, 프록시 호환 및 청킹 하이퍼파라미터
    ├── make_data.py                  # 여행지 100선 메타데이터 생성 스크립트
    ├── index_metadata.py             # travel_meta 컬렉션 색인 스크립트
    ├── collect_and_index_wiki.py     # 위키백과 수집 및 travel_wiki 색인 스크립트
    ├── core_rag.py                   # LangGraph 파이프라인 및 도메인 특화 핵심 로직
    ├── background_inference.py       # 무중단 백그라운드 병렬 추론 엔진
    ├── nature_visuals.py             # 자연 친화 힐링 뷰파인더 갤러리 모듈
    ├── pdf_route_map.py              # 일자별 독립 동선 분할 지도 렌더러
    └── publish_mobile_itinerary.py   # 모바일 QR 반응형 웹 일정표 생성 모듈
```

---

## 🚀 빠른 시작 (Quick Start)

### 1) 환경 준비 및 패키지 설치
```bash
# Python 3.10 이상 권장
python -m venv .venv

# Windows 환경
.\.venv\Scripts\activate

# 의존성 라이브러리 설치
pip install -r requirements.txt
```

### 2) 환경변수 설정 (`.env`)
프로젝트 루트 경로에 `.env` 파일을 생성하고 LLM API 키를 입력합니다.
```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-5.4-mini
WIKI_CONTACT=trippilot_contact@example.com
```

### 3) 메타데이터 및 벡터 색인 구축
```bash
# 1. 100대 여행지 메타데이터 생성 및 travel_meta 색인
python src/make_data.py
python src/index_metadata.py

# 2. 위키백과 데이터 수집 및 travel_wiki 색인 (선택)
python src/collect_and_index_wiki.py
```

### 4) Streamlit 웹 애플리케이션 실행
```bash
streamlit run app.py
```
브라우저에서 `http://localhost:8501`로 접속하면 TripPilot 서비스를 바로 이용할 수 있습니다.

---

## 📜 데이터 출처 및 라이선스 고지 (License & Attribution)

1. **한국어 위키백과 (Korean Wikipedia)**:
   - 문서 출처: [ko.wikipedia.org](https://ko.wikipedia.org/) via MediaWiki Action API
   - 라이선스: **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)** 및 GFDL
   - 본 서비스는 모든 인용 정보에 대해 위키백과 원문 링크와 저작자 출처를 투명하게 제공합니다.
2. **API User-Agent 준수**:
   - 위키미디어 재단의 User-Agent 정책에 따라 요청 헤더에 연락처 정보를 명시하고 정중한 호출 간격(0.25s 및 지수 백오프)을 준수합니다.

---

<div align="center">
  <b>TripPilot</b> — Safe, Empathetic, and Intelligent Journey
</div>
