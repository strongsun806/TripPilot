"""
PDF 여행 일정표용 고정밀 동선 지도(Static Route Map) 생성기
- 일자별 방문지 좌표를 수집하여 Slippy Tile 기반 배경 지도 위에
  최적 줌 레벨과 핀 마커, 연결 동선, 명소명 칩을 정확하게 렌더링합니다.
- [동선 뭉침 방지]: 일자별(Day 1, Day 2, Day 3...) 분할 지도를 지원하여,
  특정 일차만의 동선과 스팟을 고배율로 선명하게 표시할 수 있습니다.
"""
import os
import math
import urllib.request
from typing import Dict, Any, List, Tuple
from PIL import Image, ImageDraw, ImageFont

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tile_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

DAY_PALETTE: List[Tuple[str, str]] = [
    ("#059669", "#ECFDF5"),  # 1: 에메랄드 그린
    ("#0284C7", "#E0F2FE"),  # 2: 스카이 블루
    ("#7C3AED", "#F3E8FF"),  # 3: 바이올렛
    ("#D97706", "#FEF3C7"),  # 4: 앰버
    ("#E11D48", "#FFE4E6"),  # 5: 로즈
    ("#0D9488", "#CCFBF1"),  # 6: 틸
    ("#4F46E5", "#EEF2FF"),  # 7: 인디고
    ("#2563EB", "#DBEAFE"),  # 8: 블루
    ("#16A34A", "#DCFCE7"),  # 9: 포레스트
    ("#9333EA", "#F3E8FF"),  # 10: 퍼플
]


def get_day_color(d: int) -> Tuple[str, str]:
    """1일차부터 30일차(한달살기)까지 순환 색상 반환"""
    return DAY_PALETTE[(max(1, d) - 1) % len(DAY_PALETTE)]


def latlng_to_world_px(lat: float, lng: float, z: int) -> Tuple[float, float]:
    """WGS84 위경도를 Web Mercator 월드 픽셀 좌표로 변환"""
    lat_clamped = max(min(lat, 85.0511), -85.0511)
    lat_rad = math.radians(lat_clamped)
    n = 2.0 ** z
    x = ((lng + 180.0) / 360.0) * n * 256.0
    y = ((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0) * n * 256.0
    return (x, y)


def fetch_osm_tile(x: int, y: int, z: int) -> Image.Image:
    """OpenStreetMap 타일 다운로드 및 로컬 캐싱"""
    max_tile = 2 ** z
    x = x % max_tile
    if y < 0 or y >= max_tile:
        return Image.new("RGB", (256, 256), "#F5F2EB")

    tile_file = os.path.join(CACHE_DIR, f"{z}_{x}_{y}.png")
    if os.path.exists(tile_file):
        try:
            return Image.open(tile_file).convert("RGB")
        except Exception:
            pass

    try:
        url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TripPilot-TravelPlanner/2.0 (student-project; contact@trippilot.io)"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = resp.read()
            with open(tile_file, "wb") as f:
                f.write(data)
            return Image.open(tile_file).convert("RGB")
    except Exception:
        img = Image.new("RGB", (256, 256), "#F5F2EB")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 255, 255], outline="#E5E0D5", width=1)
        return img


CITY_FALLBACK_COORDS = {
    "도쿄": (35.6762, 139.6503),
    "오사카": (34.6937, 135.5023),
    "교토": (35.0116, 135.7681),
    "후쿠오카": (33.5904, 130.4017),
    "삿포로": (43.0618, 141.3545),
    "오키나와": (26.2124, 127.6809),
    "파리": (48.8566, 2.3522),
    "런던": (51.5074, -0.1278),
    "로마": (41.9028, 12.4964),
    "바르셀로나": (41.3851, 2.1734),
    "다낭": (16.0544, 108.2022),
    "방콕": (13.7563, 100.5018),
    "싱가포르": (1.3521, 103.8198),
    "타이베이": (25.0330, 121.5654),
    "홍콩": (22.3193, 114.1694),
    "뉴욕": (40.7128, -74.0060),
    "시드니": (-33.8688, 151.2093),
    "탈린": (59.4370, 24.7536),
    "리가": (56.9496, 24.1052),
    "프라하": (50.0755, 14.4378),
    "비엔나": (48.2082, 16.3738),
    "부다페스트": (47.4979, 19.0402),
    "밀라노": (45.4642, 9.1900),
    "인터라켄": (46.6863, 7.8632),
    "취리히": (47.3769, 8.5417),
    "하와이": (21.3069, -157.8583),
    "괌": (13.4443, 144.7937),
    "세부": (10.3157, 123.8854),
    "보라카이": (11.9674, 121.9248),
    "발리": (-8.4095, 115.1889),
}


def _resolve_spot_coords(dest_name: str, place_name: str, lat_val: Any, lng_val: Any) -> Tuple[float, float]:
    """스팟의 위경도를 검증하고 유효하지 않을 경우 명칭/도시 기반 지능적 추론"""
    if isinstance(lat_val, (int, float)) and isinstance(lng_val, (int, float)):
        if abs(lat_val) > 0.01 or abs(lng_val) > 0.01:
            return float(lat_val), float(lng_val)

    combined = f"{dest_name} {place_name}".lower()
    for city_key, coords in CITY_FALLBACK_COORDS.items():
        if city_key.lower() in combined:
            return coords

    return (35.6762, 139.6503)


def generate_itinerary_route_map_image(
    dest_name: str,
    structured_plan: Dict[str, Any],
    output_path: str,
    selected_day: int | None = None,
    width: int = 760,
    height: int = 270,
) -> bool:
    """
    일정표의 일자별 방문지들을 정밀 수학 알고리즘으로 스크린에 투영하여
    고해상도 동선 지도(Route Map) 이미지를 생성합니다.
    
    [일자별 분할 지원]:
    - selected_day가 지정되면(예: 1일차) 해당 일차만의 스팟과 동선만 집중적으로 고배율 투영하여
      여러 날짜가 한 지도에 엉켜 뭉치는 현상을 100% 원천 차단합니다.
    - selected_day가 None 또는 0이면 전체 일정 종합 동선 지도를 생성합니다.
    """
    days = structured_plan.get("days", [])
    if not days:
        return False

    is_single_day = False
    target_day_obj = None
    if selected_day is not None and selected_day > 0:
        matched = [d for d in days if int(d.get("day", 1)) == selected_day]
        if matched:
            days_to_draw = matched
            target_day_obj = matched[0]
            is_single_day = True
        else:
            days_to_draw = days
    else:
        days_to_draw = days

    # 1. 스팟 좌표 수집 및 검증
    day_stops = []
    all_raw_coords: List[Tuple[float, float]] = []

    for day_obj in days_to_draw:
        d_num = int(day_obj.get("day", 1))
        stops_in_day = []
        for idx, sc in enumerate(day_obj.get("schedule", []), 1):
            p_name = sc.get("place", f"명소 {idx}")
            lat_in = sc.get("lat")
            lng_in = sc.get("lng")
            s_lat, s_lng = _resolve_spot_coords(dest_name, p_name, lat_in, lng_in)
            stops_in_day.append({"idx": idx, "name": p_name, "lat": s_lat, "lng": s_lng})
            all_raw_coords.append((s_lat, s_lng))
        if stops_in_day:
            day_stops.append((d_num, stops_in_day))

    if not all_raw_coords:
        return False

    # 2. 가용 영역 및 최적 줌(Zoom) 레벨 수학적 결정
    banner_top_h = 42
    usable_w = width * 0.74
    usable_h = (height - banner_top_h) * 0.70

    best_z = 5
    for z in range(15, 3, -1):
        wxs = [latlng_to_world_px(lat, lng, z)[0] for lat, lng in all_raw_coords]
        wys = [latlng_to_world_px(lat, lng, z)[1] for lat, lng in all_raw_coords]
        dx = max(wxs) - min(wxs)
        dy = max(wys) - min(wys)
        if dx <= usable_w and dy <= usable_h:
            best_z = z
            break

    # 일자별 분할 지도이거나 스팟이 가까우면 시내/동네 상세 뷰로 줌인 (시인성 극대화)
    wxs = [latlng_to_world_px(lat, lng, best_z)[0] for lat, lng in all_raw_coords]
    wys = [latlng_to_world_px(lat, lng, best_z)[1] for lat, lng in all_raw_coords]
    if (max(wxs) - min(wxs)) < 60 and (max(wys) - min(wys)) < 60:
        best_z = min(14, best_z + 2)
        wxs = [latlng_to_world_px(lat, lng, best_z)[0] for lat, lng in all_raw_coords]
        wys = [latlng_to_world_px(lat, lng, best_z)[1] for lat, lng in all_raw_coords]

    # 3. 뷰포트 중심 및 원점 월드 픽셀 좌표 계산
    center_wx = (min(wxs) + max(wxs)) / 2.0
    center_wy = (min(wys) + max(wys)) / 2.0

    origin_wx = center_wx - (width / 2.0)
    origin_wy = center_wy - ((height + banner_top_h) / 2.0)

    # 4. 필요한 배경 타일 다운로드 및 캔버스 합성
    tx_min = int(origin_wx // 256)
    tx_max = int((origin_wx + width) // 256)
    ty_min = int(origin_wy // 256)
    ty_max = int((origin_wy + height) // 256)

    canvas = Image.new("RGB", (width, height), "#FAF8F5")
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            tile_img = fetch_osm_tile(tx, ty, best_z)
            px = int(tx * 256 - origin_wx)
            py = int(ty * 256 - origin_wy)
            canvas.paste(tile_img, (px, py))

    # 부드러운 오트밀 톤 오버레이
    overlay = Image.new("RGBA", (width, height), (251, 248, 243, 30))
    map_base = canvas.convert("RGBA")
    map_base = Image.alpha_composite(map_base, overlay)
    draw = ImageDraw.Draw(map_base)

    # 5. 폰트 로드
    font_path = r"C:\Windows\Fonts\malgunbd.ttf"
    if not os.path.exists(font_path):
        font_path = r"C:\Windows\Fonts\malgun.ttf"
    try:
        font_pin = ImageFont.truetype(font_path, 11)
        font_label = ImageFont.truetype(font_path, 10.5)
        font_header = ImageFont.truetype(font_path, 12.5)
        font_legend = ImageFont.truetype(font_path, 10)
    except Exception:
        font_pin = ImageFont.load_default()
        font_label = font_pin
        font_header = font_pin
        font_legend = font_pin

    # 6. 각 스팟의 스크린 좌표 투영 및 지능적 미세 분산
    screen_day_stops = []
    used_screen_pts = []

    for d_num, stops in day_stops:
        day_projected = []
        for s in stops:
            wx, wy = latlng_to_world_px(s["lat"], s["lng"], best_z)
            sx = int(wx - origin_wx)
            sy = int(wy - origin_wy)

            for prev_x, prev_y in used_screen_pts:
                if abs(sx - prev_x) < 22 and abs(sy - prev_y) < 22:
                    sx += int(18 * math.cos(s["idx"]))
                    sy += int(18 * math.sin(s["idx"]))

            sx = max(24, min(width - 24, sx))
            sy = max(banner_top_h + 16, min(height - 24, sy))

            used_screen_pts.append((sx, sy))
            day_projected.append({"idx": s["idx"], "name": s["name"], "sx": sx, "sy": sy})
        screen_day_stops.append((d_num, day_projected))

    # 7. 동선 연결 라인 렌더링 (일자별로 개별 연결선)
    for d_num, stops in screen_day_stops:
        main_color, _ = get_day_color(d_num)
        coords = [(s["sx"], s["sy"]) for s in stops]

        if len(coords) >= 2:
            for i in range(len(coords) - 1):
                draw.line([coords[i], coords[i + 1]], fill=(0, 0, 0, 55), width=6)
            for i in range(len(coords) - 1):
                draw.line([coords[i], coords[i + 1]], fill=main_color, width=4)

    # 일자 간 이동 연결선 (전체 종합 지도일 때만 대시선으로 표시)
    if not is_single_day and len(screen_day_stops) >= 2:
        for d_idx in range(len(screen_day_stops) - 1):
            day_a_stops = screen_day_stops[d_idx][1]
            day_b_stops = screen_day_stops[d_idx + 1][1]
            if day_a_stops and day_b_stops:
                x1, y1 = day_a_stops[-1]["sx"], day_a_stops[-1]["sy"]
                x2, y2 = day_b_stops[0]["sx"], day_b_stops[0]["sy"]
                dist = math.hypot(x2 - x1, y2 - y1)
                steps = max(1, int(dist / 9))
                for s_i in range(0, steps, 2):
                    t1 = s_i / steps
                    t2 = min(1.0, (s_i + 1) / steps)
                    dx1 = int(x1 + (x2 - x1) * t1)
                    dy1 = int(y1 + (y2 - y1) * t1)
                    dx2 = int(x1 + (x2 - x1) * t2)
                    dy2 = int(y1 + (y2 - y1) * t2)
                    draw.line([(dx1, dy1), (dx2, dy2)], fill="#10B981", width=3)

    # 8. 핀 마커 및 명소 이름 칩 렌더링
    for d_num, stops in screen_day_stops:
        main_color, _ = get_day_color(d_num)
        for s in stops:
            map_x, map_y = s["sx"], s["sy"]

            r = 11
            draw.ellipse([map_x - r - 2, map_y - r - 2, map_x + r + 2, map_y + r + 2], fill=(0, 0, 0, 45))
            draw.ellipse([map_x - r, map_y - r, map_x + r, map_y + r], fill=main_color, outline="#FFFFFF", width=2)

            pin_text = f"{s['idx']}" if is_single_day else f"{d_num}-{s['idx']}"
            draw.text((map_x, map_y), pin_text, fill="#FFFFFF", font=font_pin, anchor="mm")

            label_name = s["name"]
            if label_name:
                short_name = label_name[:12] + (".." if len(label_name) > 12 else "")
                name_w = len(short_name) * 10 + 10
                name_h = 18

                if map_x + 14 + name_w > width - 12:
                    lx = map_x - 14 - name_w
                else:
                    lx = map_x + 14

                if map_y - 8 < banner_top_h + 4:
                    ly = map_y + 12
                else:
                    ly = map_y - 9

                draw.rounded_rectangle([lx, ly, lx + name_w, ly + name_h], radius=5, fill="#0F291E", outline="#A7F3D0", width=1)
                draw.text((lx + 5, ly + 2), short_name, fill="#FFFFFF", font=font_label)

    # 9. 상단 헤더 배너 (일자별 분할 맞춤 배너)
    banner_h = 34
    draw.rounded_rectangle([8, 6, width - 8, banner_h + 6], radius=8, fill="#0F291E", outline="#10B981", width=1)

    if is_single_day and target_day_obj:
        m_col, _ = get_day_color(selected_day)
        s_count = len(target_day_obj.get("schedule", []))
        leg_txt = f"Day {selected_day} ({s_count}개 코스)"
        tw = len(leg_txt) * 7 + 16
        leg_x = width - 18 - tw
        draw.ellipse([leg_x, 17, leg_x + 8, 25], fill=m_col, outline="#FFFFFF", width=1)
        draw.text((leg_x + 12, 15), leg_txt, fill="#FFFFFF", font=font_legend)

        theme_txt = target_day_obj.get("theme_title", "")
        if theme_txt:
            clean_title = f"[{dest_name}] Day {selected_day} 맞춤 동선 지도 : {theme_txt}"
        else:
            clean_title = f"[{dest_name}] Day {selected_day} 맞춤 동선 지도"
        if len(clean_title) * 8 > leg_x - 26:
            clean_title = f"[{dest_name}] Day {selected_day} 맞춤 동선 지도"
        draw.text((18, 15), clean_title, fill="#FFFFFF", font=font_header)
    else:
        leg_x = width - 20
        for d_num in range(min(len(days), 3), 0, -1):
            m_col, _ = get_day_color(d_num)
            txt = f"Day {d_num}"
            tw = len(txt) * 7 + 16
            leg_x -= tw
            draw.ellipse([leg_x, 17, leg_x + 8, 25], fill=m_col, outline="#FFFFFF", width=1)
            draw.text((leg_x + 12, 15), txt, fill="#FFFFFF", font=font_legend)
            leg_x -= 10

        max_title_w = leg_x - 16
        clean_title = f"[{dest_name}] 맞춤 여행 종합 동선 지도 (전체 일정)"
        if len(clean_title) * 8 > max_title_w:
            clean_title = f"[{dest_name}] 맞춤 동선 지도"
        draw.text((18, 15), clean_title, fill="#FFFFFF", font=font_header)

    final_img = map_base.convert("RGB")
    final_img.save(output_path, quality=92)
    return True
