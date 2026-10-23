"""
모바일 공유용 웹 일정표 발행 모듈 (Rentry & Telegraph API 기반)
스마트폰 기본 카메라로 QR 코드를 스캔했을 때, 대한민국 통신사 환경에서도 차단 없이
즉시 깔끔한 반응형 모바일 2박 3일 여행 계획표 웹페이지가 열리도록 지원합니다.
"""
import re
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from src.core_rag import clean_ai_artifacts

_TELEGRAPH_TOKEN: Optional[str] = None
_MOBILE_URL_CACHE: Dict[str, str] = {}


def build_itinerary_markdown(
    dest_name: str,
    country: str,
    structured_plan: Dict[str, Any],
) -> str:
    """모바일 스마트폰 환경에 최적화된 고대비 마크다운 일정표 텍스트 생성"""
    summary_text = str(structured_plan.get("summary", "")).strip()
    best_season = str(structured_plan.get("best_season", "")).strip()
    budget = str(structured_plan.get("budget", "")).strip()
    care_note = clean_ai_artifacts(str(structured_plan.get("dietary_care_note", "")).strip())
    days = structured_plan.get("days", [])

    days_cnt = len(days) or 3
    if days_cnt == 1:
        dur_lbl = "당일치기"
    elif days_cnt == 30:
        dur_lbl = "29박 30일 (한달살기)"
    elif days_cnt == 7:
        dur_lbl = "6박 7일 (1주일)"
    elif days_cnt == 14:
        dur_lbl = "13박 14일 (2주 살기)"
    elif days_cnt == 21:
        dur_lbl = "20박 21일 (3주 살기)"
    else:
        dur_lbl = f"{days_cnt-1}박 {days_cnt}일"

    md_lines = [
        f"# ✈️ TripPilot [{country}] {dest_name} {dur_lbl} 맞춤 여행 일정표",
        "> 🐣 **AI 여행 메이트 파일럿 토리가 설계한 실시간 맞춤 여행 계획표**",
        "",
        "---",
        "",
        "### 📋 핵심 여행 정보",
        f"- **도시 및 국가**: {dest_name} ({country})",
        f"- **여행 테마**: {summary_text}",
        f"- **추천 여행 시기**: {best_season}",
        f"- **예상 여행 경비**: {budget}",
    ]
    if care_note:
        md_lines.append(f"- **맞춤 배려 & 알러지 케어**: {care_note}")

    md_lines.extend(["", "---", ""])

    for day_obj in days:
        d_num = day_obj.get("day", 1)
        t_title = day_obj.get("theme_title", "")
        stay_area = day_obj.get("stay_area", "")
        md_lines.append(f"## 📅 Day {d_num} · {t_title}")
        if stay_area:
            md_lines.append(f"- 🏨 **추천 숙소 거점**: {stay_area}")
        md_lines.append("")

        schedule = day_obj.get("schedule", [])
        for idx, sc in enumerate(schedule, 1):
            p_name = sc.get("place", "")
            t_slot = sc.get("time_slot", "")
            act = sc.get("activity", "")
            tip = sc.get("tip", "")
            trans = sc.get("transport", "")

            md_lines.append(f"### {idx}. 📍 {p_name} ({t_slot})")
            if act:
                md_lines.append(f"- **주요 일정/활동**: {act}")
            if trans:
                md_lines.append(f"- **이동 방법**: {trans}")
            if tip:
                md_lines.append(f"- 💡 **토리가 전하는 꿀팁**: {tip}")
            md_lines.append("")

        md_lines.append("---")
        md_lines.append("")

    md_lines.append("*🌟 본 일정표는 TripPilot AI에서 실시간 맞춤 생성된 모바일 웹 가이드입니다. 안전하고 즐거운 여행 되세요! ✈️*")
    return "\n".join(md_lines)


def publish_itinerary_to_rentry(md_text: str) -> Optional[str]:
    """
    국내(SKT/KT/LGU+) 방심위 차단 없는 Rentry API를 통해
    초고속 모바일 반응형 웹페이지를 발행합니다.
    """
    try:
        url = "https://rentry.co/api/new"
        data = urllib.parse.urlencode({"text": md_text}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TripPilot/2.0",
                "Referer": "https://rentry.co",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("status") == "200" or res.get("url"):
                return res.get("url")
    except Exception:
        pass
    return None


def get_or_create_telegraph_token() -> Optional[str]:
    global _TELEGRAPH_TOKEN
    if _TELEGRAPH_TOKEN:
        return _TELEGRAPH_TOKEN
    try:
        url = "https://api.telegra.ph/createAccount?short_name=TripPilot&author_name=PilotTori"
        req = urllib.request.Request(url, headers={"User-Agent": "TripPilot/2.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("ok"):
                _TELEGRAPH_TOKEN = res["result"]["access_token"]
                return _TELEGRAPH_TOKEN
    except Exception:
        pass
    return None


def _clean_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-")
    return cleaned or "Travel"


def publish_itinerary_to_telegraph(
    dest_name: str,
    country: str,
    structured_plan: Dict[str, Any],
) -> Optional[str]:
    """폴백용 Telegraph API 발행"""
    token = get_or_create_telegraph_token()
    if not token:
        return None

    try:
        days = structured_plan.get("days", [])
        summary_text = str(structured_plan.get("summary", "")).strip()
        best_season = str(structured_plan.get("best_season", "")).strip()
        budget = str(structured_plan.get("budget", "")).strip()
        care_note = clean_ai_artifacts(str(structured_plan.get("dietary_care_note", "")).strip())

        nodes = [
            {"tag": "h3", "children": [f"✈️ [{country}] {dest_name} 맞춤 여행 일정표"]},
            {"tag": "p", "children": [f"🐣 TripPilot AI 여행 코파일럿 · {len(days)}일 맞춤 코스"]},
            {"tag": "p", "children": [f"✨ 핵심 요약: {summary_text}"]},
            {"tag": "p", "children": [f"🗓️ 추천 여행 시기: {best_season} | 💰 예상 경비: {budget}"]},
        ]
        if care_note:
            nodes.append({"tag": "p", "children": [f"🛡️ 맞춤 배려 및 알러지 케어: {care_note}"]})

        for day_obj in days:
            d_num = day_obj.get("day", 1)
            t_title = day_obj.get("theme_title", "")
            nodes.append({"tag": "h3", "children": [f"📅 Day {d_num} · {t_title}"]})

            stay_area = day_obj.get("stay_area", "")
            if stay_area:
                nodes.append({"tag": "p", "children": [f"🏨 추천 숙소 거점: {stay_area}"]})

            schedule = day_obj.get("schedule", [])
            for idx, sc in enumerate(schedule, 1):
                p_name = sc.get("place", "")
                t_slot = sc.get("time_slot", "")
                act = sc.get("activity", "")
                tip = sc.get("tip", "")
                trans = sc.get("transport", "")

                nodes.append({"tag": "h4", "children": [f"{idx}. {p_name} ({t_slot})"]})
                if act:
                    nodes.append({"tag": "p", "children": [f"• 주요 활동: {act}"]})
                if trans:
                    nodes.append({"tag": "p", "children": [f"• 이동 방법: {trans}"]})
                if tip:
                    nodes.append({"tag": "p", "children": [f"💡 토리의 꿀팁: {tip}"]})

        nodes.append({"tag": "hr", "children": []})
        nodes.append({"tag": "p", "children": ["🌟 TripPilot AI로 실시간 생성된 맞춤형 모바일 여행 가이드입니다. 즐거운 여행 되세요! ✈️"]})

        dest_slug = _clean_slug(dest_name)
        post_title = f"TripPilot-{dest_slug}-Itinerary"

        post_data = {
            "access_token": token,
            "title": post_title,
            "author_name": "TripPilot 파일럿 토리",
            "content": json.dumps(nodes, ensure_ascii=False),
            "return_content": False,
        }

        req = urllib.request.Request(
            "https://api.telegra.ph/createPage",
            data=json.dumps(post_data, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "TripPilot/2.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("ok"):
                return res["result"]["url"]
    except Exception:
        pass
    return None


def publish_itinerary_to_mobile_web(
    trip_id: str,
    dest_name: str,
    country: str,
    structured_plan: Dict[str, Any],
) -> Optional[str]:
    """
    구조화된 여행 일정표(structured_plan)를 모바일 웹페이지로 발행하고
    스마트폰 카메라로 바로 열 수 있는 정식 https:// URL을 반환합니다.
    동일 일정은 캐싱하여 0ms로 즉시 반환합니다.
    """
    days = structured_plan.get("days", [])
    cache_key = f"{trip_id}_{len(days)}_{structured_plan.get('summary', '')[:20]}"
    if cache_key in _MOBILE_URL_CACHE:
        return _MOBILE_URL_CACHE[cache_key]

    md_text = build_itinerary_markdown(dest_name, country, structured_plan)

    # 1차: 국내 모든 통신사(SKT/KT/LGU+)에서 즉시 열리는 Rentry API 발행
    published_url = publish_itinerary_to_rentry(md_text)

    # 2차: 폴백 Telegraph
    if not published_url:
        published_url = publish_itinerary_to_telegraph(dest_name, country, structured_plan)

    if published_url:
        _MOBILE_URL_CACHE[cache_key] = published_url
        return published_url

    return None
