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
import time
import urllib.parse
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
from index_metadata import get_collection_count, load_and_index_metadata, METADATA_JSON_PATH
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
    clean_ai_artifacts,
)
import importlib
import nature_visuals
from background_inference import (
    submit_itinerary_task,
    submit_chat_task,
    get_active_task_for_trip,
    sync_completed_background_tasks,
    get_any_completed_tasks_for_trip,
)
try:
    importlib.reload(nature_visuals)
except Exception:
    pass
from nature_visuals import (
    get_destination_visuals,
    render_nature_hero_html,
    render_nature_gallery_html,
    render_pilot_tori_mascot_html,
    render_flying_tori_overlay_html,
    render_welcome_hero_banner_html,
    get_pilot_tori_b64,
)
from publish_mobile_itinerary import publish_itinerary_to_mobile_web

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
    """자연과 쉼이 어우러진 눈이 편안한 밝은 오트밀 & 포레스트 그린 테마로 단일 고정"""
    return "nature"


def inject_theme_css_and_background(vibe_mode: str = "nature", dest_name: str = "") -> None:
    """
    TripPilot 단일 통일 테마 — Warm Oatmeal (#FAF8F5) & Biophilic Forest Green (#064E3B)
    - 배경: 따뜻하고 눈이 편안한 밝은 오트밀/아이보리 (#FAF8F5 ~ #F5F1EB)
    - 타이포그래피 & 버튼: 딥 포레스트 그린 (#064E3B, #0F291E)과 파스텔 에메랄드 (#ECFDF5)
    - 실사 풍경 포토와 히어로 배너 내 텍스트는 100% 순백색(#FFFFFF) 고대비 보장
    """
    css_and_bg = """
    <style>
    /* ── [눈누 Y이드스트릿체 (Yidstreet / Ydestreet / Y이든스트릿) 웹폰트 CDN] ── */
    @font-face {
        font-family: 'Yidstreet';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetL.woff2') format('woff2');
        font-weight: 300;
        font-style: normal;
        font-display: swap;
    }
    @font-face {
        font-family: 'Yidstreet';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetB.woff2') format('woff2');
        font-weight: 700;
        font-style: normal;
        font-display: swap;
    }
    @font-face {
        font-family: 'Ydestreet';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetL.woff2') format('woff2');
        font-weight: 300;
        font-style: normal;
        font-display: swap;
    }
    @font-face {
        font-family: 'Ydestreet';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetB.woff2') format('woff2');
        font-weight: 700;
        font-style: normal;
        font-display: swap;
    }
    @font-face {
        font-family: 'Y이든스트릿';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetB.woff2') format('woff2');
        font-weight: 700;
        font-style: normal;
        font-display: swap;
    }
    @font-face {
        font-family: 'Y이든스트릿';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetL.woff2') format('woff2');
        font-weight: 300;
        font-style: normal;
        font-display: swap;
    }
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap');

    :root {
        color-scheme: light !important;
        --primary-color: #059669 !important;
        --background-color: #FAF8F5 !important;
        --secondary-background-color: #F3EFEA !important;
        --text-color: #0F291E !important;
    }

    html, body, [class*="css"], .stApp,
    button, input, select, textarea,
    div[data-testid*="st"], [data-baseweb],
    h1, h2, h3, h4, h5, h6, p, span, a, label {
        font-family: 'Yidstreet', 'Ydestreet', 'Y이든스트릿', 'Pretendard', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
        color: #0F291E;
        scroll-behavior: smooth !important;
    }

    /* 전체 앱 배경: 부드러운 밝은 오트밀(아이보리) 그라데이션 */
    .stApp {
        background: linear-gradient(180deg, #FAF8F5 0%, #F5F1EB 55%, #EFE9E0 100%) !important;
        color: #0F291E !important;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    .main .block-container {
        position: relative;
        z-index: 2;
        padding-top: 1.2rem !important;
        padding-bottom: 5rem !important;
        padding-left: clamp(1rem, 2.4vw, 2.6rem) !important;
        padding-right: clamp(1rem, 2.4vw, 2.6rem) !important;
        max-width: 1540px !important;
    }

    /* 물결표(~) 범위 표기 시 GFM strikethrough 오작동 방지 */
    del, s, strike {
        text-decoration: none !important;
        color: inherit !important;
        background: transparent !important;
    }

    /* 본문 텍스트: 딥 포레스트 차콜(#0F291E) 고대비 */
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
        color: #375346 !important;
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

    /* ── [히어로 배너 내부 텍스트 & [일본] 도쿄 순백색(#FFFFFF) 영구 보장] ── */
    div[data-testid="stMarkdownContainer"] .nature-hero-card,
    div[data-testid="stMarkdownContainer"] .nature-hero-card *,
    div[data-testid="stMarkdownContainer"] .nature-hero-heading,
    div[data-testid="stMarkdownContainer"] .nature-hero-heading *,
    div[data-testid="stMarkdownContainer"] .nature-hero-heading-badge,
    div[data-testid="stMarkdownContainer"] .nature-hero-heading-badge * {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* ── [상단 웰컴 히어로 배너 내부 텍스트 순백색(#FFFFFF) 영구 보장] ── */
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card *,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card h1,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card h2,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card h3,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card h4,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card p,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card span,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card div,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card b,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card strong,
    div[data-testid="stMarkdownContainer"] .welcome-heading,
    div[data-testid="stMarkdownContainer"] .welcome-subtext {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card .welcome-copilot-tag,
    div[data-testid="stMarkdownContainer"] .trippilot-welcome-card .welcome-copilot-tag * {
        color: #064E3B !important;
        -webkit-text-fill-color: #064E3B !important;
        background: #FFFFFF !important;
    }

    /* ── [메트릭 줄임표(...) 방지 & 워드랩 가독성 최적화] ── */
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] * {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: keep-all !important;
        font-size: clamp(15px, 1.25vw, 19px) !important;
        line-height: 1.35 !important;
    }
    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricLabel"] * {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: keep-all !important;
    }

    /* 입력창 및 셀렉트박스 */
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
    span[data-baseweb="tag"] {
        background: #ECFDF5 !important;
        background-color: #ECFDF5 !important;
        border: 1px solid #10B981 !important;
        color: #065F46 !important;
        border-radius: 8px !important;
    }
    span[data-baseweb="tag"] span {
        color: #065F46 !important;
        -webkit-text-fill-color: #065F46 !important;
        font-weight: 700 !important;
    }

    /* 사이드바 */
    section[data-testid="stSidebar"] {
        background: rgba(253, 252, 250, 0.96) !important;
        backdrop-filter: blur(20px) !important;
        border-right: 1px solid rgba(6, 78, 59, 0.16) !important;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] h4 {
        color: #0F291E !important;
    }

    /* 카드 및 컨테이너 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, 0.94) !important;
        backdrop-filter: blur(16px) !important;
        border: 1.2px solid rgba(6, 78, 59, 0.18) !important;
        border-radius: 20px !important;
        box-shadow: 0 8px 24px -6px rgba(15, 41, 30, 0.07) !important;
        padding: clamp(14px, 1.4vw, 20px) !important;
    }

    /* 버튼 스타일 */
    .stButton > button,
    .stDownloadButton > button {
        width: 100%;
        min-height: 42px !important;
        border-radius: 14px !important;
        font-weight: 700 !important;
        font-size: clamp(12px, 0.85vw, 14px) !important;
        line-height: 1.3 !important;
        border: 1.5px solid rgba(16, 185, 129, 0.45) !important;
        background: #FFFFFF !important;
        color: #065F46 !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:not([kind="primary"]) *,
    .stDownloadButton > button * {
        color: #065F46 !important;
        font-weight: 700 !important;
    }
    .stButton > button:not([kind="primary"]):hover,
    .stDownloadButton > button:hover {
        background: #ECFDF5 !important;
        border-color: #059669 !important;
        color: #047857 !important;
        transform: translateY(-1.5px) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        box-shadow: 0 8px 20px -4px rgba(5, 150, 105, 0.40) !important;
    }
    .stButton > button[kind="primary"] * {
        color: #FFFFFF !important;
        font-weight: 800 !important;
    }

    /* 채팅 메시지 버블 */
    div[data-testid="stChatMessage"] {
        background: rgba(255, 255, 255, 0.96) !important;
        border: 1px solid rgba(16, 185, 129, 0.22) !important;
        border-radius: 18px !important;
        padding: 12px 16px !important;
        margin-bottom: 10px !important;
        box-shadow: 0 4px 12px rgba(5, 150, 105, 0.05) !important;
    }

    
    /* 사이드바 파일럿 토리 위젯 */
    .tori-mascot-wrapper {
        display: flex;
        align-items: center;
        gap: 12px;
        background: #FFFFFF !important;
        border: 1.5px solid rgba(16, 185, 129, 0.35) !important;
        border-radius: 18px !important;
        padding: 10px 14px !important;
        margin-bottom: 14px !important;
        box-shadow: 0 4px 14px rgba(15, 41, 30, 0.05) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    }
    .tori-mascot-wrapper:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(15, 41, 30, 0.10) !important;
        border-color: #059669 !important;
    }
    .tori-mascot-avatar {
        width: 52px !important;
        height: 52px !important;
        object-fit: contain !important;
        display: block !important;
        filter: drop-shadow(0 4px 10px rgba(6, 78, 59, 0.35)) !important;
        transition: transform 0.25s ease !important;
    }
    .tori-mascot-wrapper:hover .tori-mascot-avatar {
        transform: scale(1.15) rotate(6deg) !important;
    }
    .tori-mascot-info {
        display: flex !important;
        flex-direction: column !important;
        gap: 2px !important;
        flex: 1 !important;
    }
    .tori-mascot-name {
        font-size: 13.5px !important;
        font-weight: 800 !important;
        color: #064E3B !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
    }
    .tori-live-status {
        background: #059669 !important;
        color: #FFFFFF !important;
        font-size: 9.5px !important;
        font-weight: 800 !important;
        padding: 2px 7px !important;
        border-radius: 999px !important;
        letter-spacing: 0.04em !important;
    }
    .tori-mascot-desc {
        font-size: 11px !important;
        color: #375346 !important;
        line-height: 1.35 !important;
    }

    /* ── [TripPilot 실사화 자연 디자인 시스템] ── */
    .nature-hero-card {
        position: relative;
        overflow: hidden;
        border-radius: 26px;
        margin-bottom: 20px;
        box-shadow: 0 16px 40px -10px rgba(15, 41, 30, 0.18);
        border: 1.5px solid rgba(16, 185, 129, 0.45);
        background: #143324;
        min-height: 280px;
        height: auto !important;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    .nature-hero-backdrop {
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background-size: cover;
        background-position: center 40%;
        filter: brightness(1.02) contrast(1.04);
        transition: transform 6s cubic-bezier(0.25, 1, 0.5, 1);
        z-index: 1;
    }
    .nature-hero-card:hover .nature-hero-backdrop {
        transform: scale(1.04);
    }
    .nature-hero-gradient-overlay {
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: linear-gradient(180deg, 
            rgba(15, 41, 30, 0.06) 0%, 
            rgba(15, 41, 30, 0.26) 45%, 
            rgba(6, 26, 18, 0.58) 100%
        );
        backdrop-filter: blur(0.5px);
        z-index: 2;
    }
    .nature-hero-inner {
        position: relative;
        z-index: 3;
        padding: clamp(18px, 2.2vw, 28px);
        width: 100%;
    }
    .nature-hero-meta-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        flex-wrap: wrap;
    }
    .nature-hero-highlights {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }
    .nature-hero-info-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px;
    }

    /* ── [배경 살랑살랑 나뭇잎 애니메이션] ── */
    .ambient-stage {
        position: fixed;
        top: 0; left: 0; width: 100vw; height: 100vh;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }
    .leaf-drift {
        position: absolute;
        font-size: 20px;
        opacity: 0.35;
        user-select: none;
        animation: leafFloat 18s linear infinite;
    }
    .leaf-1 { left: 8vw; top: -10px; animation-duration: 22s; animation-delay: 0s; }
    .leaf-2 { left: 34vw; top: -10px; animation-duration: 26s; animation-delay: 5s; font-size: 24px; }
    .leaf-3 { left: 68vw; top: -10px; animation-duration: 20s; animation-delay: 8s; font-size: 18px; }
    .leaf-4 { left: 88vw; top: -10px; animation-duration: 24s; animation-delay: 12s; font-size: 22px; }

    @keyframes leafFloat {
        0% { transform: translateY(-30px) rotate(0deg); opacity: 0; }
        15% { opacity: 0.45; }
        85% { opacity: 0.45; }
        100% { transform: translateY(105vh) rotate(360deg); opacity: 0; }
    }

    /* 예약 칩 링크 */
    .booking-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: #ECFDF5;
        border: 1px solid #10B981;
        color: #065F46 !important;
        font-size: 11px;
        font-weight: 700;
        padding: 3px 9px;
        border-radius: 999px;
        text-decoration: none;
        margin-right: 6px;
        margin-top: 4px;
        transition: all 0.2s ease;
    }
    .booking-chip:hover {
        background: #10B981;
        color: #FFFFFF !important;
    }
    </style>

    <div class="ambient-stage">
        <div class="leaf-drift leaf-1">🍃</div>
        <div class="leaf-drift leaf-2">🌿</div>
        <div class="leaf-drift leaf-3">🍃</div>
        <div class="leaf-drift leaf-4">🌿</div>
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


@st.cache_data
def get_cached_wiki_cache() -> dict:
    return load_wiki_cache()


@st.cache_data
def get_cached_destination_visuals(name: str, country: str, theme: str) -> dict:
    return get_destination_visuals({"name": name, "country": country, "theme": theme})


@st.cache_data
def get_cached_currency_and_cost(country: str, budget_level: str) -> dict:
    return get_currency_and_cost_info(country, budget_level)


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
        palette_list = ["#00F5D4", "#38BDF8", "#E879F9", "#F43F5E", "#A855F7", "#06B6D4", "#F59E0B"]
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
        palette_list = ["#38BDF8", "#818CF8", "#C084FC", "#0284C7", "#6366F1", "#A855F7", "#38BDF8"]
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
        palette_list = ["#D97706", "#DC2626", "#B45309", "#92400E", "#B91C1C", "#D97706", "#78350F"]
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
        palette_list = ["#10B981", "#0EA5E9", "#8B5CF6", "#F59E0B", "#EC4899", "#14B8A6", "#6366F1", "#10B981"]
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

    def get_vibe_day_color(d_i: int) -> str:
        return palette_list[(max(1, d_i) - 1) % len(palette_list)]

    seen_coords = []
    stops_data = []
    polylines_data = []

    for d_obj in days:
        d_num = int(d_obj.get("day", 1))
        if selected_day not in (0, d_num):
            continue
        color = get_vibe_day_color(d_num)
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
    if selected_day != 0:
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
            * {{ box-sizing: border-box; font-family: 'Yidstreet', 'Ydestreet', 'Pretendard', -apple-system, sans-serif !important; }}
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
                var popupHtml = '<div style="font-family:Yidstreet,Pretendard,sans-serif;min-width:185px;line-height:1.45;">' +
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


@st.fragment(run_every="1.5s")
def render_background_task_monitor(trip_id: str, dest_name: str, duration_label: str):
    """백그라운드에서 병렬 실행 중인 AI 추론을 1.5초 주기로 모니터링하고 완료 시 즉시 화면에 커밋"""
    completed_list = get_any_completed_tasks_for_trip(trip_id)
    if completed_list:
        for t in completed_list:
            if t["status"] == "completed":
                if t["task_type"] == "itinerary":
                    itin_res = t["result"]
                    st.session_state.itinerary_by_trip[trip_id] = itin_res
                    st.session_state[f"planner_day_{trip_id}"] = 1
                    if trip_id in st.session_state.messages_by_trip:
                        st.session_state.messages_by_trip[trip_id].append({
                            "role": "assistant",
                            "content": itin_res.get("bot_message", itin_res.get("answer", "")),
                            "cited_sources": itin_res.get("cited_sources", []),
                            "all_contexts": itin_res.get("all_contexts", []),
                            "expanded_queries": itin_res.get("expanded_queries", []),
                        })
                    st.toast(f"🎉 '{dest_name}' {t.get('duration_label', '')} 일정이 완성되었습니다!", icon="✨")
                elif t["task_type"] == "chat":
                    res_p = t["result"]
                    if res_p.get("is_itin_update") and res_p.get("itin_res"):
                        st.session_state.itinerary_by_trip[trip_id] = res_p["itin_res"]
                    if trip_id in st.session_state.messages_by_trip:
                        st.session_state.messages_by_trip[trip_id].append({
                            "role": "assistant",
                            "content": res_p["answer"],
                            "cited_sources": res_p.get("cited_sources", []),
                            "all_contexts": res_p.get("all_contexts", []),
                            "expanded_queries": res_p.get("expanded_queries", []),
                        })
                    st.toast("💬 토리의 맞춤 답변이 도착했습니다!", icon="🐣")
            elif t["status"] == "error":
                st.error(f"⚠️ 백그라운드 추론 중 오류: {t.get('error')}")
        st.rerun()
        return

    active_task = get_active_task_for_trip(trip_id)
    if active_task:
        elapsed = int(time.time() - active_task.get("start_time", time.time()))
        st.markdown(
            f"""
            <div style="background:#F0FDF4;border:2px solid #10B981;border-radius:14px;padding:14px 16px;margin:10px 0;box-shadow:0 4px 14px rgba(16,185,129,0.12);">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                    <span style="font-weight:800;font-size:13.5px;color:#064E3B;">
                        🐣 파일럿 토리가 백그라운드에서 병렬 추론 중... ({elapsed}초)
                    </span>
                    <span style="background:#064E3B;color:#FFFFFF;font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:999px;">
                        ⚡ 백그라운드 병렬 안전
                    </span>
                </div>
                <div style="font-size:12px;font-weight:600;color:#047857;margin-bottom:6px;">
                    {active_task.get('step', 'AI 분석 및 동선 계산 중...')}
                </div>
                <div style="font-size:11px;color:#065F46;opacity:0.85;line-height:1.45;">
                    🛡️ <b>자유롭게 화면을 둘러보세요!</b> 다른 탭을 클릭하거나 설정을 변경하셔도 추론이 <b>중단 없이 100% 안전하게 완주</b>됩니다.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(active_task.get("progress", 0.3))


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
    target_days: int = 3,
    duration_label: str = "2박 3일",
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

    active_bg_task = get_active_task_for_trip(trip_id)
    btn_disabled = (active_bg_task is not None)
    btn_label = f"⏳ '{dest_name}' {duration_label} 백그라운드 추론 중..." if btn_disabled else f"✨ 내 취향 반영 '{dest_name}' {duration_label} 일정표 & 동선 지도 생성"

    if st.button(
        btn_label,
        key=f"gen_itin_btn_{panel_key}",
        type="primary",
        use_container_width=True,
        disabled=btn_disabled,
    ):
        submit_itinerary_task(
            trip_id=trip_id,
            dest_name=dest_name,
            country=country,
            theme=selected_trip.get("theme", ""),
            user_pref_summary=user_pref_summary,
            current_plan=st.session_state.itinerary_by_trip.get(trip_id, {}).get("structured_plan"),
            top_k_val=top_k_val,
            chunk_size_val=chunk_size_val,
            chunk_overlap_val=chunk_overlap_val,
            force_recollect=force_recollect,
            target_days=target_days,
            duration_label=duration_label,
        )
        st.toast(f"🚀 파일럿 토리가 '{dest_name}' {duration_label} 일정 설계를 백그라운드에서 시작했습니다!", icon="🐣")
        st.rerun()

    # 백그라운드 추론 상태 실시간 모니터링 (다른 탭으로 이동하거나 클릭해도 중단되지 않음)
    render_background_task_monitor(trip_id, dest_name, duration_label)

    if trip_id not in st.session_state.itinerary_by_trip:
        if active_bg_task:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div style="text-align:center;padding:32px 16px;">
                        <div style="font-size:40px;margin-bottom:8px;">🐣✈️</div>
                        <h4 style="margin:6px 0 6px 0;font-weight:800;color:#064E3B;">'{dest_name}' {duration_label} 일정을 열심히 설계하고 있어요!</h4>
                        <p style="font-size:13px;color:#047857;line-height:1.6;margin:0;">
                            백그라운드에서 위키백과를 분석하고 최적 동선을 계산 중입니다.<br/>
                            다른 탭이나 관광 정보를 둘러보셔도 안전하게 완료됩니다.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            return

        with st.container(border=True):
            empty_icon = "🌿🌊" if vibe_mode == "nature" else "⚡🌃"
            st.markdown(
                f"""
                <div style="text-align:center;padding:36px 16px;">
                    <div style="font-size:44px;margin-bottom:8px;">🐣 {empty_icon}</div>
                    <h4 style="margin:6px 0 6px 0;font-weight:800;">나만의 {dest_name} 여행 코스를 그려볼까요?</h4>
                    <p style="font-size:13px;opacity:0.8;line-height:1.6;margin:0;">
                        왼쪽에서 <b>파일럿 토리 🐣</b>에게 취향을 말해주거나,<br/>
                        위의 <b>'일정표 & 동선 지도 생성'</b> 버튼을 눌러보세요!
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    itin_data = st.session_state.itinerary_by_trip[trip_id]
    structured_plan = itin_data.get("structured_plan", {})
    days_list = structured_plan.get("days", [])

    # 실시간 반영된 알러지·식이제한·맞춤 수정 배너 표시 (인공지능 어투 [근거 N] 및 ** 표시 완전 정제)
    dietary_note = clean_ai_artifacts(str(structured_plan.get("dietary_care_note") or "").strip())
    active_chat_constraints = [
        clean_ai_artifacts(c)
        for c in st.session_state.get("chat_constraints_by_trip", {}).get(trip_id, [])
    ]
    if dietary_note or active_chat_constraints:
        care_bg = "#ECFDF5" if vibe_mode == "nature" else "rgba(0, 245, 212, 0.14)"
        care_border = "#10B981" if vibe_mode == "nature" else "#00F5D4"
        care_text_col = "#065F46" if vibe_mode == "nature" else "#00F5D4"
        notes_joined = dietary_note if dietary_note else " · ".join(active_chat_constraints)
        notes_joined = clean_ai_artifacts(notes_joined)
        st.markdown(
            f"""
            <div style="background:{care_bg};border:1.5px solid {care_border};border-radius:14px;padding:10px 14px;margin-bottom:12px;">
                <div style="font-size:12.5px;font-weight:800;color:{care_text_col};">
                    🛡️ 실시간 맞춤 케어 & 대화 수정 반영 완료
                </div>
                <div style="font-size:12px;margin-top:3px;opacity:0.92;line-height:1.55;">
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
                    file_name=f"TripPilot_{dest_name}_{duration_label}_여행계획표.pdf",
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

        with st.expander("📱 스마트폰 카메라 스캔용 모바일 일정표 QR 코드", expanded=False):
            mobile_web_url = publish_itinerary_to_mobile_web(
                trip_id=trip_id,
                dest_name=dest_name,
                country=country,
                structured_plan=structured_plan,
            )
            target_url = mobile_web_url or f"https://www.google.com/maps/search/{urllib.parse.quote(dest_name + ' 여행')}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={urllib.parse.quote(target_url)}&color=064E3B&bgcolor=FAF8F5"
            q1, q2 = st.columns([1, 2.4], gap="medium")
            with q1:
                st.image(qr_url, caption="스마트폰 기본 카메라로 스캔", width=150)
            with q2:
                st.markdown(f"#### 📲 [{country}] {dest_name} 모바일 여행 일정표")
                st.markdown(
                    f"스마트폰 기본 카메라로 비추면 **2박 3일 맞춤 여행 계획표 웹페이지**가 즉시 열립니다!<br/>"
                    f"- **포함 내용**: 일차별 세부 시간표, 추천 맛집·명소, 알러지 케어, 토리의 여행 꿀팁<br/>"
                    f'<div style="margin-top: 10px; margin-bottom: 8px;">'
                    f'<a class="booking-chip" href="{target_url}" target="_blank" style="font-size: 13px; padding: 6px 14px; background: #064E3B; color: #FFFFFF !important; border: none; font-weight: 700;">🌐 모바일 여행 계획표 바로 열기</a>'
                    f'</div>'
                    f'<span style="font-size: 11px; color: #059669; word-break: break-all;">🔗 바로가기 링크: <a href="{target_url}" target="_blank" style="color: #059669;">{target_url}</a></span>',
                    unsafe_allow_html=True,
                )

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
            f'<div class="metric-pill"><div class="metric-label">여행 일정</div>'
            f'<div class="metric-val">{duration_label}</div></div>',
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

    # ── 반응형 일차 전환 바 (1일부터 최대 30일 한달살기까지 유연 지원) ──
    num_days = len(days_list) or target_days
    cur_day = st.session_state.get(day_state_key, 1)

    def _get_day_label(d_n: int) -> str:
        if d_n == 0:
            return "🌐 전체 일정 종합 보기"
        elif d_n == 999:
            return "💰 예산 배분 & 추천 숙소"
        elif 1 <= d_n <= len(days_list):
            tt = days_list[d_n - 1].get("theme_title", "")
            return f"📅 Day {d_n} : {tt}" if tt else f"📅 Day {d_n} 동선 & 타임라인"
        else:
            return f"📅 Day {d_n}"

    if num_days <= 5:
        tab_cols = st.columns([1.05] + [0.95] * num_days + [1.15], gap="small")
        with tab_cols[0]:
            if st.button("🌐 전체", key=f"day0_{panel_key}", type="primary" if cur_day == 0 else "secondary", use_container_width=True):
                st.session_state[day_state_key] = 0
                st.rerun()
        for d_idx in range(1, num_days + 1):
            with tab_cols[d_idx]:
                if st.button(f"Day {d_idx}", key=f"day{d_idx}_{panel_key}", type="primary" if cur_day == d_idx else "secondary", use_container_width=True):
                    st.session_state[day_state_key] = d_idx
                    st.rerun()
        with tab_cols[-1]:
            if st.button("💰 예산·숙소", key=f"day_bud_{panel_key}", type="primary" if cur_day == 999 else "secondary", use_container_width=True):
                st.session_state[day_state_key] = 999
                st.rerun()

    arrow_cols = st.columns([1.1, 2.5, 1.1], gap="small")
    with arrow_cols[0]:
        if st.button("◀ 이전 일차", key=f"prev_day_{panel_key}", use_container_width=True):
            if cur_day == 0:
                st.session_state[day_state_key] = 999
            elif cur_day == 1:
                st.session_state[day_state_key] = 0
            elif cur_day == 999:
                st.session_state[day_state_key] = num_days
            else:
                st.session_state[day_state_key] = cur_day - 1
            st.rerun()

    with arrow_cols[1]:
        if num_days > 5:
            day_opts = [0] + list(range(1, num_days + 1)) + [999]
            s_idx = day_opts.index(cur_day) if cur_day in day_opts else 1
            ch_day = st.selectbox(
                "일차 선택",
                options=day_opts,
                index=s_idx,
                format_func=_get_day_label,
                key=f"box_sel_day_{panel_key}",
                label_visibility="collapsed",
            )
            if ch_day != cur_day:
                st.session_state[day_state_key] = ch_day
                st.rerun()
        else:
            st.markdown(
                f'<div style="text-align:center;padding-top:8px;font-size:12.5px;font-weight:800;opacity:0.88;">'
                f'{_get_day_label(cur_day)}</div>',
                unsafe_allow_html=True,
            )

    with arrow_cols[2]:
        if st.button("다음 일차 ▶", key=f"next_day_{panel_key}", use_container_width=True):
            if cur_day == 999:
                st.session_state[day_state_key] = 0
            elif cur_day == num_days:
                st.session_state[day_state_key] = 999
            elif cur_day == 0:
                st.session_state[day_state_key] = 1
            else:
                st.session_state[day_state_key] = cur_day + 1
            st.rerun()

    active_day = st.session_state[day_state_key]

    # 1) 테마 연동 인터랙티브 동선 지도 렌더링 (선택 일차만 표시하여 동선 뭉침 방지!)
    if days_list and (active_day == 0 or 1 <= active_day <= num_days):
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
    elif 1 <= active_day <= num_days:
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
    else:
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
    with st.spinner("🚀 초기 실행 감지: 여행지 메타데이터 100선 벡터 색인을 자동으로 구축하고 있습니다..."):
        try:
            load_and_index_metadata(METADATA_JSON_PATH)
            meta_count = get_collection_count(META_COLLECTION)
            st.success("✅ 메타데이터 벡터 색인 자동 구축 완료!")
        except Exception as e:
            st.warning(f"메타데이터 색인 안내: {e}")

# 3. 세션 상태 초기화
if "messages_by_trip" not in st.session_state:
    st.session_state.messages_by_trip = {}
if "selected_trip_id" not in st.session_state:
    st.session_state.selected_trip_id = str(travel_list[0]["id"])
if "condition_results" not in st.session_state:
    st.session_state.condition_results = None
if "itinerary_by_trip" not in st.session_state:
    st.session_state.itinerary_by_trip = {}

# 🎬 기본 완성형 추천 일정 & 토리 대화 자동 프리로드 (초기 사용자 경험 및 완성도 극대화)
if "1" not in st.session_state.itinerary_by_trip:
    try:
        import json as _demo_json
        import os as _demo_os
        if _demo_os.path.exists("data/demo_itinerary_tokyo.json"):
            with open("data/demo_itinerary_tokyo.json", "r", encoding="utf-8") as _df:
                _demo_data = _demo_json.load(_df)
                st.session_state.itinerary_by_trip["1"] = _demo_data
                st.session_state.itinerary_by_trip["0"] = _demo_data
            _demo_msgs = [
                {
                    "role": "user",
                    "content": "도쿄 2박 3일 코스로 짜줘! 감성 카페 위주로 부탁하고 생선 알러지가 있어서 해산물은 빼줘.",
                },
                {
                    "role": "assistant",
                    "content": "안녕하세요! 🐣 AI 여행 코파일럿 토리예요. 친구들과 함께하는 도쿄 2박 3일 감성 카페 & 여유로운 힐링 일정을 맞춤 설계했습니다. 생선 알러지를 고려하여 해산물 코스는 완전히 배제하고, 아사쿠사 말차 카페, 오모테산도 가든 테라스, 와규 로컬 맛집 위주로 알차게 구성했어요! 우측 일정표와 1일차 동선 지도를 확인해 보세요. 🌿",
                },
            ]
            st.session_state.messages_by_trip["1"] = _demo_msgs
            st.session_state.messages_by_trip["0"] = _demo_msgs
            st.session_state.chat_constraints_by_trip["1"] = ["생선 및 해산물 알러지 케어 코스 반영"]
            st.session_state.chat_constraints_by_trip["0"] = ["생선 및 해산물 알러지 케어 코스 반영"]
    except Exception:
        pass
if "chat_constraints_by_trip" not in st.session_state:
    st.session_state.chat_constraints_by_trip = {}
if "vibe_override" not in st.session_state:
    st.session_state.vibe_override = "auto"
if "packing_checklist" not in st.session_state:
    st.session_state.packing_checklist = [
        {"item": "여권 및 항공권 e-티켓 (유효기간 6개월 이상 확인)", "done": True},
        {"item": "해외 결제 카드 (트래블로그/트래블월렛) & 현지 비상 현금", "done": True},
        {"item": "로밍 / 유심(USIM) / eSIM 사전 개통", "done": False},
        {"item": "멀티 어댑터 & 대용량 보조배터리", "done": False},
        {"item": "상비약 (소화제, 진통제, 밴드, 멀미약)", "done": False},
        {"item": "우산 / 우비 및 일교차 대비 가벼운 겉옷", "done": False},
    ]

# ── [단계별 대화형 플래너 위자드 세션 상태] ──
if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = 1  # 1: 어디로, 2: 언제/얼마나, 3: 누구와/취향, 'completed': 완료 요약
if "travel_month_num" not in st.session_state:
    st.session_state.travel_month_num = 11
if "duration_preset" not in st.session_state:
    st.session_state.duration_preset = "2박 3일 (인기 추천)"
if "target_days" not in st.session_state:
    st.session_state.target_days = 3
if "companion_choice" not in st.session_state:
    st.session_state.companion_choice = "👫 친구들과 우정 여행"
if "style_choices" not in st.session_state:
    st.session_state.style_choices = ["☕ 감성 카페 & 힐링", "🍣 현지 미식 & 로컬 맛집"]
if "pace_choice" not in st.session_state:
    st.session_state.pace_choice = "😌 여유롭게 (힐링)"
if "dietary_choices" not in st.session_state:
    st.session_state.dietary_choices = ["✅ 해당 없음 (알러지 없음)"]

# 0. 백그라운드 병렬 추론 완료 태스크 자동 감지 및 세션 동기화
sync_completed_background_tasks(st.session_state)


def select_destination_callback(target_trip_id: str):
    """조건 탐색 카드에서 여행지 선택 시 사이드바 필터와 선택 상태를 즉시 동기화하고 2단계(언제)로 안내"""
    st.session_state.selected_trip_id = str(target_trip_id)
    st.session_state.continent_filter = "전체 대륙"
    st.session_state.wizard_step = 2


# 4. 사이드바 구성 (단계별 대화형 플래너 위자드)
with st.sidebar:
    st.markdown("## 🐣 TripPilot")
    st.caption("AI 여행 코파일럿 토리와 함께하는 감성 여행")
    st.markdown(render_pilot_tori_mascot_html(), unsafe_allow_html=True)

    wizard_step = st.session_state.get("wizard_step", 1)

    # 상단 3-Step 탭 네비게이터 (언제든 클릭하여 단계 전환 가능)
    st.markdown(
        """<div style="font-size:11px; font-weight:800; color:#059669; margin-bottom:4px; letter-spacing:0.04em;">🧭 단계별 맞춤 여행 플래너</div>""",
        unsafe_allow_html=True,
    )
    w_nav1, w_nav2, w_nav3 = st.columns(3)
    with w_nav1:
        s1_type = "primary" if wizard_step == 1 else "secondary"
        if st.button("📍 1.어디로", key="w_nav_1", use_container_width=True, type=s1_type):
            st.session_state.wizard_step = 1
            st.rerun()
    with w_nav2:
        s2_type = "primary" if wizard_step == 2 else "secondary"
        if st.button("🗓️ 2.언제", key="w_nav_2", use_container_width=True, type=s2_type):
            st.session_state.wizard_step = 2
            st.rerun()
    with w_nav3:
        s3_type = "primary" if wizard_step in (3, "completed") else "secondary"
        if st.button("✨ 3.취향", key="w_nav_3", use_container_width=True, type=s3_type):
            st.session_state.wizard_step = 3
            st.rerun()

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    continents = ["전체 대륙"] + sorted(list({item["continent"] for item in travel_list}))
    filtered_trips = travel_list
    sel_cont = st.session_state.get("continent_filter", "전체 대륙")
    if sel_cont != "전체 대륙":
        filtered_trips = [item for item in filtered_trips if item["continent"] == sel_cont]
    if not filtered_trips:
        filtered_trips = travel_list
    trip_id_to_item = {str(item["id"]): item for item in filtered_trips}

    if st.session_state.selected_trip_id not in trip_id_to_item:
        st.session_state.selected_trip_id = str(filtered_trips[0]["id"])

    # ── [STEP 1: 어디로 떠나실 건가요?] ──
    if wizard_step == 1:
        st.markdown("""
<div style="background:#F0FDF4; border:1.5px solid #10B981; border-radius:14px; padding:10px 13px; margin-bottom:12px;">
    <div style="font-size:10.5px; font-weight:800; color:#059669;">STEP 1 / 3</div>
    <div style="font-size:14px; font-weight:800; color:#064E3B; margin-bottom:3px;">📍 어디로 떠나고 싶으신가요?</div>
    <div style="font-size:11.5px; color:#047857; line-height:1.45;">원하시는 대륙과 도시를 고르면 실시간 위키 정보와 자연 뷰파인더가 준비됩니다.</div>
</div>
""", unsafe_allow_html=True)

        selected_continent = st.selectbox("🌍 대륙 선택", continents, key="continent_filter")

        id_options = list(trip_id_to_item.keys())
        current_idx = id_options.index(st.session_state.selected_trip_id) if st.session_state.selected_trip_id in id_options else 0

        chosen_id = st.selectbox(
            "📍 여행할 도시 · 랜드마크",
            options=id_options,
            index=current_idx,
            format_func=lambda tid: f"[{trip_id_to_item[tid]['country']}] {trip_id_to_item[tid]['name']} ({trip_id_to_item[tid]['theme']})",
            key="sb_city_select",
        )
        st.session_state.selected_trip_id = chosen_id
        selected_trip = trip_id_to_item[chosen_id]

        selected_visuals = get_cached_destination_visuals(
            selected_trip["name"], selected_trip["country"], selected_trip.get("theme", "")
        )
        with st.container(border=True):
            preview_rendered = """
<div style="border-radius:10px; overflow:hidden; margin-bottom:8px; position:relative;">
    <img src="{thumb_url}" style="width:100%; height:95px; object-fit:cover; display:block;" />
    <span style="position:absolute; bottom:5px; right:6px; background:rgba(6,78,59,0.92); color:#fff; font-size:10px; font-weight:700; padding:2px 7px; border-radius:999px;">🌿 자연 {nature_score}%</span>
</div>
<div style="font-size:13.5px; font-weight:800; color:#064E3B; margin-bottom:2px;">[{country}] {dest_name}</div>
<div style="font-size:11.5px; color:#375346; line-height:1.5;">
    • <b>테마</b>: {theme}<br/>
    • <b>추천 시기</b>: {best_season}<br/>
    • <b>예상 예산</b>: {budget_level}
</div>
""".format(
                thumb_url=selected_visuals['thumb_url'],
                nature_score=selected_visuals['nature_score'],
                country=selected_trip['country'],
                dest_name=selected_trip['name'],
                theme=selected_trip['theme'],
                best_season=selected_trip['best_season'],
                budget_level=selected_trip['budget_level']
            )
            st.markdown(preview_rendered, unsafe_allow_html=True)

        if st.button("다음: 언제 떠나시나요? ➔", type="primary", use_container_width=True, key="w1_btn_next"):
            st.session_state.wizard_step = 2
            st.rerun()

    # ── [STEP 2: 언제, 얼마 동안 머무르실 예정인가요?] ──
    elif wizard_step == 2:
        trip_id = st.session_state.selected_trip_id
        selected_trip = next((t for t in travel_list if str(t["id"]) == trip_id), travel_list[0])

        st.markdown("""
<div style="background:#F0FDF4; border:1.5px solid #10B981; border-radius:14px; padding:10px 13px; margin-bottom:12px;">
    <div style="font-size:10.5px; font-weight:800; color:#059669;">STEP 2 / 3</div>
    <div style="font-size:14px; font-weight:800; color:#064E3B; margin-bottom:3px;">🗓️ 언제, 얼마 동안 머무르실 예정인가요?</div>
    <div style="font-size:11.5px; color:#047857; line-height:1.45;">선택하신 여행지의 최적 날씨와 일정 길이를 고려합니다.</div>
</div>
""", unsafe_allow_html=True)
        st.info(f"💡 **{selected_trip['name']}** 추천 여행 시기: **{selected_trip['best_season']}**")

        travel_month_num = st.selectbox(
            "📅 출발 예정 월",
            options=list(range(1, 13)),
            index=st.session_state.get("travel_month_num", 11) - 1,
            format_func=lambda m: f"{m}월",
            key="w2_month_select",
        )
        st.session_state.travel_month_num = travel_month_num

        dur_presets = [
            "2박 3일 (인기 추천)",
            "당일치기 (1일)",
            "1박 2일",
            "3박 4일",
            "4박 5일",
            "5박 6일",
            "6박 7일 (1주일)",
            "9박 10일 (열흘 코스)",
            "13박 14일 (2주 살기)",
            "20박 21일 (3주 살기)",
            "29박 30일 (한달살기)",
            "⚙️ 일수 직접 입력 (1~30일)",
        ]
        cur_preset = st.session_state.get("duration_preset", "2박 3일 (인기 추천)")
        p_idx = dur_presets.index(cur_preset) if cur_preset in dur_presets else 0

        duration_preset = st.selectbox("⏱️ 여행 기간 선택 (최대 30일)", dur_presets, index=p_idx, key="w2_dur_select")
        st.session_state.duration_preset = duration_preset

        if duration_preset == "⚙️ 일수 직접 입력 (1~30일)":
            target_days = st.slider("여행 일수 선택 (최대 30일)", min_value=1, max_value=30, value=st.session_state.get("target_days", 3), format="%d일", key="w2_dur_slider")
            st.session_state.target_days = target_days
        else:
            dur_preset_map = {
                "당일치기 (1일)": 1,
                "1박 2일": 2,
                "2박 3일 (인기 추천)": 3,
                "3박 4일": 4,
                "4박 5일": 5,
                "5박 6일": 6,
                "6박 7일 (1주일)": 7,
                "9박 10일 (열흘 코스)": 10,
                "13박 14일 (2주 살기)": 14,
                "20박 21일 (3주 살기)": 21,
                "29박 30일 (한달살기)": 30,
            }
            target_days = dur_preset_map.get(duration_preset, 3)
            st.session_state.target_days = target_days

        w2_col1, w2_col2 = st.columns(2)
        with w2_col1:
            if st.button("◀ 이전: 여행지", use_container_width=True, key="w2_btn_back"):
                st.session_state.wizard_step = 1
                st.rerun()
        with w2_col2:
            if st.button("다음: 취향 선택 ➔", type="primary", use_container_width=True, key="w2_btn_fwd"):
                st.session_state.wizard_step = 3
                st.rerun()

    # ── [STEP 3: 누구와 어떤 스타일로 떠나시나요?] ──
    elif wizard_step == 3:
        trip_id = st.session_state.selected_trip_id
        selected_trip = next((t for t in travel_list if str(t["id"]) == trip_id), travel_list[0])

        st.markdown("""
<div style="background:#F0FDF4; border:1.5px solid #10B981; border-radius:14px; padding:10px 13px; margin-bottom:12px;">
    <div style="font-size:10.5px; font-weight:800; color:#059669;">STEP 3 / 3</div>
    <div style="font-size:14px; font-weight:800; color:#064E3B; margin-bottom:3px;">✨ 누구와 어떤 스타일로 떠나시나요?</div>
    <div style="font-size:11.5px; color:#047857; line-height:1.45;">동행자와 여행 취향, 알러지 케어를 반영해 최적의 동선과 맛집을 조율합니다.</div>
</div>
""", unsafe_allow_html=True)

        comp_options = ["👫 친구들과 우정 여행", "💑 연인과 로맨틱 여행", "👨‍👩‍👧 가족/부모님과 편한 여행", "🎒 혼자 떠나는 자유 여행"]
        cur_comp = st.session_state.get("companion_choice", comp_options[0])
        c_idx = comp_options.index(cur_comp) if cur_comp in comp_options else 0
        companion_choice = st.selectbox("👥 누구와 함께 가나요?", comp_options, index=c_idx, key="w3_comp_select")
        st.session_state.companion_choice = companion_choice

        style_options = [
            "☕ 감성 카페 & 힐링",
            "🍣 현지 미식 & 로컬 맛집",
            "🏛️ 문화 예술 & 역사 유적",
            "📸 인생샷 포토존",
            "🌿 자연 & 산책 힐링",
            "🛍️ 쇼핑 & 소품샵",
            "🌃 야경 & 루프탑",
            "🎢 액티비티 & 체험",
        ]
        cur_styles = st.session_state.get("style_choices", ["☕ 감성 카페 & 힐링", "🍣 현지 미식 & 로컬 맛집"])
        style_choices = st.multiselect("✨ 선호하는 여행 취향", style_options, default=cur_styles, key="w3_style_select")
        st.session_state.style_choices = style_choices

        pace_options = ["😌 여유롭게 (힐링)", "👟 알차게 (핵심 정복)", "😴 늦잠 모드 (11시)"]
        cur_pace = st.session_state.get("pace_choice", pace_options[0])
        pace_idx = pace_options.index(cur_pace) if cur_pace in pace_options else 0
        pace_choice = st.selectbox("⏰ 일정 템포", pace_options, index=pace_idx, key="w3_pace_select")
        st.session_state.pace_choice = pace_choice

        dietary_options = [
            "✅ 해당 없음 (알러지 없음)",
            "🚫 생선·해산물 알러지 (육류 대체)",
            "🚫 갑각류(새우·게) 알러지",
            "🥜 견과류·땅콩 알러지",
            "🥗 비건·채식 위주 식단",
            "🥩 돼지고기 제외 (할랄)",
            "♿ 계단 최소화·택시 이동",
        ]
        cur_diet = st.session_state.get("dietary_choices", ["✅ 해당 없음 (알러지 없음)"])
        dietary_choices = st.multiselect("🛡️ 알러지·식이제한 케어", dietary_options, default=cur_diet, key="w3_diet_select")
        st.session_state.dietary_choices = dietary_choices

        w3_col1, w3_col2 = st.columns(2)
        with w3_col1:
            if st.button("◀ 이전: 일정", use_container_width=True, key="w3_btn_back"):
                st.session_state.wizard_step = 2
                st.rerun()
        with w3_col2:
            if st.button("🎉 설정 완료 & 일정 보기", type="primary", use_container_width=True, key="w3_btn_done"):
                st.session_state.wizard_step = "completed"
                st.rerun()

    # ── [설정 완료 모드: 나만의 여정 브리프 요약 카드] ──
    else:
        trip_id = st.session_state.selected_trip_id
        selected_trip = next((t for t in travel_list if str(t["id"]) == trip_id), travel_list[0])
        travel_month_num = st.session_state.get("travel_month_num", 11)
        target_days = st.session_state.get("target_days", 3)
        duration_label = "2박 3일" if target_days == 3 else ("당일치기" if target_days == 1 else f"{target_days-1}박 {target_days}일")
        companion_choice = st.session_state.get("companion_choice", "친구들과 우정 여행")
        style_choices = st.session_state.get("style_choices", ["감성 카페", "현지 미식"])
        pace_choice = st.session_state.get("pace_choice", "여유롭게")
        dietary_choices = st.session_state.get("dietary_choices", ["해당 없음"])

        summary_rendered = """
<div style="background:#FAF8F5; border:1.5px solid #10B981; border-radius:16px; padding:13px 14px; margin-bottom:12px; box-shadow:0 4px 14px rgba(6,78,59,0.06);">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
        <span style="font-size:11px; font-weight:800; color:#059669;">✨ 나만의 맞춤 여정 브리프</span>
        <span style="background:#ECFDF5; border:1px solid #A7F3D0; color:#065F46; font-size:10px; font-weight:700; padding:2px 7px; border-radius:999px;">설정 완료</span>
    </div>
    <div style="font-size:15px; font-weight:800; color:#064E3B; margin-bottom:5px;">
        [{country}] {dest_name}
    </div>
    <div style="font-size:11.8px; color:#375346; line-height:1.55;">
        • <b>일정</b>: {month}월 출발 · {dur_label}<br/>
        • <b>동행</b>: {comp_txt}<br/>
        • <b>취향</b>: {style_txt}<br/>
        • <b>템포/식이</b>: {pace_txt} · {diet_txt}
    </div>
</div>
""".format(
            country=selected_trip['country'],
            dest_name=selected_trip['name'],
            month=travel_month_num,
            dur_label=duration_label,
            comp_txt=companion_choice.split()[1] if len(companion_choice.split())>1 else companion_choice,
            style_txt=', '.join(style_choices[:2]),
            pace_txt=pace_choice.split()[0],
            diet_txt=dietary_choices[0].split()[0]
        )
        st.markdown(summary_rendered, unsafe_allow_html=True)

        sc_col1, sc_col2 = st.columns(2)
        with sc_col1:
            if st.button("✏️ 조건 수정", use_container_width=True, key="sb_btn_edit"):
                st.session_state.wizard_step = 1
                st.rerun()
        with sc_col2:
            if st.button("🔄 다른 여행지", use_container_width=True, key="sb_btn_change"):
                st.session_state.wizard_step = 1
                st.rerun()

    # 사이드바 하단 공통 예약 칩 및 보조 도구
    trip_id = str(st.session_state.selected_trip_id)
    selected_trip = next((t for t in travel_list if str(t["id"]) == trip_id), travel_list[0])
    dest_name = selected_trip["name"]
    sidebar_links = make_booking_links(dest_name, selected_trip["country"])
    st.markdown(
        f'<div style="margin-top:10px; margin-bottom:8px;">'
        f'<a class="booking-chip" href="{sidebar_links["google_maps"]}" target="_blank">📍 구글 지도</a>'
        f'<a class="booking-chip" href="{sidebar_links["agoda"]}" target="_blank">🏨 숙소 검색</a>'
        f'<a class="booking-chip" href="{sidebar_links["skyscanner"]}" target="_blank">✈️ 항공권</a>'
        f'</div>',
        unsafe_allow_html=True,
    )

    wiki_cache = get_cached_wiki_cache()
    trip_cached_info = wiki_cache.get(trip_id, {})
    cached_titles = trip_cached_info.get("titles", [])

    st.caption(
        f"여행지 메타데이터 색인: {meta_count}건 | "
        f"수집된 위키 문서: {len(cached_titles)}건 (전체 {wiki_count}청크)"
    )

    with st.expander("⚙️ 검색 및 문서 분할 설정", expanded=False):
        search_type_label = st.radio(
            "문서 검색 방식",
            options=["similarity", "mmr"],
            format_func=lambda x: "유사도 중심 검색 (Similarity)" if x == "similarity" else "다양성 고려 검색 (MMR)",
            index=0,
            key="cfg_search_type",
        )
        top_k_val = st.slider("참조 문서 검색 수 (Top-k)", min_value=1, max_value=8, value=WIKI_TOP_K, key="cfg_top_k")
        chunk_size_val = st.select_slider("문서 청크 크기", options=[500, 800, 1000, 1500], value=CHUNK_SIZE, key="cfg_chunk_size")
        chunk_overlap_val = st.select_slider("청크 중복 길이", options=[50, 100, 200, 300], value=CHUNK_OVERLAP, key="cfg_chunk_overlap")
        force_recollect = st.checkbox("위키백과 문서 새로 수집하기", value=False, key="cfg_recollect")

    if st.button("🗑️ 현재 여행지 대화 초기화", use_container_width=True, key="btn_reset_chat"):
        st.session_state.messages_by_trip[trip_id] = [
            {"role": "assistant", "content": build_welcome_message(selected_trip, "nature"), "cited_sources": []}
        ]
        st.rerun()

    st.divider()
    st.warning(DISCLAIMER_TEXT)
    st.caption("문서 출처: 한국어 위키백과 (CC BY-SA 4.0)")

# ── [전역 활성 여정 파라미터 도출] ──
active_vibe = "nature"
target_days = st.session_state.get("target_days", 3)
travel_month_num = st.session_state.get("travel_month_num", 11)
companion_choice = st.session_state.get("companion_choice", "👫 친구들과 우정 여행")
style_choices = st.session_state.get("style_choices", ["☕ 감성 카페 & 힐링", "🍣 현지 미식 & 로컬 맛집"])
pace_choice = st.session_state.get("pace_choice", "😌 여유롭게 (힐링)")
dietary_choices = st.session_state.get("dietary_choices", ["✅ 해당 없음 (알러지 없음)"])

if target_days == 1:
    duration_label = "당일치기"
elif target_days == 30:
    duration_label = "29박 30일 (한달살기)"
elif target_days == 7:
    duration_label = "6박 7일 (1주일)"
elif target_days == 14:
    duration_label = "13박 14일 (2주 살기)"
elif target_days == 21:
    duration_label = "20박 21일 (3주 살기)"
else:
    duration_label = f"{target_days-1}박 {target_days}일"

chat_constraints_list = st.session_state.chat_constraints_by_trip.get(trip_id, [])
active_dietary = [c for c in dietary_choices if "해당 없음" not in c and "알러지 없음" not in c]
all_constraints = list(active_dietary) + [c for c in chat_constraints_list if c not in active_dietary and "해당 없음" not in c and "알러지 없음" not in c]
constraint_str = f", 필수 배려·식이제한: {', '.join(all_constraints)}" if all_constraints else ""
user_pref_summary = (
    f"{companion_choice}, 기간: {duration_label} (총 {target_days}일), "
    f"선호 테마: {', '.join(style_choices) or '힐링/미식'}, "
    f"템포: {pace_choice}, 출발 예정: {travel_month_num}월{constraint_str}"
)

selected_visuals = get_cached_destination_visuals(
    selected_trip["name"], selected_trip["country"], selected_trip.get("theme", "")
)

# 선택된 무드(밝은 오트밀 & 포레스트 그린) CSS 및 배경 애니메이션 주입
inject_theme_css_and_background(active_vibe, dest_name)

# 🐥 하늘을 날아다니는 3D 파일럿 토리 오버레이 (클릭 시 하단 여행 라운지로 스크롤 이동)
st.markdown(render_flying_tori_overlay_html(dest_name), unsafe_allow_html=True)

# 🌟 1. TripPilot 메인 웰컴 히어로 배너 (첫 접속자 환영 및 3단계 온보딩 안내)
st.markdown(
    render_welcome_hero_banner_html(
        selected_trip=selected_trip,
        wizard_step=st.session_state.get("wizard_step", 1),
        duration_label=duration_label,
        companion_choice=companion_choice,
    ),
    unsafe_allow_html=True,
)

# 📸 2. 현실감 넘치는 고해상도 실사 자연 히어로 배너 & 갤러리
vibe_badge_text = "🌿 WARM OATMEAL & BIOPHILIC FOREST · 자연과 쉼이 어우러진 감성 여행 가이드"

st.markdown(
    render_nature_hero_html(selected_trip, selected_visuals, vibe_badge_text),
    unsafe_allow_html=True,
)

with st.expander(f"📸 {dest_name} 실사 힐링 명소 & 자연 뷰파인더 갤러리 열기 (자연 친화도 {selected_visuals['nature_score']}%)", expanded=True):
    st.markdown(
        render_nature_gallery_html(selected_visuals, dest_name, vibe_mode=active_vibe),
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
    # ── [깔끔한 선택 여정 브리프 & 원클릭 생성 콘솔 바] ──
    with st.container(border=True):
        br_c1, br_c2 = st.columns([2.4, 1.3], gap="medium")
        with br_c1:
            comp_short = companion_choice.split()[1] if len(companion_choice.split()) > 1 else companion_choice
            styles_short = ", ".join(style_choices[:3]) if style_choices else "자유 힐링"
            diet_short = dietary_choices[0].split()[0] if dietary_choices else "해당 없음"
            pace_short = pace_choice.split()[0] if pace_choice else "여유롭게"

            st.markdown(
                f"""
                <div style="display:flex; flex-direction:column; gap:4px;">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <span style="font-size:16px; font-weight:800; color:#064E3B;">📍 [{selected_trip['country']}] {dest_name} 맞춤 플래너</span>
                        <span style="background:#ECFDF5; border:1px solid #A7F3D0; color:#065F46; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px;">🗓️ {travel_month_num}월 출발 · {duration_label}</span>
                        <span style="background:#FAF8F5; border:1px solid #E5E0D5; color:#375346; font-size:11px; font-weight:600; padding:2px 8px; border-radius:999px;">👥 {comp_short}</span>
                    </div>
                    <div style="font-size:12px; color:#375346;">
                        ✨ <b>선호 취향</b>: {styles_short} · ⏰ <b>템포</b>: {pace_short} · 🛡️ <b>식이</b>: {diet_short}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with br_c2:
            active_bg_task = get_active_task_for_trip(trip_id)
            btn_disabled = (active_bg_task is not None)
            btn_top_label = f"⏳ 백그라운드 추론 중..." if btn_disabled else f"🚀 {dest_name} {duration_label} 일정 생성"
            if st.button(
                btn_top_label,
                key=f"btn_gen_top_{trip_id}",
                type="primary",
                use_container_width=True,
                disabled=btn_disabled,
            ):
                submit_itinerary_task(
                    trip_id=trip_id,
                    dest_name=dest_name,
                    country=selected_trip["country"],
                    theme=selected_trip.get("theme", ""),
                    user_pref_summary=user_pref_summary,
                    current_plan=st.session_state.itinerary_by_trip.get(trip_id, {}).get("structured_plan"),
                    top_k_val=top_k_val,
                    chunk_size_val=chunk_size_val,
                    chunk_overlap_val=chunk_overlap_val,
                    force_recollect=force_recollect,
                    target_days=target_days,
                    duration_label=duration_label,
                )
                st.toast(f"🚀 파일럿 토리가 '{dest_name}' {duration_label} 일정 설계를 백그라운드에서 시작했습니다!", icon="🐣")
                st.rerun()

    # 💱 실시간 체감 환율 및 현지 물가 지표 바
    currency_info = get_currency_and_cost_info(selected_trip["country"])
    sample_krw = int(round(currency_info["sample_amt"] * currency_info["krw_rate"], -2))
    curr_unit = currency_info["currency"].split(" ")[0].strip()
    with st.container(border=True):
        st.markdown(
            f'''
            <div style="margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px;">
                <span style="font-size: 15px; font-weight: 800; color: #064E3B;">💱 {dest_name} 실시간 체감 환율 & 현지 물가 시뮬레이터</span>
                <span style="background: #ECFDF5; border: 1px solid #A7F3D0; color: #065F46; font-size: 11.5px; font-weight: 700; padding: 2px 8px; border-radius: 999px;">현지 통화: {currency_info['currency']}</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px;">
                <div style="background: #FFFFFF; border: 1.5px solid #D1FAE5; border-radius: 12px; padding: 10px 14px; box-shadow: 0 2px 6px rgba(6,78,59,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #047857; margin-bottom: 4px;">체감 환율 기준 ({curr_unit})</div>
                    <div style="font-size: 15.5px; font-weight: 800; color: #0F291E; line-height: 1.35; word-break: keep-all;">{currency_info['sample_amt']:,} {curr_unit} = <span style="color:#059669; font-weight:800;">약 {sample_krw:,}원</span></div>
                </div>
                <div style="background: #FFFFFF; border: 1.5px solid #D1FAE5; border-radius: 12px; padding: 10px 14px; box-shadow: 0 2px 6px rgba(6,78,59,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #047857; margin-bottom: 4px;">☕ 스타벅스/카페 커피 1잔</div>
                    <div style="font-size: 15px; font-weight: 800; color: #0F291E; line-height: 1.35; word-break: keep-all;">{currency_info['coffee']}</div>
                </div>
                <div style="background: #FFFFFF; border: 1.5px solid #D1FAE5; border-radius: 12px; padding: 10px 14px; box-shadow: 0 2px 6px rgba(6,78,59,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #047857; margin-bottom: 4px;">🍽️ 로컬 식당 식사 1끼</div>
                    <div style="font-size: 15px; font-weight: 800; color: #0F291E; line-height: 1.35; word-break: keep-all;">{currency_info['meal']}</div>
                </div>
                <div style="background: #FFFFFF; border: 1.5px solid #D1FAE5; border-radius: 12px; padding: 10px 14px; box-shadow: 0 2px 6px rgba(6,78,59,0.04);">
                    <div style="font-size: 11.5px; font-weight: 700; color: #047857; margin-bottom: 4px;">🚕 택시/그랩 기본요금</div>
                    <div style="font-size: 15px; font-weight: 800; color: #0F291E; line-height: 1.35; word-break: keep-all;">{currency_info['taxi']}</div>
                </div>
            </div>
            ''',
            unsafe_allow_html=True,
        )

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
        st.markdown(
            '<div id="pilot-tori-lounge" style="scroll-margin-top: 80px;"></div>'
            '<h4 style="color:#064E3B; font-weight:800; margin:0 0 4px 0;">🐣 파일럿 토리와의 여행 라운지</h4>',
            unsafe_allow_html=True,
        )
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
            if st.button(f"✨ 내 취향대로 {duration_label} 코스 짜줘!", use_container_width=True):
                quick_prompt = f"내 취향({user_pref_summary})에 맞춰서 {dest_name} {duration_label} 여행 일정과 추천 숙소를 짜줘!"
            if st.button("🚫 생선 알러지! 고기 맛집 코스로 수정", use_container_width=True):
                quick_prompt = (
                    f"나는 생선·해산물 알러지가 있어! {dest_name} {duration_label} 일정에서 생선·해산물·초밥·수산시장 코스를 모두 빼고, "
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

            active_chat_task = get_active_task_for_trip(trip_id)
            if active_chat_task:
                with st.chat_message("assistant", avatar="🐣"):
                    elapsed_chat = int(time.time() - active_chat_task.get("start_time", time.time()))
                    st.markdown(
                        f"""
                        <div style="background:#F0FDF4;border:1.5px solid #10B981;border-radius:12px;padding:10px 14px;margin-bottom:6px;">
                            <div style="font-weight:700;font-size:13px;color:#064E3B;margin-bottom:4px;">
                                🐣 파일럿 토리가 백그라운드에서 추론하고 있어요... ({elapsed_chat}초)
                            </div>
                            <div style="font-size:12px;color:#047857;">
                                {active_chat_task.get('step', '데이터 검색 및 답변 생성 중...')}
                            </div>
                            <div style="font-size:11px;color:#065F46;opacity:0.85;margin-top:3px;">
                                💡 다른 화면으로 이동하셔도 백그라운드에서 멈추지 않고 계속 처리됩니다.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
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
                detected_constraint = clean_ai_artifacts(detected_constraint)
                prev_list = st.session_state.chat_constraints_by_trip.get(trip_id, [])
                if detected_constraint not in prev_list:
                    prev_list.append(detected_constraint)
                st.session_state.chat_constraints_by_trip[trip_id] = prev_list

            has_existing_plan = trip_id in st.session_state.itinerary_by_trip
            current_messages.append({"role": "user", "content": active_user_input})
            is_itin = is_itinerary_or_preference_request(active_user_input, has_existing_plan=has_existing_plan)
            active_constraints_now = st.session_state.chat_constraints_by_trip.get(trip_id, [])
            active_dietary_now = [c for c in dietary_choices if "해당 없음" not in c and "알러지 없음" not in c]
            merged_constraints = list(active_dietary_now) + [c for c in active_constraints_now if c not in active_dietary_now and "해당 없음" not in c and "알러지 없음" not in c]
            constraint_note = f" / 누적 필수 배려사항: {' | '.join(merged_constraints)}" if merged_constraints else ""
            combined_pref = f"{user_pref_summary}{constraint_note} / 이번 실시간 수정·취향 요청: {active_user_input}"

            submit_chat_task(
                trip_id=trip_id,
                dest_name=dest_name,
                country=selected_trip["country"],
                theme=selected_trip["theme"],
                active_user_input=active_user_input,
                user_pref_summary=combined_pref if is_itin else user_pref_summary,
                current_plan=st.session_state.itinerary_by_trip.get(trip_id, {}).get("structured_plan"),
                top_k_val=top_k_val,
                search_type_label=search_type_label,
                chunk_size_val=chunk_size_val,
                chunk_overlap_val=chunk_overlap_val,
                force_recollect=force_recollect,
                target_days=target_days,
                duration_label=duration_label,
                is_itin_request=is_itin,
            )
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
            target_days=target_days,
            duration_label=duration_label,
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
                            file_name=f"TripPilot_{dest_name}_맞춤_여행계획표.pdf",
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

                with st.expander("📱 스마트폰 카메라 스캔용 모바일 일정표 QR 코드", expanded=False):
                    hub_mobile_url = publish_itinerary_to_mobile_web(
                        trip_id=trip_id,
                        dest_name=dest_name,
                        country=selected_trip["country"],
                        structured_plan=itin_obj,
                    )
                    hub_target_url = hub_mobile_url or f"https://www.google.com/maps/search/{urllib.parse.quote(dest_name + ' 여행')}"
                    hub_qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={urllib.parse.quote(hub_target_url)}&color=064E3B&bgcolor=FAF8F5"
                    hq1, hq2 = st.columns([1, 2.4], gap="medium")
                    with hq1:
                        st.image(hub_qr_url, caption="스마트폰 기본 카메라로 스캔", width=150)
                    with hq2:
                        st.markdown(f"#### 📲 동행자 모바일 공유 일정표")
                        st.markdown(
                            f"친구들이 스마트폰 카메라로 QR 코드를 비추면 **맞춤 일정표 웹페이지**가 즉시 열립니다!<br/>"
                            f'<div style="margin-top: 8px;">'
                            f'<a class="booking-chip" href="{hub_target_url}" target="_blank" style="font-size: 13px; padding: 6px 14px; background: #064E3B; color: #FFFFFF !important; border: none; font-weight: 700;">🌐 모바일 여행 계획표 바로 열기</a>'
                            f'</div>'
                            f'<span style="font-size: 11px; color: #059669; word-break: break-all;">🔗 바로가기 링크: <a href="{hub_target_url}" target="_blank" style="color: #059669;">{hub_target_url}</a></span>',
                            unsafe_allow_html=True,
                        )
            else:
                st.caption("💡 먼저 첫 번째 탭에서 일정표를 생성하면 PDF, 웹 가이드북, 캘린더(.ics) 다운로드 버튼이 활성화됩니다!")

            days_summary = []
            for d in itin_obj.get("days", []):
                spots = " → ".join(s.get("place", "") for s in d.get("schedule", []))
                days_summary.append(f"• Day {d.get('day')}: {spots}")
            care_line = f"\n- 맞춤 배려/알러지 케어: {itin_obj.get('dietary_care_note')}" if itin_obj.get("dietary_care_note") else ""
            share_text = (
                f"✈️ [{selected_trip['country']} {dest_name} 맞춤 여행 계획 공유]\n"
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
