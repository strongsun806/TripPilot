"""
F2003 ~ F2005, NF2002, NF2006:
한국어 위키백과 API를 통한 여행지 검색어 추출(프롬프트 1), 후보 문서 선별 및 본문 수집(프롬프트 2),
1,000자 청킹 / 200자 중복 분할 후 ChromaDB 'travel_wiki' 컬렉션 색인 모듈
식별자 규칙: {trip_id}:{doc_title}:{chunk_index}
"""
import os
import re
import sys
import html
import json
import time
import requests
from datetime import datetime
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import (
    get_api_key,
    get_base_url,
    get_wiki_contact,
    CHAT_MODEL,
    PERSIST_DIRECTORY,
    WIKI_COLLECTION,
    WIKI_CACHE_PATH,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from index_metadata import embeddings

api_key = get_api_key()
base_url = get_base_url()
wiki_contact = get_wiki_contact()

llm = ChatOpenAI(
    model=CHAT_MODEL,
    temperature=0.0,
    openai_api_key=api_key or "missing_key",
    openai_api_base=base_url,
)

# 위키백과 API 호출 설정 (NF2006, NF2007 준수: User-Agent 헤더에 연락처 명시)
WIKI_API_URL = "https://ko.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": f"TripPilotApp/1.0 ({wiki_contact}) python-requests"}


# ── 수집 캐시 관리 (F2004, NF2002: 이미 수집·색인한 검색어는 다시 수집하지 않음) ──
def load_wiki_cache() -> dict:
    if os.path.exists(WIKI_CACHE_PATH):
        try:
            with open(WIKI_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_wiki_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(WIKI_CACHE_PATH), exist_ok=True)
    with open(WIKI_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── 위키백과 HTTP 호출 (NF2006: 재시도 및 호출 간격 규칙 준수) ──
def request_wikipedia(params: dict, max_retries: int = 3) -> dict | list | None:
    wait = 1.5
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(WIKI_API_URL, headers=HEADERS, params=params, timeout=10)
            if res.status_code == 200:
                time.sleep(0.25)  # NF2006: 외부 API 호출 간격 예절 준수
                return res.json()
            if res.status_code == 429:
                retry_after = float(res.headers.get("Retry-After") or wait)
                print(f"⚠️ [429 Too Many Requests] {retry_after:.1f}초 대기 후 재시도 ({attempt}/{max_retries})")
                time.sleep(retry_after)
                wait *= 2
                continue
        except Exception as e:
            print(f"⚠️ 위키백과 API 요청 오류 ({attempt}/{max_retries}): {e}")
            time.sleep(wait)
    return None


def _clean_dest_name(dest_name: str) -> str:
    """'씨엠립(앙코르와트)' 같은 표기에서 핵심 지명/랜드마크 추출 보조"""
    return re.sub(r"\([^)]*\)", "", dest_name).strip() or dest_name


def search_wiki_candidates(query: str, limit: int = 4) -> list[dict]:
    """위키백과 검색어로 후보 문서의 제목과 요약(snippet) 목록을 검색 (F2004)"""
    data = request_wikipedia({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "formatversion": 2,
    })
    if not isinstance(data, dict):
        return []
    search_items = data.get("query", {}).get("search", [])
    results = []
    for item in search_items:
        clean_snippet = html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", "")))
        results.append({
            "page_id": item.get("pageid"),
            "title": item.get("title"),
            "snippet": clean_snippet,
            "search_query": query,
        })
    return results


def get_wiki_content(title: str) -> dict | None:
    """위키백과 문서 본문(plain text) 및 원문 URL 조회 (F2004)"""
    data = request_wikipedia({
        "action": "query",
        "prop": "extracts|info",
        "explaintext": 1,
        "titles": title,
        "inprop": "url",
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    })
    if not isinstance(data, dict):
        return None
    pages = data.get("query", {}).get("pages", [])
    for page_data in pages:
        if not page_data.get("missing"):
            return {
                "page_id": page_data.get("pageid"),
                "title": page_data.get("title"),
                "text": page_data.get("extract", ""),
                "url": page_data.get("fullurl", f"https://ko.wikipedia.org/wiki/{title}"),
            }
    return None


# ── F2003: 프롬프트 1 - 도메인 전문가 검색어 추출 ──
def extract_search_keywords(dest_name: str, question: str, country: str = "", theme: str = "") -> list[str]:
    base_name = _clean_dest_name(dest_name)
    system_msg = SystemMessage(
        content=(
            "너는 20년 경력의 글로벌 여행 큐레이터이자 지리·문화·관광 백과사전 전문 컨설턴트다. "
            "주어진 여행지 명칭과 사용자 질문을 분석하여, 한국어 위키백과에서 검색할 **구체적인 고유명사(도시 정식 명칭, 대표 랜드마크, 유명 관광 명소, 대표 축제, 광역 지역명)** 키워드 4~5개를 선정하라.\n"
            "[절대 규칙]\n"
            "1. 첫 번째 키워드는 반드시 선택된 여행지 명칭 자체로 지정하라.\n"
            "2. '역사', '기후', '미식', '축제', '주요 관광지', '문화' 같은 추상적·일반 명사를 단독 키워드로 절대 출력하지 마라.\n"
            "3. 반드시 해당 여행지의 실제 랜드마크나 구체적 명칭(예: 삿포로 -> [\"삿포로\", \"삿포로시\", \"삿포로 눈축제\", \"오도리 공원\", \"스스키노\"] / 파리 -> [\"파리\", \"에펠탑\", \"루브르 박물관\", \"베르사유 궁전\", \"몽마르트르\"])만 출력하라.\n"
            "4. 결과는 오직 파싱 가능한 JSON 문자열 배열 형식으로만 출력하라."
        )
    )
    context_hint = f" (국가: {country}, 테마: {theme})" if (country or theme) else ""
    user_msg = HumanMessage(content=f"여행지명: {dest_name}{context_hint}\n질문: {question}")

    generic_words = {"주요 관광지", "관광지", "역사", "기후", "미식", "축제", "문화", "여행", "교통", "음식", "랜드마크"}

    try:
        response = llm.invoke([system_msg, user_msg]).content.strip()
        if "```" in response:
            response = re.sub(r"```(?:json)?", "", response).replace("```", "").strip()
        raw_keywords = json.loads(response)
        if not isinstance(raw_keywords, list):
            raw_keywords = [base_name]

        keywords = []
        for kw in raw_keywords:
            kw_str = str(kw).strip()
            if not kw_str:
                continue
            if kw_str in generic_words:
                kw_str = f"{base_name} {kw_str}"
            if kw_str not in keywords:
                keywords.append(kw_str)

        if base_name in keywords:
            keywords.remove(base_name)
        keywords.insert(0, base_name)
        return keywords[:5]
    except Exception:
        fallback = [base_name]
        if "(" in dest_name and ")" in dest_name:
            inner = re.findall(r"\(([^)]+)\)", dest_name)
            for item in inner:
                if item not in fallback:
                    fallback.append(item)
        if "&" in base_name:
            for part in base_name.split("&"):
                p = part.strip()
                if p and p not in fallback:
                    fallback.append(p)
        if country and country not in fallback:
            fallback.append(f"{base_name} {country}")
        return fallback[:5]


# ── F2004: 프롬프트 2 - 후보 문서 선별 및 본문 수집 ──
def filter_and_collect_docs(
    dest_name: str,
    candidates: list,
    return_details: bool = False,
) -> list[dict] | tuple[list[dict], list[str], list[str]]:
    """후보 목록(문자열 제목 리스트 또는 {title, snippet} 딕셔너리 리스트)에서
    프롬프트 2로 관련성이 높은 문서만 선별하여 본문과 원문 URL을 수집한다."""
    base_name = _clean_dest_name(dest_name)
    normalized_candidates = []
    for c in candidates:
        if isinstance(c, dict):
            normalized_candidates.append(c)
        else:
            normalized_candidates.append({"title": str(c), "snippet": ""})

    candidate_titles = [c["title"] for c in normalized_candidates]

    system_msg = SystemMessage(
        content=(
            "너는 글로벌 여행 정보 및 지리·역사 백과사전 문서 선별 전문가다. "
            "검색된 위키백과 후보 문서(제목 및 요약) 목록 중, 해당 여행지의 역사, 지리, 기후, 핵심 랜드마크, 관광 명소, "
            "교통, 문화유산과 직접 연관성이 높은 문서만 선별하라. "
            "동음이의어(예: 인명, 무관한 영화/소설/스포츠 경기 등) 문서는 제외하라. "
            "단, 선택한 여행지 명칭과 직접 일치하거나 여행지 자체를 다룬 문서는 어떤 제외 규칙보다 우선하여 무조건 포함해야 한다. "
            "결과는 선별된 문서의 제목(title)들만 JSON 문자열 배열 형식으로 반환하라."
        )
    )
    user_msg = HumanMessage(
        content=f"기준 여행지: {dest_name}\n후보 문서 목록: {json.dumps(normalized_candidates, ensure_ascii=False)}"
    )

    try:
        response = llm.invoke([system_msg, user_msg]).content.strip()
        if "```" in response:
            response = re.sub(r"```(?:json)?", "", response).replace("```", "").strip()
        selected_titles = json.loads(response)
        if not isinstance(selected_titles, list):
            selected_titles = candidate_titles[:4]
    except Exception:
        selected_titles = candidate_titles[:4]

    # F2004: 선택한 항목 자체를 다룬 문서는 선별·길이 등 어떤 제외 규칙보다 우선하여 항상 포함
    for t in candidate_titles:
        if (t == dest_name or t == base_name or base_name in t) and t not in selected_titles:
            selected_titles.insert(0, t)

    rejected_titles = [t for t in candidate_titles if t not in selected_titles]

    collected_docs = []
    for title in selected_titles:
        doc_data = get_wiki_content(title)
        if not doc_data:
            continue
        text_len = len(doc_data["text"].strip())
        # 여행지 본체 문서는 길이 제한 없이 무조건 포함, 일반 관련 문서는 50자 초과 시 포함
        is_self_doc = (title == dest_name) or (title == base_name) or (base_name in title)
        if is_self_doc or text_len > 50:
            collected_docs.append(doc_data)
            print(f"  📄 [선별/수집 완료] {doc_data['title']} ({text_len:,}자) - {doc_data['url']}")

    if rejected_titles:
        print(f"  🗑️ [선별 제외 문서] {rejected_titles}")

    if return_details:
        return collected_docs, selected_titles, rejected_titles
    return collected_docs


# ── F2005: 청킹 및 ChromaDB (travel_wiki) 별도 컬렉션 색인 ──
def chunk_and_index_wiki(
    trip_id: str,
    dest_name: str,
    docs: list[dict],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> int:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    documents = []
    ids = []
    collected_date = datetime.now().strftime("%Y-%m-%d")

    for doc in docs:
        chunks = splitter.split_text(doc["text"])
        for idx, chunk_text in enumerate(chunks):
            # 2.3 청크 메타데이터 설계 적용
            meta = {
                "trip_id": str(trip_id),
                "dest_name": dest_name,
                "doc_title": doc["title"],
                "page_id": str(doc.get("page_id", "")),
                "source_url": doc["url"],
                "source_type": "한국어 위키백과",
                "chunk_id": idx,
                "collected_at": collected_date,
            }
            # F2005 식별자 규칙: {trip_id}:{doc_title}:{chunk_index}
            chunk_unique_id = f"{trip_id}:{doc['title']}:{idx}"

            documents.append(Document(page_content=chunk_text, metadata=meta))
            ids.append(chunk_unique_id)

    if not documents:
        print("⚠️ 색인할 위키 청크가 없습니다.")
        return 0

    vectorstore = Chroma(
        collection_name=WIKI_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )

    print(
        f"⏳ '{dest_name}' 관련 위키 문서 {len(documents)}개 청크를 "
        f"(청크 크기={chunk_size}, 중복={chunk_overlap}) 'travel_wiki' 컬렉션에 임베딩/색인 중..."
    )
    vectorstore.add_documents(documents=documents, ids=ids)

    total_chunks = vectorstore._collection.count()
    print(f"✅ 색인 완료! 컬렉션 '{WIKI_COLLECTION}'의 누적 청크 수: {total_chunks}건")
    return len(documents)


# ── 전체 수집·색인 파이프라인 통합 실행 함수 (캐시 지원) ──
def process_wiki_for_destination(
    trip_id: str,
    dest_name: str,
    sample_question: str,
    country: str = "",
    theme: str = "",
    force_recollect: bool = False,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    print("\n==========================================")
    print(f"🌍 위키 문서 수집 및 색인 파이프라인: {dest_name} (ID: {trip_id})")
    print("==========================================")

    cache = load_wiki_cache()
    trip_cache = cache.get(str(trip_id), {"keywords": [], "titles": []})

    # 1) F2003: 검색어 추출
    print("\n[Step 1] 프롬프트 1 - 검색어 추출 중...")
    keywords = extract_search_keywords(dest_name, sample_question, country=country, theme=theme)
    print(f"  🔍 추출된 검색어: {keywords}")

    # NF2002: 이미 수집한 검색어는 재수집 생략
    if not force_recollect:
        new_keywords = [kw for kw in keywords if kw not in trip_cache.get("keywords", [])]
        skipped_keywords = [kw for kw in keywords if kw in trip_cache.get("keywords", [])]
    else:
        new_keywords = list(keywords)
        skipped_keywords = []

    if skipped_keywords:
        print(f"  ⚡ [캐시 적중 - NF2002] 이미 수집된 검색어 재수집 생략: {skipped_keywords}")

    if not new_keywords:
        print("  ✅ 모든 추출 검색어가 이미 수집·색인되어 있어 외부 API 호출을 생략합니다.")
        return {
            "keywords": keywords,
            "new_keywords": [],
            "skipped_keywords": skipped_keywords,
            "candidates": [],
            "selected_titles": trip_cache.get("titles", []),
            "rejected_titles": [],
            "docs": [],
            "indexed_chunks": 0,
            "cached": True,
        }

    # 2) 후보 문서 검색
    print("\n[Step 2] 위키백과 후보 검색 중...")
    candidates = []
    seen_titles = set()
    for kw in new_keywords:
        for cand in search_wiki_candidates(kw, limit=3):
            if cand["title"] not in seen_titles:
                seen_titles.add(cand["title"])
                candidates.append(cand)
    print(f"  📋 발견된 후보 목록 ({len(candidates)}개): {[c['title'] for c in candidates]}")

    # 3) F2004: 프롬프트 2 - 후보 문서 선별 및 본문 로드
    print("\n[Step 3] 프롬프트 2 - 유효 문서 선별 및 본문 수집 중...")
    valid_docs, selected_titles, rejected_titles = filter_and_collect_docs(
        dest_name, candidates, return_details=True
    )

    # 4) F2005: 문서 청킹 및 벡터 색인
    print("\n[Step 4] 문서 청킹 및 travel_wiki 컬렉션 색인...")
    indexed_chunks = chunk_and_index_wiki(
        trip_id=str(trip_id),
        dest_name=dest_name,
        docs=valid_docs,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    # 캐시 업데이트 (NF2002)
    merged_keywords = list(dict.fromkeys(trip_cache.get("keywords", []) + new_keywords))
    merged_titles = list(dict.fromkeys(trip_cache.get("titles", []) + [d["title"] for d in valid_docs]))
    cache[str(trip_id)] = {
        "dest_name": dest_name,
        "keywords": merged_keywords,
        "titles": merged_titles,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_wiki_cache(cache)

    return {
        "keywords": keywords,
        "new_keywords": new_keywords,
        "skipped_keywords": skipped_keywords,
        "candidates": [c["title"] for c in candidates],
        "selected_titles": selected_titles,
        "rejected_titles": rejected_titles,
        "docs": valid_docs,
        "indexed_chunks": indexed_chunks,
        "cached": False,
    }


if __name__ == "__main__":
    process_wiki_for_destination(
        trip_id="5",
        dest_name="삿포로",
        sample_question="삿포로 눈축제 오도리 공원 스스키노 모이와산 맥주 박물관 오타루 비에이 여행",
        country="일본",
        theme="자연/설경/미식",
        force_recollect=True,
    )
