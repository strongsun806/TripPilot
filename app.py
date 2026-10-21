"""
글로벌 여행지 추천 및 일정 생성 RAG 서비스 (TripPilot) Streamlit 메인 UI
- 여행지 성격에 따라 자동으로 전환되는 듀얼 비주얼 테마:
  1) 🌿 네이처 & 오션 웨이브 (자연·휴양 여행지): 심플하고 청량한 그린+화이트 글래스모피즘 & 배경 파도 애니메이션
  2) ⚡ 사이버 네온 퓨처 (도시·인공 여행지): 네온 시안/마젠타 오로라 & 미래지향적 3D 홀로그램 그리드·네온 웨이브
- 귀여운 여행 메이트 봇 '파일럿 토리 🐣✈️' 대화형 취향 탐색 & 실시간 일정 코파일럿
- GDM_test 스타일 맞춤 일정 대시보드: 일차별 전환, 클릭 가능한 방문 순서 칩스 연동 동선 지도, 원클릭 숙소·티켓 예약 콘솔
"""
import os
import sys
import html
import json
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# src 모듈 경로 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from config import (
    get_api_key,
    META_COLLECTION,
    WIKI_COLLECTION,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    WIKI_TOP_K,
)
from index_metadata import get_collection_count
from collect_and_index_wiki import process_wiki_for_destination, load_wiki_cache
from core_rag import (
    query_trip_pilot,
    generate_itinerary,
    verify_travel_claim,
    search_destinations_by_condition,
    make_google_maps_url,
    make_google_maps_dir_url,
    make_booking_links,
    is_itinerary_or_preference_request,
    extract_user_constraint,
    detect_mentioned_destination,
    export_itinerary_pdf_bytes,
    export_itinerary_html_bytes,
    export_itinerary_ics_bytes,
    generate_survival_cards,
    get_currency_and_cost_info,
    compare_destinations,
    get_monthly_packing_and_weather,
    safe_md,
)

load_dotenv()

# 마크다운 내 물결표(~) 범위 표기 시 GFM 취소선(----) 파싱 및 글자 취소선 오작동 방지 래퍼
_orig_st_markdown = st.markdown

def _safe_st_markdown(body, *args, **kwargs):
    if isinstance(body, str):
        body = safe_md(body)
    return _orig_st_markdown(body, *args, **kwargs)

st.markdown = _safe_st_markdown

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="TripPilot | AI 여행 메이트 토리 & 맞춤 일정 플래너",
    page_icon="🐣",
    layout="wide",
)

DISCLAIMER_TEXT = (
    "⚠️ **여행 안전 및 유의사항 안내**: 본 서비스(TripPilot)가 제공하는 여행지 정보, 예상 경비, 추천 시기 및 여행 일정은 "
    "공공 백과사전 문서를 바탕으로 구성된 참고용 가이드입니다. "
    "실제 출국 전 비자·여권 유효기간 등 입국 규정, 외교부 해외안전여행 여행경보(치안·안전), 현지 기상 상황 및 명소 운영 시간·요금은 "
    "반드시 대한민국 외교부 해외안전여행(0404.go.kr) 및 해당 국가 공식 관광청·대사관을 통해 최신 정보를 확인하시기 바랍니다."
)

# 4대 공간 공감(Spatial Empathy) 테마 분류 데이터
WINTER_SNOW_DESTINATIONS = {
    "삿포로", "오타루", "하코다테", "아사히카와", "레이캬비크", "트롬쇠", "로바니에미",
    "인터라켄", "체르마트", "그린델발트", "루체른", "옐로나이프", "밴프", "재스퍼",
    "휘슬러", "평창", "강릉", "무주", "퀸스타운", "체르비니아",
}

HERITAGE_CLASSIC_DESTINATIONS = {
    "교토", "나라", "가마쿠라", "로마", "피렌체", "베네치아", "아테네", "경주", "전주", "안동", "부여", "공주",
    "프라하", "비엔나", "부다페스트", "이스탄불", "카이로", "룩소르", "앙코르와트", "시엠립", "바간",
    "시안", "베이징", "루앙프라방", "바르셀로나", "그라나다", "세비야", "톨레도", "두브로브니크",
}

URBAN_FUTURISTIC_DESTINATIONS = {
    "도쿄", "오사카", "후쿠오카", "싱가포르", "홍콩", "마카오", "상하이",
    "타이베이", "방콕", "호치민", "쿠알라룸푸르", "두바이", "아부다비", "도하",
    "뉴욕", "라스베이거스", "시카고", "로스앤젤레스", "샌프란시스코", "토론토",
    "런던", "파리", "베를린", "밀라노", "마드리드", "시드니", "멜버른",
}


def detect_destination_vibe(trip_item: dict) -> str:
    """
    여행지의 지리·문화적 성격에 맞춰 4대 공간 공감(Spatial Empathy) 비주얼 테마를 자동 판별:
    1) 'winter'   : ❄️ 오로라 & 윈터 원더랜드 (설경/스키/오로라/빙하)
    2) 'heritage' : 🏛️ 클래식 헤리티지 & 선셋 골드 (역사/유적/고도/예술)
    3) 'cyber'    : ⚡ 사이버 네온 퓨처 (대도시/마천루/야경/쇼핑)
    4) 'nature'   : 🌿 네이처 & 오션 웨이브 (자연/해양/휴양/섬/리조트)
    """
    name = trip_item.get("name", "")
    theme = trip_item.get("theme", "")
    summary = trip_item.get("summary", "")

    winter_keywords = ["설경", "스키", "오로라", "빙하", "눈", "겨울", "북극", "알프스"]
    heritage_keywords = ["역사", "유적", "문화재", "사찰", "고도", "궁전", "성당", "세계문화유산", "신사", "고대", "유산"]
    nature_keywords = ["자연", "휴양", "해양", "리조트", "온천", "사파리", "사막", "폭포", "협곡", "섬", "산악", "와인"]
    urban_keywords = ["도시", "쇼핑", "테마파크", "마천루", "야경", "현대적인", "카지노", "첨단"]

    if name in WINTER_SNOW_DESTINATIONS or any(k in theme for k in winter_keywords) or any(k in summary for k in ["눈 덮인", "설경", "오로라"]):
        return "winter"
    if name in HERITAGE_CLASSIC_DESTINATIONS or any(k in theme for k in heritage_keywords):
        return "heritage"
    if name in URBAN_FUTURISTIC_DESTINATIONS:
        return "cyber"
    if any(k in theme for k in nature_keywords):
        return "nature"
    if any(k in theme for k in urban_keywords) or any(k in summary for k in ["마천루", "야경", "쇼핑몰", "대도시"]):
        return "cyber"
    return "nature"


def inject_theme_css_and_background(vibe_mode: str, dest_name: str) -> None:
    """
    TripPilot 디자인 철학 — 'Spatial Empathy & Adaptive Contrast (공간 공감형 적응 디자인)'
    - 🌿 Biophilic Serenity (nature): 숲의 피톤치드(#064E3B~#10B981)와 파도 윤슬(#F7FDF9)을 결합한 바이오필릭 화이트·그린 테마.
      OS 다크모드 환경에서도 흰 글씨가 흰 배경에 묻히지 않도록 모든 본문·라벨·입력창·보조 버튼에 딥 포레스트 차콜(#0F291E, 명도 대비 13.5:1)을 강제 적용.
    - ⚡ Neo-Urban Horizon (cyber): 야간 비행 콕핏(HUD)과 메가시티 네온 스카이라인에서 영감을 받은 심해 네이비(#040711) & 네온 시안(#00F5D4)·바이올렛(#A855F7) 다크 테마.
    - 화면 너비(Viewport)에 따라 버튼 크기·폰트·그리드가 유연하게 반응하는 Fluid Responsive Button System 적용.
    """
    if vibe_mode == "nature":
        # 🌿 그린 + 화이트 + 잔잔하게 밀려오는 에메랄드 파도 & 바이오필릭 고대비 타이포그래피
        css_and_bg = """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap');

        :root {
            color-scheme: light !important;
            --primary-color: #059669 !important;
            --background-color: #F7FDF9 !important;
            --secondary-background-color: #ECFDF5 !important;
            --text-color: #0F291E !important;
            --bg-primary: #F7FDF9;
            --card-bg: rgba(255, 255, 255, 0.90);
            --card-border: rgba(16, 185, 129, 0.24);
            --accent-main: #10B981;
            --accent-deep: #059669;
            --accent-soft: #ECFDF5;
            --text-main: #0F291E;
            --text-sub: #2C5243;
            --text-muted: #47695B;
            --shadow-soft: 0 14px 36px -10px rgba(5, 150, 105, 0.10);
        }

        html, body, [class*="css"] {
            font-family: 'Pretendard', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            color: #0F291E !important;
        }

        /* Streamlit 기본 배경 및 전체 텍스트 고대비(Deep Forest Charcoal) 강제 적용 */
        .stApp {
            background: linear-gradient(180deg, #FFFFFF 0%, #F4FBF7 48%, #E6F8EF 100%) !important;
            color: #0F291E !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .main .block-container {
            position: relative;
            z-index: 2;
            padding-top: 1.4rem !important;
            padding-bottom: 6rem !important;
            padding-left: clamp(1rem, 2.5vw, 2.5rem) !important;
            padding-right: clamp(1rem, 2.5vw, 2.5rem) !important;
            max-width: 1520px !important;
        }

        /* 화이트 테마에서 흰 글씨가 나오는 현상 원천 차단 (마크다운·라벨·캡션·위젯·표 전체) */
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stMarkdownContainer"] strong,
        div[data-testid="stText"],
        label[data-testid="stWidgetLabel"],
        label[data-testid="stWidgetLabel"] p,
        label[data-testid="stWidgetLabel"] span,
        div[data-testid="stRadio"] label span,
        div[data-testid="stCheckbox"] label span,
        div[data-testid="stExpander"] summary span,
        div[data-testid="stExpander"] summary p,
        div[data-testid="stStatusWidget"] *,
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] *,
        .stTable th, .stTable td, table th, table td {
            color: #0F291E !important;
        }
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4 {
            color: #064E3B !important;
            letter-spacing: -0.02em;
        }
        div[data-testid="stCaptionContainer"],
        div[data-testid="stCaptionContainer"] p,
        div[data-testid="stCaptionContainer"] span {
            color: #3D6354 !important;
        }
        div[data-testid="stMarkdownContainer"] a {
            color: #047857 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMarkdownContainer"] code {
            background: #ECFDF5 !important;
            color: #065F46 !important;
            border: 1px solid #A7F3D0 !important;
            padding: 2px 6px !important;
            border-radius: 6px !important;
        }

        /* 입력창·셀렉트박스·멀티셀렉트·숫자입력창·채팅 입력창 화이트+그린 고대비 스타일 */
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="textarea"],
        div[data-testid="stNumberInputContainer"] {
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            border: 1.5px solid rgba(16, 185, 129, 0.40) !important;
            color: #0F291E !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="select"] div,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="textarea"] textarea {
            color: #0F291E !important;
            -webkit-text-fill-color: #0F291E !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] svg {
            fill: #047857 !important;
            color: #047857 !important;
        }
        /* 멀티셀렉트 선택 태그(Tag) */
        span[data-baseweb="tag"] {
            background: #ECFDF5 !important;
            background-color: #ECFDF5 !important;
            border: 1px solid #10B981 !important;
            color: #065F46 !important;
            border-radius: 8px !important;
        }
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] svg {
            color: #065F46 !important;
            fill: #065F46 !important;
            -webkit-text-fill-color: #065F46 !important;
            font-weight: 700 !important;
        }
        /* 드롭다운 팝오버 메뉴 */
        ul[data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="menu"],
        div[role="listbox"] {
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            border: 1.5px solid #6EE7B7 !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="popover"] li,
        div[data-baseweb="menu"] li,
        div[role="option"],
        ul[data-testid="stSelectboxVirtualDropdown"] li {
            color: #0F291E !important;
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="popover"] li *,
        div[role="option"] *,
        ul[data-testid="stSelectboxVirtualDropdown"] li * {
            color: #0F291E !important;
        }
        div[data-baseweb="popover"] li:hover,
        div[role="option"]:hover,
        ul[data-testid="stSelectboxVirtualDropdown"] li:hover {
            background: #ECFDF5 !important;
            background-color: #ECFDF5 !important;
            color: #047857 !important;
        }
        /* 하단 채팅 입력창 */
        div[data-testid="stChatInput"],
        div[data-testid="stChatInput"] > div {
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            border: 1.5px solid rgba(16, 185, 129, 0.45) !important;
            color: #0F291E !important;
            border-radius: 16px !important;
        }
        div[data-testid="stChatInput"] textarea {
            color: #0F291E !important;
            -webkit-text-fill-color: #0F291E !important;
            font-weight: 600 !important;
        }
        div[data-testid="stChatInput"] textarea::placeholder {
            color: #5C8374 !important;
            -webkit-text-fill-color: #5C8374 !important;
        }

        /* 사이드바: 깔끔한 화이트-민트 글래스 */
        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.96) !important;
            backdrop-filter: blur(20px) !important;
            border-right: 1px solid rgba(16, 185, 129, 0.24) !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4 {
            color: #0F291E !important;
        }

        /* 컨테이너 & 카드 미니멀 글래스모피즘 */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.92) !important;
            backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(16, 185, 129, 0.24) !important;
            border-radius: 22px !important;
            box-shadow: 0 12px 32px -10px rgba(5, 150, 105, 0.09) !important;
            padding: clamp(14px, 1.4vw, 20px) !important;
            transition: transform 0.22s ease, box-shadow 0.22s ease !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(16, 185, 129, 0.42) !important;
            box-shadow: 0 16px 38px -10px rgba(5, 150, 105, 0.15) !important;
        }

        /* 익스팬더 & 상태 위젯 화이트 글래스 고정 */
        details[data-testid="stExpander"],
        div[data-testid="stStatusWidget"] {
            background: rgba(255, 255, 255, 0.94) !important;
            border: 1px solid rgba(16, 185, 129, 0.28) !important;
            border-radius: 16px !important;
        }

        /* 📐 반응형 버튼 & 다운로드 버튼 시스템 (화면 크기에 맞춰 유연하게 리사이즈 & 내부 텍스트 색상 완벽 고정) */
        .stButton > button,
        .stDownloadButton > button {
            width: 100%;
            min-height: 42px !important;
            border-radius: 14px !important;
            font-weight: 700 !important;
            font-size: clamp(11.8px, 0.82vw, 13.5px) !important;
            line-height: 1.3 !important;
            padding: clamp(6px, 0.55vw, 10px) clamp(10px, 0.9vw, 16px) !important;
            word-break: keep-all !important;
            white-space: normal !important;
            border: 1.5px solid rgba(16, 185, 129, 0.40) !important;
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            color: #065F46 !important;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.07) !important;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
        }
        /* 보조 버튼 및 다운로드 버튼 내부의 p, span 텍스트를 짙은 에메랄드(#065F46)로 강제 고정 */
        .stButton > button:not([kind="primary"]) *,
        .stButton > button[kind="secondary"] *,
        .stDownloadButton > button * {
            color: #065F46 !important;
            font-weight: 700 !important;
        }
        .stButton > button:not([kind="primary"]):hover,
        .stDownloadButton > button:hover {
            background: #ECFDF5 !important;
            background-color: #ECFDF5 !important;
            border-color: #059669 !important;
            color: #047857 !important;
            transform: translateY(-1.5px) !important;
            box-shadow: 0 8px 20px rgba(16, 185, 129, 0.16) !important;
        }
        .stButton > button:not([kind="primary"]):hover *,
        .stDownloadButton > button:hover * {
            color: #047857 !important;
        }
        /* 프라이머리 버튼: 짙은 에메랄드 그라데이션 + 순백색(#FFFFFF) 글씨 강제 고정 */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            box-shadow: 0 8px 22px -4px rgba(5, 150, 105, 0.42) !important;
        }
        .stButton > button[kind="primary"] *,
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span {
            color: #FFFFFF !important;
            font-weight: 800 !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
            color: #FFFFFF !important;
            box-shadow: 0 12px 26px -4px rgba(4, 120, 87, 0.55) !important;
        }

        /* 탭 디자인: 미니멀 필 탭 (반응형 간격) */
        div[data-baseweb="tab-list"] {
            gap: clamp(4px, 0.6vw, 10px) !important;
            flex-wrap: wrap !important;
        }
        button[data-baseweb="tab"] {
            font-weight: 700 !important;
            font-size: clamp(12.5px, 0.9vw, 14.5px) !important;
            color: #3D6354 !important;
            padding: 10px clamp(12px, 1.2vw, 20px) !important;
            white-space: nowrap !important;
        }
        button[data-baseweb="tab"] * {
            color: #3D6354 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"],
        button[data-baseweb="tab"][aria-selected="true"] * {
            color: #047857 !important;
            font-weight: 800 !important;
        }

        /* 채팅 메시지 버블 */
        div[data-testid="stChatMessage"] {
            background: rgba(255, 255, 255, 0.94) !important;
            border: 1px solid rgba(16, 185, 129, 0.22) !important;
            border-radius: 18px !important;
            padding: 12px 16px !important;
            margin-bottom: 10px !important;
            box-shadow: 0 4px 14px rgba(5, 150, 105, 0.06) !important;
        }

        /* 화면 폭(태블릿·작은 노트북·모바일)에 맞춘 반응형 컬럼/버튼 자동 줄바꿈 */
        @media (max-width: 1200px) {
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 8px !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: calc(50% - 8px) !important;
                flex: 1 1 calc(50% - 8px) !important;
            }
        }
        @media (max-width: 680px) {
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
        }

        /* 물결표(~) 범위 표기 시 GFM strikethrough 오작동으로 인한 텍스트 가로줄(----) 완전 무효화 */
        del, s, strike {
            text-decoration: none !important;
            color: inherit !important;
            background: transparent !important;
        }

        /* 히어로 배너 (네이처 웨이브) */
        .hero-shell {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(236, 253, 245, 0.92) 100%);
            backdrop-filter: blur(22px);
            border: 1px solid rgba(16, 185, 129, 0.28);
            border-radius: 26px;
            padding: clamp(18px, 2vw, 26px) clamp(20px, 2.4vw, 30px);
            margin-bottom: 18px;
            box-shadow: 0 18px 42px -12px rgba(5, 150, 105, 0.12);
        }
        .vibe-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(135deg, #10B981, #059669);
            color: #FFFFFF !important;
            padding: 5px 14px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.04em;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
        }
        .hero-title {
            font-size: clamp(22px, 2vw, 28px);
            font-weight: 800;
            color: #064E3B !important;
            margin: 10px 0 6px 0;
            letter-spacing: -0.02em;
        }
        .hero-desc {
            font-size: clamp(13px, 0.95vw, 14.5px);
            color: #1E3A2F !important;
            margin: 0 0 14px 0;
            line-height: 1.6;
        }
        .hero-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .hero-tag {
            background: #FFFFFF;
            border: 1px solid rgba(16, 185, 129, 0.35);
            color: #047857 !important;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }

        /* 일정 타임라인 카드 */
        .timeline-card {
            background: rgba(255, 255, 255, 0.96);
            border: 1px solid rgba(16, 185, 129, 0.26);
            border-left: 4px solid #10B981;
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 12px;
            box-shadow: 0 8px 22px -8px rgba(5, 150, 105, 0.08);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .timeline-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 28px -6px rgba(5, 150, 105, 0.15);
        }
        .timeline-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 8px;
        }
        .timeline-place {
            font-size: 16px;
            font-weight: 800;
            color: #064E3B !important;
        }
        .timeline-time {
            background: #ECFDF5;
            color: #047857 !important;
            border: 1px solid #A7F3D0;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
        }
        .timeline-body {
            font-size: 13.5px;
            color: #1E3A2F !important;
            line-height: 1.55;
            margin-bottom: 8px;
        }
        .timeline-tip {
            background: #F0FDF4;
            border: 1px solid #BBF7D0;
            border-radius: 10px;
            padding: 7px 11px;
            font-size: 12px;
            color: #065F46 !important;
            margin-bottom: 10px;
        }

        /* 요약 메트릭 필 */
        .metric-pill {
            background: rgba(255, 255, 255, 0.95);
            border: 1px solid rgba(16, 185, 129, 0.28);
            border-radius: 16px;
            padding: 10px 12px;
            text-align: center;
            box-shadow: 0 6px 18px -6px rgba(5, 150, 105, 0.08);
        }
        .metric-label { font-size: 11px; color: #3D6354 !important; font-weight: 700; }
        .metric-val { font-size: clamp(12.5px, 0.9vw, 14px); font-weight: 800; color: #047857 !important; margin-top: 2px; word-break: keep-all; }

        /* 원클릭 예약 칩 (반응형 플렉스 랩) */
        .booking-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 10px;
        }
        .booking-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            background: #FFFFFF;
            color: #047857 !important;
            border: 1.5px solid rgba(16, 185, 129, 0.40);
            padding: 6px 12px;
            border-radius: 999px;
            font-size: clamp(11px, 0.78vw, 12.5px);
            font-weight: 700;
            white-space: nowrap;
            text-decoration: none !important;
            margin-right: 4px;
            margin-bottom: 4px;
            box-shadow: 0 2px 6px rgba(16, 185, 129, 0.08);
            transition: all 0.18s ease;
        }
        .booking-chip:hover {
            background: #059669;
            color: #FFFFFF !important;
            border-color: #059669;
            transform: translateY(-1px);
            box-shadow: 0 6px 14px rgba(5, 150, 105, 0.25);
        }

        /* 🌊 배경 파도 & 자연 빛 오로라 애니메이션 레이어 */
        .ambient-stage {
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }
        .nature-orb-1 {
            position: absolute;
            top: -120px;
            right: -80px;
            width: 520px;
            height: 520px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(16, 185, 129, 0.16) 0%, rgba(167, 243, 208, 0.05) 55%, transparent 75%);
            animation: floatSlow 14s ease-in-out infinite alternate;
        }
        .nature-orb-2 {
            position: absolute;
            top: 22%;
            left: -140px;
            width: 460px;
            height: 460px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(20, 184, 166, 0.13) 0%, rgba(153, 246, 228, 0.04) 55%, transparent 75%);
            animation: floatSlow 18s ease-in-out infinite alternate-reverse;
        }
        .wave-dock {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 220px;
            overflow: hidden;
            line-height: 0;
        }
        .wave-track {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 200%;
            height: 100%;
            display: flex;
        }
        .wave-track svg {
            width: 50%;
            height: 100%;
        }
        .wave-1 {
            animation: waveRoll 18s linear infinite;
            opacity: 0.85;
        }
        .wave-2 {
            animation: waveRollReverse 25s linear infinite;
            opacity: 0.65;
            bottom: -8px;
        }
        .wave-3 {
            animation: waveRoll 13s linear infinite;
            opacity: 0.45;
            bottom: -16px;
        }
        @keyframes waveRoll {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
        }
        @keyframes waveRollReverse {
            0% { transform: translateX(-50%); }
            100% { transform: translateX(0); }
        }
        @keyframes floatSlow {
            0% { transform: translate(0, 0) scale(1); }
            100% { transform: translate(30px, 24px) scale(1.08); }
        }
        </style>

        <div class="ambient-stage">
            <div class="nature-orb-1"></div>
            <div class="nature-orb-2"></div>
            <div class="wave-dock">
                <div class="wave-track wave-1">
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(16, 185, 129, 0.14)" d="M0,192L60,186.7C120,181,240,171,360,181.3C480,192,600,224,720,218.7C840,213,960,171,1080,160C1200,149,1320,171,1380,181.3L1440,192L1440,320L0,320Z"></path>
                    </svg>
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(16, 185, 129, 0.14)" d="M0,192L60,186.7C120,181,240,171,360,181.3C480,192,600,224,720,218.7C840,213,960,171,1080,160C1200,149,1320,171,1380,181.3L1440,192L1440,320L0,320Z"></path>
                    </svg>
                </div>
                <div class="wave-track wave-2">
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(20, 184, 166, 0.16)" d="M0,224L80,213.3C160,203,320,181,480,186.7C640,192,800,224,960,229.3C1120,235,1280,213,1360,202.7L1440,192L1440,320L0,320Z"></path>
                    </svg>
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(20, 184, 166, 0.16)" d="M0,224L80,213.3C160,203,320,181,480,186.7C640,192,800,224,960,229.3C1120,235,1280,213,1360,202.7L1440,192L1440,320L0,320Z"></path>
                    </svg>
                </div>
                <div class="wave-track wave-3">
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(5, 150, 105, 0.18)" d="M0,256L60,245.3C120,235,240,213,360,208C480,203,600,213,720,229.3C840,245,960,267,1080,261.3C1200,256,1320,224,1380,208L1440,192L1440,320L0,320Z"></path>
                    </svg>
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(5, 150, 105, 0.18)" d="M0,256L60,245.3C120,235,240,213,360,208C480,203,600,213,720,229.3C840,245,960,267,1080,261.3C1200,256,1320,224,1380,208L1440,192L1440,320L0,320Z"></path>
                    </svg>
                </div>
            </div>
        </div>
        """
    elif vibe_mode == "heritage":
        # 🏛️ 클래식 헤리티지 & 선셋 골드 (역사·유적·고도·예술 도시 테마)
        css_and_bg = """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap');

        :root {
            color-scheme: light !important;
            --primary-color: #B45309 !important;
            --background-color: #FDFBF7 !important;
            --secondary-background-color: #FFFBEB !important;
            --text-color: #271C16 !important;
            --bg-primary: #FDFBF7;
            --card-bg: rgba(255, 253, 248, 0.94);
            --card-border: rgba(217, 119, 6, 0.28);
            --accent-main: #D97706;
            --accent-deep: #B45309;
            --accent-soft: #FEF3C7;
            --text-main: #271C16;
            --text-sub: #451A03;
            --text-muted: #78350F;
        }

        html, body, [class*="css"] {
            font-family: 'Pretendard', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            color: #271C16 !important;
        }

        .stApp {
            background: linear-gradient(180deg, #FFFFFF 0%, #FAF5EC 48%, #F2E8D5 100%) !important;
            color: #271C16 !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .main .block-container {
            position: relative;
            z-index: 2;
            padding-top: 1.4rem !important;
            padding-bottom: 6rem !important;
            padding-left: clamp(1rem, 2.5vw, 2.5rem) !important;
            padding-right: clamp(1rem, 2.5vw, 2.5rem) !important;
            max-width: 1520px !important;
        }

        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stMarkdownContainer"] strong,
        div[data-testid="stText"],
        label[data-testid="stWidgetLabel"],
        label[data-testid="stWidgetLabel"] p,
        label[data-testid="stWidgetLabel"] span,
        div[data-testid="stRadio"] label span,
        div[data-testid="stCheckbox"] label span,
        div[data-testid="stExpander"] summary span,
        div[data-testid="stExpander"] summary p,
        div[data-testid="stStatusWidget"] *,
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] *,
        .stTable th, .stTable td, table th, table td {
            color: #271C16 !important;
        }
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4 {
            color: #78350F !important;
            letter-spacing: -0.02em;
        }
        div[data-testid="stCaptionContainer"],
        div[data-testid="stCaptionContainer"] p,
        div[data-testid="stCaptionContainer"] span {
            color: #78350F !important;
        }
        div[data-testid="stMarkdownContainer"] a {
            color: #B45309 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMarkdownContainer"] code {
            background: #FEF3C7 !important;
            color: #92400E !important;
            border: 1px solid #FDE68A !important;
            padding: 2px 6px !important;
            border-radius: 6px !important;
        }

        /* 입력창 & 셀렉트박스 골드 헤리티지 스타일 */
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="textarea"],
        div[data-testid="stNumberInputContainer"] {
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            border: 1.5px solid rgba(217, 119, 6, 0.40) !important;
            color: #271C16 !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="select"] div,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="textarea"] textarea {
            color: #271C16 !important;
            -webkit-text-fill-color: #271C16 !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] svg {
            fill: #B45309 !important;
            color: #B45309 !important;
        }
        span[data-baseweb="tag"] {
            background: #FEF3C7 !important;
            border: 1px solid #F59E0B !important;
            color: #92400E !important;
        }
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] svg {
            color: #92400E !important;
            fill: #92400E !important;
            font-weight: 700 !important;
        }
        ul[data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="menu"],
        div[role="listbox"] {
            background: #FFFFFF !important;
            border: 1.5px solid #FCD34D !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="popover"] li,
        div[data-baseweb="menu"] li,
        div[role="option"],
        ul[data-testid="stSelectboxVirtualDropdown"] li {
            color: #271C16 !important;
            background: #FFFFFF !important;
        }
        div[data-baseweb="popover"] li:hover,
        div[role="option"]:hover,
        ul[data-testid="stSelectboxVirtualDropdown"] li:hover {
            background: #FFFBEB !important;
            color: #B45309 !important;
        }
        div[data-testid="stChatInput"],
        div[data-testid="stChatInput"] > div {
            background: #FFFFFF !important;
            border: 1.5px solid rgba(217, 119, 6, 0.45) !important;
            color: #271C16 !important;
            border-radius: 16px !important;
        }
        div[data-testid="stChatInput"] textarea {
            color: #271C16 !important;
            -webkit-text-fill-color: #271C16 !important;
            font-weight: 600 !important;
        }

        section[data-testid="stSidebar"] {
            background: rgba(255, 253, 248, 0.96) !important;
            backdrop-filter: blur(20px) !important;
            border-right: 1px solid rgba(217, 119, 6, 0.25) !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4 {
            color: #271C16 !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 253, 248, 0.94) !important;
            backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(217, 119, 6, 0.25) !important;
            border-radius: 22px !important;
            box-shadow: 0 12px 32px -10px rgba(180, 83, 9, 0.10) !important;
            padding: clamp(14px, 1.4vw, 20px) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(217, 119, 6, 0.45) !important;
            box-shadow: 0 16px 38px -10px rgba(180, 83, 9, 0.18) !important;
        }

        .stButton > button,
        .stDownloadButton > button {
            width: 100%;
            min-height: 42px !important;
            border-radius: 14px !important;
            font-weight: 700 !important;
            font-size: clamp(11.8px, 0.82vw, 13.5px) !important;
            border: 1.5px solid rgba(217, 119, 6, 0.40) !important;
            background: #FFFFFF !important;
            color: #92400E !important;
            box-shadow: 0 4px 12px rgba(180, 83, 9, 0.08) !important;
        }
        .stButton > button:not([kind="primary"]) *,
        .stButton > button[kind="secondary"] *,
        .stDownloadButton > button * {
            color: #92400E !important;
            font-weight: 700 !important;
        }
        .stButton > button:not([kind="primary"]):hover,
        .stDownloadButton > button:hover {
            background: #FEF3C7 !important;
            border-color: #B45309 !important;
            color: #78350F !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #D97706 0%, #B45309 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            box-shadow: 0 8px 22px -4px rgba(180, 83, 9, 0.45) !important;
        }
        .stButton > button[kind="primary"] *,
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span {
            color: #FFFFFF !important;
            font-weight: 800 !important;
        }

        .hero-shell {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(254, 243, 199, 0.88) 100%);
            border: 1px solid rgba(217, 119, 6, 0.32);
            border-radius: 26px;
            padding: clamp(18px, 2vw, 26px) clamp(20px, 2.4vw, 30px);
            margin-bottom: 18px;
            box-shadow: 0 18px 42px -12px rgba(180, 83, 9, 0.14);
        }
        .vibe-badge {
            background: linear-gradient(135deg, #D97706, #B45309);
            color: #FFFFFF !important;
            padding: 5px 14px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 800;
        }
        .hero-title {
            color: #78350F !important;
            font-size: clamp(22px, 2vw, 28px);
            font-weight: 800;
        }
        .hero-desc { color: #451A03 !important; }
        .hero-tag {
            background: #FFFFFF;
            border: 1px solid rgba(217, 119, 6, 0.38);
            color: #92400E !important;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }
        .booking-chip {
            background: #FFFFFF;
            color: #92400E !important;
            border: 1.5px solid rgba(217, 119, 6, 0.42);
            padding: 6px 12px;
            border-radius: 999px;
            font-size: clamp(11px, 0.78vw, 12.5px);
            font-weight: 700;
            text-decoration: none !important;
            margin-right: 4px;
            margin-bottom: 4px;
            display: inline-flex;
        }
        .booking-chip:hover {
            background: #B45309;
            color: #FFFFFF !important;
            border-color: #B45309;
        }
        .timeline-card {
            background: rgba(255, 253, 248, 0.96);
            border: 1px solid rgba(217, 119, 6, 0.28);
            border-left: 4px solid #D97706;
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 12px;
        }
        .timeline-place { color: #78350F !important; font-size: 16px; font-weight: 800; }
        .timeline-time { background: #FEF3C7; color: #92400E !important; border: 1px solid #FDE68A; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; }
        .timeline-body { color: #451A03 !important; font-size: 13.5px; line-height: 1.55; }
        .timeline-tip { background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 10px; padding: 7px 11px; font-size: 12px; color: #78350F !important; }
        .metric-pill { background: #FFFFFF; border: 1px solid rgba(217, 119, 6, 0.30); border-radius: 16px; padding: 10px 12px; text-align: center; }
        .metric-label { font-size: 11px; color: #78350F !important; font-weight: 700; }
        .metric-val { font-size: 14px; font-weight: 800; color: #B45309 !important; }

        /* 🌅 클래식 헤리티지 선셋 골든 더스트 입자 애니메이션 */
        .ambient-stage {
            position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden;
        }
        .heritage-sun-orb {
            position: absolute; top: -100px; right: -50px; width: 500px; height: 500px; border-radius: 50%;
            background: radial-gradient(circle, rgba(245, 158, 11, 0.18) 0%, rgba(251, 191, 36, 0.06) 55%, transparent 75%);
            animation: floatSlow 15s ease-in-out infinite alternate;
        }
        .dust-particle {
            position: absolute; border-radius: 50%; background: rgba(217, 119, 6, 0.45);
            animation: dustDrift 14s infinite linear;
        }
        .d1 { width: 6px; height: 6px; left: 15%; top: 90%; animation-duration: 18s; animation-delay: 0s; }
        .d2 { width: 8px; height: 8px; left: 35%; top: 95%; animation-duration: 22s; animation-delay: 3s; }
        .d3 { width: 5px; height: 5px; left: 60%; top: 88%; animation-duration: 16s; animation-delay: 6s; }
        .d4 { width: 7px; height: 7px; left: 80%; top: 92%; animation-duration: 20s; animation-delay: 2s; }
        @keyframes dustDrift {
            0% { transform: translateY(0) scale(1); opacity: 0; }
            30% { opacity: 0.8; }
            80% { opacity: 0.6; }
            100% { transform: translateY(-750px) scale(0.6); opacity: 0; }
        }
        </style>
        <div class="ambient-stage">
            <div class="heritage-sun-orb"></div>
            <div class="dust-particle d1"></div>
            <div class="dust-particle d2"></div>
            <div class="dust-particle d3"></div>
            <div class="dust-particle d4"></div>
        </div>
        """
    elif vibe_mode == "winter":
        # ❄️ 오로라 & 윈터 원더랜드 (설경/오로라/겨울 도시 테마)
        css_and_bg = """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap');

        :root {
            color-scheme: dark !important;
            --primary-color: #38BDF8 !important;
            --background-color: #061121 !important;
            --secondary-background-color: #0B1E38 !important;
            --text-color: #F8FAFC !important;
            --bg-primary: #061121;
            --card-bg: rgba(11, 30, 56, 0.85);
            --card-border: rgba(56, 189, 248, 0.35);
            --accent-main: #38BDF8;
            --accent-secondary: #34D399;
            --text-main: #F8FAFC;
            --text-sub: #BAE6FD;
            --text-muted: #94A3B8;
        }

        html, body, [class*="css"] {
            font-family: 'Pretendard', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            color: #F8FAFC !important;
        }

        .stApp {
            background: radial-gradient(circle at 45% 10%, rgba(56, 189, 248, 0.20) 0%, transparent 45%),
                        radial-gradient(circle at 82% 20%, rgba(52, 211, 153, 0.16) 0%, transparent 42%),
                        linear-gradient(175deg, #050D1A 0%, #0B1E38 52%, #112B4E 100%) !important;
            color: #F8FAFC !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .main .block-container {
            position: relative;
            z-index: 2;
            padding-top: 1.4rem !important;
            padding-bottom: 6rem !important;
            padding-left: clamp(1rem, 2.5vw, 2.5rem) !important;
            padding-right: clamp(1rem, 2.5vw, 2.5rem) !important;
            max-width: 1520px !important;
        }

        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stMarkdownContainer"] strong,
        div[data-testid="stText"],
        label[data-testid="stWidgetLabel"],
        label[data-testid="stWidgetLabel"] p,
        label[data-testid="stWidgetLabel"] span,
        div[data-testid="stRadio"] label span,
        div[data-testid="stCheckbox"] label span,
        div[data-testid="stExpander"] summary span,
        div[data-testid="stExpander"] summary p,
        div[data-testid="stStatusWidget"] *,
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] *,
        .stTable th, .stTable td, table th, table td {
            color: #F8FAFC !important;
        }
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4 {
            color: #E0F2FE !important;
        }
        div[data-testid="stCaptionContainer"],
        div[data-testid="stCaptionContainer"] p,
        div[data-testid="stCaptionContainer"] span {
            color: #94A3B8 !important;
        }
        div[data-testid="stMarkdownContainer"] a {
            color: #38BDF8 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMarkdownContainer"] code {
            background: rgba(15, 36, 68, 0.9) !important;
            color: #38BDF8 !important;
            border: 1px solid rgba(56, 189, 248, 0.40) !important;
            padding: 2px 6px !important;
            border-radius: 6px !important;
        }

        /* 입력창 & 셀렉트박스 프로스트 윈터 스타일 */
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="textarea"],
        div[data-testid="stNumberInputContainer"] {
            background: #0B1E38 !important;
            background-color: #0B1E38 !important;
            border: 1.5px solid rgba(56, 189, 248, 0.45) !important;
            color: #F8FAFC !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="select"] div,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="textarea"] textarea {
            color: #F8FAFC !important;
            -webkit-text-fill-color: #F8FAFC !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] svg {
            fill: #38BDF8 !important;
            color: #38BDF8 !important;
        }
        span[data-baseweb="tag"] {
            background: rgba(56, 189, 248, 0.20) !important;
            border: 1px solid #38BDF8 !important;
            color: #E0F2FE !important;
        }
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] svg {
            color: #E0F2FE !important;
            fill: #E0F2FE !important;
            font-weight: 700 !important;
        }
        ul[data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="menu"],
        div[role="listbox"] {
            background: #0B1E38 !important;
            border: 1.5px solid rgba(56, 189, 248, 0.50) !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="popover"] li,
        div[data-baseweb="menu"] li,
        div[role="option"],
        ul[data-testid="stSelectboxVirtualDropdown"] li {
            color: #F8FAFC !important;
            background: #0B1E38 !important;
        }
        div[data-baseweb="popover"] li:hover,
        div[role="option"]:hover,
        ul[data-testid="stSelectboxVirtualDropdown"] li:hover {
            background: rgba(56, 189, 248, 0.22) !important;
            color: #38BDF8 !important;
        }
        div[data-testid="stChatInput"],
        div[data-testid="stChatInput"] > div {
            background: #0B1E38 !important;
            border: 1.5px solid rgba(56, 189, 248, 0.48) !important;
            color: #F8FAFC !important;
            border-radius: 16px !important;
        }
        div[data-testid="stChatInput"] textarea {
            color: #F8FAFC !important;
            -webkit-text-fill-color: #F8FAFC !important;
            font-weight: 600 !important;
        }

        section[data-testid="stSidebar"] {
            background: rgba(6, 17, 33, 0.95) !important;
            backdrop-filter: blur(20px) !important;
            border-right: 1px solid rgba(56, 189, 248, 0.30) !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4 {
            color: #F8FAFC !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(11, 30, 56, 0.82) !important;
            backdrop-filter: blur(18px) !important;
            border: 1px solid rgba(56, 189, 248, 0.30) !important;
            border-radius: 22px !important;
            box-shadow: 0 14px 36px -10px rgba(56, 189, 248, 0.14) !important;
            padding: clamp(14px, 1.4vw, 20px) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(56, 189, 248, 0.60) !important;
            box-shadow: 0 18px 42px -10px rgba(52, 211, 153, 0.25) !important;
        }

        .stButton > button,
        .stDownloadButton > button {
            width: 100%;
            min-height: 42px !important;
            border-radius: 14px !important;
            font-weight: 700 !important;
            font-size: clamp(11.8px, 0.82vw, 13.5px) !important;
            border: 1.5px solid rgba(56, 189, 248, 0.45) !important;
            background: #0B1E38 !important;
            color: #38BDF8 !important;
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.12) !important;
        }
        .stButton > button:not([kind="primary"]) *,
        .stButton > button[kind="secondary"] *,
        .stDownloadButton > button * {
            color: #38BDF8 !important;
            font-weight: 700 !important;
        }
        .stButton > button:not([kind="primary"]):hover,
        .stDownloadButton > button:hover {
            background: rgba(56, 189, 248, 0.22) !important;
            border-color: #38BDF8 !important;
            color: #FFFFFF !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #38BDF8 0%, #0284C7 50%, #6366F1 100%) !important;
            color: #050D1A !important;
            font-weight: 800 !important;
            border: none !important;
            box-shadow: 0 8px 24px -4px rgba(56, 189, 248, 0.50) !important;
        }
        .stButton > button[kind="primary"] *,
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span {
            color: #050D1A !important;
            font-weight: 800 !important;
        }

        .hero-shell {
            background: linear-gradient(135deg, rgba(11, 30, 56, 0.90) 0%, rgba(15, 23, 42, 0.88) 100%);
            border: 1px solid rgba(56, 189, 248, 0.42);
            border-radius: 26px;
            padding: 26px 30px;
            margin-bottom: 18px;
            box-shadow: 0 0 36px rgba(56, 189, 248, 0.20), 0 0 60px rgba(52, 211, 153, 0.16);
        }
        .vibe-badge {
            background: linear-gradient(135deg, #38BDF8, #34D399);
            color: #050D1A !important;
            padding: 5px 14px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 800;
        }
        .hero-title {
            color: #F8FAFC !important;
            font-size: 28px;
            font-weight: 800;
            text-shadow: 0 0 16px rgba(56, 189, 248, 0.40);
        }
        .hero-desc { color: #BAE6FD !important; }
        .hero-tag {
            background: rgba(11, 30, 56, 0.9);
            border: 1px solid rgba(56, 189, 248, 0.42);
            color: #38BDF8 !important;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }
        .booking-chip {
            background: rgba(11, 30, 56, 0.9);
            color: #38BDF8 !important;
            border: 1px solid rgba(56, 189, 248, 0.45);
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            text-decoration: none !important;
            margin-right: 6px;
            margin-bottom: 6px;
            display: inline-flex;
        }
        .booking-chip:hover {
            background: linear-gradient(135deg, #38BDF8, #34D399);
            color: #050D1A !important;
        }
        .timeline-card {
            background: rgba(11, 30, 56, 0.88);
            border: 1px solid rgba(56, 189, 248, 0.28);
            border-left: 4px solid #38BDF8;
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 12px;
        }
        .timeline-place { color: #F8FAFC !important; font-size: 16px; font-weight: 800; }
        .timeline-time { background: rgba(56, 189, 248, 0.18); color: #38BDF8 !important; border: 1px solid rgba(56, 189, 248, 0.42); padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; }
        .timeline-body { color: #E0F2FE !important; font-size: 13.5px; line-height: 1.55; }
        .timeline-tip { background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 10px; padding: 7px 11px; font-size: 12px; color: #A7F3D0 !important; }
        .metric-pill { background: rgba(11, 30, 56, 0.88); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 16px; padding: 12px 14px; text-align: center; }
        .metric-label { font-size: 11px; color: #94A3B8; font-weight: 600; }
        .metric-val { font-size: 14px; font-weight: 800; color: #38BDF8; }

        /* ❄️ 윈터 원더랜드 흩날리는 눈송이(Snowfall) & 오로라 커튼 애니메이션 */
        .ambient-stage {
            position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden;
        }
        .aurora-ribbon {
            position: absolute; top: -140px; left: -10%; width: 120%; height: 380px;
            background: radial-gradient(ellipse at 50% 50%, rgba(52, 211, 153, 0.18) 0%, rgba(56, 189, 248, 0.12) 45%, transparent 70%);
            filter: blur(40px); animation: auroraShift 16s ease-in-out infinite alternate;
        }
        .snow-flake {
            position: absolute; color: #E0F2FE; font-size: 16px; opacity: 0.85;
            animation: fallSnow 12s linear infinite;
        }
        .sf1 { left: 8%; top: -20px; font-size: 12px; animation-duration: 9s; animation-delay: 0s; }
        .sf2 { left: 24%; top: -20px; font-size: 18px; animation-duration: 13s; animation-delay: 2s; }
        .sf3 { left: 45%; top: -20px; font-size: 14px; animation-duration: 11s; animation-delay: 4s; }
        .sf4 { left: 68%; top: -20px; font-size: 20px; animation-duration: 15s; animation-delay: 1s; }
        .sf5 { left: 88%; top: -20px; font-size: 13px; animation-duration: 10s; animation-delay: 3s; }
        @keyframes fallSnow {
            0% { transform: translateY(0) rotate(0deg); opacity: 0; }
            20% { opacity: 0.9; }
            80% { opacity: 0.8; }
            100% { transform: translateY(105vh) rotate(360deg); opacity: 0; }
        }
        @keyframes auroraShift {
            0% { transform: skewX(-12deg) scale(1); opacity: 0.6; }
            100% { transform: skewX(12deg) scale(1.15); opacity: 0.95; }
        }
        </style>
        <div class="ambient-stage">
            <div class="aurora-ribbon"></div>
            <div class="snow-flake sf1">❄</div>
            <div class="snow-flake sf2">❅</div>
            <div class="snow-flake sf3">❄</div>
            <div class="snow-flake sf4">❅</div>
            <div class="snow-flake sf5">❄</div>
        </div>
        """
    else:
        # ⚡ 사이버 네온 & 미래지향적 메트로폴리스 테마 (인공/도시 여행지)
        css_and_bg = """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap');

        :root {
            color-scheme: dark !important;
            --primary-color: #00F5D4 !important;
            --background-color: #050814 !important;
            --secondary-background-color: #0F172A !important;
            --text-color: #F8FAFC !important;
            --bg-primary: #050814;
            --card-bg: rgba(13, 19, 38, 0.80);
            --card-border: rgba(0, 245, 212, 0.30);
            --accent-main: #00F5D4;
            --accent-secondary: #A855F7;
            --text-main: #F8FAFC;
            --text-sub: #CBD5E1;
            --text-muted: #94A3B8;
        }

        html, body, [class*="css"] {
            font-family: 'Pretendard', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            color: #F8FAFC !important;
        }

        .stApp {
            background: radial-gradient(circle at 18% 12%, rgba(168, 85, 247, 0.18) 0%, transparent 38%),
                        radial-gradient(circle at 85% 18%, rgba(0, 245, 212, 0.16) 0%, transparent 40%),
                        linear-gradient(165deg, #040711 0%, #090D1F 52%, #0F172A 100%) !important;
            color: #F8FAFC !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        .main .block-container {
            position: relative;
            z-index: 2;
            padding-top: 1.4rem !important;
            padding-bottom: 6rem !important;
            padding-left: clamp(1rem, 2.5vw, 2.5rem) !important;
            padding-right: clamp(1rem, 2.5vw, 2.5rem) !important;
            max-width: 1520px !important;
        }

        /* 다크 네온 모드 텍스트 고대비(Crystal White) 보장 */
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stMarkdownContainer"] strong,
        div[data-testid="stText"],
        label[data-testid="stWidgetLabel"],
        label[data-testid="stWidgetLabel"] p,
        label[data-testid="stWidgetLabel"] span,
        div[data-testid="stRadio"] label span,
        div[data-testid="stCheckbox"] label span,
        div[data-testid="stExpander"] summary span,
        div[data-testid="stExpander"] summary p,
        div[data-testid="stStatusWidget"] *,
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] *,
        .stTable th, .stTable td, table th, table td {
            color: #F8FAFC !important;
        }
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4 {
            color: #FFFFFF !important;
        }
        div[data-testid="stCaptionContainer"],
        div[data-testid="stCaptionContainer"] p,
        div[data-testid="stCaptionContainer"] span {
            color: #94A3B8 !important;
        }
        div[data-testid="stMarkdownContainer"] a {
            color: #00F5D4 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMarkdownContainer"] code {
            background: rgba(15, 23, 42, 0.9) !important;
            color: #00F5D4 !important;
            border: 1px solid rgba(0, 245, 212, 0.35) !important;
            padding: 2px 6px !important;
            border-radius: 6px !important;
        }

        /* 사이드바: 다크 홀로그램 글래스 */
        section[data-testid="stSidebar"] {
            background: rgba(8, 12, 26, 0.96) !important;
            backdrop-filter: blur(22px) !important;
            border-right: 1px solid rgba(0, 245, 212, 0.28) !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4 {
            color: #F8FAFC !important;
        }

        /* 입력창 및 셀렉트박스·멀티셀렉트·숫자입력창·채팅창 다크 네온 고대비 대응 */
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="textarea"],
        div[data-testid="stNumberInputContainer"] {
            background: #0F172A !important;
            background-color: #0F172A !important;
            border: 1.5px solid rgba(0, 245, 212, 0.42) !important;
            color: #F8FAFC !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="select"] div,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="textarea"] textarea {
            color: #F8FAFC !important;
            -webkit-text-fill-color: #F8FAFC !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] svg {
            fill: #00F5D4 !important;
            color: #00F5D4 !important;
        }
        span[data-baseweb="tag"] {
            background: rgba(0, 245, 212, 0.18) !important;
            background-color: rgba(0, 245, 212, 0.18) !important;
            border: 1px solid rgba(0, 245, 212, 0.55) !important;
            color: #00F5D4 !important;
            border-radius: 8px !important;
        }
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] svg {
            color: #00F5D4 !important;
            fill: #00F5D4 !important;
            -webkit-text-fill-color: #00F5D4 !important;
            font-weight: 700 !important;
        }
        ul[data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="menu"],
        div[role="listbox"] {
            background: #0F172A !important;
            background-color: #0F172A !important;
            border: 1.5px solid rgba(0, 245, 212, 0.45) !important;
            border-radius: 12px !important;
        }
        div[data-baseweb="popover"] li,
        div[data-baseweb="menu"] li,
        div[role="option"],
        ul[data-testid="stSelectboxVirtualDropdown"] li {
            color: #F8FAFC !important;
            background: #0F172A !important;
            background-color: #0F172A !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="popover"] li *,
        div[role="option"] *,
        ul[data-testid="stSelectboxVirtualDropdown"] li * {
            color: #F8FAFC !important;
        }
        div[data-baseweb="popover"] li:hover,
        div[role="option"]:hover,
        ul[data-testid="stSelectboxVirtualDropdown"] li:hover {
            background: rgba(0, 245, 212, 0.20) !important;
            background-color: rgba(0, 245, 212, 0.20) !important;
            color: #00F5D4 !important;
        }
        div[data-testid="stChatInput"],
        div[data-testid="stChatInput"] > div {
            background: #0F172A !important;
            background-color: #0F172A !important;
            border: 1.5px solid rgba(0, 245, 212, 0.45) !important;
            color: #F8FAFC !important;
            border-radius: 16px !important;
        }
        div[data-testid="stChatInput"] textarea {
            color: #F8FAFC !important;
            -webkit-text-fill-color: #F8FAFC !important;
            font-weight: 600 !important;
        }
        div[data-testid="stChatInput"] textarea::placeholder {
            color: #94A3B8 !important;
            -webkit-text-fill-color: #94A3B8 !important;
        }

        /* 컨테이너 & 카드: 다크 옵시디언 네온 글래스 */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(13, 19, 38, 0.84) !important;
            backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(0, 245, 212, 0.28) !important;
            border-radius: 22px !important;
            box-shadow: 0 14px 36px -10px rgba(0, 245, 212, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
            padding: clamp(14px, 1.4vw, 20px) !important;
            transition: all 0.22s ease !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(0, 245, 212, 0.55) !important;
            box-shadow: 0 18px 42px -10px rgba(168, 85, 247, 0.25), 0 0 18px rgba(0, 245, 212, 0.16) !important;
        }
        details[data-testid="stExpander"],
        div[data-testid="stStatusWidget"] {
            background: rgba(15, 23, 42, 0.90) !important;
            border: 1px solid rgba(0, 245, 212, 0.28) !important;
            border-radius: 16px !important;
        }

        /* 📐 반응형 버튼 & 다운로드 버튼: 사이버 네온 캡슐 (내부 텍스트 대비 강제) */
        .stButton > button,
        .stDownloadButton > button {
            width: 100%;
            min-height: 42px !important;
            border-radius: 14px !important;
            font-weight: 700 !important;
            font-size: clamp(11.8px, 0.82vw, 13.5px) !important;
            line-height: 1.3 !important;
            padding: clamp(6px, 0.55vw, 10px) clamp(10px, 0.9vw, 16px) !important;
            word-break: keep-all !important;
            white-space: normal !important;
            border: 1.5px solid rgba(0, 245, 212, 0.42) !important;
            background: #0F172A !important;
            background-color: #0F172A !important;
            color: #00F5D4 !important;
            box-shadow: 0 4px 14px rgba(0, 245, 212, 0.10) !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
        }
        .stButton > button:not([kind="primary"]) *,
        .stButton > button[kind="secondary"] *,
        .stDownloadButton > button * {
            color: #00F5D4 !important;
            font-weight: 700 !important;
        }
        .stButton > button:not([kind="primary"]):hover,
        .stDownloadButton > button:hover {
            background: rgba(0, 245, 212, 0.20) !important;
            background-color: rgba(0, 245, 212, 0.20) !important;
            border-color: #00F5D4 !important;
            color: #FFFFFF !important;
            transform: translateY(-1.5px) !important;
            box-shadow: 0 0 20px rgba(0, 245, 212, 0.35) !important;
        }
        .stButton > button:not([kind="primary"]):hover *,
        .stDownloadButton > button:hover * {
            color: #FFFFFF !important;
        }
        /* 프라이머리 버튼: 네온 그라데이션 + 딥 어비설 네이비(#040711) 텍스트 강제 */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #00F5D4 0%, #38BDF8 50%, #A855F7 100%) !important;
            color: #040711 !important;
            font-weight: 800 !important;
            border: none !important;
            box-shadow: 0 8px 26px -4px rgba(0, 245, 212, 0.50) !important;
        }
        .stButton > button[kind="primary"] *,
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span {
            color: #040711 !important;
            font-weight: 800 !important;
        }
        .stButton > button[kind="primary"]:hover {
            color: #040711 !important;
            box-shadow: 0 0 30px rgba(0, 245, 212, 0.75), 0 0 40px rgba(168, 85, 247, 0.45) !important;
        }

        div[data-baseweb="tab-list"] {
            gap: clamp(4px, 0.6vw, 10px) !important;
            flex-wrap: wrap !important;
        }
        button[data-baseweb="tab"] {
            font-weight: 700 !important;
            font-size: clamp(12.5px, 0.9vw, 14.5px) !important;
            color: #94A3B8 !important;
            padding: 10px clamp(12px, 1.2vw, 20px) !important;
            white-space: nowrap !important;
        }
        button[data-baseweb="tab"] * {
            color: #94A3B8 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"],
        button[data-baseweb="tab"][aria-selected="true"] * {
            color: #00F5D4 !important;
            font-weight: 800 !important;
        }

        div[data-testid="stChatMessage"] {
            background: rgba(15, 23, 42, 0.86) !important;
            border: 1px solid rgba(56, 189, 248, 0.25) !important;
            border-radius: 18px !important;
            padding: 12px 16px !important;
            margin-bottom: 10px !important;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35) !important;
        }

        @media (max-width: 1200px) {
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 8px !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: calc(50% - 8px) !important;
                flex: 1 1 calc(50% - 8px) !important;
            }
        }
        @media (max-width: 680px) {
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
        }

        /* 물결표(~) 범위 표기 시 GFM strikethrough 오작동으로 인한 텍스트 가로줄(----) 완전 무효화 */
        del, s, strike {
            text-decoration: none !important;
            color: inherit !important;
            background: transparent !important;
        }

        /* 히어로 배너 (사이버 네온) */
        .hero-shell {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, rgba(13, 19, 38, 0.88) 0%, rgba(24, 16, 48, 0.84) 100%);
            backdrop-filter: blur(24px);
            border: 1px solid rgba(0, 245, 212, 0.40);
            border-radius: 26px;
            padding: 26px 30px;
            margin-bottom: 18px;
            box-shadow: 0 0 38px -6px rgba(0, 245, 212, 0.22), 0 0 60px -15px rgba(168, 85, 247, 0.28);
        }
        .vibe-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(135deg, #00F5D4, #A855F7);
            color: #040711;
            padding: 5px 14px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.05em;
            box-shadow: 0 0 16px rgba(0, 245, 212, 0.55);
        }
        .hero-title {
            font-size: 28px;
            font-weight: 800;
            color: #FFFFFF;
            margin: 10px 0 6px 0;
            letter-spacing: -0.02em;
            text-shadow: 0 0 18px rgba(0, 245, 212, 0.35);
        }
        .hero-desc {
            font-size: 14px;
            color: #CBD5E1;
            margin: 0 0 14px 0;
            line-height: 1.55;
        }
        .hero-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .hero-tag {
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(0, 245, 212, 0.38);
            color: #00F5D4;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            box-shadow: 0 0 10px rgba(0, 245, 212, 0.12);
        }

        /* 일정 타임라인 카드 (사이버 네온) */
        .timeline-card {
            background: rgba(15, 23, 42, 0.86);
            border: 1px solid rgba(0, 245, 212, 0.25);
            border-left: 4px solid #00F5D4;
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 12px;
            box-shadow: 0 8px 26px -6px rgba(0, 0, 0, 0.45);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .timeline-card:hover {
            transform: translateY(-2px);
            border-color: #00F5D4;
            box-shadow: 0 0 24px rgba(0, 245, 212, 0.22);
        }
        .timeline-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 8px;
        }
        .timeline-place {
            font-size: 16px;
            font-weight: 800;
            color: #F8FAFC;
        }
        .timeline-time {
            background: rgba(0, 245, 212, 0.14);
            color: #00F5D4;
            border: 1px solid rgba(0, 245, 212, 0.4);
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
        }
        .timeline-body {
            font-size: 13.5px;
            color: #CBD5E1;
            line-height: 1.55;
            margin-bottom: 8px;
        }
        .timeline-tip {
            background: rgba(168, 85, 247, 0.14);
            border: 1px solid rgba(168, 85, 247, 0.32);
            border-radius: 10px;
            padding: 7px 11px;
            font-size: 12px;
            color: #E9D5FF;
            margin-bottom: 10px;
        }

        .metric-pill {
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(0, 245, 212, 0.30);
            border-radius: 16px;
            padding: 12px 14px;
            text-align: center;
            box-shadow: 0 0 18px rgba(0, 245, 212, 0.10);
        }
        .metric-label { font-size: 11px; color: #94A3B8; font-weight: 600; }
        .metric-val { font-size: 14px; font-weight: 800; color: #00F5D4; margin-top: 2px; }

        .booking-chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: rgba(15, 23, 42, 0.9);
            color: #00F5D4 !important;
            border: 1px solid rgba(0, 245, 212, 0.42);
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            text-decoration: none !important;
            margin-right: 6px;
            margin-bottom: 6px;
            box-shadow: 0 0 10px rgba(0, 245, 212, 0.12);
            transition: all 0.18s ease;
        }
        .booking-chip:hover {
            background: linear-gradient(135deg, #00F5D4, #A855F7);
            color: #040711 !important;
            border-color: transparent;
            transform: translateY(-1px);
            box-shadow: 0 0 18px rgba(0, 245, 212, 0.55);
        }

        /* ⚡ 배경 3D 사이버 네온 그리드 & 홀로그램 에너지 파도 레이어 */
        .ambient-stage {
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }
        .cyber-glow-cyan {
            position: absolute;
            top: 8%;
            right: 8%;
            width: 480px;
            height: 480px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(0, 245, 212, 0.16) 0%, transparent 70%);
            filter: blur(25px);
            animation: pulseCyber 10s ease-in-out infinite alternate;
        }
        .cyber-glow-violet {
            position: absolute;
            bottom: 18%;
            left: 6%;
            width: 540px;
            height: 540px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(168, 85, 247, 0.18) 0%, rgba(236, 72, 153, 0.08) 45%, transparent 72%);
            filter: blur(28px);
            animation: pulseCyber 14s ease-in-out infinite alternate-reverse;
        }
        .cyber-grid-floor {
            position: absolute;
            bottom: -35%;
            left: -25%;
            width: 150%;
            height: 70%;
            background-image:
                linear-gradient(to right, rgba(0, 245, 212, 0.18) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(168, 85, 247, 0.22) 1px, transparent 1px);
            background-size: 56px 56px;
            transform: perspective(520px) rotateX(68deg);
            mask-image: linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.2) 60%, transparent 100%);
            -webkit-mask-image: linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.2) 60%, transparent 100%);
            animation: cyberGridMove 6s linear infinite;
        }
        .wave-dock {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 190px;
            overflow: hidden;
            line-height: 0;
        }
        .wave-track {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 200%;
            height: 100%;
            display: flex;
        }
        .wave-track svg {
            width: 50%;
            height: 100%;
        }
        .cyber-wave-1 {
            animation: waveRoll 16s linear infinite;
            filter: drop-shadow(0 0 12px rgba(0, 245, 212, 0.45));
        }
        .cyber-wave-2 {
            animation: waveRollReverse 22s linear infinite;
            filter: drop-shadow(0 0 14px rgba(168, 85, 247, 0.45));
        }
        @keyframes cyberGridMove {
            0% { background-position: 0 0; }
            100% { background-position: 0 56px; }
        }
        @keyframes waveRoll {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
        }
        @keyframes waveRollReverse {
            0% { transform: translateX(-50%); }
            100% { transform: translateX(0); }
        }
        @keyframes pulseCyber {
            0% { transform: scale(1) translate(0, 0); opacity: 0.75; }
            100% { transform: scale(1.15) translate(20px, -18px); opacity: 1; }
        }
        </style>

        <div class="ambient-stage">
            <div class="cyber-glow-cyan"></div>
            <div class="cyber-glow-violet"></div>
            <div class="cyber-grid-floor"></div>
            <div class="wave-dock">
                <div class="wave-track cyber-wave-1">
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(0, 245, 212, 0.10)" d="M0,208L80,197.3C160,187,320,165,480,176C640,187,800,229,960,229.3C1120,229,1280,187,1360,165.3L1440,144L1440,320L0,320Z"></path>
                        <path fill="none" stroke="rgba(0, 245, 212, 0.55)" stroke-width="2" d="M0,208L80,197.3C160,187,320,165,480,176C640,187,800,229,960,229.3C1120,229,1280,187,1360,165.3L1440,144"></path>
                    </svg>
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(0, 245, 212, 0.10)" d="M0,208L80,197.3C160,187,320,165,480,176C640,187,800,229,960,229.3C1120,229,1280,187,1360,165.3L1440,144L1440,320L0,320Z"></path>
                        <path fill="none" stroke="rgba(0, 245, 212, 0.55)" stroke-width="2" d="M0,208L80,197.3C160,187,320,165,480,176C640,187,800,229,960,229.3C1120,229,1280,187,1360,165.3L1440,144"></path>
                    </svg>
                </div>
                <div class="wave-track cyber-wave-2">
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(168, 85, 247, 0.12)" d="M0,240L60,229.3C120,219,240,197,360,197.3C480,197,600,219,720,234.7C840,251,960,261,1080,250.7C1200,240,1320,208,1380,192L1440,176L1440,320L0,320Z"></path>
                        <path fill="none" stroke="rgba(236, 72, 153, 0.50)" stroke-width="2" d="M0,240L60,229.3C120,219,240,197,360,197.3C480,197,600,219,720,234.7C840,251,960,261,1080,250.7C1200,240,1320,208,1380,192L1440,176"></path>
                    </svg>
                    <svg viewBox="0 0 1440 320" preserveAspectRatio="none">
                        <path fill="rgba(168, 85, 247, 0.12)" d="M0,240L60,229.3C120,219,240,197,360,197.3C480,197,600,219,720,234.7C840,251,960,261,1080,250.7C1200,240,1320,208,1380,192L1440,176L1440,320L0,320Z"></path>
                        <path fill="none" stroke="rgba(236, 72, 153, 0.50)" stroke-width="2" d="M0,240L60,229.3C120,219,240,197,360,197.3C480,197,600,219,720,234.7C840,251,960,261,1080,250.7C1200,240,1320,208,1380,192L1440,176"></path>
                    </svg>
                </div>
            </div>
        </div>
        """
    st.markdown(css_and_bg, unsafe_allow_html=True)


@st.cache_data
def load_travel_metadata() -> list[dict]:
    json_path = os.path.join(BASE_DIR, "data", "travel_metadata.json")
    if not os.path.exists(json_path):
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_welcome_message(trip_item: dict, vibe_mode: str = "nature") -> str:
    name = trip_item["name"]
    country = trip_item["country"]
    season = trip_item["best_season"]
    budget = trip_item["budget_level"]
    vibe_emoji = "🌿🌊" if vibe_mode == "nature" else "⚡🌃"
    return (
        f"안녕! 나는 너의 AI 여행 메이트 **파일럿 토리 🐣✈️**야!\n\n"
        f"지금 **[{country}] {name}** 여행을 보고 있구나! {vibe_emoji} "
        f"(추천 시기: `{season}` · 예상 예산: `{budget}`)\n\n"
        f"나랑 수다 떨면서 너한테 딱 맞는 여행 계획을 같이 완성해 볼까? 편하게 알려줘!\n"
        f"- 👥 **누구랑 함께 떠나는 여행이야?** *(혼자 / 친구들과 / 연인과 / 부모님·가족)*\n"
        f"- 🎨 **어떤 취향의 코스가 좋아?** *(☕ 감성 카페 & 힐링 / 🍣 로컬 맛집 투어 / 📸 인생샷 & 야경 / 🏛️ 역사·미술관)*\n"
        f"- ⏰ **아침 일찍 알차게 vs 느긋하게 늦잠 모드?**\n\n"
        f"위의 **빠른 취향 버튼**을 콕 누르거나 채팅창에 말해 주면, 내가 위키백과 진짜 정보를 찾아서 **오른쪽 창에 맞춤 2박 3일 일정표랑 동선 지도**를 바로 그려 줄게! 💚"
    )


def render_cited_sources(
    cited_sources: list[dict],
    all_contexts: list[dict] | None = None,
    expanded_queries: list[str] | None = None,
) -> None:
    """답변에 실제로 사용된 다단계(1차·2차) RAG 근거 문서의 제목과 원문 출처를 표시"""
    if not cited_sources:
        st.caption("ⓘ 답변에 인용된 근거 문서가 없습니다.")
    else:
        with st.expander(f"📚 참고한 여행 정보 및 출처 펼쳐보기 (1차·2차 다단계 RAG 근거 {len(cited_sources)}건)", expanded=False):
            if expanded_queries:
                st.caption("🔄 **2차 심층 RAG 확장 검색어**: " + " · ".join(f"`{q}`" for q in expanded_queries))
            for src in cited_sources:
                idx = src.get("index")
                rag_stage = src.get("rag_stage", "1차 RAG (기본·메타 검색)")
                src_type = src.get("source_type", "문서")
                title = src.get("title", "제목 없음")
                url = src.get("url", "")
                content = src.get("content", "")

                if str(url).startswith("http"):
                    st.markdown(f"**[근거 {idx}]** {title} · `{src_type}` · `{rag_stage}` · [원문 보기]({url})")
                else:
                    st.markdown(f"**[근거 {idx}]** {title} · `{src_type}` · `{rag_stage}`")

                if content:
                    preview = content[:260] + ("..." if len(content) > 260 else "")
                    st.caption(preview)

    if all_contexts:
        pass1_cnt = sum(1 for c in all_contexts if "1차" in str(c.get("rag_stage", "1차")))
        pass2_cnt = len(all_contexts) - pass1_cnt
        with st.expander(
            f"🔎 다단계 RAG 검색 문맥 전체 보기 (총 {len(all_contexts)}건 · 1차 RAG {pass1_cnt}건 + 2차 심층 RAG {pass2_cnt}건)",
            expanded=False,
        ):
            if expanded_queries:
                st.markdown("##### 🔄 2차 심층 RAG 확장 서브쿼리")
                st.markdown(" · ".join(f"`{q}`" for q in expanded_queries))
            for i, ctx in enumerate(all_contexts, start=1):
                stage_badge = ctx.get("rag_stage", "1차 RAG")
                st.markdown(f"**[문맥 {i}]** `{stage_badge}` | `{ctx['source_type']}` — {ctx['title']}")
                st.caption(ctx["content"][:280] + ("..." if len(ctx["content"]) > 280 else ""))


def render_gdm_style_route_map_html(
    structured_plan: dict,
    selected_day: int = 0,
    dest_name: str = "",
    vibe_mode: str = "nature",
) -> None:
    """테마(🌿 네이처 웨이브 vs ⚡ 사이버 네온)에 맞춰 스타일이 자동 전환되는 인터랙티브 동선 지도 + 클릭 가능한 방문 순서 칩스"""
    days = structured_plan.get("days", [])
    center_lat = structured_plan.get("center_lat") or 35.6762
    center_lng = structured_plan.get("center_lng") or 139.6503

    if vibe_mode == "cyber":
        day_palette = {1: "#00F5D4", 2: "#38BDF8", 3: "#E879F9"}
        card_bg = "rgba(13, 19, 38, 0.90)"
        card_border = "rgba(0, 245, 212, 0.35)"
        title_color = "#F8FAFC"
        sub_color = "#94A3B8"
        btn_bg = "rgba(0, 245, 212, 0.14)"
        btn_color = "#00F5D4"
        btn_border = "rgba(0, 245, 212, 0.45)"
        chip_bg = "rgba(15, 23, 42, 0.92)"
        chip_color = "#E2E8F0"
        chip_border = "rgba(56, 189, 248, 0.35)"
        pin_text_color = "#040711"
    elif vibe_mode == "winter":
        day_palette = {1: "#38BDF8", 2: "#818CF8", 3: "#C084FC"}
        card_bg = "rgba(10, 25, 47, 0.92)"
        card_border = "rgba(56, 189, 248, 0.4)"
        title_color = "#F0F9FF"
        sub_color = "#BAE6FD"
        btn_bg = "rgba(56, 189, 248, 0.15)"
        btn_color = "#38BDF8"
        btn_border = "rgba(56, 189, 248, 0.45)"
        chip_bg = "rgba(15, 30, 55, 0.92)"
        chip_color = "#E0F2FE"
        chip_border = "rgba(56, 189, 248, 0.35)"
        pin_text_color = "#0B1528"
    elif vibe_mode == "heritage":
        day_palette = {1: "#D97706", 2: "#DC2626", 3: "#B45309"}
        card_bg = "rgba(255, 253, 248, 0.96)"
        card_border = "rgba(217, 119, 6, 0.3)"
        title_color = "#451A03"
        sub_color = "#78350F"
        btn_bg = "#FEF3C7"
        btn_color = "#B45309"
        btn_border = "#FDE68A"
        chip_bg = "#FFFBEB"
        chip_color = "#78350F"
        chip_border = "#FCD34D"
        pin_text_color = "#FFFFFF"
    else:
        day_palette = {1: "#10B981", 2: "#0EA5E9", 3: "#8B5CF6"}
        card_bg = "rgba(255, 255, 255, 0.94)"
        card_border = "rgba(16, 185, 129, 0.25)"
        title_color = "#064E3B"
        sub_color = "#648276"
        btn_bg = "#ECFDF5"
        btn_color = "#047857"
        btn_border = "#A7F3D0"
        chip_bg = "#F8FAFC"
        chip_color = "#1E293B"
        chip_border = "#CBD5E1"
        pin_text_color = "#FFFFFF"

    seen_coords = []
    stops_data = []
    polylines_data = []

    for d_obj in days:
        d_num = int(d_obj.get("day", 1))
        if selected_day not in (0, d_num):
            continue
        color = day_palette.get(d_num, "#10B981")
        day_coords = []
        for idx, stop in enumerate(d_obj.get("schedule", []), start=1):
            lat = stop.get("lat")
            lng = stop.get("lng")
            if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
                continue
            if abs(lat) < 0.01 and abs(lng) < 0.01:
                continue
            lat, lng = float(lat), float(lng)
            for prev_lat, prev_lng in seen_coords:
                if abs(lat - prev_lat) < 0.0012 and abs(lng - prev_lng) < 0.0012:
                    lat += 0.0018 * idx
                    lng += 0.0018 * idx
            seen_coords.append((lat, lng))
            day_coords.append([lat, lng])

            place_name = str(stop.get("place", dest_name))
            time_str = str(stop.get("time_slot", ""))
            short_time = time_str.split("(")[0].strip()
            gmap_url = stop.get("google_maps_url") or make_google_maps_url(place_name, dest_name)
            food_url = stop.get("food_url") or make_google_maps_url(f"{place_name} 맛집", dest_name)
            pin_label = f"{idx}" if selected_day != 0 else f"{d_num}-{idx}"

            stops_data.append({
                "day": d_num,
                "spotNum": idx,
                "pinLabel": pin_label,
                "color": color,
                "name": place_name,
                "time": short_time,
                "lat": lat,
                "lng": lng,
                "mapsUrl": gmap_url,
                "foodUrl": food_url,
            })

        if len(day_coords) >= 2:
            polylines_data.append({"coords": day_coords, "color": color})

    route_dir_url = structured_plan.get("all_google_dir_url") or make_google_maps_url(dest_name)
    if selected_day in (1, 2, 3):
        matching = [d for d in days if int(d.get("day", 0)) == selected_day]
        if matching and matching[0].get("google_dir_url"):
            route_dir_url = matching[0]["google_dir_url"]

    title_text = f"{selected_day}일차 추천 동선 지도" if selected_day in (1, 2, 3) else "전체 여행 추천 동선 지도"
    subtitle_text = (
        f"Day {selected_day} 방문 순서대로 최단 경로 연결"
        if selected_day in (1, 2, 3)
        else "모든 일차의 이동 경로를 한눈에 확인하세요"
    )

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            * {{ box-sizing: border-box; font-family: 'Pretendard', -apple-system, sans-serif; }}
            body {{ margin: 0; padding: 0; background: transparent; }}
            .map-card {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 22px;
                padding: 16px;
                box-shadow: 0 12px 30px -8px rgba(0, 0, 0, 0.12);
            }}
            .map-header {{
                display: flex; align-items: center; justify-content: space-between;
                padding-bottom: 12px; margin-bottom: 12px;
                border-bottom: 1px solid {card_border};
            }}
            .map-title {{ font-size: 14.5px; font-weight: 800; color: {title_color}; margin: 0; }}
            .map-sub {{ font-size: 11px; color: {sub_color}; margin: 2px 0 0 0; }}
            .gmap-route-btn {{
                background: {btn_bg}; color: {btn_color}; border: 1px solid {btn_border};
                padding: 6px 13px; border-radius: 999px; font-size: 11px; font-weight: 700;
                text-decoration: none; transition: all 0.2s ease; white-space: nowrap;
            }}
            .gmap-route-btn:hover {{
                background: #10B981; color: #FFFFFF; border-color: #10B981;
            }}
            .map-wrap {{
                position: relative; width: 100%; height: 335px; border-radius: 16px;
                overflow: hidden; border: 1px solid {card_border};
            }}
            #route-map {{ width: 100%; height: 100%; }}
            .map-badge {{
                position: absolute; bottom: 10px; left: 10px; z-index: 1000;
                background: {card_bg}; backdrop-filter: blur(10px);
                padding: 5px 12px; border-radius: 999px; border: 1px solid {card_border};
                font-size: 11px; font-weight: 700; color: {title_color};
                display: flex; align-items: center; gap: 6px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.12);
            }}
            .pulse-dot {{
                width: 8px; height: 8px; border-radius: 50%; background: #10B981;
            }}
            .route-marker-pin {{
                width: 30px; height: 30px; border-radius: 50%;
                border: 2.5px solid #FFFFFF; color: {pin_text_color};
                font-weight: 800; font-size: 12px;
                display: flex; align-items: center; justify-content: center;
                box-shadow: 0 4px 14px rgba(16, 185, 129, 0.45);
                cursor: pointer; transition: transform 0.2s ease;
            }}
            .route-marker-pin:hover {{ transform: scale(1.2); }}
            .chips-header {{
                display: flex; align-items: center; justify-content: space-between;
                font-size: 11px; font-weight: 700; color: {sub_color}; margin-top: 12px; margin-bottom: 6px;
            }}
            .chips-row {{
                display: flex; align-items: center; gap: 6px; overflow-x: auto;
                padding-bottom: 4px;
            }}
            .spot-chip {{
                flex-shrink: 0; padding: 6px 12px; border-radius: 999px;
                background: {chip_bg}; color: {chip_color}; border: 1px solid {chip_border};
                font-size: 12px; font-weight: 700; cursor: pointer;
                display: inline-flex; align-items: center; gap: 6px;
                transition: all 0.15s ease;
            }}
            .spot-chip:hover {{
                border-color: #10B981;
                transform: translateY(-1px);
            }}
            .spot-num {{
                width: 18px; height: 18px; border-radius: 50%; color: {pin_text_color};
                font-size: 10px; font-weight: 800; display: inline-flex;
                align-items: center; justify-content: center;
            }}
            .arrow {{ color: #10B981; font-weight: 800; font-size: 12px; flex-shrink: 0; }}
        </style>
    </head>
    <body>
        <div class="map-card">
            <div class="map-header">
                <div>
                    <p class="map-title">🗺️ {title_text}</p>
                    <p class="map-sub">{subtitle_text}</p>
                </div>
                <a href="{route_dir_url}" target="_blank" class="gmap-route-btn">구글 지도 전체 동선 길찾기 ↗</a>
            </div>
            <div class="map-wrap">
                <div id="route-map"></div>
                <div class="map-badge">
                    <span class="pulse-dot"></span>
                    <span>총 {len(stops_data)}개 추천 스팟 동선 연결됨</span>
                </div>
            </div>
            <div class="chips-header">
                <span>📍 방문 순서 칩스 (클릭하면 지도가 해당 명소로 이동합니다)</span>
                <span style="font-weight:600;font-size:10px;">Day 1 · Day 2 · Day 3</span>
            </div>
            <div class="chips-row" id="chips-container"></div>
        </div>

        <script>
            var stops = {json.dumps(stops_data, ensure_ascii=False)};
            var polylines = {json.dumps(polylines_data, ensure_ascii=False)};
            var map = L.map('route-map').setView([{center_lat}, {center_lng}], 12);

            var googleStreets = L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&hl=ko', {{
                maxZoom: 20,
                attribution: '&copy; Google Maps'
            }}).addTo(map);
            var osmLayer = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap'
            }});
            L.control.layers({{"구글 지도 (한국어)": googleStreets, "오픈스트리트맵": osmLayer}}).addTo(map);

            var bounds = [];
            var markers = [];

            polylines.forEach(function(pl) {{
                L.polyline(pl.coords, {{
                    color: pl.color, weight: 4, opacity: 0.88, dashArray: '6, 8'
                }}).addTo(map);
            }});

            stops.forEach(function(s, idx) {{
                var icon = L.divIcon({{
                    className: 'custom-pin',
                    html: '<div class="route-marker-pin" style="background:' + s.color + ';">' + s.pinLabel + '</div>',
                    iconSize: [30, 30],
                    iconAnchor: [15, 15],
                    popupAnchor: [0, -16]
                }});
                var popupHtml = '<div style="font-family:Pretendard,sans-serif;min-width:185px;line-height:1.45;">' +
                    '<div style="font-weight:800;font-size:13px;color:#0F172A;">[' + s.day + '일차] ' + s.name + '</div>' +
                    '<div style="font-size:11px;color:#059669;font-weight:700;margin-top:2px;">⏰ ' + s.time + '</div>' +
                    '<div style="margin-top:6px;display:flex;gap:8px;">' +
                    '<a href="' + s.mapsUrl + '" target="_blank" style="color:#047857;font-size:11px;font-weight:700;text-decoration:underline;">📍 구글 지도 ↗</a>' +
                    '<a href="' + s.foodUrl + '" target="_blank" style="color:#0284C7;font-size:11px;font-weight:700;text-decoration:underline;">🍽️ 주변 맛집 ↗</a>' +
                    '</div></div>';
                var m = L.marker([s.lat, s.lng], {{icon: icon}}).addTo(map).bindPopup(popupHtml);
                markers.push(m);
                bounds.push([s.lat, s.lng]);
            }});

            if (bounds.length === 1) {{
                map.setView(bounds[0], 14);
            }} else if (bounds.length > 1) {{
                map.fitBounds(bounds, {{padding: [40, 40], maxZoom: 15}});
            }}

            var chipsContainer = document.getElementById('chips-container');
            var chipsHtml = '';
            stops.forEach(function(s, idx) {{
                chipsHtml += '<button type="button" class="spot-chip" onclick="focusSpot(' + idx + ')">' +
                    '<span class="spot-num" style="background:' + s.color + ';">' + s.pinLabel + '</span>' +
                    '<span>' + s.name + '</span>' +
                    '</button>';
                if (idx < stops.length - 1) {{
                    chipsHtml += '<span class="arrow">➔</span>';
                }}
            }});
            chipsContainer.innerHTML = chipsHtml;

            window.focusSpot = function(idx) {{
                var s = stops[idx];
                if (!s) return;
                map.flyTo([s.lat, s.lng], 15, {{duration: 1.0}});
                setTimeout(function() {{
                    if (markers[idx]) markers[idx].openPopup();
                }}, 450);
            }};
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=490)


def render_interactive_planner_panel(
    trip_id: str,
    selected_trip: dict,
    chunk_size_val: int,
    chunk_overlap_val: int,
    top_k_val: int,
    force_recollect: bool,
    user_pref_summary: str,
    vibe_mode: str = "nature",
    panel_key: str = "side",
) -> None:
    """우측 옆 창: 심플하고 감각적인 맞춤 일정 대시보드"""
    dest_name = selected_trip["name"]
    country = selected_trip["country"]
    city_links = make_booking_links(dest_name, country)

    day_state_key = f"planner_day_{trip_id}"
    if day_state_key not in st.session_state:
        st.session_state[day_state_key] = 1

    header_icon = "🌿" if vibe_mode == "nature" else "⚡"
    st.markdown(f"#### {header_icon} {dest_name} 맞춤 일정 & 동선 플래너")

    # 원클릭 예약 & 지도 콘솔 바
    st.markdown(
        f'<div style="margin-bottom:10px;">'
        f'<a class="booking-chip" href="{city_links["google_maps"]}" target="_blank">📍 {dest_name} 구글 지도</a>'
        f'<a class="booking-chip" href="{city_links["agoda"]}" target="_blank">🏨 아고다 최저가</a>'
        f'<a class="booking-chip" href="{city_links["booking"]}" target="_blank">🏨 부킹닷컴</a>'
        f'<a class="booking-chip" href="{city_links["airbnb"]}" target="_blank">🏠 에어비앤비</a>'
        f'<a class="booking-chip" href="{city_links["skyscanner"]}" target="_blank">✈️ 스카이스캐너</a>'
        f'<a class="booking-chip" href="{city_links["klook"]}" target="_blank">🎟️ 클룩 액티비티</a>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        f"✨ 내 취향 반영 '{dest_name}' 2박 3일 일정표 & 동선 지도 생성",
        key=f"gen_itin_btn_{panel_key}",
        type="primary",
        use_container_width=True,
    ):
        with st.status(f"🐣 파일럿 토리가 '{dest_name}' 맞춤 코스와 최적 동선을 설계하고 있어요...", expanded=True) as status:
            st.write(f"1️⃣ `{dest_name}` 위키백과 명소·기후·역사 자료 확인 중...")
            collect_info = ensure_wiki_indexed(
                trip_id=trip_id,
                dest_name=dest_name,
                question=f"{dest_name} 관광 명소 랜드마크 역사 문화 음식 여행 코스 {user_pref_summary}",
                country=country,
                theme=selected_trip["theme"],
                force_recollect=force_recollect,
                chunk_size=chunk_size_val,
                chunk_overlap=chunk_overlap_val,
            )
            if collect_info["cached"]:
                st.caption(f"✓ 이미 수집된 위키 문서 {len(collect_info['selected_titles'])}건 활용")
            else:
                st.caption(f"✓ 위키 문서 {len(collect_info['selected_titles'])}건 수집 및 색인 완료")

            st.write("2️⃣ 다단계 RAG (1차 기본·메타 검색 ➔ 2차 랜드마크·미식·근교 MMR 심층 재검색) 및 동선 설계 중...")
            itin_res = generate_itinerary(
                trip_id=trip_id,
                dest_name=dest_name,
                country=country,
                user_preference=user_pref_summary,
                current_plan=st.session_state.itinerary_by_trip.get(trip_id, {}).get("structured_plan"),
                top_k=max(4, top_k_val),
            )
            st.session_state.itinerary_by_trip[trip_id] = itin_res
            st.session_state[day_state_key] = 1

            if trip_id in st.session_state.messages_by_trip:
                st.session_state.messages_by_trip[trip_id].append({
                    "role": "assistant",
                    "content": itin_res.get("bot_message", itin_res["answer"]),
                    "cited_sources": itin_res.get("cited_sources", []),
                    "all_contexts": itin_res.get("all_contexts", []),
                    "expanded_queries": itin_res.get("expanded_queries", []),
                })

            status.update(label=f"✨ '{dest_name}' 맞춤 2박 3일 일정표 & 동선 지도 완성!", state="complete", expanded=False)
        st.rerun()

    if trip_id not in st.session_state.itinerary_by_trip:
        with st.container(border=True):
            empty_icon = "🌿🌊" if vibe_mode == "nature" else "⚡🌃"
            st.markdown(
                f"""
                <div style="text-align:center;padding:36px 16px;">
                    <div style="font-size:44px;margin-bottom:8px;">🐣 {empty_icon}</div>
                    <h4 style="margin:6px 0 6px 0;font-weight:800;">나만의 {dest_name} 여행 코스를 그려볼까요?</h4>
                    <p style="font-size:13px;opacity:0.8;line-height:1.6;margin:0;">
                        왼쪽에서 <b>파일럿 토리 🐣</b>에게 취향을 말해주거나,<br/>
                        위의 <b>'2박 3일 일정표 & 동선 지도 생성'</b> 버튼을 눌러보세요!
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    itin_data = st.session_state.itinerary_by_trip[trip_id]
    structured_plan = itin_data.get("structured_plan", {})
    days_list = structured_plan.get("days", [])

    # 실시간 반영된 알러지·식이제한·맞춤 수정 배너 표시
    dietary_note = str(structured_plan.get("dietary_care_note") or "").strip()
    active_chat_constraints = st.session_state.get("chat_constraints_by_trip", {}).get(trip_id, [])
    if dietary_note or active_chat_constraints:
        care_bg = "#ECFDF5" if vibe_mode == "nature" else "rgba(0, 245, 212, 0.14)"
        care_border = "#10B981" if vibe_mode == "nature" else "#00F5D4"
        care_text_col = "#065F46" if vibe_mode == "nature" else "#00F5D4"
        notes_joined = dietary_note if dietary_note else " · ".join(active_chat_constraints)
        st.markdown(
            f"""
            <div style="background:{care_bg};border:1.5px solid {care_border};border-radius:14px;padding:10px 14px;margin-bottom:12px;">
                <div style="font-size:12.5px;font-weight:800;color:{care_text_col};">
                    🛡️ 실시간 맞춤 케어 & 대화 수정 반영 완료
                </div>
                <div style="font-size:12px;margin-top:3px;opacity:0.92;">
                    {html.escape(notes_joined)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 📤 친구·연인·가족과 공유하기: PDF / 인터랙티브 웹 가이드북(HTML) / 스마트폰 캘린더(.ics) / 마크다운 원클릭 저장 바
    with st.container(border=True):
        st.markdown("**📤 친구·연인·동행자와 여행 계획표 공유하기 (올인원 내보내기 & 캘린더 등록)**")
        st.caption("완성된 2박 3일 일정표, 동선 지도, 알러지·맞춤 케어 노트를 파일 하나로 저장해 카카오톡·캘린더로 바로 공유하세요.")
        exp_c1, exp_c2, exp_c3, exp_c4 = st.columns(4, gap="small")
        with exp_c1:
            try:
                pdf_bytes = export_itinerary_pdf_bytes(
                    selected_trip,
                    structured_plan,
                    st.session_state.get("packing_checklist", []),
                )
                st.download_button(
                    label="📄 일정표 PDF 저장",
                    data=pdf_bytes,
                    file_name=f"TripPilot_{dest_name}_2박3일_여행계획표.pdf",
                    mime="application/pdf",
                    key=f"dl_pdf_{panel_key}_{trip_id}",
                    use_container_width=True,
                )
            except Exception as e:
                st.caption(f"PDF 생성 준비 중: {e}")
        with exp_c2:
            html_bytes = export_itinerary_html_bytes(
                selected_trip,
                structured_plan,
                st.session_state.get("packing_checklist", []),
            )
            st.download_button(
                label="🌐 웹 가이드북 저장",
                data=html_bytes,
                file_name=f"TripPilot_{dest_name}_인터랙티브_가이드북.html",
                mime="text/html",
                key=f"dl_html_{panel_key}_{trip_id}",
                use_container_width=True,
            )
        with exp_c3:
            try:
                ics_bytes = export_itinerary_ics_bytes(
                    selected_trip,
                    structured_plan,
                )
                st.download_button(
                    label="📅 폰 캘린더 등록 (.ics)",
                    data=ics_bytes,
                    file_name=f"TripPilot_{dest_name}_일정.ics",
                    mime="text/calendar",
                    key=f"dl_ics_{panel_key}_{trip_id}",
                    use_container_width=True,
                )
            except Exception as e:
                st.caption(f"캘린더 파일 생성: {e}")
        with exp_c4:
            md_bytes = str(itin_data.get("answer", "")).encode("utf-8")
            st.download_button(
                label="📝 마크다운 (.md)",
                data=md_bytes,
                file_name=f"TripPilot_{dest_name}_일정표.md",
                mime="text/markdown",
                key=f"dl_md_{panel_key}_{trip_id}",
                use_container_width=True,
            )

        with st.expander("📱 스마트폰 카메라 스캔용 모바일 공유 QR 코드", expanded=False):
            qr_text = f"TripPilot {dest_name} 2박 3일 여행 가이드: {selected_trip['summary']} (추천 시기: {selected_trip['best_season']})"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={urllib.parse.quote(qr_text)}"
            q1, q2 = st.columns([1, 2.5])
            with q1:
                st.image(qr_url, caption="스마트폰 카메라로 스캔", width=140)
            with q2:
                st.markdown(f"**[{country}] {dest_name} 여행 요약 카드**")
                st.caption("친구들이나 동행자가 스마트폰 기본 카메라로 비추면 여행지 요약과 추천 일정을 바로 확인할 수 있습니다.")

    # 🗣️ 현지 식당·기사님께 바로 보여주는 AI 서바이벌 소통 카드
    all_spots_flat = []
    for d_item in days_list:
        for sc in d_item.get("schedule", []):
            if sc.get("place"):
                all_spots_flat.append(sc["place"])
    survival_data = generate_survival_cards(
        dest_name=dest_name,
        country=country,
        spots=all_spots_flat,
        active_constraints=active_chat_constraints or [c for c in user_pref_summary.split(",") if "알러지" in c],
    )
    with st.expander(f"🗣️ 현지 식당·택시 기사님 제시용 『AI 서바이벌 소통 카드』 ({survival_data['language_name']})", expanded=False):
        st.caption(f"말이 통하지 않을 때 스마트폰 화면을 현지 식당 직원이나 택시 기사님께 그대로 보여주세요! (언어: **{survival_data['language_name']}**)")
        sc_tab1, sc_tab2, sc_tab3 = st.tabs(["🚫 식당 알러지 카드", "🚕 기사님 택시 카드", "🆘 긴급 SOS 회화"])
        with sc_tab1:
            for acard in survival_data.get("allergy_cards", []):
                st.markdown(
                    f"""
                    <div style="background:#FFFBEB;border:2px solid #F59E0B;border-radius:16px;padding:14px;margin-bottom:10px;">
                        <div style="font-size:15px;font-weight:800;color:#92400E;">{acard['icon']} {acard['title']} (직원에게 보여주세요)</div>
                        <div style="font-size:18px;font-weight:800;color:#1E293B;margin:8px 0;background:#FFFFFF;padding:10px 12px;border-radius:10px;border:1px solid #FCD34D;">
                            {acard['foreign'].replace(chr(10), '<br/>')}
                        </div>
                        <div style="font-size:12.5px;color:#059669;font-weight:700;">🗣️ 발음: {acard['pronounce']}</div>
                        <div style="font-size:12px;color:#78350F;margin-top:4px;">🇰🇷 뜻: {acard['korean']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        with sc_tab2:
            st.markdown(f"**🚕 주요 명소 목적지 카드 (기사님께 화면을 보여주세요)**")
            for tcard in survival_data.get("taxi_cards", []):
                st.markdown(
                    f"""
                    <div style="background:#F0FDF4;border:1.5px solid #10B981;border-radius:14px;padding:12px;margin-bottom:8px;">
                        <div style="font-weight:800;font-size:13px;color:#065F46;">📍 목적지: {tcard['place']}</div>
                        <div style="font-size:15px;font-weight:800;color:#0F172A;margin:6px 0;background:#FFFFFF;padding:8px 10px;border-radius:8px;">
                            {tcard['foreign'].replace(chr(10), '<br/>')}
                        </div>
                        <div style="font-size:12px;color:#047857;font-weight:600;">🗣️ 발음: {tcard['pronounce']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        with sc_tab3:
            st.markdown(f"**🆘 현지 필수 생존 회화 TOP**")
            for kr_p, for_p, pro_p in survival_data.get("sos_phrases", []):
                st.markdown(f"• **{kr_p}** ➔ `{for_p}` *(발음: {pro_p})*")

    # 상단 핵심 요약 배지 (4대 미니멀 글래스 필)
    m_cols = st.columns(4)
    with m_cols[0]:
        st.markdown(
            '<div class="metric-pill"><div class="metric-label">여행 일정</div>'
            '<div class="metric-val">2박 3일</div></div>',
            unsafe_allow_html=True,
        )
    with m_cols[1]:
        st.markdown(
            f'<div class="metric-pill"><div class="metric-label">예상 경비</div>'
            f'<div class="metric-val">{selected_trip["budget_level"].split("(")[0].strip()}</div></div>',
            unsafe_allow_html=True,
        )
    with m_cols[2]:
        st.markdown(
            f'<div class="metric-pill"><div class="metric-label">추천 시기</div>'
            f'<div class="metric-val">{selected_trip["best_season"].split(",")[0].strip()}</div></div>',
            unsafe_allow_html=True,
        )
    with m_cols[3]:
        st.markdown(
            '<div class="metric-pill"><div class="metric-label">동선 검증</div>'
            '<div class="metric-val">위키 근거 완료</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")

    # ── 반응형 일차 전환 바 (화면 크기에 맞춰 찌그러지지 않는 5-탭 + 이전/다음 네비게이션) ──
    cur_day = st.session_state[day_state_key]
    tab_cols = st.columns([1.05, 0.95, 0.95, 0.95, 1.15], gap="small")

    with tab_cols[0]:
        if st.button(
            "🌐 전체",
            key=f"day0_{panel_key}",
            type="primary" if cur_day == 0 else "secondary",
            use_container_width=True,
        ):
            st.session_state[day_state_key] = 0
            st.rerun()
    for d_idx in [1, 2, 3]:
        with tab_cols[d_idx]:
            if st.button(
                f"Day {d_idx}",
                key=f"day{d_idx}_{panel_key}",
                type="primary" if cur_day == d_idx else "secondary",
                use_container_width=True,
            ):
                st.session_state[day_state_key] = d_idx
                st.rerun()
    with tab_cols[4]:
        if st.button(
            "💰 예산·숙소",
            key=f"day4_{panel_key}",
            type="primary" if cur_day == 4 else "secondary",
            use_container_width=True,
        ):
            st.session_state[day_state_key] = 4
            st.rerun()

    arrow_cols = st.columns([1, 2.2, 1], gap="small")
    with arrow_cols[0]:
        if st.button("◀ 이전 일차", key=f"prev_day_{panel_key}", use_container_width=True):
            st.session_state[day_state_key] = (cur_day - 1) if cur_day > 0 else 4
            st.rerun()
    with arrow_cols[1]:
        day_label_map = {
            0: "🌐 전체 일정 요약 보기",
            1: "📅 Day 1 동선 & 타임라인",
            2: "📅 Day 2 동선 & 타임라인",
            3: "📅 Day 3 동선 & 타임라인",
            4: "💰 예산 배분 & 추천 숙소",
        }
        st.markdown(
            f'<div style="text-align:center;padding-top:8px;font-size:12.5px;font-weight:800;opacity:0.88;">'
            f'{day_label_map.get(cur_day, "")}</div>',
            unsafe_allow_html=True,
        )
    with arrow_cols[2]:
        if st.button("다음 일차 ▶", key=f"next_day_{panel_key}", use_container_width=True):
            st.session_state[day_state_key] = (cur_day + 1) if cur_day < 4 else 0
            st.rerun()

    active_day = st.session_state[day_state_key]

    # 1) 테마 연동 인터랙티브 동선 지도 렌더링
    if days_list and active_day in (0, 1, 2, 3):
        render_gdm_style_route_map_html(
            structured_plan,
            selected_day=active_day,
            dest_name=dest_name,
            vibe_mode=vibe_mode,
        )

    # 2) 선택된 탭별 상세 일정표 / 예산·숙소 뷰
    if active_day == 0:
        with st.container(border=True):
            st.markdown(itin_data["answer"])
    elif active_day in (1, 2, 3):
        matching_days = [d for d in days_list if int(d.get("day", 0)) == active_day]
        if matching_days:
            d_obj = matching_days[0]
            stay_area = d_obj.get("stay_area", dest_name)
            stay_links = make_booking_links(dest_name, country, stay_area)
            st.markdown(f"#### 📅 Day {active_day} · {d_obj.get('theme_title', '')}")

            for idx, item in enumerate(d_obj.get("schedule", []), start=1):
                place = html.escape(str(item.get("place", dest_name)))
                t_slot = html.escape(str(item.get("time_slot", "")))
                act = html.escape(str(item.get("activity", "")))
                tip = html.escape(str(item.get("tip", "")))
                trans = html.escape(str(item.get("transport", "도보/대중교통")))
                gmap = item.get("google_maps_url") or make_google_maps_url(item.get("place", dest_name), dest_name, country)
                food_url = item.get("food_url") or make_google_maps_url(f"{item.get('place', dest_name)} 맛집", dest_name, country)
                klook_spot = item.get("klook_url") or f"https://www.klook.com/ko/search/result/?query={item.get('place', dest_name)}"

                tip_html = f'<div class="timeline-tip">💡 <b>토리의 꿀팁</b>: {tip}</div>' if tip else ""
                st.markdown(
                    f"""
                    <div class="timeline-card">
                        <div class="timeline-header">
                            <span class="timeline-place">{idx}. {place}</span>
                            <div>
                                <span class="timeline-time">⏰ {t_slot}</span>
                                <span class="timeline-time" style="margin-left:4px;">🚇 {trans}</span>
                            </div>
                        </div>
                        <div class="timeline-body">{act}</div>
                        {tip_html}
                        <div>
                            <a class="booking-chip" href="{gmap}" target="_blank">📍 구글 지도</a>
                            <a class="booking-chip" href="{food_url}" target="_blank">🍽️ 주변 맛집</a>
                            <a class="booking-chip" href="{klook_spot}" target="_blank">🎟️ 입장권·투어</a>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with st.container(border=True):
                st.markdown(f"**🏨 Day {active_day} 추천 숙소 거점: `{stay_area}`**")
                st.markdown(
                    f'<a class="booking-chip" href="{stay_links["google_maps"]}" target="_blank">📍 숙소 주변 지도</a>'
                    f'<a class="booking-chip" href="{stay_links["agoda"]}" target="_blank">🏨 아고다 특가</a>'
                    f'<a class="booking-chip" href="{stay_links["booking"]}" target="_blank">🏨 부킹닷컴</a>'
                    f'<a class="booking-chip" href="{stay_links["airbnb"]}" target="_blank">🏠 에어비앤비</a>'
                    f'<a class="booking-chip" href="{stay_links["google_hotels"]}" target="_blank">🛏️ 구글 호텔</a>',
                    unsafe_allow_html=True,
                )

            # ✏️ 사용자가 직접 특정 시간대·장소·메뉴를 커스텀 편집할 수 있는 에디터
            with st.expander(f"✏️ Day {active_day} 일정표 직접 수정하기 (장소·시간·식당·메모 커스텀 편집)", expanded=False):
                st.caption("토리와 채팅으로 수정할 수도 있고, 아래에서 직접 장소나 메뉴를 고쳐서 지도·PDF·가이드북에 즉시 반영할 수도 있어요!")
                sched_items = d_obj.get("schedule", [])
                updated_sched = []
                for s_idx, s_item in enumerate(sched_items):
                    st.markdown(f"**📍 스팟 {s_idx + 1}**")
                    ec1, ec2 = st.columns([1.2, 1.0])
                    with ec1:
                        new_place = st.text_input(
                            "장소 / 식당명",
                            value=str(s_item.get("place", "")),
                            key=f"edit_place_{panel_key}_{trip_id}_d{active_day}_{s_idx}",
                        )
                    with ec2:
                        new_time = st.text_input(
                            "시간대",
                            value=str(s_item.get("time_slot", "")),
                            key=f"edit_time_{panel_key}_{trip_id}_d{active_day}_{s_idx}",
                        )
                    new_act = st.text_input(
                        "활동 및 추천 메뉴 설명",
                        value=str(s_item.get("activity", "")),
                        key=f"edit_act_{panel_key}_{trip_id}_d{active_day}_{s_idx}",
                    )
                    new_tip = st.text_input(
                        "여행 팁 / 알러지·대체 메뉴 메모",
                        value=str(s_item.get("tip", "")),
                        key=f"edit_tip_{panel_key}_{trip_id}_d{active_day}_{s_idx}",
                    )
                    copied = dict(s_item)
                    copied["place"] = new_place.strip() or s_item.get("place", dest_name)
                    copied["time_slot"] = new_time.strip() or s_item.get("time_slot", "")
                    copied["activity"] = new_act.strip() or s_item.get("activity", "")
                    copied["tip"] = new_tip.strip()
                    copied["google_maps_url"] = make_google_maps_url(copied["place"], dest_name, country)
                    copied["food_url"] = make_google_maps_url(f"{copied['place']} 맛집", dest_name, country)
                    updated_sched.append(copied)

                if st.button(
                    f"💾 Day {active_day} 직접 수정 사항 저장 (동선 지도·PDF 즉시 반영)",
                    key=f"save_manual_{panel_key}_{trip_id}_d{active_day}",
                    type="primary",
                    use_container_width=True,
                ):
                    d_obj["schedule"] = updated_sched
                    d_obj["google_dir_url"] = make_google_maps_dir_url(
                        [x["place"] for x in updated_sched], dest_name, country
                    )
                    all_places_flat = []
                    for d_iter in days_list:
                        for sc in d_iter.get("schedule", []):
                            if sc.get("place"):
                                all_places_flat.append(sc["place"])
                    structured_plan["all_google_dir_url"] = make_google_maps_dir_url(
                        all_places_flat, dest_name, country
                    )
                    st.toast(f"Day {active_day} 일정이 수정되어 동선 지도와 PDF/HTML 가이드북에 반영되었습니다!", icon="✅")
                    st.rerun()
    elif active_day == 4:
        st.markdown(f"#### 💰 {dest_name} 예산 배분 포트폴리오 & 추천 숙소")
        st.caption(f"기준 예산 수준: **{selected_trip['budget_level']}**")
        breakdown = structured_plan.get("budget_breakdown") or [
            {"category": "🏨 숙박비", "ratio": 35, "desc": "추천 숙소 구역 2박 기준"},
            {"category": "🍽️ 식비 & 카페", "ratio": 28, "desc": "현지 미식 및 감성 카페"},
            {"category": "🚇 현지 교통비", "ratio": 15, "desc": "공항 및 도심 대중교통"},
            {"category": "🎟️ 입장권 & 투어", "ratio": 14, "desc": "주요 명소 티켓 및 투어"},
            {"category": "🛡️ 예비비", "ratio": 8, "desc": "기념품 및 비상 예산"},
        ]
        with st.container(border=True):
            for b in breakdown:
                ratio = int(b.get("ratio", 20))
                st.markdown(f"**{b.get('category')}** — `{ratio}%` · *{b.get('desc', '')}*")
                st.progress(min(max(ratio, 0), 100))

        stays = structured_plan.get("recommended_stays", [])
        if stays:
            st.markdown("#### 🏨 추천 숙박 지역 & 원클릭 예약")
            for s in stays:
                links = s.get("links") or make_booking_links(dest_name, country, s.get("area_name", ""))
                with st.container(border=True):
                    st.markdown(f"**{s.get('area_name', dest_name)}** (`{s.get('style', '추천 숙소')}`)")
                    st.write(s.get("reason", ""))
                    st.markdown(
                        f'<a class="booking-chip" href="{links["google_maps"]}" target="_blank">📍 구글 지도</a>'
                        f'<a class="booking-chip" href="{links["agoda"]}" target="_blank">🏨 아고다 최저가</a>'
                        f'<a class="booking-chip" href="{links["booking"]}" target="_blank">🏨 부킹닷컴</a>'
                        f'<a class="booking-chip" href="{links["airbnb"]}" target="_blank">🏠 에어비앤비</a>',
                        unsafe_allow_html=True,
                    )

        st.markdown("#### 🔍 파일럿 토리의 맞춤 여행 꿀팁")
        with st.container(border=True):
            if structured_plan.get("best_season_tip"):
                st.markdown(f"- **🌤️ 추천 시즌 & 날씨**: {structured_plan['best_season_tip']}")
            if structured_plan.get("budget_transport_tip"):
                st.markdown(f"- **🚇 예산 & 교통 패스 팁**: {structured_plan['budget_transport_tip']}")
            if structured_plan.get("plan_b_tip"):
                st.markdown(f"- **☔ 우천·돌발 대비 플랜 B**: {structured_plan['plan_b_tip']}")

    render_cited_sources(
        itin_data.get("cited_sources", []),
        itin_data.get("all_contexts"),
        itin_data.get("expanded_queries"),
    )


def ensure_wiki_indexed(
    trip_id: str,
    dest_name: str,
    question: str,
    country: str,
    theme: str,
    force_recollect: bool,
    chunk_size: int,
    chunk_overlap: int,
) -> dict:
    """선택 여행지의 위키 문서를 수집·색인하고 결과 요약을 반환 (캐시 적중 시 생략)"""
    return process_wiki_for_destination(
        trip_id=trip_id,
        dest_name=dest_name,
        sample_question=question,
        country=country,
        theme=theme,
        force_recollect=force_recollect,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


# 2. 비정상 상황 점검 안내
api_key = get_api_key()
if not api_key or api_key == "your_key_here":
    st.error("⚠️ `.env` 파일에 유효한 `GMS_KEY`가 설정되지 않았습니다. `.env`에 API 키를 입력한 뒤 다시 실행해 주세요.")
    st.stop()

travel_list = load_travel_metadata()
if not travel_list:
    st.error("⚠️ 여행지 데이터 파일(`data/travel_metadata.json`)이 없습니다. 먼저 `python src/make_data.py`를 실행해 주세요.")
    st.stop()

meta_count = get_collection_count(META_COLLECTION)
wiki_count = get_collection_count(WIKI_COLLECTION)

if meta_count == 0:
    st.warning(
        "⚠️ 현재 색인된 여행지 메타데이터가 0건입니다. "
        "터미널에서 `python src/index_metadata.py`를 실행해 메타데이터를 색인해 주세요."
    )

# 3. 세션 상태 초기화
if "messages_by_trip" not in st.session_state:
    st.session_state.messages_by_trip = {}
if "selected_trip_id" not in st.session_state:
    st.session_state.selected_trip_id = str(travel_list[0]["id"])
if "condition_results" not in st.session_state:
    st.session_state.condition_results = None
if "itinerary_by_trip" not in st.session_state:
    st.session_state.itinerary_by_trip = {}
if "chat_constraints_by_trip" not in st.session_state:
    st.session_state.chat_constraints_by_trip = {}
if "vibe_override" not in st.session_state:
    st.session_state.vibe_override = "auto"  # 'auto', 'nature', 'cyber'
if "packing_checklist" not in st.session_state:
    st.session_state.packing_checklist = [
        {"item": "여권 및 항공권 e-티켓 (유효기간 6개월 이상 확인)", "done": True},
        {"item": "해외 결제 카드 (트래블로그/트래블월렛) & 현지 비상 현금", "done": True},
        {"item": "로밍 / 유심(USIM) / eSIM 사전 개통", "done": False},
        {"item": "멀티 어댑터 & 대용량 보조배터리", "done": False},
        {"item": "상비약 (소화제, 진통제, 밴드, 멀미약)", "done": False},
        {"item": "우산 / 우비 및 일교차 대비 가벼운 겉옷", "done": False},
    ]


def select_destination_callback(target_trip_id: str):
    """조건 탐색 카드에서 여행지 선택 시 사이드바 필터와 선택 상태를 즉시 동기화"""
    st.session_state.selected_trip_id = str(target_trip_id)
    st.session_state.continent_filter = "전체 대륙"
    st.session_state.theme_filter = "전체 테마"


# 4. 사이드바 구성
with st.sidebar:
    st.markdown("## 🐣 TripPilot")
    st.caption("AI 여행 메이트 토리 & 맞춤 일정 플래너")

    continents = ["전체 대륙"] + sorted(list({item["continent"] for item in travel_list}))
    selected_continent = st.selectbox("🌍 대륙 선택", continents, key="continent_filter")

    all_themes_set = set()
    for item in travel_list:
        for t in item["theme"].split("/"):
            if t.strip():
                all_themes_set.add(t.strip())
    theme_options = ["전체 테마"] + sorted(list(all_themes_set))
    selected_theme = st.selectbox("🏷️ 여행 테마 선택", theme_options, key="theme_filter")

    filtered_trips = travel_list
    if selected_continent != "전체 대륙":
        filtered_trips = [item for item in filtered_trips if item["continent"] == selected_continent]
    if selected_theme != "전체 테마":
        filtered_trips = [item for item in filtered_trips if selected_theme in item["theme"].split("/")]

    if not filtered_trips:
        st.info("해당 대륙/테마 조합의 여행지가 없어 전체 목록을 표시합니다.")
        filtered_trips = travel_list

    trip_id_to_item = {str(item["id"]): item for item in filtered_trips}
    if st.session_state.selected_trip_id not in trip_id_to_item:
        st.session_state.selected_trip_id = str(filtered_trips[0]["id"])

    id_options = list(trip_id_to_item.keys())
    current_idx = id_options.index(st.session_state.selected_trip_id)

    chosen_id = st.selectbox(
        "📍 여행할 도시 · 랜드마크",
        options=id_options,
        index=current_idx,
        format_func=lambda tid: f"[{trip_id_to_item[tid]['country']}] {trip_id_to_item[tid]['name']} ({trip_id_to_item[tid]['theme']})",
    )
    st.session_state.selected_trip_id = chosen_id
    selected_trip = trip_id_to_item[chosen_id]
    trip_id = str(selected_trip["id"])
    dest_name = selected_trip["name"]

    # 여행지 성격에 따른 테마 자동 감지 & 수동 전환 옵션
    auto_vibe = detect_destination_vibe(selected_trip)
    vibe_choice = st.radio(
        "🎨 배경 무드 (여행지 성격 자동 연동)",
        options=["auto", "nature", "heritage", "winter", "cyber"],
        format_func=lambda v: (
            f"🔄 여행지 자동 ({'❄️ 윈터 오로라' if auto_vibe == 'winter' else ('🏛️ 헤리티지 선셋' if auto_vibe == 'heritage' else ('⚡ 네온 퓨처' if auto_vibe == 'cyber' else '🌿 네이처 파도'))})"
            if v == "auto"
            else {
                "nature": "🌿 네이처 & 오션 웨이브 (자연/휴양)",
                "heritage": "🏛️ 클래식 헤리티지 선셋 (역사/유적/예술)",
                "winter": "❄️ 오로라 & 윈터 스노우 (설경/오로라)",
                "cyber": "⚡ 사이버 네온 시티 (대도시/야경)",
            }.get(v, v)
        ),
        horizontal=False,
        key="vibe_override",
    )
    active_vibe = auto_vibe if vibe_choice == "auto" else vibe_choice

    with st.expander("🎨 4대 공간 공감 디자인 철학 (Spatial Empathy)", expanded=False):
        st.markdown(
            """
**1. 핵심 디자인 철학: 공간 공감(Spatial Empathy)**
- 여행 계획은 단순한 텍스트 검색이 아니라 **여행지의 공기·빛·온도를 미리 경험하는 과정**이라는 철학으로 설계되었습니다.

**2. 4대 공간 공감 비주얼 테마 시스템**
- **🌿 Biophilic Serenity (자연·휴양·해양·섬)**
  - *영감*: 숲의 피톤치드(`#059669`)와 파도 윤슬(`#F7FDF9`). 3중 SVG 파도 애니메이션으로 시각적 휴식을 제공합니다.
- **🏛️ Classic Heritage & Sunset Gold (역사·유적·고도·예술 도시: 교토, 로마, 경주 등)**
  - *영감*: 따뜻한 파피루스 아이보리(`#FAF5EC`)와 황금빛 노을(`#B45309`). 하늘로 피어오르는 골든 더스트 입자 효과.
- **❄️ Aurora & Winter Wonderland (설경·오로라·빙하: 삿포로, 인터라켄, 레이캬비크 등)**
  - *영감*: 딥 네이비 밤하늘과 빛나는 오로라 리본 커튼, 화면 가득 흩날리는 **실시간 눈송이(Snowfall)** 애니메이션.
- **⚡ Neo-Urban Horizon (메가시티·마천루·야경: 도쿄, 뉴욕, 싱가포르 등)**
  - *영감*: 야간 비행 조종석(HUD)과 미래 도시 스카이라인. 다크 옵시디언 글래스 & 네온 시안/바이올렛 3D 그리드.
            """
        )

    wiki_cache = load_wiki_cache()
    trip_cached_info = wiki_cache.get(trip_id, {})
    cached_titles = trip_cached_info.get("titles", [])
    sidebar_links = make_booking_links(dest_name, selected_trip["country"])

    st.markdown("#### 🗺️ 선택 여행지 요약")
    with st.container(border=True):
        st.markdown(
            f"""
**{selected_trip['name']}** (`{selected_trip['country']}` · {selected_trip['continent']})
- **테마**: `{selected_trip['theme']}`
- **예산**: `{selected_trip['budget_level']}`
- **추천 시기**: `{selected_trip['best_season']}`
- **소개**: {selected_trip['summary']}
            """
        )
        st.markdown(
            f'<a class="booking-chip" href="{sidebar_links["google_maps"]}" target="_blank">📍 구글 지도</a>'
            f'<a class="booking-chip" href="{sidebar_links["agoda"]}" target="_blank">🏨 숙소 검색</a>'
            f'<a class="booking-chip" href="{sidebar_links["skyscanner"]}" target="_blank">✈️ 항공권</a>',
            unsafe_allow_html=True,
        )

    st.caption(
        f"여행지 메타데이터 색인: {meta_count}건 | "
        f"수집된 위키 문서: {len(cached_titles)}건 (전체 {wiki_count}청크)"
    )
    if cached_titles:
        st.caption(" · ".join(cached_titles))

    with st.expander("⚙️ 검색 및 문서 분할 설정", expanded=False):
        search_type_label = st.radio(
            "문서 검색 방식",
            options=["similarity", "mmr"],
            format_func=lambda x: "유사도 중심 검색 (Similarity)" if x == "similarity" else "다양성 고려 검색 (MMR)",
            index=0,
        )
        top_k_val = st.slider("참조 문서 검색 수 (Top-k)", min_value=1, max_value=8, value=WIKI_TOP_K)
        chunk_size_val = st.select_slider("문서 청크 크기", options=[500, 800, 1000, 1500], value=CHUNK_SIZE)
        chunk_overlap_val = st.select_slider("청크 중복 길이", options=[50, 100, 200, 300], value=CHUNK_OVERLAP)
        force_recollect = st.checkbox("위키백과 문서 새로 수집하기", value=False)

    if st.button("🗑️ 현재 여행지 대화 초기화", use_container_width=True):
        st.session_state.messages_by_trip[trip_id] = [
            {"role": "assistant", "content": build_welcome_message(selected_trip, active_vibe), "cited_sources": []}
        ]
        st.rerun()

    st.divider()
    st.warning(DISCLAIMER_TEXT)
    st.caption("문서 출처: 한국어 위키백과 (CC BY-SA 4.0)")

# 선택된 무드(4대 공간 공감 테마) CSS 및 배경 애니메이션 주입
inject_theme_css_and_background(active_vibe, dest_name)

# 5. 메인 상단 미니멀 히어로 배너
if active_vibe == "winter":
    vibe_badge_text = "❄️ AURORA & WINTER WONDERLAND · 눈부신 설경과 신비로운 오로라 무드"
elif active_vibe == "heritage":
    vibe_badge_text = "🏛️ CLASSIC HERITAGE & SUNSET GOLD · 천년의 역사와 노을빛이 깃든 앤티크 무드"
elif active_vibe == "cyber":
    vibe_badge_text = "⚡ CYBER NEON METROPOLIS · 미래지향적 네온 시티 무드"
else:
    vibe_badge_text = "🌿 NATURE & OCEAN WAVE · 자연과 파도가 어우러진 힐링 무드"

st.markdown(
    f"""
    <div class="hero-shell">
        <span class="vibe-badge">{vibe_badge_text}</span>
        <div class="hero-title">[{selected_trip['country']}] {dest_name}</div>
        <p class="hero-desc">{selected_trip['summary']}</p>
        <div class="hero-tags">
            <span class="hero-tag">🗓️ 추천 시기 · {selected_trip['best_season']}</span>
            <span class="hero-tag">💰 예상 경비 · {selected_trip['budget_level']}</span>
            <span class="hero-tag">🧭 테마 · {selected_trip['theme']}</span>
            <span class="hero-tag">🐣 파일럿 토리 실시간 코파일럿</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_main, tab_explore, tab_compare, tab_friends, tab_factcheck = st.tabs([
    "🐣 토리랑 취향 채팅 & 맞춤 일정·동선 지도",
    "🔎 맞춤 조건으로 여행지 추천받기",
    "⚖️ 여행지 1:1 매치업 비교 보드",
    "👥 동행자 허브 (월별 옷차림 & N분의1 정산)",
    "⚖️ 여행 정보 사실 확인",
])

# ── 탭 1: 좌측(토리와 취향 채팅) + 우측(맞춤 일정·동선 지도 대시보드) ──
with tab_main:
    # 취향 & 알러지 & 출발 월 선택 바
    with st.container(border=True):
        pref_c1, pref_c2, pref_c3, pref_c4, pref_c5 = st.columns([1.0, 1.6, 0.95, 1.25, 0.8])
        with pref_c1:
            companion_choice = st.selectbox(
                "👥 누구와 함께 가나요?",
                ["👫 친구들과 우정 여행", "💑 연인과 로맨틱 여행", "👨‍👩‍👧 가족/부모님과 편한 여행", "🎒 혼자 떠나는 자유 여행"],
                key=f"comp_{trip_id}",
            )
        with pref_c2:
            style_choices = st.multiselect(
                "✨ 선호하는 여행 취향 (다중 선택)",
                [
                    "☕ 감성 카페 & 힐링",
                    "🍣 현지 미식 & 로컬 맛집",
                    "🏛️ 문화 예술 & 역사 유적",
                    "📸 인생샷 포토존",
                    "🌿 자연 & 산책 힐링",
                    "🛍️ 쇼핑 & 소품샵",
                    "🌃 야경 & 루프탑",
                    "🎢 액티비티 & 체험",
                ],
                default=["☕ 감성 카페 & 힐링", "🍣 현지 미식 & 로컬 맛집"],
                key=f"styles_{trip_id}",
            )
        with pref_c3:
            pace_choice = st.selectbox(
                "⏰ 일정 템포",
                ["😌 여유롭게 (힐링)", "👟 알차게 (핵심 정복)", "😴 늦잠 모드 (11시)"],
                key=f"pace_{trip_id}",
            )
        with pref_c4:
            dietary_choices = st.multiselect(
                "🛡️ 알러지·식이제한·배려",
                [
                    "🚫 생선·해산물 알러지 (육류 대체)",
                    "🚫 갑각류(새우·게) 알러지",
                    "🥜 견과류·땅콩 알러지",
                    "🥗 비건·채식 위주 식단",
                    "🥩 돼지고기 제외 (할랄)",
                    "♿ 계단 최소화·택시 이동",
                ],
                default=[],
                key=f"diet_{trip_id}",
            )
        with pref_c5:
            travel_month_num = st.selectbox(
                "📅 출발 예정 월",
                options=list(range(1, 13)),
                index=10,
                format_func=lambda m: f"{m}월",
                key=f"month_sel_{trip_id}",
            )

    chat_constraints_list = st.session_state.chat_constraints_by_trip.get(trip_id, [])
    all_constraints = list(dietary_choices) + [c for c in chat_constraints_list if c not in dietary_choices]
    constraint_str = f", 필수 배려·식이제한: {', '.join(all_constraints)}" if all_constraints else ""
    user_pref_summary = (
        f"{companion_choice}, 선호 테마: {', '.join(style_choices) or '힐링/미식'}, "
        f"템포: {pace_choice}, 출발 예정: {travel_month_num}월{constraint_str}"
    )

    # 💱 실시간 체감 환율 및 현지 물가 지표 바
    currency_info = get_currency_and_cost_info(selected_trip["country"])
    with st.container(border=True):
        st.markdown(f"**💱 {dest_name} 실시간 체감 환율 & 현지 물가 시뮬레이터** `(현지 통화: {currency_info['currency']})`")
        curr_c1, curr_c2, curr_c3, curr_c4 = st.columns(4)
        sample_krw = int(round(currency_info["sample_amt"] * currency_info["krw_rate"], -2))
        with curr_c1:
            st.metric(
                f"체감 환율 기준 ({currency_info['symbol']})",
                f"{currency_info['sample_amt']:,} = 약 {sample_krw:,}원",
            )
        with curr_c2:
            st.metric("☕ 스타벅스/카페 커피 1잔", currency_info["coffee"])
        with curr_c3:
            st.metric("🍽️ 로컬 식당 식사 1끼", currency_info["meal"])
        with curr_c4:
            st.metric("🚕 택시/그랩 기본요금", currency_info["taxi"])

    # 📡 다단계 RAG 파이프라인 X-Ray 시각화
    with st.expander("📡 다단계 RAG 파이프라인 X-Ray (1차 메타 검색 ➔ 2차 서브쿼리 확장 ➔ MMR 심층 재검색 ➔ 가드레일)", expanded=False):
        st.markdown(
            """
```mermaid
graph LR
    U["👤 사용자 질문 & 취향"] --> P1["🔍 1차 RAG: 메타데이터 & 초기 의미 검색"]
    P1 --> EX["🔄 토리의 2차 서브쿼리 확장<br/>(랜드마크·미식·근교·알러지 대체)"]
    EX --> P2["⚡ 2차 심층 RAG: MMR 다양성 재검색<br/>(ChromaDB wiki_docs)"]
    P2 --> LLM["🐣 파일럿 토리 언어모델<br/>(동선 설계 & 시간표 매핑)"]
    LLM --> GD["🛡️ 기밀 보호 & 할루시네이션 검증"]
    GD --> OUT["✨ 2박3일 일정표 & Leaflet 동선 지도 & PDF/HTML 가이드북"]
```
- **1차 RAG**: 메타데이터 500건 중 조건 및 기초 지리적 요약 검색
- **2차 심층 RAG**: 세부 명소, 역사, 미식, 대체 식당에 대한 서브쿼리를 자동으로 파생 생성 후 ChromaDB MMR 다양성 검색
- **할루시네이션 가드레일**: 본문 인용 근거(`[근거 N]`) 검증 및 비공개 내부 기밀 코드 자동 은닉
            """
        )

    col_chat_pane, col_plan_pane = st.columns([1.0, 1.14], gap="large")

    with col_chat_pane:
        st.markdown("#### 🐣 파일럿 토리와의 여행 라운지")
        st.caption(
            "취향을 말하거나 **'나는 생선 알러지가 있는데 생선 말고 고기 맛집으로 바꿔줘'**, **'2일차 비 올 때 실내 코스로 바꿔줘'**처럼 얘기하면 오른쪽 일정표와 동선 지도가 실시간으로 수정됩니다!"
        )

        if trip_id not in st.session_state.messages_by_trip or not st.session_state.messages_by_trip[trip_id]:
            st.session_state.messages_by_trip[trip_id] = [
                {
                    "role": "assistant",
                    "content": build_welcome_message(selected_trip, active_vibe),
                    "cited_sources": [],
                }
            ]

        current_messages = st.session_state.messages_by_trip[trip_id]

        # 빠른 대화 & 실시간 일정 조율 버튼 (알러지/식이제한 실시간 수정 버튼 포함)
        q_cols = st.columns(2)
        quick_prompt = None
        with q_cols[0]:
            if st.button("✨ 내 취향대로 2박 3일 코스 짜줘!", use_container_width=True):
                quick_prompt = f"내 취향({user_pref_summary})에 맞춰서 {dest_name} 2박 3일 여행 일정과 추천 숙소를 짜줘!"
            if st.button("🚫 생선 알러지! 고기 맛집 코스로 수정", use_container_width=True):
                quick_prompt = (
                    f"나는 생선·해산물 알러지가 있어! {dest_name} 2박 3일 일정에서 생선·해산물·초밥·수산시장 코스를 모두 빼고, "
                    f"육류(스테이크·구이·바비큐)나 알러지 걱정 없는 현지 대표 맛집·디저트 코스로 일정을 실시간 수정해줘!"
                )
        with q_cols[1]:
            if st.button("☔ 비 올 때 대비 실내 코스로 수정해줘", use_container_width=True):
                quick_prompt = f"{dest_name} 2일차 일정을 비 올 때 대비해서 실내 박물관/미술관/쇼핑·맛집 위주 코스로 바꿔줘!"
            if st.button("😴 아침 늦잠 모드(11시)로 여유롭게", use_container_width=True):
                quick_prompt = f"{dest_name} 일정을 아침 늦잠 모드(오전 11시 시작)로 여유롭게 바꾸고 야경·맛집 비중을 높여줘!"

        chat_container = st.container(height=530)
        with chat_container:
            for msg in current_messages:
                avatar_icon = "🐣" if msg["role"] == "assistant" else "🧳"
                with st.chat_message(msg["role"], avatar=avatar_icon):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant" and msg.get("cited_sources"):
                        render_cited_sources(
                            msg.get("cited_sources", []),
                            msg.get("all_contexts"),
                            msg.get("expanded_queries"),
                        )

        typed_question = st.chat_input(
            f"토리에게 '생선 알러지가 있어', '2일차 오후는 카페로 바꿔줘' 등 '{dest_name}' 일정 수정이나 질문을 말해 보세요..."
        )
        active_user_input = quick_prompt or typed_question

        if active_user_input:
            # 사용자가 채팅에서 다른 여행지(예: 도쿄 화면에서 '삿포로 알려줘')를 언급하면 자동으로 해당 여행지로 전환
            mentioned_trip = detect_mentioned_destination(active_user_input, travel_list)
            if mentioned_trip and str(mentioned_trip["id"]) != trip_id:
                selected_trip = mentioned_trip
                trip_id = str(mentioned_trip["id"])
                dest_name = mentioned_trip["name"]
                st.session_state.selected_trip_id = trip_id
                st.session_state.continent_filter = "전체 대륙"
                st.session_state.theme_filter = "전체 테마"
                if trip_id not in st.session_state.messages_by_trip or not st.session_state.messages_by_trip[trip_id]:
                    st.session_state.messages_by_trip[trip_id] = [
                        {
                            "role": "assistant",
                            "content": build_welcome_message(selected_trip, detect_destination_vibe(selected_trip)),
                            "cited_sources": [],
                        }
                    ]
                current_messages = st.session_state.messages_by_trip[trip_id]

            # 대화 중 알러지·식이제한·일정 수정 요청이 감지되면 세션 상태에 누적 저장
            detected_constraint = extract_user_constraint(active_user_input)
            if detected_constraint:
                prev_list = st.session_state.chat_constraints_by_trip.get(trip_id, [])
                if detected_constraint not in prev_list:
                    prev_list.append(detected_constraint)
                st.session_state.chat_constraints_by_trip[trip_id] = prev_list

            has_existing_plan = trip_id in st.session_state.itinerary_by_trip
            current_messages.append({"role": "user", "content": active_user_input})
            with chat_container:
                with st.chat_message("user", avatar="🧳"):
                    st.markdown(active_user_input)

                with st.chat_message("assistant", avatar="🐣"):
                    with st.status(f"🐣 파일럿 토리가 '{dest_name}' 다단계(1차·2차) RAG 검색을 수행하고 있어요...", expanded=True) as status:
                        collect_info = ensure_wiki_indexed(
                            trip_id=trip_id,
                            dest_name=dest_name,
                            question=active_user_input,
                            country=selected_trip["country"],
                            theme=selected_trip["theme"],
                            force_recollect=force_recollect,
                            chunk_size=chunk_size_val,
                            chunk_overlap=chunk_overlap_val,
                        )
                        if collect_info["cached"]:
                            st.caption(f"✓ 이미 수집된 위키 문서 {len(collect_info['selected_titles'])}건 활용")
                        else:
                            st.caption(f"✓ 위키 문서 {len(collect_info['selected_titles'])}건 수집 완료")

                        expanded_queries = []
                        if is_itinerary_or_preference_request(active_user_input, has_existing_plan=has_existing_plan):
                            st.write("🔍 1차 RAG(기본·메타 검색) ➔ 2차 심층 RAG(알러지·취향·대체 코스 MMR 재검색) 후 일정표와 동선 지도를 실시간 업데이트하고 있어요...")
                            active_constraints_now = st.session_state.chat_constraints_by_trip.get(trip_id, [])
                            merged_constraints = list(dietary_choices) + [c for c in active_constraints_now if c not in dietary_choices]
                            constraint_note = f" / 누적 필수 배려사항: {' | '.join(merged_constraints)}" if merged_constraints else ""
                            combined_pref = f"{user_pref_summary}{constraint_note} / 이번 실시간 수정·취향 요청: {active_user_input}"
                            itin_res = generate_itinerary(
                                trip_id=trip_id,
                                dest_name=dest_name,
                                country=selected_trip["country"],
                                user_preference=combined_pref,
                                current_plan=st.session_state.itinerary_by_trip.get(trip_id, {}).get("structured_plan"),
                                top_k=max(4, top_k_val),
                            )
                            st.session_state.itinerary_by_trip[trip_id] = itin_res
                            answer = itin_res.get("bot_message", itin_res["answer"])
                            cited_sources = itin_res.get("cited_sources", [])
                            all_contexts = itin_res.get("all_contexts", [])
                            expanded_queries = itin_res.get("expanded_queries", [])
                            status.update(
                                label=f"✨ '{dest_name}' 다단계 RAG 기반 맞춤 일정 & 동선 지도 실시간 업데이트 완료! (근거 {len(cited_sources)}건 인용)",
                                state="complete",
                                expanded=False,
                            )
                        else:
                            st.write("🔍 1차 RAG(메타데이터·초기 의미 검색) ➔ 2차 심층 RAG(서브쿼리 확장 MMR 재검색) ➔ 답변 생성 중...")
                            rag_result = query_trip_pilot(
                                trip_id=trip_id,
                                dest_name=dest_name,
                                question=active_user_input,
                                top_k=top_k_val,
                                search_type=search_type_label,
                            )
                            answer = rag_result["answer"]
                            cited_sources = rag_result["cited_sources"]
                            all_contexts = rag_result["all_contexts"]
                            expanded_queries = rag_result.get("expanded_queries", [])
                            status.update(
                                label=f"✓ '{dest_name}' 다단계 RAG 답변 완료! (근거 {len(cited_sources)}건 인용)",
                                state="complete",
                                expanded=False,
                            )

                    st.markdown(answer)
                    if cited_sources:
                        render_cited_sources(cited_sources, all_contexts, expanded_queries)

            current_messages.append({
                "role": "assistant",
                "content": answer,
                "cited_sources": cited_sources,
                "all_contexts": all_contexts,
                "expanded_queries": expanded_queries,
            })
            st.rerun()

    with col_plan_pane:
        render_interactive_planner_panel(
            trip_id=trip_id,
            selected_trip=selected_trip,
            chunk_size_val=chunk_size_val,
            chunk_overlap_val=chunk_overlap_val,
            top_k_val=top_k_val,
            force_recollect=force_recollect,
            user_pref_summary=user_pref_summary,
            vibe_mode=active_vibe,
            panel_key="main_right",
        )

# ── 탭 2: 조건 기반 자연어 탐색 ──
with tab_explore:
    st.subheader("🔎 토리에게 조건 말하고 딱 맞는 여행지 추천받기")
    st.caption(
        "예산, 휴양/역사/미식 테마, 계절, 대륙 등을 자유롭게 입력하시면 500곳의 글로벌·국내 여행지 중 조건에 꼭 맞는 곳만 선별해 드립니다."
    )

    cond_query = st.text_input(
        "어떤 여행지를 찾고 계신가요?",
        value="예산 100만원 이하 휴양지",
        placeholder="예: 예산 100만원 이하 휴양지 / 겨울에 오로라를 볼 수 있는 여행지 / 예술과 역사가 살아있는 유럽 도시",
    )
    if st.button("🚀 조건에 맞는 여행지 추천받기", type="primary"):
        if not cond_query.strip():
            st.warning("원하시는 여행 조건을 입력해 주세요.")
        else:
            with st.spinner("🐣 파일럿 토리가 조건에 딱 맞는 여행지를 고르고 있어요..."):
                st.session_state.condition_results = search_destinations_by_condition(cond_query.strip())

    if st.session_state.condition_results is not None:
        results = st.session_state.condition_results
        if not results:
            st.info("입력하신 조건과 일치하는 여행지를 찾지 못했습니다. 다른 조건으로 검색해 보세요.")
        else:
            st.success(f"✨ 조건에 어울리는 추천 여행지 **{len(results)}곳**을 찾았어요! 원하는 여행지를 선택하면 해당 여행지의 무드와 플래너로 즉시 전환됩니다.")
            for item in results:
                item_links = make_booking_links(item["name"], item["country"])
                item_vibe = detect_destination_vibe(item)
                vibe_tag = "🌿 네이처·휴양 무드" if item_vibe == "nature" else "⚡ 네온·시티 무드"
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(
                            f"### ✈️ [{item['country']}] {item['name']} — `{item['continent']}` · `{vibe_tag}`"
                        )
                        st.markdown(
                            f"- **테마**: `{item['theme']}` | **예산 수준**: `{item['budget_level']}` | "
                            f"**추천 시기**: `{item['best_season']}`\n"
                            f"- **토리의 추천 이유**: {item.get('match_reason', '')}"
                        )
                        st.markdown(
                            f'<a class="booking-chip" href="{item_links["google_maps"]}" target="_blank">📍 구글 지도</a>'
                            f'<a class="booking-chip" href="{item_links["agoda"]}" target="_blank">🏨 숙소 최저가</a>'
                            f'<a class="booking-chip" href="{item_links["skyscanner"]}" target="_blank">✈️ 항공권 조회</a>',
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.button(
                            "👉 이 여행지로 계획 짜기",
                            key=f"select_btn_{item['trip_id']}",
                            on_click=select_destination_callback,
                            args=(str(item["trip_id"]),),
                            use_container_width=True,
                        )

# ── 탭 3: 여행지 1:1 매치업 비교 보드 (신규 기능) ──
with tab_compare:
    st.subheader("⚖️ 여행지 1:1 매치업 비교 보드 (어디로 갈까?)")
    st.caption("고민 중인 두 여행지를 나란히 올려놓고 예산, 최적 시즌, 현지 식비 물가, 여행 테마 적합도를 실시간으로 비교해 보세요!")

    other_trips = [t for t in travel_list if str(t["id"]) != trip_id]
    other_trip_map = {str(t["id"]): t for t in other_trips}
    c_col1, c_col2 = st.columns(2)
    with c_col1:
        st.markdown(f"#### 📍 기준 여행지 A: **[{selected_trip['country']}] {dest_name}**")
        st.caption(f"테마: {selected_trip['theme']} · 예산: {selected_trip['budget_level']}")
    with c_col2:
        compare_target_id = st.selectbox(
            "📍 비교할 여행지 B 선택",
            options=list(other_trip_map.keys()),
            format_func=lambda tid: f"[{other_trip_map[tid]['country']}] {other_trip_map[tid]['name']} ({other_trip_map[tid]['theme']})",
            key="compare_target_select",
        )
        dest_b_item = other_trip_map[compare_target_id]

    cmp_data = compare_destinations(selected_trip, dest_b_item)

    cmp_c1, cmp_c2 = st.columns(2, gap="medium")
    with cmp_c1:
        with st.container(border=True):
            st.markdown(f"### 🅰️ {dest_name} ({selected_trip['country']})")
            st.markdown(f"- **대륙**: `{selected_trip['continent']}`")
            st.markdown(f"- **핵심 테마**: `{selected_trip['theme']}`")
            st.markdown(f"- **예상 경비**: `{selected_trip['budget_level']}`")
            st.markdown(f"- **추천 시기**: `{selected_trip['best_season']}`")
            st.markdown(f"- **현지 통화**: `{cmp_data['trip_a']['currency']}`")
            st.markdown(f"- **식사 1끼 물가**: `{cmp_data['trip_a']['meal_cost']}`")
            st.markdown(f"- **소개**: {selected_trip['summary']}")
            links_a = make_booking_links(dest_name, selected_trip["country"])
            st.markdown(
                f'<a class="booking-chip" href="{links_a["google_maps"]}" target="_blank">📍 구글 지도</a>'
                f'<a class="booking-chip" href="{links_a["agoda"]}" target="_blank">🏨 숙소 검색</a>',
                unsafe_allow_html=True,
            )

    with cmp_c2:
        with st.container(border=True):
            st.markdown(f"### 🅱️ {dest_b_item['name']} ({dest_b_item['country']})")
            st.markdown(f"- **대륙**: `{dest_b_item['continent']}`")
            st.markdown(f"- **핵심 테마**: `{dest_b_item['theme']}`")
            st.markdown(f"- **예상 경비**: `{dest_b_item['budget_level']}`")
            st.markdown(f"- **추천 시기**: `{dest_b_item['best_season']}`")
            st.markdown(f"- **현지 통화**: `{cmp_data['trip_b']['currency']}`")
            st.markdown(f"- **식사 1끼 물가**: `{cmp_data['trip_b']['meal_cost']}`")
            st.markdown(f"- **소개**: {dest_b_item['summary']}")
            links_b = make_booking_links(dest_b_item["name"], dest_b_item["country"])
            st.markdown(
                f'<a class="booking-chip" href="{links_b["google_maps"]}" target="_blank">📍 구글 지도</a>'
                f'<a class="booking-chip" href="{links_b["agoda"]}" target="_blank">🏨 숙소 검색</a>',
                unsafe_allow_html=True,
            )
            if st.button(f"👉 '{dest_b_item['name']}'(으)로 목적지 전환하고 계획 짜기", type="primary", use_container_width=True):
                select_destination_callback(str(dest_b_item["id"]))
                st.rerun()

    with st.container(border=True):
        st.markdown("#### 📊 핵심 항목별 1:1 맞비교")
        for cp in cmp_data["comparison_points"]:
            c1, c2, c3 = st.columns([1.2, 2.0, 2.0])
            with c1:
                st.markdown(f"**{cp['category']}**")
            with c2:
                st.markdown(f"🅰️ `{cp['a']}`")
            with c3:
                st.markdown(f"🅱️ `{cp['b']}`")

# ── 탭 4: 동행자 허브 (월별 옷차림·준비물 체크리스트 & N분의 1 정산 & PDF/캘린더 공유) ──
with tab_friends:
    st.subheader(f"👥 {dest_name} 동행자 허브 — {travel_month_num}월 옷차림·준비물 체크리스트 & N분의 1 정산 & 공유")
    
    # 🌤️ 선택한 출발 월 기반 계절 날씨 & 옷차림 가이드
    weather_info = get_monthly_packing_and_weather(dest_name, selected_trip["country"], travel_month_num)
    with st.container(border=True):
        st.markdown(f"#### 🌤️ {dest_name} {travel_month_num}월 날씨 & 옷차림 추천 가이드 (`{weather_info['season_type']}`)")
        wc1, wc2 = st.columns([1.2, 2.0])
        with wc1:
            st.markdown(f"- **기온/기후**: {weather_info['temp_desc']}")
            st.markdown(f"- **추천 시즌**: `{weather_info['season_type']}`")
        with wc2:
            st.markdown(f"👔 **토리의 추천 코디**: {weather_info['clothes_guide']}")
            if st.button(f"➕ {travel_month_num}월 맞춤 추천 준비물 체크리스트에 자동 추가하기", use_container_width=True):
                current_items = [x["item"] for x in st.session_state.packing_checklist]
                added_cnt = 0
                for ex in weather_info["checklist_extra"]:
                    if ex not in current_items:
                        st.session_state.packing_checklist.append({"item": ex, "done": False})
                        added_cnt += 1
                if added_cnt > 0:
                    st.toast(f"{travel_month_num}월 맞춤 준비물 {added_cnt}개가 추가되었습니다!", icon="🎒")
                    st.rerun()

    col_chk, col_dutch = st.columns([1.15, 1.0], gap="large")

    with col_chk:
        with st.container(border=True):
            st.markdown("#### 📋 우리들의 여행 준비물 체크리스트")
            done_cnt = sum(1 for x in st.session_state.packing_checklist if x["done"])
            total_cnt = len(st.session_state.packing_checklist)
            st.caption(f"진행률: **{done_cnt} / {total_cnt} 완료**")
            st.progress(done_cnt / max(total_cnt, 1))

            for i, chk in enumerate(st.session_state.packing_checklist):
                st.session_state.packing_checklist[i]["done"] = st.checkbox(
                    chk["item"], value=chk["done"], key=f"pack_chk_{i}"
                )

            new_item = st.text_input("추가할 준비물 입력", placeholder="예: 수중 카메라, 삼각대, 국제운전면허증")
            if st.button("➕ 준비물 추가"):
                if new_item.strip():
                    st.session_state.packing_checklist.append({"item": new_item.strip(), "done": False})
                    st.rerun()

    with col_dutch:
        with st.container(border=True):
            st.markdown("#### 💰 N분의 1 스마트 정산기 (Dutch Pay)")
            total_krw = st.number_input("총 공동 경비 / 결제 금액 (원)", min_value=0, value=600000, step=10000)
            people_cnt = st.number_input("함께한 인원 수 (명)", min_value=1, value=4, step=1)
            per_person = int(round(total_krw / max(people_cnt, 1), -2))
            st.metric("1인당 정산 금액 (100원 단위 반올림)", f"{per_person:,} 원")

        with st.container(border=True):
            st.markdown("#### 📤 여행 계획표 파일(PDF / 웹 가이드북 / 캘린더) & 카톡 요약 공유")
            itin_full = st.session_state.itinerary_by_trip.get(trip_id, {})
            itin_obj = itin_full.get("structured_plan", {})
            if itin_full:
                f_c1, f_c2, f_c3 = st.columns(3, gap="small")
                with f_c1:
                    try:
                        pdf_bytes_hub = export_itinerary_pdf_bytes(
                            selected_trip,
                            itin_obj,
                            st.session_state.get("packing_checklist", []),
                            f"1인당 정산 예정액: {per_person:,}원 ({people_cnt}명 기준)",
                        )
                        st.download_button(
                            label="📄 일정표 PDF 저장",
                            data=pdf_bytes_hub,
                            file_name=f"TripPilot_{dest_name}_2박3일_여행계획표.pdf",
                            mime="application/pdf",
                            key=f"hub_dl_pdf_{trip_id}",
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.caption(f"PDF 준비 중: {e}")
                with f_c2:
                    html_bytes_hub = export_itinerary_html_bytes(
                        selected_trip,
                        itin_obj,
                        st.session_state.get("packing_checklist", []),
                    )
                    st.download_button(
                        label="🌐 웹 가이드북 저장",
                        data=html_bytes_hub,
                        file_name=f"TripPilot_{dest_name}_인터랙티브_가이드북.html",
                        mime="text/html",
                        key=f"hub_dl_html_{trip_id}",
                        use_container_width=True,
                    )
                with f_c3:
                    try:
                        ics_bytes_hub = export_itinerary_ics_bytes(
                            selected_trip,
                            itin_obj,
                        )
                        st.download_button(
                            label="📅 폰 캘린더 등록 (.ics)",
                            data=ics_bytes_hub,
                            file_name=f"TripPilot_{dest_name}_일정.ics",
                            mime="text/calendar",
                            key=f"hub_dl_ics_{trip_id}",
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.caption(f"캘린더: {e}")
            else:
                st.caption("💡 먼저 첫 번째 탭에서 2박 3일 일정표를 생성하면 PDF, 웹 가이드북, 캘린더(.ics) 다운로드 버튼이 활성화됩니다!")

            days_summary = []
            for d in itin_obj.get("days", []):
                spots = " → ".join(s.get("place", "") for s in d.get("schedule", []))
                days_summary.append(f"• Day {d.get('day')}: {spots}")
            care_line = f"\n- 맞춤 배려/알러지 케어: {itin_obj.get('dietary_care_note')}" if itin_obj.get("dietary_care_note") else ""
            share_text = (
                f"✈️ [{selected_trip['country']} {dest_name} 2박 3일 여행 계획 공유]\n"
                f"- 추천 시기: {selected_trip['best_season']}\n"
                f"- 예상 예산: {selected_trip['budget_level']}\n"
                f"- 여행 스타일: {itin_obj.get('applied_style', user_pref_summary)}"
                f"{care_line}\n"
                + ("\n".join(days_summary) if days_summary else "• 아직 상세 일정을 생성하기 전입니다.")
                + f"\n- 1인당 정산 예정액: {per_person:,}원 ({people_cnt}명 기준)"
            )
            st.code(share_text, language="text")

# ── 탭 5: 여행지 정보 사실 확인 ──
with tab_factcheck:
    st.subheader(f"⚖️ {dest_name} 여행 정보 사실 확인")
    st.caption("알고 계신 여행 정보(건기/우기 시기, 랜드마크 역사, 지리적 특징 등)가 정확한지 백과사전 문서를 바탕으로 확인해 드립니다.")

    default_claim = (
        f"{dest_name}의 추천 여행 시기는 {selected_trip['best_season']}이며, "
        f"예산 수준은 {selected_trip['budget_level']}이다."
    )
    claim_input = st.text_input("확인하고 싶은 여행 정보를 입력하세요", value=default_claim)
    if st.button("🔍 사실 여부 확인하기", type="primary"):
        with st.status("🐣 파일럿 토리가 관련 백과사전 문서를 대조하고 있어요...", expanded=True) as s2:
            ensure_wiki_indexed(
                trip_id=trip_id,
                dest_name=dest_name,
                question=claim_input,
                country=selected_trip["country"],
                theme=selected_trip["theme"],
                force_recollect=False,
                chunk_size=chunk_size_val,
                chunk_overlap=chunk_overlap_val,
            )
            fc_res = verify_travel_claim(trip_id=trip_id, dest_name=dest_name, claim=claim_input, top_k=top_k_val)
            s2.update(label="✓ 사실 확인 완료", state="complete", expanded=False)
        st.markdown(fc_res["answer"])
        render_cited_sources(fc_res["cited_sources"], fc_res["all_contexts"])

st.divider()
st.caption(DISCLAIMER_TEXT)
