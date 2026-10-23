"""TripPilot 전역 설정 모듈 (NF2005, F2005, F2006, F2014 준수)

청크 크기, 중복 길이, 검색 Top-k, 검색 방식(유사도/MMR), 경로 및 모델 설정을
코드 로직에서 분리하여 한곳에서 관리하고 실험·비교할 수 있도록 구성한다.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 1. 디렉터리 및 파일 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PERSIST_DIRECTORY = os.path.join(BASE_DIR, "chroma_db")
METADATA_JSON_PATH = os.path.join(DATA_DIR, "travel_metadata.json")
WIKI_CACHE_PATH = os.path.join(DATA_DIR, "wiki_cache.json")

# 2. ChromaDB 컬렉션 이름 (2.3 컬렉션 분리 설계)
META_COLLECTION = "travel_meta"
WIKI_COLLECTION = "travel_wiki"

# 3. API 및 모델 설정 (보안 및 호환성 관리)
DEFAULT_API_BASE_URL = "https://api.openai.com/v1"


def get_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or os.getenv("GMS_KEY") or "").strip()


def get_base_url() -> str:
    raw_url = (os.getenv("OPENAI_BASE_URL") or DEFAULT_API_BASE_URL).strip()
    # 프록시 기본 엔드포인트 입력 시 실제 OpenAI 호환 프록시 경로로 자동 보정 지원
    clean = raw_url.rstrip("/")
    if clean.endswith("/api/v1") and "gms" in clean:
        return clean.replace("/api/v1", "/gmsapi/api.openai.com/v1/")
    return raw_url


def get_wiki_contact() -> str:
    return (os.getenv("WIKI_CONTACT") or "trippilot_contact@example.com").strip()


EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-5.4-nano")

# 4. 청킹 및 검색 하이퍼파라미터 설정 (2.5 검색 설정 설계: F2005, F2006, F2014)
CHUNK_SIZE = int(os.getenv("TRIPPILOT_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("TRIPPILOT_CHUNK_OVERLAP", "200"))
WIKI_TOP_K = int(os.getenv("TRIPPILOT_TOP_K", "3"))

# 검색 방식: "similarity" (기본 유사도 검색) 또는 "mmr" (심화 F2014 다양성 검색)
SEARCH_TYPE = os.getenv("TRIPPILOT_SEARCH_TYPE", "similarity")
MMR_FETCH_K = int(os.getenv("TRIPPILOT_MMR_FETCH_K", "10"))
MMR_LAMBDA = float(os.getenv("TRIPPILOT_MMR_LAMBDA", "0.6"))
