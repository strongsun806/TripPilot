"""
LangGraph 기반 다단계(Multi-Stage / 2-Pass: retrieve -> deep_retrieve -> generate) RAG 워크플로우 및
취향 맞춤형 여행 일정·동선 설계(Human-in-the-Loop 대화형 수정 포함), 조건 기반 자연어 탐색 모듈
"""
import os
import re
import sys
import json
import urllib.parse
from typing import TypedDict, List, Dict, Any
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import (
    get_api_key,
    get_base_url,
    CHAT_MODEL,
    PERSIST_DIRECTORY,
    META_COLLECTION,
    WIKI_COLLECTION,
    WIKI_TOP_K,
    SEARCH_TYPE,
    MMR_FETCH_K,
    MMR_LAMBDA,
)
from index_metadata import embeddings

api_key = get_api_key()
base_url = get_base_url()

llm_kwargs = {
    "model": CHAT_MODEL,
    "openai_api_key": api_key or "missing_key",
    "openai_api_base": base_url,
}
# gpt-6-luna 및 o1/o3 등 추론(Reasoning) 모델은 temperature 커스텀 지정 시 HTTP 400 에러 방지를 위해 기본값 유지
if not any(k in CHAT_MODEL.lower() for k in ["luna", "o1", "o3", "gpt-5-"]):
    llm_kwargs["temperature"] = 0.2

llm = ChatOpenAI(**llm_kwargs)

CITE_REGEX = re.compile(r"\[근거\s*([\d,\s]+)\]")


def strip_citations(text: str) -> str:
    """
    답변 본문, 일정표, 팁, 챗봇 메시지 등 사용자 화면에 노출되는 모든 텍스트에서
    [근거 6], [근거 1, 2], [근거 1~3], (근거 6), [6] 등 기계적인 인용 표기 일체를 완벽 제거하여
    자연스럽고 읽기 쉬운 문장으로 정돈합니다.
    """
    if not isinstance(text, str) or not text:
        return text if text is not None else ""
    # 1. 괄호 포함 ([근거 N] 포함), [근거 N 포함] 등 제거
    cleaned = re.sub(r"\(\s*\[근거\s*[\d,\s~-]+\]\s*포함\s*\)", "", text)
    cleaned = re.sub(r"\[\s*근거\s*[\d,\s~-]+\s*포함\s*\]", "", cleaned)
    # 2. [근거 1], [근거 1, 2], [근거 1~3], [근거 6] 등 대괄호 근거 표기 제거
    cleaned = re.sub(r"\[근거\s*[\d,\s~-]+\]", "", cleaned)
    # 3. (근거 1), (근거 1, 2), (근거 6) 등 소괄호 근거 표기 제거
    cleaned = re.sub(r"\(근거\s*[\d,\s~-]+\)", "", cleaned)
    # 4. 【근거 1】 등 특수 괄호 근거 표기 제거
    cleaned = re.sub(r"【근거\s*[\d,\s~-]+】", "", cleaned)
    # 5. [1], [2], [1, 2] 와 같이 남은 단독 대괄호 숫자 인용 제거 (단 마크다운 링크 [텍스트](url)는 보존)
    cleaned = re.sub(r"(?<!\]\()\s*\[\d+(?:[,\s]*\d+)*\]", "", cleaned)
    # 6. 불필요한 연속 공백 정리
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # 7. 문장 부호 앞의 어색한 공백 정리
    cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)
    return cleaned.strip()


def clean_ai_artifacts(text: str) -> str:
    """
    사용자 화면(배너, 일정표, 요약)에 노출되는 문구에서 [근거 N] 인용 태그 및 ** 마크다운 표시를 완전히 제거하여
    인공지능 특유의 기계적인 어투를 없애고 자연스럽고 친근한 텍스트로 정제합니다.
    """
    if not isinstance(text, str) or not text:
        return text if text is not None else ""
    cleaned = strip_citations(text)
    # **텍스트** 형태의 마크다운 볼드 기호 제거
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned



def safe_md(text: str) -> str:
    """
    마크다운 렌더링 시 물결표(~)가 2개 이상 들어갈 때
    GFM 취소선(strikethrough: ~~텍스트~~ 또는 ~텍스트~)으로 파싱되어
    글씨에 취소선(----)이 그어지고 물결표가 소실되는 현상을 완벽 방지합니다.
    코드 블록(```...```)을 제외한 일반 텍스트 구간의 물결표(~)를 전각 물결표('～')로 변환합니다.
    """
    if not isinstance(text, str) or "~" not in text:
        return text
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
        else:
            result.append(part.replace("~", "～"))
    return "".join(result)


# ── 1. LangGraph 상태(State) 정의 (다단계 Multi-Hop RAG 지원) ──
class RAGState(TypedDict):
    trip_id: str                        # 선택된 여행지 ID
    dest_name: str                      # 선택된 여행지 이름
    question: str                       # 사용자 질문
    top_k: int                          # 검색할 외부 문서 근거 수
    search_type: str                    # "similarity" 또는 "mmr"
    expanded_queries: List[str]         # 1차 RAG 문맥 분석 후 생성된 2차 심층 RAG 확장 서브쿼리 목록
    context_docs: List[Dict[str, Any]]  # 1차 + 2차 RAG에서 검색/병합된 근거 청크 목록
    answer: str                         # LLM이 생성한 최종 답변
    cited_sources: List[Dict[str, Any]] # 답변에서 실제 인용된 출처 목록


def extract_cited_sources(answer: str, context_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """답변 본문의 [근거 N] 또는 [근거 1, 2] 표기를 파싱해 실제 인용된 문서만 매핑"""
    raw_matches = CITE_REGEX.findall(answer)
    used_indices = {
        int(n.strip())
        for group in raw_matches
        for n in group.split(",")
        if n.strip().isdigit()
    }

    cited_sources = []
    for idx in sorted(used_indices):
        if 1 <= idx <= len(context_docs):
            doc = context_docs[idx - 1]
            cited_sources.append({
                "index": idx,
                "rag_stage": doc.get("rag_stage", "1차 RAG (기본·메타 검색)"),
                "source_type": doc["source_type"],
                "title": doc["title"],
                "url": doc["url"],
                "content": doc["content"],
            })
    return cited_sources


def make_google_maps_url(place: str, city: str = "", country: str = "") -> str:
    query = " ".join(x for x in [place, city, country] if x).strip()
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"


def make_google_maps_dir_url(places: List[str], city: str = "") -> str:
    """여러 방문지를 순서대로 연결하는 구글 지도 다중 경유지 길찾기 URL 생성"""
    if not places:
        return make_google_maps_url(city)
    if len(places) == 1:
        return make_google_maps_url(places[0], city)
    encoded_stops = [urllib.parse.quote(f"{p} {city}".strip()) for p in places]
    return "https://www.google.com/maps/dir/" + "/".join(encoded_stops)


def make_booking_links(dest_name: str, country: str = "", stay_area: str = "") -> Dict[str, str]:
    q_hotel = urllib.parse.quote(f"{dest_name} {stay_area}".strip())
    q_city = urllib.parse.quote(f"{dest_name} {country}".strip())
    return {
        "booking": f"https://www.booking.com/searchresults.ko.html?ss={q_hotel}",
        "agoda": f"https://www.agoda.com/ko-kr/search?text={q_hotel}",
        "airbnb": f"https://www.airbnb.co.kr/s/{q_hotel}/homes",
        "google_hotels": f"https://www.google.com/travel/hotels?q={q_hotel}",
        "klook": f"https://www.klook.com/ko/search/result/?query={urllib.parse.quote(dest_name)}",
        "skyscanner": f"https://www.skyscanner.co.kr/transport/flights-from/kr/?q={q_city}",
        "google_maps": make_google_maps_url(stay_area or dest_name, dest_name, country),
    }


def is_itinerary_or_preference_request(text: str, has_existing_plan: bool = False) -> bool:
    """사용자 발화가 여행 취향·알러지·식이제한 전달이나 실시간 일정 생성/수정 요청인지 판별"""
    plan_keywords = [
        "일정", "계획", "코스", "짜줘", "만들어", "바꿔", "수정", "추가", "빼줘", "빼고", "제외",
        "대신", "말고", "변경", "넣어", "다르게", "조정", "다시 짜",
        "1일차", "2일차", "3일차", "첫째", "둘째", "셋째", "오전", "오후", "저녁", "점심", "아침",
        "늦잠", "실내", "우천", "비 올", "비오면",
        "맛집", "식당", "카페", "힐링", "야경", "포토존", "인생샷", "액티비티", "쇼핑", "숙소", "호텔",
        "친구", "연인", "가족", "혼자", "부모님", "아이", "가성비", "여유", "빡빡",
        "알러지", "알레르기", "생선", "해산물", "초밥", "스시", "회", "날것", "갑각류", "새우", "게", "조개",
        "땅콩", "견과류", "유제품", "밀가루", "글루텐", "비건", "채식", "할랄", "고기", "육류", "소고기", "돼지고기",
        "못 먹", "안 먹", "싫어", "피해", "다리", "무릎", "체력", "걷기", "계단", "유모차", "휠체어",
    ]
    if any(k in text for k in plan_keywords):
        return True
    # 이미 우측에 일정표가 생성되어 있는 상태라면 추천/어때/가고 싶어 등도 실시간 일정 반영으로 처리
    if has_existing_plan and any(w in text for w in ["추천", "가고 싶", "먹고 싶", "어때", "넣을래", "갈래"]):
        return True
    return False


def extract_user_constraint(text: str) -> str | None:
    """사용자 채팅 발화에서 알러지·식이제한·동선 배려 등 지속 반영해야 할 제약사항을 추출"""
    constraint_triggers = [
        "알러지", "알레르기", "생선", "해산물", "초밥", "스시", "회", "날것", "갑각류", "새우", "게", "조개",
        "땅콩", "견과류", "비건", "채식", "할랄", "고기", "육류", "못 먹", "안 먹", "빼줘", "빼고", "제외",
        "말고", "대신", "다리", "무릎", "걷기", "계단", "유모차", "휠체어", "늦잠", "실내", "비 올",
    ]
    if any(t in text for t in constraint_triggers):
        return text.strip()
    return None


def detect_mentioned_destination(text: str, travel_list: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """사용자 채팅 입력에서 특정 여행지(250곳 중 하나 또는 주요 별칭)가 언급되었는지 자동 감지"""
    if not text or not travel_list:
        return None

    alias_map = {
        "북해도": "삿포로",
        "홋카이도": "삿포로",
        "스스키노": "삿포로",
        "오도리": "삿포로",
        "비에이": "비에이 & 후라노",
        "후라노": "비에이 & 후라노",
        "노보리베츠": "노보리베츠 & 도야호",
        "도야호": "노보리베츠 & 도야호",
        "유후인": "유후인 & 벳푸",
        "벳푸": "유후인 & 벳푸",
        "시라카와고": "다카야마 & 시라카와고",
        "다카야마": "다카야마 & 시라카와고",
        "고베": "고베 & 아리마 온천",
        "아리마": "고베 & 아리마 온천",
        "히로시마": "히로시마 & 미야지마",
        "미야지마": "히로시마 & 미야지마",
        "다카마쓰": "다카마쓰(나오시마 & 쇼도시마)",
        "나오시마": "다카마쓰(나오시마 & 쇼도시마)",
        "쇼도시마": "다카마쓰(나오시마 & 쇼도시마)",
        "나가사키": "나가사키 & 하우스텐보스",
        "하우스텐보스": "나가사키 & 하우스텐보스",
        "구마모토": "구마모토 & 아소산",
        "아소산": "구마모토 & 아소산",
        "가고시마": "가고시마 & 야쿠시마",
        "야쿠시마": "가고시마 & 야쿠시마",
        "하코네": "하코네 & 가와구치코(후지산)",
        "가와구치코": "하코네 & 가와구치코(후지산)",
        "후지산": "하코네 & 가와구치코(후지산)",
        "가마쿠라": "가마쿠라 & 에노시마",
        "에노시마": "가마쿠라 & 에노시마",
        "대마도": "대마도(쓰시마)",
        "쓰시마": "대마도(쓰시마)",
        "돗토리": "돗토리 & 요나고(다이센)",
        "요나고": "돗토리 & 요나고(다이센)",
        "도야마": "도야마 & 알펜루트(다테야마)",
        "알펜루트": "도야마 & 알펜루트(다테야마)",
        "아오모리": "아오모리 & 히로사키",
        "센다이": "센다이 & 마쓰시마",
        "강릉": "강릉 & 속초(설악산)",
        "속초": "강릉 & 속초(설악산)",
        "설악산": "강릉 & 속초(설악산)",
        "통영": "통영 & 거제",
        "거제": "통영 & 거제",
        "춘천": "춘천 & 가평",
        "가평": "춘천 & 가평",
        "담양": "담양 & 순천",
        "순천": "담양 & 순천",
        "울릉도": "울릉도 & 독도",
        "독도": "울릉도 & 독도",
        "단양": "단양 & 제천",
        "제천": "단양 & 제천",
        "하롱베이": "하롱베이 & 닌빈",
        "닌빈": "하롱베이 & 닌빈",
        "크라비": "크라비(끄라비)",
        "끄라비": "크라비(끄라비)",
        "팔라완": "팔라완(엘니도 & 코론)",
        "엘니도": "팔라완(엘니도 & 코론)",
        "코론": "팔라완(엘니도 & 코론)",
        "롬복": "롬복 & 길리 트라왕안",
        "길리": "롬복 & 길리 트라왕안",
        "타이중": "타이중 & 일월담",
        "일월담": "타이중 & 일월담",
        "화련": "화련(타이루거 협곡)",
        "타이루거": "화련(타이루거 협곡)",
        "태로각": "화련(타이루거 협곡)",
        "지우펀": "지우펀 & 스펀 & 예류(신베이)",
        "스펀": "지우펀 & 스펀 & 예류(신베이)",
        "예류": "지우펀 & 스펀 & 예류(신베이)",
        "청두": "청두(성도)",
        "성도": "청두(성도)",
        "시안": "시안(서안)",
        "서안": "시안(서안)",
        "계림": "구이린(계림) & 양숴",
        "구이린": "구이린(계림) & 양숴",
        "리장": "리장 & 샹그릴라(운남성)",
        "샹그릴라": "리장 & 샹그릴라(운남성)",
        "항저우": "항저우 & 우전(수향마을)",
        "우전": "항저우 & 우전(수향마을)",
        "방비엥": "방비엥 & 비엔티안",
        "비엔티안": "방비엥 & 비엔티안",
        "울란바토르": "울란바토르 & 고비사막(테를지)",
        "고비사막": "울란바토르 & 고비사막(테를지)",
        "몽골": "울란바토르 & 고비사막(테를지)",
        "앙코르와트": "씨엠립(앙코르와트)",
        "씨엠립": "씨엠립(앙코르와트)",
        "시엠립": "씨엠립(앙코르와트)",
        "융프라우": "인터라켄(융프라우)",
        "인터라켄": "인터라켄(융프라우)",
        "체르마트": "체르마트(마테호른)",
        "마테호른": "체르마트(마테호른)",
        "그린델발트": "그린델발트 & 라우터브루넨",
        "라우터브루넨": "그린델발트 & 라우터브루넨",
        "할슈타트": "잘츠부르크 & 할슈타트",
        "잘츠부르크": "잘츠부르크 & 할슈타트",
        "비엔나": "빈(비엔나)",
        "포지타노": "아말피 코스트(포지타노)",
        "아말피": "아말피 코스트(포지타노)",
        "돌로미티": "돌로미티(코르티나담페초 & 오르티세이)",
        "폼페이": "나폴리 & 폼페이 & 카프리섬",
        "카프리": "나폴리 & 폼페이 & 카프리섬",
        "나폴리": "나폴리 & 폼페이 & 카프리섬",
        "시칠리아": "시칠리아(팔레르모 & 타오르미나)",
        "마요르카": "마요르카(팔마 데 마요르카)",
        "톨레도": "톨레도 & 세고비아",
        "세고비아": "톨레도 & 세고비아",
        "론다": "말라가 & 론다 & 네르하",
        "말라가": "말라가 & 론다 & 네르하",
        "콜마르": "스트라스부르 & 콜마르",
        "스트라스부르": "스트라스부르 & 콜마르",
        "몽생미셸": "몽생미셸 & 노르망디",
        "샤모니": "샤모니(몽블랑)",
        "몽블랑": "샤모니(몽블랑)",
        "코츠월드": "옥스퍼드 & 코츠월드",
        "옥스퍼드": "옥스퍼드 & 코츠월드",
        "밀라노": "밀라노 & 코모 호수",
        "코모": "밀라노 & 코모 호수",
        "플리트비체": "스플리트 & 플리트비체 국립공원",
        "스플리트": "스플리트 & 플리트비체 국립공원",
        "블레드": "블레드 호수 & 류블랴나",
        "크라쿠프": "크라쿠프(아우슈비츠 & 소금광산)",
        "트롬쇠": "트롬쇠 & 로포텐 제도",
        "로포텐": "트롬쇠 & 로포텐 제도",
        "로바니에미": "헬싱키 & 로바니에미(산타마을)",
        "헬싱키": "헬싱키 & 로바니에미(산타마을)",
        "산타마을": "헬싱키 & 로바니에미(산타마을)",
        "레이캬비크": "레이캬비크(골든서클)",
        "아이슬란드": "레이캬비크(골든서클)",
        "베르겐": "베르겐 & 송네피오르드",
        "하와이": "하와이(호놀룰루)",
        "호놀룰루": "하와이(호놀룰루)",
        "와이키키": "하와이(호놀룰루)",
        "마우이": "마우이 & 빅아일랜드(하와이)",
        "빅아일랜드": "마우이 & 빅아일랜드(하와이)",
        "로스앤젤레스": "로스앤젤레스(LA)",
        "라스베이거스": "라스베이거스 & 그랜드캐니언",
        "그랜드캐니언": "라스베이거스 & 그랜드캐니언",
        "토론토": "토론토 & 나이아가라 폭포",
        "나이아가라": "토론토 & 나이아가라 폭포",
        "밴프": "밴프 국립공원(로키산맥)",
        "로키산맥": "밴프 국립공원(로키산맥)",
        "요세미티": "요세미티 국립공원",
        "옐로스톤": "옐로스톤 국립공원",
        "알래스카": "앵커리지 & 페어뱅크스(알래스카)",
        "마추픽추": "쿠스코 & 마추픽추",
        "쿠스코": "쿠스코 & 마추픽추",
        "우유니": "우유니 소금사막",
        "이과수": "부에노스아이레스 & 이과수 폭포",
        "부에노스아이레스": "부에노스아이레스 & 이과수 폭포",
        "파타고니아": "파타고니아(토레스 델 파이네)",
        "골드코스트": "골드코스트 & 케언즈",
        "케언즈": "골드코스트 & 케언즈",
        "퀸스타운": "퀸스타운 & 밀포드사운드",
        "밀포드사운드": "퀸스타운 & 밀포드사운드",
        "오클랜드": "오클랜드 & 로토루아",
        "로토루아": "오클랜드 & 로토루아",
        "보라보라": "보라보라섬(타히티)",
        "타히티": "보라보라섬(타히티)",
        "울루루": "울루루(에어즈 록)",
        "퍼스": "퍼스 & 로트네스트섬",
        "쿼카": "퍼스 & 로트네스트섬",
        "페트라": "페트라 & 와디럼",
        "와디럼": "페트라 & 와디럼",
        "카이로": "카이로 & 룩소르",
        "룩소르": "카이로 & 룩소르",
        "마라케시": "마라케시 & 사하라 사막",
        "사하라": "마라케시 & 사하라 사막",
        "세렝게티": "세렝게티 & 잔지바르",
        "잔지바르": "세렝게티 & 잔지바르",
        "빅토리아 폭포": "빅토리아 폭포 & 초베 국립공원",
        "타지마할": "아그라(타지마할) & 자이푸르",
        "자이푸르": "아그라(타지마할) & 자이푸르",
        "포카라": "카트만두 & 포카라(안나푸르나)",
        "카트만두": "카트만두 & 포카라(안나푸르나)",
        "사마르칸트": "사마르칸트 & 부하라",
        "알마티": "알마티(차른 캐니언 & 콜사이 호수)",
    }

    name_to_item = {item["name"]: item for item in travel_list}

    # 1) 긴 지명부터 정확 매칭 확인
    sorted_items = sorted(travel_list, key=lambda x: len(x["name"]), reverse=True)
    for item in sorted_items:
        full_name = item["name"]
        base_name = re.sub(r"\([^)]*\)", "", full_name).strip()
        if full_name in text or (len(base_name) >= 2 and base_name in text):
            return item

    # 2) 별칭(alias) 매칭 확인
    for alias, target_name in sorted(alias_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        if alias in text and target_name in name_to_item:
            return name_to_item[target_name]

    return None


# ── 2. Node 1 - 1차 RAG: Retrieve (메타데이터 기본 검색 + 초기 위키 의미 검색) ──
def retrieve_node(state: RAGState) -> Dict[str, Any]:
    trip_id = str(state["trip_id"])
    dest_name = state["dest_name"]
    question = state["question"]
    top_k = state.get("top_k") or WIKI_TOP_K
    search_type = state.get("search_type") or SEARCH_TYPE

    merged_docs = []
    seen_texts = set()

    # 1) travel_meta 컬렉션(500건)에서 선택 여행지의 메타데이터 청크 기본 조회 + 연관 여행지 검색
    meta_store = Chroma(
        collection_name=META_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )

    meta_results = meta_store.get(ids=[f"TRIP_{trip_id}"])
    if meta_results and meta_results.get("documents"):
        meta_content = meta_results["documents"][0]
        merged_docs.append({
            "rag_stage": "1차 RAG (기본·메타 검색)",
            "source_type": "여행지 메타데이터",
            "title": f"{dest_name} 여행지 기본 정보",
            "url": "내부 메타데이터",
            "content": meta_content,
        })
        seen_texts.add(meta_content.strip())

    # 질문에 근교 도시나 다른 여행지가 함께 언급된 경우 travel_meta에서 유사 여행지 메타데이터도 함께 병합
    try:
        extra_metas = meta_store.similarity_search(query=f"{dest_name} {question}", k=2)
        for m_doc in extra_metas:
            m_text = m_doc.page_content.strip()
            if m_text and m_text not in seen_texts:
                seen_texts.add(m_text)
                m_name = m_doc.metadata.get("name", "연관 여행지")
                merged_docs.append({
                    "rag_stage": "1차 RAG (기본·메타 검색)",
                    "source_type": "여행지 메타데이터",
                    "title": f"{m_name} 여행지 기본 정보",
                    "url": "내부 메타데이터",
                    "content": m_doc.page_content,
                })
    except Exception:
        pass

    # 2) travel_wiki 컬렉션에서 1차 의미 유사도 또는 MMR 기반 검색
    wiki_store = Chroma(
        collection_name=WIKI_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )

    wiki_results = []
    try:
        if search_type == "mmr":
            wiki_results = wiki_store.max_marginal_relevance_search(
                query=question,
                k=top_k,
                fetch_k=max(MMR_FETCH_K, top_k * 3),
                lambda_mult=MMR_LAMBDA,
                filter={"trip_id": trip_id},
            )
        else:
            wiki_results = wiki_store.similarity_search(
                query=question,
                k=top_k,
                filter={"trip_id": trip_id},
            )
    except Exception:
        wiki_results = []

    if len(wiki_results) < top_k:
        try:
            more_wiki = wiki_store.similarity_search(
                query=f"{dest_name} {question}",
                k=top_k,
            )
            wiki_results.extend(more_wiki)
        except Exception:
            pass

    # 3) 중복 제거 및 1차 근거 병합
    for doc in wiki_results:
        clean_text = doc.page_content.strip()
        if clean_text and clean_text not in seen_texts:
            seen_texts.add(clean_text)
            merged_docs.append({
                "rag_stage": "1차 RAG (기본·메타 검색)",
                "source_type": doc.metadata.get("source_type", "한국어 위키백과"),
                "title": doc.metadata.get("doc_title", "위키백과 문서"),
                "url": doc.metadata.get("source_url", "https://ko.wikipedia.org"),
                "content": doc.page_content,
            })

    return {"context_docs": merged_docs}


# ── 2-2. Node 2 - 2차 심층 RAG: Deep Retrieve (1차 검색 문맥 분석 -> 서브쿼리 확장 -> MMR 교차 재검색) ──
def deep_retrieve_node(state: RAGState) -> Dict[str, Any]:
    """1차 RAG에서 확보한 메타데이터·초기 문서의 핵심 고유명사(랜드마크, 인접 소도시, 향토 음식, 계절 특징)와
    사용자 질문 의도를 결합해 2차 확장 서브쿼리를 생성하고, ChromaDB 두 컬렉션에 대해 2차 MMR 심층 재검색(Multi-Hop RAG)을 수행합니다."""
    trip_id = str(state["trip_id"])
    dest_name = state["dest_name"]
    question = state["question"]
    top_k = state.get("top_k") or WIKI_TOP_K
    first_pass_docs = list(state.get("context_docs") or [])

    seen_texts = {d["content"].strip() for d in first_pass_docs if d.get("content")}

    # 1차 문맥에서 핵심 랜드마크/특징 요약 추출하여 2차 확장 쿼리 2개 생성
    first_pass_snippet = "\n".join(d["content"][:300] for d in first_pass_docs[:3])
    expanded_queries: List[str] = []
    try:
        subq_prompt = (
            f"여행지 '{dest_name}'에 대한 사용자 질문: \"{question}\"\n"
            f"[1차 RAG 검색 문맥 요약]:\n{first_pass_snippet}\n\n"
            f"위 1차 문맥에 등장하는 구체적인 핵심 랜드마크·명소·인접 지역·미식·역사·기후 키워드 중 "
            f"답변의 깊이를 높이기 위해 추가 벡터 검색할 **2개의 구체적인 한국어 검색 쿼리**만 JSON 배열(예: [\"쿼리1\", \"쿼리2\"])로 출력하라."
        )
        raw_subq = llm.invoke([HumanMessage(content=subq_prompt)]).content.strip()
        if "```" in raw_subq:
            raw_subq = re.sub(r"```(?:json)?", "", raw_subq).replace("```", "").strip()
        parsed_q = json.loads(raw_subq)
        if isinstance(parsed_q, list):
            expanded_queries = [str(q).strip() for q in parsed_q if str(q).strip()][:2]
    except Exception:
        expanded_queries = []

    if not expanded_queries:
        expanded_queries = [
            f"{dest_name} 대표 랜드마크 명소 역사 볼거리",
            f"{dest_name} 근교 연계 여행지 현지 미식 계절 기후 특징",
        ]

    meta_store = Chroma(
        collection_name=META_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )
    wiki_store = Chroma(
        collection_name=WIKI_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )

    merged_docs = list(first_pass_docs)

    for sub_q in expanded_queries:
        # 2차 위키백과 MMR 다양성 확장 검색 (trip_id 필터 + 전역 보완)
        try:
            sub_wiki = wiki_store.max_marginal_relevance_search(
                query=sub_q,
                k=max(2, top_k),
                fetch_k=max(MMR_FETCH_K, top_k * 4),
                lambda_mult=MMR_LAMBDA,
                filter={"trip_id": trip_id},
            )
        except Exception:
            sub_wiki = []

        if len(sub_wiki) < 2:
            try:
                sub_wiki.extend(
                    wiki_store.max_marginal_relevance_search(
                        query=f"{dest_name} {sub_k if (sub_k := sub_q) else ''}",
                        k=2,
                        fetch_k=10,
                        lambda_mult=MMR_LAMBDA,
                    )
                )
            except Exception:
                pass

        for doc in sub_wiki:
            clean_text = doc.page_content.strip()
            if clean_text and clean_text not in seen_texts:
                seen_texts.add(clean_text)
                merged_docs.append({
                    "rag_stage": f"2차 심층 RAG (확장 쿼리: {sub_q})",
                    "source_type": doc.metadata.get("source_type", "한국어 위키백과"),
                    "title": doc.metadata.get("doc_title", "위키백과 문서"),
                    "url": doc.metadata.get("source_url", "https://ko.wikipedia.org"),
                    "content": doc.page_content,
                })

        # 2차 메타데이터(근교/연계 소도시 및 유사 테마) 교차 검색
        try:
            sub_metas = meta_store.max_marginal_relevance_search(
                query=f"{dest_name} {sub_q}",
                k=2,
                fetch_k=10,
                lambda_mult=0.6,
            )
            for m_doc in sub_metas:
                m_text = m_doc.page_content.strip()
                if m_text and m_text not in seen_texts:
                    seen_texts.add(m_text)
                    m_name = m_doc.metadata.get("name", "연계 여행지")
                    merged_docs.append({
                        "rag_stage": f"2차 심층 RAG (확장 쿼리: {sub_q})",
                        "source_type": "여행지 메타데이터",
                        "title": f"{m_name} 연계 여행지 정보",
                        "url": "내부 메타데이터",
                        "content": m_doc.page_content,
                    })
        except Exception:
            pass

    return {
        "expanded_queries": expanded_queries,
        "context_docs": merged_docs,
    }


# ── 3. Node 2 - Generate (프롬프트 3 근거 기반 답변 생성 + 귀여운 여행 봇 페르소나) ──
def generate_node(state: RAGState) -> Dict[str, Any]:
    context_docs = state["context_docs"]
    question = state["question"]
    dest_name = state["dest_name"]

    if not context_docs:
        return {
            "answer": "제공된 문서에서 확인되지 않습니다.",
            "cited_sources": [],
        }

    context_text = ""
    for idx, doc in enumerate(context_docs, start=1):
        context_text += f"\n[근거 {idx}] (출처 유형: {doc['source_type']} | 문서명: {doc['title']})\n{doc['content']}\n"

    system_prompt = f"""당신은 다정하고 똑똑한 귀여운 여행 메이트 봇 **'파일럿 토리 🐣✈️'**입니다!
반드시 제공된 [참조 문서]의 내용만을 바탕으로 사용자의 질문에 친절하게 답하고, 사용자의 여행 취향을 자연스럽게 물어보며 대화를 이어가세요.

[작성 및 인용 원칙 — 필수 준수]
1. 사실 정보(기후·시즌, 랜드마크, 역사, 예산 수준, 지리·교통 등)는 오직 [참조 문서]에 있는 내용만 사용하고, 각 문장이나 주요 정보 끝에 반드시 `[근거 1]`, `[근거 2]` 형태로 근거 번호를 표기하십시오.
2. 문서에 등장하는 주요 명소나 랜드마크를 언급할 때는 사용자가 바로 눌러볼 수 있도록 `[📍 장소명 구글 지도](https://www.google.com/maps/search/?api=1&query=장소명+{urllib.parse.quote(dest_name)})` 링크를 함께 달아주십시오.
3. 제공된 문서에 전혀 없는 사실이나 확인되지 않은 수치(예: 미래 미출시 시설, 확인 불가 요금 등)를 물으면 절대 추측하지 말고, 반드시 `"제공된 문서에서 확인되지 않습니다."` 문구를 포함하여 정중히 안내하십시오 (이 경우 근거 번호를 붙이지 마십시오).
4. 사실 확인이 가능한 일반 여행 질문에 답할 때는 답변 마지막 줄에 귀여운 여행 봇 톤으로 **사용자의 여행 취향(예: 누구와 가는지, 감성 카페·맛집·야경·힐링 중 어떤 코스를 선호하는지, 이 내용으로 오른쪽 창에 맞춤 2박 3일 일정을 짜줄지)**을 다정하게 한 줄로 물어보십시오.

[참조 문서]
{context_text}
"""

    human_prompt = f"질문 대상 여행지: {dest_name}\n사용자 메시지: {question}"

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]).content.strip()
    except Exception:
        response = f"🐣 {dest_name} 기본 정보야! {context_docs[0]['content']}."

    cited_sources = extract_cited_sources(response, context_docs)

    return {
        "answer": strip_citations(response),
        "cited_sources": cited_sources,
    }


# ── 4. LangGraph 다단계(Multi-Stage / 2-Pass) RAG 워크플로우 빌드 (retrieve -> deep_retrieve -> generate -> END) ──
def build_rag_graph():
    workflow = StateGraph(RAGState)

    workflow.add_node("retrieve", retrieve_node)           # 1차 RAG: 메타데이터 + 초기 위키 의미 검색
    workflow.add_node("deep_retrieve", deep_retrieve_node) # 2차 심층 RAG: 1차 문맥 분석 -> 서브쿼리 확장 -> MMR 교차 재검색
    workflow.add_node("generate", generate_node)           # 3단계: 다중 근거 통합 답변 생성

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "deep_retrieve")
    workflow.add_edge("deep_retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()


rag_app = build_rag_graph()


def query_trip_pilot(
    trip_id: str,
    dest_name: str,
    question: str,
    top_k: int = WIKI_TOP_K,
    search_type: str = SEARCH_TYPE,
) -> Dict[str, Any]:
    """다단계(2-Pass) LangGraph RAG 질의 함수 (1차 기본·메타 검색 -> 2차 서브쿼리 확장 MMR 재검색 -> 근거 기반 생성)"""
    initial_state: RAGState = {
        "trip_id": str(trip_id),
        "dest_name": dest_name,
        "question": question,
        "top_k": top_k,
        "search_type": search_type,
        "expanded_queries": [],
        "context_docs": [],
        "answer": "",
        "cited_sources": [],
    }

    result = rag_app.invoke(initial_state)
    return {
        "answer": strip_citations(safe_md(result["answer"])),
        "cited_sources": result["cited_sources"],
        "all_contexts": result["context_docs"],
        "expanded_queries": result.get("expanded_queries", []),
    }


# ── 5. 도메인 특화 기능 1 — 취향 반영 맞춤 2박 3일 일정표 + 동선 지도 + 예산 포트폴리오 + 숙소/구글맵 링크 (2-Stage RAG 적용) ──
def generate_itinerary(
    trip_id: str,
    dest_name: str,
    country: str = "",
    user_preference: str = "",
    current_plan: Dict[str, Any] | None = None,
    top_k: int = 4,
    target_days: int | None = None,
) -> Dict[str, Any]:
    """선택한 여행지의 색인된 메타데이터 및 위키백과 문서에 대해
    1차 RAG(개요·메타데이터) + 2차 심층 RAG(랜드마크·미식·근교 코스 MMR 재검색)를 수행하여
    사용자 취향 및 설정 기간(당일치기부터 최대 30일 한달살기까지)이 반영된 맞춤 일정표, 지도 동선 좌표, 예산 시뮬레이션, 추천 숙소 및 예약 링크를 생성"""
    search_q = f"{dest_name} 관광 명소 랜드마크 역사 문화 음식 교통 여행 코스 {user_preference}".strip()
    state_pass1: RAGState = {
        "trip_id": str(trip_id),
        "dest_name": dest_name,
        "question": search_q,
        "top_k": top_k,
        "search_type": "mmr",
        "expanded_queries": [],
        "context_docs": [],
        "answer": "",
        "cited_sources": [],
    }
    pass1_out = retrieve_node(state_pass1)
    state_pass1["context_docs"] = pass1_out["context_docs"]
    pass2_out = deep_retrieve_node(state_pass1)

    context_docs = pass2_out["context_docs"]
    expanded_queries = pass2_out.get("expanded_queries", [])
    context_text = "\n".join(
        f"[근거 {i}] ({d.get('rag_stage', '1차 RAG')} | {d['source_type']}: {d['title']})\n{d['content']}"
        for i, d in enumerate(context_docs, start=1)
    )

    pref_desc = user_preference.strip() or "핵심 랜드마크 & 현지 맛집 & 여유로운 힐링 밸런스 코스"

    # 여행 기간 (target_days) 자동 감지 및 설정 (최대 30일 한달살기 완벽 지원)
    if target_days is None or target_days <= 0:
        target_days = 3
        if any(w in pref_desc for w in ["한달살기", "한달", "30일", "29박 30일", "29박30일"]):
            target_days = 30
        elif any(w in pref_desc for w in ["3주살기", "3주", "21일", "20박 21일", "20박21일"]):
            target_days = 21
        elif any(w in pref_desc for w in ["2주살기", "2주", "14일", "13박 14일", "13박14일"]):
            target_days = 14
        elif any(w in pref_desc for w in ["열흘", "10일", "9박 10일", "9박10일"]):
            target_days = 10
        elif any(w in pref_desc for w in ["일주일", "1주일", "6박 7일", "6박7일", "7일"]):
            target_days = 7
        elif any(w in pref_desc for w in ["당일치기", "당일"]):
            target_days = 1
        else:
            m_nd = re.search(r"(\d+)\s*박\s*(\d+)\s*일", pref_desc)
            if m_nd:
                target_days = int(m_nd.group(2))
            else:
                m_d = re.search(r"(\d+)\s*일(?:간|치)?", pref_desc)
                if m_d:
                    target_days = int(m_d.group(1))

    target_days = max(1, min(30, int(target_days)))

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
    prev_plan_summary = ""
    if current_plan and current_plan.get("days"):
        prev_plan_summary = f"\n[기존 일정 요약 (이 일정을 바탕으로 사용자의 수정 요청·알러지·식이제한을 즉시 반영해 업데이트할 것)]:\n{json.dumps(current_plan.get('days'), ensure_ascii=False)}\n"

    json_prompt = f"""당신은 다정하고 똑똑한 AI 여행 아키텍트 봇 **'파일럿 토리 🐣✈️'**입니다.
아래 [참조 문서]에 등장하는 '{dest_name}'({country})의 실제 명소, 랜드마크, 지역 특성, 문화·미식, 기후/시즌 정보를 바탕으로
사용자의 취향 및 특별 제약/수정 요청(`{pref_desc}`)을 완벽히 반영한 **맞춤 {duration_label} (총 {target_days}일치) 여행 청사진 및 동선 데이터**를 JSON 형식으로 작성하십시오.
{prev_plan_summary}
[작성 규칙 — 최우선 준수]
1. **알러지·식이제한·체력/동선 수정 요청 절대 준수**:
   - 사용자가 `'생선 알러지'`, `'해산물 제외'`, `'초밥/회 못 먹음'`, `'갑각류 알러지'`, `'비건'` 등을 언급한 경우, 일정(`place`, `activity`, `tip`)에서 생선·초밥·수산시장 해산물 시식 코스를 **100% 완전히 제거**하고, 해당 도시의 다른 유명한 육류/면류/디저트/온천/문화 코스로 대체하십시오.
   - 특정 일차/시간대 수정 요청(예: `'2일차 실내 코스로'`, `'늦잠 모드 11시 시작'`, `'많이 걷는 곳 제외'`)이 있으면 해당 부분을 정확히 수정하고, `dietary_care_note`와 `bot_message`에 어떤 요청을 어떻게 반영해 수정했는지 구체적으로 설명하십시오.
2. 문서에 확인된 실제 명소와 특징을 중심으로 **1일차부터 {target_days}일차까지 정확히 {target_days}개의 일차(`day` 객체)**를 `days` 배열에 포함하여 동선이 꼬이지 않게 구성하십시오.
   - 단기(1~5일): 각 일차마다 오전/오후/저녁 총 3개 방문지(`schedule` 아이템)를 포함하십시오.
   - 중기(6~10일): 각 일차마다 주간 핵심 1~2개와 저녁 1개, 총 2~3개 방문지를 포함하십시오.
   - 장기/한달살기(11~30일): 각 일차마다 주간 1개와 저녁 1개(총 2개 슬롯)로 간결하게 작성하고, 각 스팟 설명은 1~2문장으로 압축하여 응답 토큰 한도를 초과하지 않도록 하십시오.
3. 각 활동 설명(`activity`), 여행 팁 문장 끝에는 참조한 문서 번호인 `[근거 1]`, `[근거 2]` 등을 자연스럽게 포함하십시오. 단, `dietary_care_note`(맞춤 케어 요약)에는 `[근거 N]` 인용 태그나 마크다운 볼드(`**`) 기호를 절대 포함하지 말고 자연스럽고 편안한 일상 문장으로만 작성하십시오.
4. 지도에 동선을 표시하기 위해 각 방문지(`place`)의 실제 위도(`lat`)와 경도(`lng`)를 서로 겹치지 않게 소수점 4자리 실수(float)로 정확히 기입하십시오.
5. 출력은 반드시 파싱 가능한 순수 JSON 객체만 반환하십시오.

[JSON 출력 스키마]
{{
  "bot_message": "🐣 파일럿 토리가 사용자에게 전하는 다정하고 귀여운 일정 설계/수정 브리핑 메시지 (예: 알러지나 수정 요청을 어떻게 반영해서 어떤 코스로 바꿨는지 친절히 안내 + [근거 N] 포함 + 추가로 조정하고 싶은 점이 있는지 질문 한 줄)",
  "center_lat": 41.8826,
  "center_lng": -87.6226,
  "applied_style": "{pref_desc}",
  "dietary_care_note": "알러지·식이제한·동선 배려 등 맞춤 케어 반영 요약 (주의: [근거 N] 인용 태그나 ** 표시를 절대 포함하지 말고 '요청하신 해산물 코스를 제외하고 현지 로컬 맛집과 디저트 위주로 대체했습니다'처럼 자연스럽고 다정하게 작성)",
  "best_season_tip": "추천 여행 시기 및 기후 특징 요약 ([근거 N] 포함)",
  "budget_transport_tip": "예산 수준 및 현지 이동·교통 패스 팁 요약 ([근거 N] 포함)",
  "plan_b_tip": "우천 시 또는 돌발 상황 대비 실내 대체 코스/플랜 B 팁 ([근거 N] 포함)",
  "budget_breakdown": [
    {{"category": "🏨 숙박비", "ratio": 35, "desc": "추천 숙소 구역 기준 2박 예상 비중"}},
    {{"category": "🍽️ 식비 & 카페", "ratio": 28, "desc": "현지 미식 및 감성 카페 투어"}},
    {{"category": "🚇 현지 교통비", "ratio": 15, "desc": "공항 이동 및 도심 대중교통/택시"}},
    {{"category": "🎟️ 입장권 & 투어", "ratio": 14, "desc": "주요 랜드마크 입장 및 액티비티"}},
    {{"category": "🛡️ 예비비", "ratio": 8, "desc": "기념품 및 비상 예비 예산"}}
  ],
  "recommended_stays": [
    {{
      "area_name": "추천 숙소 거점 지역명 (예: 미케 비치 해변가 / 시카고 매그니피센트 마일)",
      "style": "추천 숙소 유형 (예: 오션뷰 풀빌라 리조트 / 도심 부티크 호텔)",
      "reason": "이 지역을 추천하는 동선·치안·접근성 이유 ([근거 N] 포함)"
    }}
  ],
  "days": [
    {{
      "day": 1,
      "theme_title": "1일차 테마 제목",
      "stay_area": "1일차 추천 숙박 구역명",
      "schedule": [
        {{
          "time_slot": "09:30 - 12:00 (오전)",
          "place": "방문 명소명",
          "lat": 41.8826,
          "lng": -87.6226,
          "activity": "명소 특징 및 추천 활동 설명 [근거 1]",
          "transport": "도보 10분 / 지하철 15분",
          "tip": "관람 포인트 또는 포토존 팁"
        }},
        {{
          "time_slot": "13:00 - 17:00 (오후)",
          "place": "방문 명소명",
          "lat": 41.8796,
          "lng": -87.6237,
          "activity": "명소 특징 및 추천 활동 설명 [근거 2]",
          "transport": "지하철 10분",
          "tip": "관람 포인트 또는 이동 팁"
        }},
        {{
          "time_slot": "18:00 - 21:00 (저녁)",
          "place": "방문 명소명",
          "lat": 41.8885,
          "lng": -87.6354,
          "activity": "저녁 코스 및 현지 미식 활동 설명 [근거 1]",
          "transport": "도보 12분",
          "tip": "야경 또는 맛집 팁"
        }}
      ]
    }},
    {{
      "day": 2,
      "theme_title": "2일차 테마 제목",
      "stay_area": "2일차 추천 숙박 구역명",
      "schedule": [
        {{"time_slot": "09:30 - 12:30 (오전)", "place": "...", "lat": 0.0, "lng": 0.0, "activity": "... [근거 N]", "transport": "...", "tip": "..."}},
        {{"time_slot": "13:30 - 17:30 (오후)", "place": "...", "lat": 0.0, "lng": 0.0, "activity": "... [근거 N]", "transport": "...", "tip": "..."}},
        {{"time_slot": "18:30 - 21:00 (저녁)", "place": "...", "lat": 0.0, "lng": 0.0, "activity": "... [근거 N]", "transport": "...", "tip": "..."}}
      ]
    }},
    {{
      "day": 3,
      "theme_title": "3일차 테마 제목",
      "stay_area": "공항 이동 또는 도심 마무리 거점",
      "schedule": [
        {{"time_slot": "10:00 - 13:00 (오전)", "place": "...", "lat": 0.0, "lng": 0.0, "activity": "... [근거 N]", "transport": "...", "tip": "..."}},
        {{"time_slot": "14:00 - 17:00 (오후)", "place": "...", "lat": 0.0, "lng": 0.0, "activity": "... [근거 N]", "transport": "...", "tip": "..."}}
      ]
    }}
  ]
}}

[참조 문서]
{context_text}
"""
    structured_plan: Dict[str, Any] = {}
    try:
        raw = llm.invoke([HumanMessage(content=json_prompt)]).content.strip()
        if "```" in raw:
            raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        structured_plan = json.loads(raw)
        if structured_plan.get("dietary_care_note"):
            structured_plan["dietary_care_note"] = clean_ai_artifacts(structured_plan["dietary_care_note"])
        if structured_plan.get("bot_message"):
            structured_plan["bot_message"] = clean_ai_artifacts(structured_plan["bot_message"])
    except Exception:
        structured_plan = {}

    city_links = make_booking_links(dest_name, country)
    structured_plan["city_links"] = city_links

    # 일차별 마크다운 및 전체 마크다운 생성 (GDM_test 스타일: 구글 지도/맛집/티켓 원클릭 버튼 포함)
    days_list = structured_plan.get("days", [])
    all_places_flat = []

    md_lines = [f"### 🌿 {dest_name} 맞춤 {duration_label} 여행 일정표\n"]
    if structured_plan.get("applied_style"):
        md_lines.append(f"- **반영된 여행 스타일**: `{structured_plan['applied_style']}`\n")

    md_lines.append("| 일차 | 시간 | 방문지 / 코스 | 세부 활동 & 원클릭 길찾기·예약 | 이동 수단 |")
    md_lines.append("| :---: | :---: | :--- | :--- | :---: |")

    for day_obj in days_list:
        d_num = day_obj.get("day", 1)
        day_places = []
        for item in day_obj.get("schedule", []):
            place = item.get("place", dest_name)
            day_places.append(place)
            all_places_flat.append(place)
            gmap_url = make_google_maps_url(place, dest_name, country)
            food_url = make_google_maps_url(f"{place} 맛집", dest_name, country)
            klook_url = f"https://www.klook.com/ko/search/result/?query={urllib.parse.quote(place)}"
            item["google_maps_url"] = gmap_url
            item["food_url"] = food_url
            item["klook_url"] = klook_url

            t_slot = item.get("time_slot", "")
            act = strip_citations(item.get("activity", ""))
            tip = strip_citations(item.get("tip", ""))
            item["activity"] = act
            item["tip"] = tip
            trans = item.get("transport", "도보/대중교통")
            links_inline = f"[📍 구글 지도]({gmap_url}) [🍽️ 주변 맛집]({food_url}) [🎟️ 티켓/투어]({klook_url})"
            desc_cell = f"{act}" + (f" *(💡 {tip})*" if tip else "") + f"<br/>{links_inline}"
            md_lines.append(
                f"| **Day {d_num}** | {t_slot} | **{place}** | {desc_cell} | {trans} |"
            )
        day_obj["google_dir_url"] = make_google_maps_dir_url(day_places, dest_name)

    structured_plan["all_google_dir_url"] = make_google_maps_dir_url(all_places_flat, dest_name)

    stays = structured_plan.get("recommended_stays", [])
    for s in stays:
        s["reason"] = strip_citations(s.get("reason", ""))
        s["links"] = make_booking_links(dest_name, country, s.get("area_name", ""))

    md_lines.append(f"\n### 🏨 {dest_name} 추천 숙소 거점 및 원클릭 예약")
    if stays:
        for s in stays:
            area = s.get("area_name", dest_name)
            style = s.get("style", "추천 숙소")
            reason = s.get("reason", "")
            links = s["links"]
            md_lines.append(
                f"- **{area}** (`{style}`): {reason}  \n"
                f"  [📍 구글 지도]({links['google_maps']}) · "
                f"[🏨 아고다 최저가]({links['agoda']}) · "
                f"[🏨 부킹닷컴]({links['booking']}) · "
                f"[🏠 에어비앤비]({links['airbnb']}) · "
                f"[🛏️ 구글 호텔]({links['google_hotels']})"
            )

    best_season_tip = strip_citations(structured_plan.get("best_season_tip", ""))
    budget_tip = strip_citations(structured_plan.get("budget_transport_tip", ""))
    plan_b_tip = strip_citations(structured_plan.get("plan_b_tip", ""))
    structured_plan["best_season_tip"] = best_season_tip
    structured_plan["budget_transport_tip"] = budget_tip
    structured_plan["plan_b_tip"] = plan_b_tip

    if best_season_tip or budget_tip or plan_b_tip:
        md_lines.append(f"\n### 🔍 플래너 토리의 맞춤 여행 꿀팁")
        if best_season_tip:
            md_lines.append(f"- **추천 시즌 & 날씨**: {best_season_tip}")
        if budget_tip:
            md_lines.append(f"- **예산 & 교통 팁**: {budget_tip}")
        if plan_b_tip:
            md_lines.append(f"- **우천/돌발 대비 플랜 B**: {plan_b_tip}")

    answer_md = safe_md("\n".join(md_lines))
    bot_msg = safe_md(structured_plan.get("bot_message") or (
        f"🐣 짜잔! **{dest_name}**의 위키백과 정보와 기본 제원을 바탕으로 맞춤 {duration_label} 여행 일정과 일자별 동선 지도를 완성했어!\n\n"
        f"**오른쪽 플래너 창**에서 일차별 탭을 눌러가며 각 날짜의 지도 동선과 숙소·구글맵 링크를 확인해 봐! "
        f"혹시 **'특정 일차는 늦잠 모드로 바꿔줘'** 라거나 **'비 올 때 실내 코스로 바꿔줘'** 같은 요청이 있으면 나한테 바로 말해줘! ✈️💛"
    ))

    combined_for_citations = f"{bot_msg}\n{answer_md}"
    extracted_sources = extract_cited_sources(combined_for_citations, context_docs)

    # 사용자 화면 노출용 답변 및 챗봇 메시지에서 [근거 N] 인용 표기 완벽 제거
    clean_answer_md = strip_citations(answer_md)
    clean_bot_msg = strip_citations(bot_msg)
    structured_plan["bot_message"] = clean_bot_msg

    return {
        "answer": clean_answer_md,
        "bot_message": clean_bot_msg,
        "structured_plan": structured_plan,
        "cited_sources": extracted_sources,
        "all_contexts": context_docs,
        "expanded_queries": expanded_queries,
    }


def _strip_emoji_for_pdf(text: str) -> str:
    """Windows 기본 맑은고딕(malgun.ttf) 폰트에서 깨질 수 있는 이모지를 깔끔한 텍스트 기호로 치환"""
    if not text:
        return ""
    # [근거 N] 표기는 그대로 유지하거나 깔끔히 정돈
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", str(text))
    cleaned = re.sub(r"[\u2600-\u27BF\uFE0F]", "", cleaned)
    return cleaned.strip()


def _clean_pdf_text(text: str) -> str:
    """PDF 출력용: 근거1, 근거7 등 불필요한 인용 표기 및 이모지를 말끔히 제거하여 깔끔한 여행 가이드북으로 정돈"""
    if not text:
        return ""
    text = re.sub(r"\[근거\s*\d+(?:[,\s]*\d+)*\]", "", text)
    text = re.sub(r"\(근거\s*\d+(?:[,\s]*\d+)*\)", "", text)
    text = re.sub(r"\[\d+(?:[,\s]*\d+)*\]", "", text)
    return _strip_emoji_for_pdf(text).strip()


def export_itinerary_pdf_bytes(
    trip_item: Dict[str, Any],
    structured_plan: Dict[str, Any],
    checklist: List[Dict[str, Any]] | None = None,
    dutch_summary: str = "",
) -> bytes:
    """완성된 맞춤 여행 계획표·동선 지도 이미지·추천 숙소·예산·체크리스트를 오트밀 & 포레스트 그린 테마의 한글 PDF로 생성"""
    from fpdf import FPDF
    from pdf_route_map import generate_itinerary_route_map_image

    if "structured_plan" in structured_plan and isinstance(structured_plan["structured_plan"], dict):
        structured_plan = structured_plan["structured_plan"]

    dest_name = trip_item.get("name", "여행지")
    country = trip_item.get("country", "")
    continent = trip_item.get("continent", "")
    season = trip_item.get("best_season", "")
    budget = trip_item.get("budget_level", "")
    days_count = len(structured_plan.get("days", [])) or 3
    applied_style = structured_plan.get("applied_style", "맞춤형 여행 코스")
    care_note = clean_ai_artifacts(structured_plan.get("dietary_care_note", ""))

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    font_reg = r"C:\Windows\Fonts\malgun.ttf"
    font_bold = r"C:\Windows\Fonts\malgunbd.ttf"
    has_kr_font = os.path.exists(font_reg)
    if has_kr_font:
        pdf.add_font("Malgun", "", font_reg)
        pdf.add_font("Malgun", "B", font_bold if os.path.exists(font_bold) else font_reg)
        font_family = "Malgun"
    else:
        font_family = "Helvetica"

    if days_count == 1:
        dur_label_pdf = "당일치기"
    elif days_count == 30:
        dur_label_pdf = "29박 30일 (한달살기)"
    elif days_count == 7:
        dur_label_pdf = "6박 7일 (1주일)"
    elif days_count == 14:
        dur_label_pdf = "13박 14일 (2주 살기)"
    elif days_count == 21:
        dur_label_pdf = "20박 21일 (3주 살기)"
    else:
        dur_label_pdf = f"{days_count-1}박 {days_count}일"

    # 상단 헤더 배너 (따스한 오트밀 & 딥 포레스트 그린)
    pdf.set_fill_color(6, 78, 59)
    pdf.rect(10, 10, 190, 28, style="F")
    pdf.set_xy(15, 12)
    pdf.set_text_color(255, 255, 255)
    title_str = _clean_pdf_text(f"TripPilot | [{country}] {dest_name} {dur_label_pdf} 맞춤 여행 가이드북")
    if len(title_str) > 28:
        pdf.set_font(font_family, "B", 12)
    else:
        pdf.set_font(font_family, "B", 13.5)
    pdf.cell(180, 7.5, title_str, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(15)
    pdf.set_font(font_family, "", 8.5)
    meta_str = _clean_pdf_text(f"대륙: {continent}  |  추천 시기: {season}  |  예상 경비: {budget}")
    pdf.cell(180, 4.8, meta_str, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(15)
    pdf.set_font(font_family, "", 8.5)
    style_str = _clean_pdf_text(f"반영된 취향: {applied_style}")
    if len(style_str) > 65:
        style_str = style_str[:62] + "..."
    pdf.cell(180, 4.8, style_str, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(41)
    pdf.set_text_color(15, 41, 30)

    temp_map_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(temp_map_dir, exist_ok=True)

    if care_note:
        pdf.set_fill_color(236, 253, 245)
        pdf.set_draw_color(167, 243, 208)
        pdf.set_font(font_family, "B", 9.5)
        pdf.set_text_color(6, 78, 59)
        pdf.multi_cell(190, 6.5, _clean_pdf_text(f"[맞춤 알러지/배려 케어] {care_note}"), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # 일차별 상세 일정 및 일자별 분할 동선 지도 (동선 뭉침 100% 방지)
    for day_obj in structured_plan.get("days", []):
        d_num = int(day_obj.get("day", 1))
        t_title = _clean_pdf_text(day_obj.get("theme_title", f"{d_num}일차 코스"))
        stay_area = _clean_pdf_text(day_obj.get("stay_area", dest_name))

        # 일차별 시작 전 페이지 잔여 높이가 부족하면 다음 페이지로 깔끔하게 넘김
        if pdf.get_y() > 145:
            pdf.add_page()

        pdf.set_fill_color(240, 253, 244)
        pdf.set_draw_color(167, 243, 208)
        pdf.set_text_color(6, 78, 59)
        pdf.set_font(font_family, "B", 11.5)
        pdf.cell(190, 8.5, f"Day {d_num} - {t_title}  (추천 숙소: {stay_area})", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # 🗺️ 해당 일차 전용 분할 동선 지도 삽입 (여러 일차가 겹쳐서 뭉치는 현상 차단)
        if d_num <= 7 or days_count <= 10:
            day_map_path = os.path.join(temp_map_dir, f"map_pdf_{trip_item.get('id', 'temp')}_day{d_num}.jpg")
            try:
                day_map_ok = generate_itinerary_route_map_image(
                    dest_name,
                    structured_plan,
                    day_map_path,
                    selected_day=d_num,
                    width=760,
                    height=250,
                )
                if day_map_ok and os.path.exists(day_map_path):
                    cur_y = pdf.get_y()
                    pdf.image(day_map_path, x=10, y=cur_y, w=190, h=62)
                    pdf.set_y(cur_y + 65)
            except Exception:
                pass

        for idx, item in enumerate(day_obj.get("schedule", []), start=1):
            t_slot = _clean_pdf_text(item.get("time_slot", ""))
            place = _clean_pdf_text(item.get("place", ""))
            trans = _clean_pdf_text(item.get("transport", "도보/대중교통"))
            act = _clean_pdf_text(item.get("activity", ""))
            tip = _clean_pdf_text(item.get("tip", ""))

            pdf.set_font(font_family, "B", 10)
            pdf.set_text_color(6, 78, 59)
            pdf.multi_cell(190, 6, f"  {idx}. [{t_slot}] {place}  (이동: {trans})", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(font_family, "", 9.5)
            pdf.set_text_color(15, 41, 30)
            pdf.multi_cell(190, 5.5, f"     - 활동: {act}", new_x="LMARGIN", new_y="NEXT")
            if tip:
                pdf.set_text_color(5, 150, 105)
                pdf.multi_cell(190, 5.5, f"     - 토리의 팁: {tip}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # 추천 숙소 및 여행 꿀팁
    stays = structured_plan.get("recommended_stays", [])
    if stays:
        pdf.set_text_color(6, 78, 59)
        pdf.set_font(font_family, "B", 11)
        pdf.cell(190, 8, "추천 숙소 거점 안내", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font_family, "", 9.5)
        pdf.set_text_color(15, 41, 30)
        for s in stays:
            area = _clean_pdf_text(s.get("area_name", ""))
            style = _clean_pdf_text(s.get("style", ""))
            reason = _clean_pdf_text(s.get("reason", ""))
            pdf.multi_cell(190, 5.5, f"• {area} ({style}): {reason}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # 동행자 준비물 & 정산 요약
    if checklist and isinstance(checklist, list):
        pdf.set_text_color(6, 78, 59)
        pdf.set_font(font_family, "B", 11)
        pdf.cell(190, 8, "동행자 준비물 체크리스트 & 정산 메모", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font_family, "", 9.5)
        pdf.set_text_color(30, 41, 59)
        for chk in checklist:
            if isinstance(chk, dict):
                mark = "[완료]" if chk.get("done") else "[준비]"
                pdf.multi_cell(190, 5.2, f"  {mark} {_strip_emoji_for_pdf(chk.get('item', ''))}", new_x="LMARGIN", new_y="NEXT")
        if dutch_summary:
            pdf.multi_cell(190, 6, _strip_emoji_for_pdf(dutch_summary), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def export_itinerary_html_bytes(
    trip_item: Dict[str, Any],
    structured_plan: Dict[str, Any],
    checklist: List[Dict[str, Any]] | None = None,
) -> bytes:
    """친구·연인·가족에게 카카오톡이나 파일로 바로 보내서 지도+일정+예약링크+인쇄를 한 번에 열 수 있는 독립형 올인원 웹 가이드북(.html) 생성"""
    if "structured_plan" in structured_plan and isinstance(structured_plan["structured_plan"], dict):
        structured_plan = structured_plan["structured_plan"]

    dest_name = trip_item.get("name", "여행지")
    country = trip_item.get("country", "")
    season = trip_item.get("best_season", "")
    budget = trip_item.get("budget_level", "")
    applied_style = structured_plan.get("applied_style", "맞춤형 여행 코스")
    care_note = clean_ai_artifacts(structured_plan.get("dietary_care_note", ""))
    city_links = structured_plan.get("city_links") or make_booking_links(dest_name, country)
    center_lat = structured_plan.get("center_lat") or 35.6762
    center_lng = structured_plan.get("center_lng") or 139.6503

    stops_js = []
    days_html = []
    palette = {1: "#059669", 2: "#0284C7", 3: "#7C3AED"}

    for d_obj in structured_plan.get("days", []):
        d_num = int(d_obj.get("day", 1))
        color = palette.get(d_num, "#059669")
        cards_html = []
        for idx, item in enumerate(d_obj.get("schedule", []), start=1):
            place = item.get("place", dest_name)
            t_slot = item.get("time_slot", "")
            act = item.get("activity", "")
            tip = item.get("tip", "")
            trans = item.get("transport", "도보/대중교통")
            gmap = item.get("google_maps_url") or make_google_maps_url(place, dest_name, country)
            food = item.get("food_url") or make_google_maps_url(f"{place} 맛집", dest_name, country)
            klook = item.get("klook_url") or f"https://www.klook.com/ko/search/result/?query={urllib.parse.quote(place)}"
            lat = item.get("lat")
            lng = item.get("lng")
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)) and (abs(lat) > 0.01 or abs(lng) > 0.01):
                stops_js.append({"day": d_num, "label": f"{d_num}-{idx}", "name": place, "time": t_slot, "lat": float(lat), "lng": float(lng), "color": color, "url": gmap})

            cards_html.append(f"""
            <div class="spot-card" style="border-left: 4px solid {color};">
                <div class="spot-top">
                    <span class="spot-title">{idx}. {place}</span>
                    <span class="spot-badge">⏰ {t_slot} · 🚇 {trans}</span>
                </div>
                <p class="spot-act">{act}</p>
                {f'<div class="spot-tip">💡 <b>토리의 꿀팁</b>: {tip}</div>' if tip else ''}
                <div class="spot-links">
                    <a href="{gmap}" target="_blank">📍 구글 지도</a>
                    <a href="{food}" target="_blank">🍽️ 주변 맛집</a>
                    <a href="{klook}" target="_blank">🎟️ 티켓·투어</a>
                </div>
            </div>
            """)

        days_html.append(f"""
        <section class="day-section">
            <h2 style="color:{color};">📅 Day {d_num} · {d_obj.get('theme_title', '')} <small style="font-size:13px;color:#47695B;">(추천 숙소 거점: {d_obj.get('stay_area', dest_name)})</small></h2>
            {''.join(cards_html)}
        </section>
        """)

    care_banner = f'<div class="care-box">🛡️ <b>맞춤 알러지·배려 반영 완료</b>: {care_note}</div>' if care_note else ""

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>TripPilot | [{country}] {dest_name} 여행 가이드북</title>
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
    @font-face {{
        font-family: 'Yidstreet';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetB.woff2') format('woff2');
        font-weight: 700;
        font-display: swap;
    }}
    @font-face {{
        font-family: 'Yidstreet';
        src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2110@1.0/YdestreetL.woff2') format('woff2');
        font-weight: 300;
        font-display: swap;
    }}
    * {{ box-sizing: border-box; font-family: 'Yidstreet', 'Pretendard', sans-serif; }}
    body {{ margin: 0; padding: 24px; background: #F4FBF7; color: #0F291E; max-width: 980px; margin-inline: auto; }}
    .top-bar {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }}
    .print-btn {{ background: #059669; color: #FFF; border: none; padding: 10px 18px; border-radius: 999px; font-weight: 800; cursor: pointer; font-size: 13px; }}
    .hero {{ background: linear-gradient(135deg, #FFFFFF, #ECFDF5); border: 1px solid #A7F3D0; border-radius: 24px; padding: 24px; margin-bottom: 18px; box-shadow: 0 10px 28px rgba(5,150,105,0.08); }}
    .hero h1 {{ margin: 0 0 8px 0; color: #064E3B; font-size: 26px; }}
    .meta-tags span {{ display: inline-block; background: #FFF; border: 1px solid #6EE7B7; color: #047857; padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; margin-right: 6px; margin-top: 6px; }}
    .care-box {{ background: #FEF3C7; border: 1px solid #F59E0B; color: #92400E; padding: 12px 16px; border-radius: 14px; margin-bottom: 16px; font-size: 13.5px; }}
    #map {{ width: 100%; height: 340px; border-radius: 18px; border: 1px solid #A7F3D0; margin-bottom: 20px; }}
    .spot-card {{ background: #FFF; border: 1px solid #D1FAE5; border-radius: 16px; padding: 14px 18px; margin-bottom: 12px; }}
    .spot-top {{ display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 6px; }}
    .spot-title {{ font-weight: 800; font-size: 16px; color: #064E3B; }}
    .spot-badge {{ background: #ECFDF5; color: #047857; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; }}
    .spot-act {{ margin: 6px 0; font-size: 13.5px; line-height: 1.55; color: #1E3A2F; }}
    .spot-tip {{ background: #F0FDF4; padding: 7px 11px; border-radius: 10px; font-size: 12px; color: #065F46; margin-bottom: 8px; }}
    .spot-links a, .quick-links a {{ display: inline-block; background: #FFF; border: 1px solid #10B981; color: #047857; padding: 4px 11px; border-radius: 999px; font-size: 11.5px; font-weight: 700; text-decoration: none; margin-right: 6px; margin-top: 4px; }}
    @media print {{ .no-print {{ display: none !important; }} body {{ background: #FFF; padding: 0; }} }}
</style>
</head>
<body>
    <div class="top-bar no-print">
        <div style="font-weight:800;color:#059669;">🐣 TripPilot 올인원 공유 가이드북 (친구·연인·가족 공유용)</div>
        <button class="print-btn" onclick="window.print()">🖨️ 지금 화면 PDF 저장 / 인쇄하기</button>
    </div>
    <div class="hero">
        <h1>✈️ [{country}] {dest_name} 맞춤 여행 계획표</h1>
        <p style="margin:4px 0 10px 0;color:#2C5243;font-size:14px;">반영된 여행 스타일: <b>{applied_style}</b></p>
        <div class="meta-tags">
            <span>🗓️ 추천 시기: {season}</span>
            <span>💰 예상 경비: {budget}</span>
        </div>
        <div class="quick-links no-print" style="margin-top:12px;">
            <a href="{city_links['google_maps']}" target="_blank">📍 {dest_name} 구글 지도</a>
            <a href="{city_links['agoda']}" target="_blank">🏨 아고다 숙소 최저가</a>
            <a href="{city_links['booking']}" target="_blank">🏨 부킹닷컴</a>
            <a href="{city_links['airbnb']}" target="_blank">🏠 에어비앤비</a>
            <a href="{city_links['skyscanner']}" target="_blank">✈️ 스카이스캐너 항공권</a>
            <a href="{city_links['klook']}" target="_blank">🎟️ 클룩 투어·패스</a>
        </div>
    </div>
    {care_banner}
    <div id="map"></div>
    {''.join(days_html)}
    <script>
        var stops = {json.dumps(stops_js, ensure_ascii=False)};
        var map = L.map('map').setView([{center_lat}, {center_lng}], 12);
        L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&hl=ko', {{ maxZoom: 20 }}).addTo(map);
        var coords = [];
        stops.forEach(function(s) {{
            coords.push([s.lat, s.lng]);
            L.circleMarker([s.lat, s.lng], {{ radius: 9, fillColor: s.color, color: '#FFF', weight: 2, fillOpacity: 0.95 }})
             .addTo(map).bindPopup('<b>[' + s.label + '] ' + s.name + '</b><br/>' + s.time);
        }});
        if (coords.length > 1) {{
            L.polyline(coords, {{ color: '#059669', weight: 3, dashArray: '6, 6' }}).addTo(map);
            map.fitBounds(coords, {{ padding: [35, 35] }});
        }}
    </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


# ── 6. 도메인 특화 기능 2 — 여행지 정보 팩트체크 (사실 여부 판정, 2-Stage RAG 적용) ──
def verify_travel_claim(trip_id: str, dest_name: str, claim: str, top_k: int = 3) -> Dict[str, Any]:
    """사용자가 입력한 여행지 관련 주장(기후/건기, 랜드마크 역사, 위치, 특징 등)을 1차·2차 다단계 검색 문서 근거로 사실 여부 판정"""
    state_pass1: RAGState = {
        "trip_id": str(trip_id),
        "dest_name": dest_name,
        "question": claim,
        "top_k": top_k,
        "search_type": "similarity",
        "expanded_queries": [],
        "context_docs": [],
        "answer": "",
        "cited_sources": [],
    }
    pass1_out = retrieve_node(state_pass1)
    state_pass1["context_docs"] = pass1_out["context_docs"]
    pass2_out = deep_retrieve_node(state_pass1)
    context_docs = pass2_out["context_docs"]
    context_text = "\n".join(
        f"[근거 {i}] ({d.get('rag_stage', '1차 RAG')} | {d['source_type']}: {d['title']})\n{d['content']}"
        for i, d in enumerate(context_docs, start=1)
    )

    prompt = f"""당신은 글로벌 여행 정보 및 지리·역사 팩트체크 가이드 '파일럿 토리 🐣'입니다.
오직 아래 [참조 문서]의 내용만을 바탕으로 사용자의 주장을 검증하십시오.

[출력 형식]
- **판정**: `사실` / `문서 내용과 다름` / `문서에서 확인되지 않음` 중 하나를 첫 줄에 명시
- **상세 설명**: 문서의 구체적인 지리·역사·시즌·예산 정보를 인용하여 `[근거 N]`과 함께 친절하게 서술 (문서에 없으면 확인되지 않는다고만 답할 것)

[검증 대상 여행지]: {dest_name}
[검증할 내용]: {claim}

[참조 문서]
{context_text}
"""
    answer = llm.invoke([HumanMessage(content=prompt)]).content.strip()
    cited_sources = extract_cited_sources(answer, context_docs)
    return {
        "answer": strip_citations(answer),
        "cited_sources": cited_sources,
        "all_contexts": context_docs,
    }


# ── 7. 자연어 조건 기반 여행지 탐색 ──
def search_destinations_by_condition(condition_query: str, candidate_k: int = 15) -> List[Dict[str, Any]]:
    """사용자의 자연어 조건(예: '예산 100만원 이하 휴양지')으로 travel_meta 컬렉션에서 후보를 검색한 뒤,
    LLM이 실제 조건에 부합하는 여행지만 엄격히 선별하여 반환한다."""
    meta_store = Chroma(
        collection_name=META_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )
    candidates = meta_store.similarity_search(query=condition_query, k=candidate_k)
    if not candidates:
        return []

    cand_list = []
    for doc in candidates:
        cand_list.append({
            "trip_id": doc.metadata.get("trip_id"),
            "name": doc.metadata.get("name"),
            "country": doc.metadata.get("country"),
            "continent": doc.metadata.get("continent"),
            "theme": doc.metadata.get("theme"),
            "budget_level": doc.metadata.get("budget_level"),
            "best_season": doc.metadata.get("best_season"),
            "spec_text": doc.page_content,
        })

    system_msg = SystemMessage(
        content=(
            "너는 글로벌 여행지 조건 검색 필터링 엔진이다. "
            "사용자의 자연어 여행 조건(예산 수준, 대륙/국가, 여행 테마, 계절/시기 등)과 후보 여행지 목록(spec_text 포함)을 비교하여, "
            "사용자의 조건에 정확히 부합하는 여행지만 선별하라. 조건과 맞지 않는 여행지는 절대 포함하지 마라. "
            "출력은 반드시 JSON 배열 형식으로만 반환하며, 각 원소는 "
            "{\"trip_id\": \"여행지ID\", \"reason\": \"조건 부합 이유 한 줄 요약\"} 형태여야 한다."
        )
    )
    user_msg = HumanMessage(
        content=f"사용자 검색 조건: {condition_query}\n\n후보 여행지 목록:\n{json.dumps(cand_list, ensure_ascii=False)}"
    )

    try:
        res_text = llm.invoke([system_msg, user_msg]).content.strip()
        if "```" in res_text:
            res_text = re.sub(r"```(?:json)?", "", res_text).replace("```", "").strip()
        selected = json.loads(res_text)
        reason_map = {str(item["trip_id"]): item.get("reason", "조건 일치") for item in selected if "trip_id" in item}
        matched = []
        for c in cand_list:
            if str(c["trip_id"]) in reason_map:
                c["match_reason"] = reason_map[str(c["trip_id"])]
                matched.append(c)
        return matched
    except Exception:
        return cand_list[:5]


# ── 8. 올인원 스마트 여행 확장 기능 (캘린더 ics, 서바이벌 소통 카드, 환율·물가, 여행지 비교, 월별 옷차림) ──

def export_itinerary_ics_bytes(
    trip_item: Dict[str, Any],
    structured_plan: Dict[str, Any],
    start_date_str: str = "2026-11-01",
) -> bytes:
    """스마트폰(구글·애플·아웃룩) 캘린더에 원클릭 등록할 수 있는 표준 iCalendar(.ics) 파일 바이트 생성"""
    if "structured_plan" in structured_plan and isinstance(structured_plan["structured_plan"], dict):
        structured_plan = structured_plan["structured_plan"]

    dest_name = trip_item.get("name", "여행지")
    country = trip_item.get("country", "")

    from datetime import datetime, timedelta

    try:
        base_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    except Exception:
        base_date = datetime.now() + timedelta(days=14)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TripPilot AI//Travel Copilot//KO",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:TripPilot | {dest_name} 여행 일정",
        "X-WR-TIMEZONE:Asia/Seoul",
    ]

    slot_hours = {
        "09:00": (9, 10, 30),
        "10:00": (10, 12, 0),
        "11:00": (11, 12, 30),
        "12:00": (12, 13, 30),
        "13:00": (13, 14, 30),
        "14:00": (14, 16, 0),
        "15:00": (15, 17, 0),
        "16:00": (16, 17, 30),
        "18:00": (18, 19, 30),
        "19:00": (19, 21, 0),
        "20:00": (20, 21, 30),
    }

    now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for day_obj in structured_plan.get("days", []):
        day_num = int(day_obj.get("day", 1))
        target_day = base_date + timedelta(days=day_num - 1)
        theme_title = day_obj.get("theme_title", f"{day_num}일차")

        for idx, item in enumerate(day_obj.get("schedule", []), start=1):
            place = str(item.get("place", dest_name))
            time_slot = str(item.get("time_slot", "10:00"))
            activity = str(item.get("activity", ""))
            tip = str(item.get("tip", ""))
            trans = str(item.get("transport", "도보/대중교통"))
            gmap = item.get("google_maps_url") or make_google_maps_url(place, dest_name, country)

            hour = 10 + (idx - 1) * 2
            minute = 0
            dur_min = 90
            for k, (sh, eh, sm) in slot_hours.items():
                if k in time_slot:
                    hour = sh
                    minute = sm if sm < 60 else 0
                    dur_min = (eh - sh) * 60 + (sm if sm < 60 else 0)
                    break

            start_dt = target_day.replace(hour=min(hour, 23), minute=minute, second=0)
            end_dt = start_dt + timedelta(minutes=dur_min)

            s_str = start_dt.strftime("%Y%m%dT%H%M%S")
            e_str = end_dt.strftime("%Y%m%dT%H%M%S")
            uid = f"trippilot-{dest_name}-d{day_num}-{idx}-{start_dt.strftime('%Y%m%d')}@trippilot.ai"

            desc_parts = [
                f"[{day_num}일차: {theme_title}]",
                f"활동: {activity}",
                f"이동: {trans}",
            ]
            if tip:
                desc_parts.append(f"토리의 꿀팁: {tip}")
            desc_parts.append(f"구글 지도: {gmap}")
            clean_desc = "\\n".join(desc_parts).replace(",", "\\,").replace(";", "\\;")

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART:{s_str}",
                f"DTEND:{e_str}",
                f"SUMMARY:[TripPilot] {day_num}일차 {idx}. {place}",
                f"DESCRIPTION:{clean_desc}",
                f"LOCATION:{place}\\, {dest_name}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")


# 국가별 언어 및 통화 데이터
COUNTRY_LANG_CURRENCY = {
    "일본": {
        "lang": "일본어",
        "code": "ja",
        "currency": "엔 (JPY)",
        "symbol": "¥",
        "krw_rate": 9.2,
        "sample_amt": 1000,
        "coffee": "약 400～550엔 (3,700～5,000원)",
        "meal": "약 900～1,500엔 (8,300～13,800원)",
        "taxi": "약 500～600엔부터 (4,600원～)",
        "water": "약 110～130엔 (1,000～1,200원)",
    },
    "대한민국": {
        "lang": "한국어",
        "code": "ko",
        "currency": "원 (KRW)",
        "symbol": "₩",
        "krw_rate": 1.0,
        "sample_amt": 10000,
        "coffee": "약 4,500～6,000원",
        "meal": "약 9,000～15,000원",
        "taxi": "기본 4,800원부터",
        "water": "약 1,000원",
    },
    "미국": {
        "lang": "영어",
        "code": "en",
        "currency": "달러 (USD)",
        "symbol": "$",
        "krw_rate": 1380.0,
        "sample_amt": 10,
        "coffee": "약 $5～7 (6,900～9,700원)",
        "meal": "약 $18～35 (25,000～48,000원, 팁 별도)",
        "taxi": "Uber 기본 $10～15 (14,000원～)",
        "water": "약 $2～3 (2,800～4,100원)",
    },
    "영국": {
        "lang": "영어",
        "code": "en",
        "currency": "파운드 (GBP)",
        "symbol": "£",
        "krw_rate": 1780.0,
        "sample_amt": 10,
        "coffee": "약 £3.5～5 (6,200～8,900원)",
        "meal": "약 £15～28 (26,700～49,800원)",
        "taxi": "블랙캡 기본 £3.8부터",
        "water": "약 £1.5 (2,700원)",
    },
    "프랑스": {
        "lang": "프랑스어",
        "code": "fr",
        "currency": "유로 (EUR)",
        "symbol": "€",
        "krw_rate": 1500.0,
        "sample_amt": 10,
        "coffee": "약 €2.5～4.5 (3,750～6,750원)",
        "meal": "약 €16～30 (24,000～45,000원)",
        "taxi": "기본 €7.5부터",
        "water": "약 €1.5～2.5 (2,250～3,750원)",
    },
    "이탈리아": {
        "lang": "이탈리아어",
        "code": "it",
        "currency": "유로 (EUR)",
        "symbol": "€",
        "krw_rate": 1500.0,
        "sample_amt": 10,
        "coffee": "에스프레소 약 €1.2～2.5 (1,800～3,750원)",
        "meal": "약 €14～26 (21,000～39,000원)",
        "taxi": "기본 €5부터",
        "water": "약 €1～2 (1,500～3,000원)",
    },
    "스페인": {
        "lang": "스페인어",
        "code": "es",
        "currency": "유로 (EUR)",
        "symbol": "€",
        "krw_rate": 1500.0,
        "sample_amt": 10,
        "coffee": "카페 콘 레체 약 €1.5～2.5 (2,250～3,750원)",
        "meal": "타파스/메누 델 디아 약 €12～22 (18,000～33,000원)",
        "taxi": "기본 €4.5부터",
        "water": "약 €1～1.8 (1,500～2,700원)",
    },
    "독일": {
        "lang": "독일어",
        "code": "de",
        "currency": "유로 (EUR)",
        "symbol": "€",
        "krw_rate": 1500.0,
        "sample_amt": 10,
        "coffee": "약 €3～4.5 (4,500～6,750원)",
        "meal": "약 €14～25 (21,000～37,500원)",
        "taxi": "기본 €4.5부터",
        "water": "약 €1.5～2 (2,250～3,000원)",
    },
    "스위스": {
        "lang": "독일어/프랑스어",
        "code": "de",
        "currency": "스위스 프랑 (CHF)",
        "symbol": "CHF",
        "krw_rate": 1580.0,
        "sample_amt": 10,
        "coffee": "약 CHF 5～7 (7,900～11,000원)",
        "meal": "약 CHF 25～45 (39,500～71,000원)",
        "taxi": "기본 CHF 7부터",
        "water": "약 CHF 3～4 (4,700～6,300원)",
    },
    "태국": {
        "lang": "태국어",
        "code": "th",
        "currency": "바트 (THB)",
        "symbol": "฿",
        "krw_rate": 38.0,
        "sample_amt": 100,
        "coffee": "약 50～90바트 (1,900～3,400원)",
        "meal": "로컬 60～120바트 (2,300～4,500원)",
        "taxi": "볼트/그랩 기본 40～50바트 (1,500원～)",
        "water": "약 10～15바트 (400～600원)",
    },
    "베트남": {
        "lang": "베트남어",
        "code": "vi",
        "currency": "동 (VND)",
        "symbol": "₫",
        "krw_rate": 0.055,
        "sample_amt": 100000,
        "coffee": "약 30,000～55,000동 (1,650～3,000원)",
        "meal": "쌀국수 약 45,000～80,000동 (2,500～4,400원)",
        "taxi": "그랩 기본 15,000동부터",
        "water": "약 10,000동 (550원)",
    },
    "대만": {
        "lang": "중국어(번체)",
        "code": "zh-tw",
        "currency": "대만 달러 (TWD)",
        "symbol": "NT$",
        "krw_rate": 43.0,
        "sample_amt": 100,
        "coffee": "약 60～90 TWD (2,600～3,900원)",
        "meal": "야시장/우육면 90～180 TWD (3,900～7,700원)",
        "taxi": "기본 85 TWD부터 (3,650원～)",
        "water": "약 20 TWD (860원)",
    },
    "싱가포르": {
        "lang": "영어",
        "code": "en",
        "currency": "싱가포르 달러 (SGD)",
        "symbol": "S$",
        "krw_rate": 1050.0,
        "sample_amt": 10,
        "coffee": "약 S$4～7 (4,200～7,350원)",
        "meal": "호커센터 S$6～10 / 레스토랑 S$20～40",
        "taxi": "그랩 기본 S$4.5부터",
        "water": "약 S$1.5～2 (1,500～2,100원)",
    },
}


def get_currency_and_cost_info(country: str) -> Dict[str, Any]:
    """국가별 통화, 실시간 체감 환율 및 대표 생활 물가 지표 반환"""
    for c_key, data in COUNTRY_LANG_CURRENCY.items():
        if c_key in country or country in c_key:
            return data
    # 기본값: 미국 달러 기준
    return COUNTRY_LANG_CURRENCY["미국"]


def generate_survival_cards(
    dest_name: str,
    country: str,
    spots: List[str] | None = None,
    active_constraints: List[str] | None = None,
) -> Dict[str, Any]:
    """현지 식당/택시/돌발 상황에서 스마트폰 화면만 보여주면 통하는 현지어 서바이벌 소통 카드 생성"""
    c_info = get_currency_and_cost_info(country)
    lang_code = c_info["code"]
    spots = spots or [dest_name]

    allergy_dict = {
        "생선": {
            "title": "생선·해산물 알러지 카드",
            "icon": "🚫🐟",
            "korean": "저는 생선 및 해산물에 심각한 알러지가 있습니다. 육수, 소스, 다시에도 해산물이 전혀 들어가지 않게 부탁드립니다.",
            "ja": ("私は魚・魚介類に重度のアレルギーがあります。\nダシやソース、スープにも魚介類を一切入れないようにお願いします。", "와타시와 사카나·교카이루이니 쥬-도노 아레루기-가 아리마스. 다시야 소-스, 스-푸니모 교카이루이오 잇사이 이레나이요-니 오네가이시마스."),
            "en": ("I have a severe fish and seafood allergy.\nPlease ensure NO seafood, fish broth, or oyster sauce is used.", "아이 해브 어 시비어 피시 앤드 씨푸드 알러지. 플리즈 인슈어 노 씨푸드, 피시 브로스, 오어 오이스터 소스 이즈 유즈드."),
            "fr": ("J'ai une allergie sévère aux poissons et fruits de mer.\nVeuillez n'utiliser aucun poisson, ni bouillon ni sauce de poisson.", "제 윈 알레르지 세베르 오 푸아송 에 프뤼 드 메르."),
            "it": ("Ho una grave allergia al pesce e ai frutti di mare.\nPer favore niente pesce, brodo di pesce o salse di pesce.", "오 우나 그라베 알레르지아 알 페셰 에 아이 프루티 디 마레."),
            "es": ("Tengo una alergia grave al pescado y mariscos.\nPor favor, nada de pescado, caldo ni salsas de marisco.", "텡고 우나 알레르히아 그라베 알 페스카도 이 마리스코스."),
            "th": ("ฉันแพ้ปลาและอาหารทะเลอย่างรุนแรง\nกรุณาอย่าใส่น้ำปลา น้ำสต๊อก หรือส่วนผสมจากอาหารทะเลครับ/ค่ะ", "찬 패 쁠라 래 아한탈레 양 룬랭. 까루나 야 싸이 남쁠라 캅/카."),
            "vi": ("Tôi bị dị ứng nghiêm trọng với cá và hải sản.\nXin vui lòng không dùng nước mắm hoặc nguyên liệu từ hải sản.", "또이 비 지 응 응이엠 쫑 버이 까 바 하이 산."),
            "zh-tw": ("我對魚類和海鮮有嚴重的過敏症。\n請不要在湯底或醬汁中使用任何魚類或海鮮成分。", "워 뛔이 위레이 한 하이시엔 요우 옌중더 궈민정."),
        },
        "갑각류": {
            "title": "갑각류(새우·게) 알러지 카드",
            "icon": "🚫🦐",
            "korean": "저는 새우, 게, 랍스터 등 갑각류 알러지가 있습니다. 교차 오염에 주의해 주세요.",
            "ja": ("エビ、カニなどの甲殻類アレルギーがあります。\nエビエキスや揚げ油の共有も避けてください。", "에비, 카니나도노 코-카쿠루이 아레루기-가 아리마스. 에비에키스야 아게아부라노 쿄-유-모 사케테 쿠다사이."),
            "en": ("I am allergic to crustacean shellfish (shrimp, crab, lobster).\nPlease be careful with cross-contamination.", "아이 앰 얼러직 투 크러스테이션 쉘피시 (쉬림프, 크랩, 랍스터)."),
            "fr": ("Je suis allergique aux crustacés (crevettes, crabes).", "주 쉬 알레르지크 오 크뤼스타세."),
            "it": ("Sono allergico ai crostacei (gamberi, granchi).", "소노 알레르지코 아이 크로스타체이."),
            "es": ("Soy alérgico a los crustáceos (gambas, cangrejos).", "소이 알레르히코 아 로스 크루스타세오스."),
            "th": ("ฉันแพ้กุ้งและปู กรุณาอย่าใส่กุ้งหรือกะปิ", "찬 패 꿍 래 뿌. 까루나 야 싸이 꿍 르 까삐."),
            "vi": ("Tôi bị dị ứng với tôm và cua.", "또이 비 지 응 버이 똠 바 꾸아."),
            "zh-tw": ("我對蝦、蟹等甲殼類過敏，請避免交叉污染。", "워 뛔이 샤, 시에 덩 지아커레이 궈민."),
        },
        "견과류": {
            "title": "견과류·땅콩 알러지 카드",
            "icon": "🚫🥜",
            "korean": "저는 땅콩 및 견과류에 치명적인 알러지가 있습니다. 견과류 기름이나 가루도 절대 안 됩니다.",
            "ja": ("ピーナッツおよびナッツ類に命に関わるアレルギーがあります。\nナッツ油や粉末も一切入れないでください。", "피-낫츠 오요비 낫츠루이니 이노치니 카카와루 아레루기-가 아리마스."),
            "en": ("I have a severe, life-threatening nut & peanut allergy.\nNo peanut oil, nuts, or crushed toppings please.", "아이 해브 어 시비어, 라이프-스렛닝 넛 앤드 피넛 알러지."),
            "fr": ("J'ai une allergie mortelle aux arachides et aux fruits à coque.", "제 윈 알레르지 모르텔 오즈 아라시드."),
            "it": ("Ho una grave allergia ad arachidi e frutta a guscio.", "오 우나 그라베 알레르지아 아드 아라키디."),
            "es": ("Tengo una alergia mortal a los cacahuetes y frutos secos.", "텡고 우나 알레르히아 모르탈 아 로스 카카우에테스."),
            "th": ("ฉันแพ้ถั่วลิสงและถั่วทุกชนิดอย่างรุนแรง", "찬 패 투아리쏭 래 투아 툭 차닛 양 룬랭."),
            "vi": ("Tôi bị dị ứng nghiêm trọng với đậu phộng và các loại hạt.", "또이 비 지 응 응이엠 쫑 버이 더우 퐁."),
            "zh-tw": ("我對花生和堅果有嚴重的致命性過敏，請勿使用堅果油或堅果粉。", "워 뛔이 화셩 한 지엔궈 요우 옌중더 쥐밍싱 궈민."),
        },
        "비건": {
            "title": "비건·채식 식단 카드",
            "icon": "🥗🌿",
            "korean": "저는 완전 채식(비건)을 합니다. 고기, 생선, 달걀, 우유, 꿀이 들어가지 않은 음식으로 부탁드립니다.",
            "ja": ("ヴィーガン（完全菜食）です。\n肉、魚、卵、乳製品、ハチミツ不使用の料理をお願いします。", "비-간(칸젠 사이쇼쿠)데스. 니쿠, 사카나, 타마고, 뉴-세이힌 후시요-노 료-리오 오네가이시마스."),
            "en": ("I am vegan. No meat, poultry, seafood, eggs, dairy, or honey please.", "아이 앰 비건. 노 미트, 폴트리, 씨푸드, 에그스, 데어리, 오어 허니 플리즈."),
            "fr": ("Je suis végétalien (végan). Aucun produit d'origine animale.", "주 쉬 베제탈리앙 (베간)."),
            "it": ("Sono vegano. Nessun prodotto di origine animale.", "소노 베가노. 네쑨 프로도토 디 오리지네 아니말레."),
            "es": ("Soy vegano. Nada de carne, pescado, lácteos ni huevos.", "소이 베가노. 나다 데 카르네, 페스카도, 락테오스 니 후에보스."),
            "th": ("ฉันทานเจ/วีแกน ไม่ทานเนื้อสัตว์ ไข่ นม หรือน้ำผึ้ง", "찬 탄 제/위깬. 마이 탄 느아 쌋, 카이, 놈 르 남픙."),
            "vi": ("Tôi ăn chay trường (thuần chay). Không thịt, cá, trứng, sữa.", "또이 안 짜이 쯔엉. 콩 팃, 까, 쯩, 쓰어."),
            "zh-tw": ("我是純素主義者（Vegan），請勿提供任何肉類、海鮮、蛋奶或蜂蜜。", "워 쉬 춘쑤주이저."),
        },
    }

    # 활성 알러지 필터링
    allergies_output = []
    active_constraints = active_constraints or []
    joined_c = " ".join(active_constraints)

    for k, card_data in allergy_dict.items():
        if k in joined_c or not active_constraints:
            trans_tuple = card_data.get(lang_code, card_data.get("en", card_data["ja"]))
            allergies_output.append({
                "title": card_data["title"],
                "icon": card_data["icon"],
                "korean": card_data["korean"],
                "foreign": trans_tuple[0],
                "pronounce": trans_tuple[1],
            })

    # 택시 / 이동 카드
    taxi_phrases = {
        "ja": ("運転手さん、{place}までお願いします。\n到着したら教えてください。領収書もいただけますか？", "운텐슈상, {place}마데 오네가이시마스. 토-챠쿠시타라 오시에테 쿠다사이. 료-슈-쇼모 이타다케마스카?"),
        "en": ("Driver, please take me to {place}.\nPlease let me know when we arrive, and may I have a receipt?", "드라이버, 플리즈 테이크 미 투 {place}. 플리즈 렛 미 노우 웬 위 어라이브, 앤드 메이 아이 해브 어 리시트?"),
        "fr": ("Chauffeur, emmenez-moi à {place}, s'il vous plaît.\nPuis-je avoir un reçu ?", "쇼푀르, 앙므네 무아 아 {place}, 실 부 플레. 퓌-즈 아부아 앙 르쉬?"),
        "it": ("Autista, mi porti a {place}, per favore.\nPosso avere una ricevuta?", "아우티스타, 미 포르티 아 {place}, 페르 파보레. 포쏘 아베레 우나 리체부타?"),
        "es": ("Conductor, lléveme a {place}, por favor.\n¿Me puede dar un recibo?", "콘둑토르, 예베메 아 {place}, 포르 파보르. 메 푸에데 다르 운 레시보?"),
        "th": ("คนขับครับ/ค่ะ ช่วยไปส่งที่ {place} หน่อยครับ/ค่ะ\nกรุณาเปิดมิเตอร์ด้วยครับ/ค่ะ", "콘 캅 캅/카, 추어이 빠이 쏭 티 {place} 너이 캅/카. 까루나 뻗 미떠 두어이 캅/카."),
        "vi": ("Bác tài ơi, làm ơn chở tôi đến {place}.\nBật đồng hồ tính cước giúp tôi nhé.", "박 따이 어이, 람 언 쩌 또이 덴 {place}. 밧 동 호 띤 꾸억 줍 또이 네."),
        "zh-tw": ("司機先生，請帶我到 {place}，謝謝。\n請開計價器並給我發票。", "쓰지 시엔셩, 칭 따이 워 따오 {place}, 시에시에. 칭 카이 지지아치 빙 게이 워 파퍄오."),
    }

    t_tpl = taxi_phrases.get(lang_code, taxi_phrases["en"])
    taxi_cards = []
    for sp in spots[:4]:
        taxi_cards.append({
            "place": sp,
            "foreign": t_tpl[0].format(place=sp),
            "pronounce": t_tpl[1].format(place=sp),
        })

    # 필수 긴급 SOS 회화
    sos_dict = {
        "ja": [
            ("화장실이 어디인가요?", "トイレはどこですか？", "토이레와 도코데스카?"),
            ("영어 메뉴판이 있나요?", "英語のメニューはありますか？", "에이고노 메뉴-와 아리마스카?"),
            ("계산서 부탁드립니다.", "お会計をお願いします。", "오카이케-오 오네가이시마스."),
            ("사진 한 장 찍어주실 수 있나요?", "写真を一枚撮っていただけますか？", "샤신오 이치마이 톳테 이타다케마스카?"),
            ("도와주세요! 긴급 상황입니다.", "助けてください！緊急です。", "타스케테 쿠다사이! 킨큐-데스."),
        ],
        "en": [
            ("화장실이 어디인가요?", "Where is the restroom?", "웨어 이즈 더 레스트룸?"),
            ("영어 메뉴판이 있나요?", "Do you have an English menu?", "두 유 해브 언 잉글리시 메뉴?"),
            ("계산서 부탁드립니다.", "Could we have the check, please?", "쿠드 위 해브 더 체크, 플리즈?"),
            ("사진 한 장 찍어주실 수 있나요?", "Could you take a picture for us?", "쿠드 유 테이크 어 픽처 포 어스?"),
            ("도와주세요! 긴급 상황입니다.", "Please help me! It's an emergency.", "플리즈 헬프 미! 잇츠 언 이머전시."),
        ],
        "fr": [
            ("화장실이 어디인가요?", "Où sont les toilettes ?", "우 송 레 투알렛?"),
            ("계산서 부탁드립니다.", "L'addition, s'il vous plaît.", "라디시옹, 실 부 플레."),
            ("도와주세요!", "Aidez-moi, s'il vous plaît !", "에데 무아, 실 부 플레!"),
        ],
        "th": [
            ("화장실이 어디인가요?", "ห้องน้ำอยู่ที่ไหนครับ/ค่ะ?", "헝남 유 티나이 캅/카?"),
            ("계산서 부탁드립니다.", "เช็คบิลด้วยครับ/ค่ะ", "첵빈 두어이 캅/카"),
            ("도와주세요!", "ช่วยด้วยครับ/ค่ะ!", "추어이 두어이 캅/카!"),
        ],
    }

    return {
        "dest_name": dest_name,
        "country": country,
        "language_name": c_info["lang"],
        "allergy_cards": allergies_output,
        "taxi_cards": taxi_cards,
        "sos_phrases": sos_dict.get(lang_code, sos_dict["en"]),
    }


def compare_destinations(trip_a: Dict[str, Any], trip_b: Dict[str, Any]) -> Dict[str, Any]:
    """두 여행지를 1:1로 맞비교하여 예산, 추천 시기, 비행/물가, 취향별 강점을 요약"""
    name_a = trip_a.get("name", "여행지 A")
    name_b = trip_b.get("name", "여행지 B")
    country_a = trip_a.get("country", "")
    country_b = trip_b.get("country", "")

    cost_a = get_currency_and_cost_info(country_a)
    cost_b = get_currency_and_cost_info(country_b)

    return {
        "trip_a": {
            "name": name_a,
            "country": country_a,
            "continent": trip_a.get("continent", ""),
            "theme": trip_a.get("theme", ""),
            "budget": trip_a.get("budget_level", ""),
            "season": trip_a.get("best_season", ""),
            "currency": cost_a["currency"],
            "meal_cost": cost_a["meal"],
            "summary": trip_a.get("summary", ""),
        },
        "trip_b": {
            "name": name_b,
            "country": country_b,
            "continent": trip_b.get("continent", ""),
            "theme": trip_b.get("theme", ""),
            "budget": trip_b.get("budget_level", ""),
            "season": trip_b.get("best_season", ""),
            "currency": cost_b["currency"],
            "meal_cost": cost_b["meal"],
            "summary": trip_b.get("summary", ""),
        },
        "comparison_points": [
            {
                "category": "💰 예상 여행 경비",
                "a": trip_a.get("budget_level", ""),
                "b": trip_b.get("budget_level", ""),
            },
            {
                "category": "🌤️ 최적 방문 시즌",
                "a": trip_a.get("best_season", ""),
                "b": trip_b.get("best_season", ""),
            },
            {
                "category": "🍽️ 한 끼 예상 식비",
                "a": cost_a["meal"],
                "b": cost_b["meal"],
            },
            {
                "category": "🎨 핵심 여행 무드",
                "a": trip_a.get("theme", ""),
                "b": trip_b.get("theme", ""),
            },
        ],
    }


def get_monthly_packing_and_weather(dest_name: str, country: str, month: int) -> Dict[str, Any]:
    """선택한 출발 월(1～12월)에 따른 여행지 계절 날씨, 옷차림 가이드 및 추천 추가 준비물"""
    # 북반구 / 남반구 / 열대 기후 구분
    is_tropical = any(c in country for c in ["태국", "베트남", "필리핀", "싱가포르", "말레이시아", "인도네시아", "하와이", "괌", "사이판", "몰디브"])
    is_southern = any(c in country for c in ["호주", "뉴질랜드", "칠레", "아르헨티나", "남아프리카"])

    if is_tropical:
        season_type = "우기 (스콜 주의)" if month in [6, 7, 8, 9, 10] else "건기 (화창·여행 최적)"
        temp_desc = "평균 28℃～34℃ 내외의 고온 다습한 열대 기후"
        clothes = "통풍이 잘되는 린넨/면 반팔 & 반바지, 실내 강한 에어컨 대비 얇은 바람막이나 가디건"
        checklist_extra = [
            "휴대용 3단 우산 또는 방수 우비",
            "방수팩 / 드라이백 (물놀이 및 스콜 대비)",
            "모기 기피제 및 버물리",
            "자외선 차단제 (SPF 50+) & 선글라스",
            "통풍 잘되는 샌들 또는 아쿠아슈즈",
        ]
    elif is_southern:
        if month in [12, 1, 2]:
            season_type = "여름 (야외 액티비티 성수기)"
            temp_desc = "평균 22℃～30℃의 따스한 여름 햇살"
            clothes = "가벼운 반팔, 모자, 선글라스, 저녁 바닷바람 대비 얇은 겉옷"
            checklist_extra = ["자외선 차단제", "수영복/래시가드", "선글라스", "보충 보조배터리"]
        elif month in [6, 7, 8]:
            season_type = "겨울 (온화한 쌀쌀함)"
            temp_desc = "평균 6℃～15℃의 서늘하고 쌀쌀한 날씨"
            clothes = "도톰한 니트, 경량 패딩, 머플러, 긴바지"
            checklist_extra = ["경량 패딩", "보온 내의", "따뜻한 양말", "보습 립밤"]
        else:
            season_type = "봄/가을 (쾌적한 온도)"
            temp_desc = "평균 14℃～22℃의 쾌적한 여행 날씨"
            clothes = "긴팔 티셔츠, 셔츠, 얇은 자켓 또는 가디건"
            checklist_extra = ["휴대용 우산", "편한 워킹화", "가벼운 외투"]
    else:
        # 일반 북반구 (한국, 일본, 유럽, 북미 등)
        if month in [12, 1, 2]:
            season_type = "겨울 (설경 & 크리스마스 시즌)"
            temp_desc = "평균 -5℃～8℃의 춥고 건조한 겨울 날씨 (설경 명소는 영하권)"
            clothes = "보온 패딩 또는 울 코트, 기모 이너웨어, 목도리, 장갑"
            checklist_extra = [
                "붙이는 핫팩 & 주머니 핫팩",
                "보온 내의(히트텍) 2～3벌",
                "방한 장갑 & 넥워머",
                "눈길 대비 미끄럼 방지 방한화/부츠",
                "고보습 핸드크림 및 립밤",
            ]
        elif month in [6, 7, 8]:
            season_type = "여름 (축제 & 바캉스 시즌)"
            temp_desc = "평균 24℃～32℃의 무덥고 햇살이 강한 여름"
            clothes = "시원한 반팔, 민소매, 반바지, 냉방용 얇은 셔츠"
            checklist_extra = [
                "미니 손선풍기 (손풍기)",
                "자외선 차단제 및 선글라스",
                "갑작스러운 소나기 대비 접이식 우산",
                "땀 닦는 쿨링 티슈",
            ]
        elif month in [3, 4, 5]:
            season_type = "봄 (벚꽃 & 신록 시즌)"
            temp_desc = "평균 10℃～20℃의 따사롭고 일교차 큰 환절기"
            clothes = "트렌치코트, 자켓, 니트, 레이어드 가능한 겉옷"
            checklist_extra = ["일교차 대비 겉옷/스카프", "꽃가루/황사 대비 마스크", "인공눈물", "편한 스니커즈"]
        else:
            season_type = "가을 (단풍 & 여행 최적기)"
            temp_desc = "평균 12℃～21℃의 청명하고 쾌적한 가을 하늘"
            clothes = "가디건, 라이더 자켓, 블레이저, 가벼운 니트"
            checklist_extra = ["카메라/삼각대 (인생샷용)", "가벼운 머플러", "휴대용 보조배터리"]

    return {
        "dest_name": dest_name,
        "country": country,
        "month": month,
        "season_type": season_type,
        "temp_desc": temp_desc,
        "clothes_guide": clothes,
        "checklist_extra": checklist_extra,
    }


