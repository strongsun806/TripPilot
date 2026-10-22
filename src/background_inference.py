# -*- coding: utf-8 -*-
"""
TripPilot 병렬 백그라운드 추론 엔진 (Parallel Background Inference Engine)
- 사용자가 버튼을 누르거나, 다른 탭으로 이동하거나, 검색 필터를 바꾸는 등
  어떤 UI 액션을 취하더라도 AI 추론(RAG 색인 + LLM 2-Stage 일정 설계)이 중단되지 않고
  독립된 백그라운드 워커 스레드(ThreadPoolExecutor)에서 안전하게 병렬 완주되도록 보장합니다.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List
from core_rag import generate_itinerary, query_trip_pilot
from collect_and_index_wiki import process_wiki_for_destination

# 전역 워커 스레드 풀 (Streamlit ScriptRunner와 완전히 분리된 데몬 스레드)
_INFERENCE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="TripPilotWorker")
_TASK_LOCK = threading.Lock()
_TASKS: Dict[str, Dict[str, Any]] = {}


def submit_itinerary_task(
    trip_id: str,
    dest_name: str,
    country: str,
    theme: str,
    user_pref_summary: str,
    current_plan: Optional[Dict[str, Any]],
    top_k_val: int,
    chunk_size_val: int,
    chunk_overlap_val: int,
    force_recollect: bool,
    target_days: int = 3,
    duration_label: str = "2박 3일",
    prompt_for_chat: Optional[str] = None,
) -> str:
    """
    맞춤 일정표 생성/수정 작업을 백그라운드 스레드로 제출.
    이미 해당 trip_id로 실행 중인 태스크가 있다면 중복 실행하지 않고 기존 task_id 반환.
    """
    with _TASK_LOCK:
        # 이미 실행 중인 동일 trip_id 태스크가 있는지 검사
        for tid, tinfo in _TASKS.items():
            if tinfo.get("trip_id") == trip_id and tinfo.get("status") == "running":
                return tid

        task_id = f"task_{trip_id}_{int(time.time() * 1000)}"
        _TASKS[task_id] = {
            "task_id": task_id,
            "task_type": "itinerary",
            "trip_id": trip_id,
            "dest_name": dest_name,
            "country": country,
            "target_days": target_days,
            "duration_label": duration_label,
            "status": "running",
            "step": f"1️⃣ '{dest_name}' 위키백과 명소·기후 자료 확인 및 색인 중...",
            "progress": 0.2,
            "result": None,
            "error": None,
            "prompt_for_chat": prompt_for_chat,
            "start_time": time.time(),
            "finished_time": None,
        }

    # 워커 스레드에 작업 위임
    def _worker():
        try:

            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["step"] = f"1️⃣ '{dest_name}' 위키백과 명소·문화·기후 자료 확인 및 색인 중..."
                    _TASKS[task_id]["progress"] = 0.35

            collect_info = process_wiki_for_destination(
                trip_id=trip_id,
                dest_name=dest_name,
                sample_question=f"{dest_name} 관광 명소 랜드마크 역사 문화 음식 여행 코스 {user_pref_summary}",
                country=country,
                theme=theme,
                force_recollect=force_recollect,
                chunk_size=chunk_size_val,
                chunk_overlap=chunk_overlap_val,
            )

            # 2. 2-Stage RAG 및 일정표 생성
            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["step"] = f"2️⃣ 다단계 RAG & {duration_label} 최적 동선 및 숙소 거점 설계 중..."
                    _TASKS[task_id]["progress"] = 0.70

            itin_res = generate_itinerary(
                trip_id=trip_id,
                dest_name=dest_name,
                country=country,
                user_preference=user_pref_summary,
                current_plan=current_plan,
                top_k=max(4, top_k_val),
                target_days=target_days,
            )

            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["status"] = "completed"
                    _TASKS[task_id]["step"] = f"✨ '{dest_name}' {duration_label} 맞춤 일정 및 동선 완성!"
                    _TASKS[task_id]["progress"] = 1.0
                    _TASKS[task_id]["result"] = itin_res
                    _TASKS[task_id]["finished_time"] = time.time()

        except Exception as exc:
            import traceback
            traceback.print_exc()
            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["status"] = "error"
                    _TASKS[task_id]["error"] = str(exc)
                    _TASKS[task_id]["finished_time"] = time.time()

    _INFERENCE_EXECUTOR.submit(_worker)
    return task_id


def submit_chat_task(
    trip_id: str,
    dest_name: str,
    country: str,
    theme: str,
    active_user_input: str,
    user_pref_summary: str,
    current_plan: Optional[Dict[str, Any]],
    top_k_val: int,
    search_type_label: str,
    chunk_size_val: int,
    chunk_overlap_val: int,
    force_recollect: bool,
    target_days: int = 3,
    duration_label: str = "2박 3일",
    is_itin_request: bool = False,
) -> str:
    """
    채팅 대화 추론(RAG 질문 답변 또는 채팅 기반 일정 변경)을 백그라운드 스레드로 제출.
    """
    with _TASK_LOCK:
        for tid, tinfo in _TASKS.items():
            if tinfo.get("trip_id") == trip_id and tinfo.get("status") == "running":
                return tid

        task_id = f"chat_{trip_id}_{int(time.time() * 1000)}"
        _TASKS[task_id] = {
            "task_id": task_id,
            "task_type": "chat",
            "trip_id": trip_id,
            "dest_name": dest_name,
            "country": country,
            "target_days": target_days,
            "duration_label": duration_label,
            "is_itin_request": is_itin_request,
            "user_input": active_user_input,
            "status": "running",
            "step": f"🔍 '{dest_name}' 위키백과 자료 확인 및 RAG 검색 중...",
            "progress": 0.25,
            "result": None,
            "error": None,
            "start_time": time.time(),
            "finished_time": None,
        }

    def _chat_worker():
        try:
            # Step 1: 위키 색인 확인
            collect_info = process_wiki_for_destination(
                trip_id=trip_id,
                dest_name=dest_name,
                sample_question=active_user_input,
                country=country,
                theme=theme,
                force_recollect=force_recollect,
                chunk_size=chunk_size_val,
                chunk_overlap=chunk_overlap_val,
            )

            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["step"] = f"🤖 2-Stage RAG 심층 추론 및 맞춤 답변 생성 중..."
                    _TASKS[task_id]["progress"] = 0.65

            if is_itin_request:
                # 일정 변경 요청인 경우 generate_itinerary 실행
                itin_res = generate_itinerary(
                    trip_id=trip_id,
                    dest_name=dest_name,
                    country=country,
                    user_preference=user_pref_summary,
                    current_plan=current_plan,
                    top_k=max(4, top_k_val),
                    target_days=target_days,
                )
                answer = itin_res.get("bot_message", itin_res.get("answer", ""))
                cited_sources = itin_res.get("cited_sources", [])
                all_contexts = itin_res.get("all_contexts", [])
                expanded_queries = itin_res.get("expanded_queries", [])
                result_payload = {
                    "is_itin_update": True,
                    "itin_res": itin_res,
                    "answer": answer,
                    "cited_sources": cited_sources,
                    "all_contexts": all_contexts,
                    "expanded_queries": expanded_queries,
                }
            else:
                # 일반 질문 답변인 경우 query_trip_pilot 실행
                rag_result = query_trip_pilot(
                    trip_id=trip_id,
                    dest_name=dest_name,
                    question=active_user_input,
                    top_k=top_k_val,
                    search_type=search_type_label,
                )
                result_payload = {
                    "is_itin_update": False,
                    "itin_res": None,
                    "answer": rag_result["answer"],
                    "cited_sources": rag_result["cited_sources"],
                    "all_contexts": rag_result["all_contexts"],
                    "expanded_queries": rag_result.get("expanded_queries", []),
                }

            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["status"] = "completed"
                    _TASKS[task_id]["step"] = "✓ 답변 및 일정 추론 완료!"
                    _TASKS[task_id]["progress"] = 1.0
                    _TASKS[task_id]["result"] = result_payload
                    _TASKS[task_id]["finished_time"] = time.time()

        except Exception as exc:
            import traceback
            traceback.print_exc()
            with _TASK_LOCK:
                if task_id in _TASKS:
                    _TASKS[task_id]["status"] = "error"
                    _TASKS[task_id]["error"] = str(exc)
                    _TASKS[task_id]["finished_time"] = time.time()

    _INFERENCE_EXECUTOR.submit(_chat_worker)
    return task_id


def get_active_task_for_trip(trip_id: str) -> Optional[Dict[str, Any]]:
    """특정 trip_id에 대해 현재 실행 중인 백그라운드 태스크 정보 반환"""
    with _TASK_LOCK:
        for tid, tinfo in _TASKS.items():
            if tinfo.get("trip_id") == trip_id and tinfo.get("status") == "running":
                return dict(tinfo)
        return None


def poll_task(task_id: str) -> Optional[Dict[str, Any]]:
    """태스크 ID로 현재 상태 및 결과 조회 (스레드 세이프)"""
    with _TASK_LOCK:
        if task_id in _TASKS:
            return dict(_TASKS[task_id])
        return None


def pop_completed_task(task_id: str) -> Optional[Dict[str, Any]]:
    """완료된 태스크 결과를 가져오고 레지스트리에서 정리"""
    with _TASK_LOCK:
        if task_id in _TASKS:
            task = _TASKS.pop(task_id)
            return task
        return None


def get_any_completed_tasks_for_trip(trip_id: str) -> List[Dict[str, Any]]:
    """해당 trip_id에 완료(completed 또는 error)된 태스크들을 수집 및 레지스트리에서 반환"""
    completed = []
    with _TASK_LOCK:
        tids_to_remove = []
        for tid, tinfo in _TASKS.items():
            if tinfo.get("trip_id") == trip_id and tinfo.get("status") in ("completed", "error"):
                completed.append(dict(tinfo))
                tids_to_remove.append(tid)
        for tid in tids_to_remove:
            _TASKS.pop(tid, None)
    return completed


def sync_completed_background_tasks(session_state) -> bool:
    """
    모든 여행지의 완료된 백그라운드 태스크를 감지하여 Streamlit session_state에 즉시 동기화합니다.
    사용자가 어느 탭이나 어느 페이지에 있더라도 백그라운드 결과가 안전하게 세션에 커밋됩니다.
    커밋된 작업이 있으면 True, 없으면 False 반환.
    """
    has_changes = False
    with _TASK_LOCK:
        completed_tids = [tid for tid, info in _TASKS.items() if info.get("status") in ("completed", "error")]
        tasks_to_process = [_TASKS.pop(tid) for tid in completed_tids]

    for t in tasks_to_process:
        trip_id = t["trip_id"]
        if t["status"] == "completed":
            has_changes = True
            if t["task_type"] == "itinerary":
                itin_res = t["result"]
                if "itinerary_by_trip" in session_state:
                    session_state.itinerary_by_trip[trip_id] = itin_res
                session_state[f"planner_day_{trip_id}"] = 1
                if "messages_by_trip" in session_state and trip_id in session_state.messages_by_trip:
                    session_state.messages_by_trip[trip_id].append({
                        "role": "assistant",
                        "content": itin_res.get("bot_message", itin_res.get("answer", "")),
                        "cited_sources": itin_res.get("cited_sources", []),
                        "all_contexts": itin_res.get("all_contexts", []),
                        "expanded_queries": itin_res.get("expanded_queries", []),
                    })
            elif t["task_type"] == "chat":
                res_payload = t["result"]
                if res_payload.get("is_itin_update") and res_payload.get("itin_res"):
                    if "itinerary_by_trip" in session_state:
                        session_state.itinerary_by_trip[trip_id] = res_payload["itin_res"]
                if "messages_by_trip" in session_state and trip_id in session_state.messages_by_trip:
                    session_state.messages_by_trip[trip_id].append({
                        "role": "assistant",
                        "content": res_payload["answer"],
                        "cited_sources": res_payload.get("cited_sources", []),
                        "all_contexts": res_payload.get("all_contexts", []),
                        "expanded_queries": res_payload.get("expanded_queries", []),
                    })
    return has_changes

