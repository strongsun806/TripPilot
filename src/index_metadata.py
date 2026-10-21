"""
F2001, F2002: 여행지 메타데이터 로드 및 ChromaDB 'travel_meta' 컬렉션 색인 모듈
ID는 'TRIP_{id}'로 고정하여 재실행 시에도 중복 저장을 방지합니다.
"""
import os
import sys
import json
import math
import hashlib
from typing import List
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import (
    get_api_key,
    get_base_url,
    EMBEDDING_MODEL,
    PERSIST_DIRECTORY,
    METADATA_JSON_PATH,
    META_COLLECTION,
)

api_key = get_api_key()
base_url = get_base_url()


class TripPilotEmbeddings(Embeddings):
    """OpenAIEmbeddings(text-embedding-3-small, 1536차원)를 기본 사용하며,
    키 미설정/오프라인 환경에서도 동일한 1536차원 벡터로 폴백하여 색인을 보장하는 래퍼."""

    def __init__(self, api_key: str, base_url: str, model: str = EMBEDDING_MODEL):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._openai_embeddings = (
            OpenAIEmbeddings(
                model=model,
                openai_api_key=self.api_key,
                openai_api_base=self.base_url,
            )
            if self.api_key and self.api_key != "your_key_here"
            else None
        )

    @staticmethod
    def _fallback_vector(text: str, dim: int = 1536) -> List[float]:
        vec = [0.0] * dim
        clean = text.lower().strip()
        tokens = clean.split()
        features = list(tokens) + [clean[i:i + 3] for i in range(max(1, len(clean) - 2))]
        for feat in features:
            h = hashlib.sha256(feat.encode("utf-8")).digest()
            for j in range(0, 28, 4):
                idx = int.from_bytes(h[j:j + 2], "little") % dim
                sign = 1.0 if (h[j + 2] & 1) == 0 else -1.0
                weight = 1.0 + (h[j + 3] / 255.0)
                vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._openai_embeddings and self.api_key != "your_key_here":
            try:
                return self._openai_embeddings.embed_documents(texts)
            except Exception as e:
                print(f"ℹ️ 원격 임베딩 호출 실패로 로컬 호환 임베딩(1536차원)을 사용합니다: {e}")
        return [self._fallback_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        if self._openai_embeddings and self.api_key != "your_key_here":
            try:
                return self._openai_embeddings.embed_query(text)
            except Exception:
                pass
        return self._fallback_vector(text)


# 전역 임베딩 객체
embeddings = TripPilotEmbeddings(api_key=api_key, base_url=base_url, model=EMBEDDING_MODEL)


def get_collection_count(collection_name: str = META_COLLECTION) -> int:
    """ChromaDB 특정 컬렉션에 저장된 현재 청크 건수를 반환 (F2002, F2012 확인용)"""
    try:
        store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=PERSIST_DIRECTORY,
        )
        return store._collection.count()
    except Exception:
        return 0


def format_travel_item_text(item: dict) -> str:
    """2.2 항목 텍스트 설계 포맷: 항목 1건을 검색에 사용할 하나의 텍스트로 구성 (F2001)"""
    return (
        f"[여행지 메타데이터] 여행지명: {item['name']} | "
        f"국가: {item['country']} | "
        f"대륙: {item['continent']} | "
        f"테마: {item['theme']} | "
        f"예산 수준: {item['budget_level']} | "
        f"추천 여행 시기(베스트 시즌): {item['best_season']} | "
        f"요약 설명: {item['summary']}"
    )


def load_and_index_metadata(json_path: str = METADATA_JSON_PATH) -> int:
    if not os.path.exists(json_path):
        raise FileNotFoundError(
            f"⚠️ {json_path} 파일이 존재하지 않습니다. 먼저 python src/make_data.py를 실행하세요."
        )

    with open(json_path, "r", encoding="utf-8") as f:
        travel_items = json.load(f)

    print(f"📦 로드된 여행지 항목 수: {len(travel_items)}건")

    documents = []
    ids = []

    for item in travel_items:
        page_content = format_travel_item_text(item)

        # 2.3 메타데이터 필드 저장 (검색 및 필터링용)
        metadata = {
            "trip_id": str(item["id"]),
            "name": item["name"],
            "country": item["country"],
            "continent": item["continent"],
            "theme": item["theme"],
            "budget_level": item["budget_level"],
            "best_season": item["best_season"],
        }

        documents.append(Document(page_content=page_content, metadata=metadata))
        # F2002: 재실행 시 덮어쓰기 및 중복 방지를 위한 고유 ID 'TRIP_{id}' 부여
        ids.append(f"TRIP_{item['id']}")

    vectorstore = Chroma(
        collection_name=META_COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
    )

    print("⏳ ChromaDB 'travel_meta' 컬렉션에 임베딩 및 색인을 진행 중입니다...")
    vectorstore.add_documents(documents=documents, ids=ids)

    current_count = vectorstore._collection.count()
    print(f"✅ 색인 완료! 컬렉션 '{META_COLLECTION}'의 총 청크 수: {current_count}건")

    print("\n[색인 텍스트 1건 예시 (4.1 검증)]")
    print(documents[0].page_content)
    return current_count


if __name__ == "__main__":
    load_and_index_metadata()
