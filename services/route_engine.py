"""
services/route_engine.py

그래프 거리 기반 루트 생성.
좌표 오프셋 대신 실제 도로망 거리로 중간 노드를 탐색해서
항상 도로 위에 있는 노드만 사용한다.
"""

import math
import random
import networkx as nx
import osmnx as ox
from services.graph_loader import get_graph, get_nearest_node


WALK_SPEED_MPS = 4 * 1000 / 3600
RUN_SPEED_MPS = 8 * 1000 / 3600
ROUTE_COUNT = 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  순환 루트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_loop_routes(
    start_lat: float,
    start_lng: float,
    goal_km: float,
    weights: dict = {},
    is_running: bool = False,
) -> list[dict]:

    G = get_graph()
    speed = RUN_SPEED_MPS if is_running else WALK_SPEED_MPS

    # 그래프 최대 범위 내로 목표 거리 제한
    goal_m = _clamp_goal(G, start_lat, start_lng, goal_km * 1000)

    start_node = get_nearest_node(start_lat, start_lng)
    half_m = goal_m / 2

    # 실제 그래프 거리로 half_m 근방 노드 탐색
    candidates = _nodes_at_distance(G, start_node, half_m)

    if len(candidates) < 2:
        return _fallback(start_lat, start_lng, goal_km)

    routes = []
    used_pairs = set()

    # 서로 방향이 다른 노드 쌍으로 루트 생성
    start_data = G.nodes[start_node]
    slat, slng = start_data["y"], start_data["x"]

    # 후보 노드들을 방향(각도)으로 정렬
    def angle_of(n):
        nd = G.nodes[n]
        return math.atan2(nd["y"] - slat, nd["x"] - slng)

    candidates.sort(key=angle_of)

    # 120도씩 벌어진 노드 쌍 선택
    n = len(candidates)
    step = max(n // 4, 1)

    for offset in range(0, min(n, 8), max(1, n // 8)):
        if len(routes) >= ROUTE_COUNT:
            break

        idx1 = offset % n
        idx2 = (offset + n // 3) % n
        idx3 = (offset + 2 * n // 3) % n

        mid1 = candidates[idx1]
        mid2 = candidates[idx2]

        pair = (min(mid1, mid2), max(mid1, mid2))
        if pair in used_pairs or mid1 == mid2:
            continue
        used_pairs.add(pair)

        try:
            path1 = nx.shortest_path(G, start_node, mid1, weight="length")
            path2 = nx.shortest_path(G, mid1, mid2, weight="length")
            path3 = nx.shortest_path(G, mid2, start_node, weight="length")
            full = path1 + path2[1:] + path3[1:]

            dist_m = _calc_distance(G, full)
            minutes = round(dist_m / speed / 60)

            routes.append(
                {
                    "id": f"route-{len(routes)+1}",
                    "name": f"코스 {['A','B','C'][len(routes)]}",
                    "color": _route_color(len(routes)),
                    "coords": _path_to_coords(G, full),
                    "distance_km": round(dist_m / 1000, 2),
                    "minutes": minutes,
                    "description": f"{'달리기' if is_running else '도보'} · {round(dist_m/1000,1)}km",
                }
            )
        except nx.NetworkXNoPath:
            continue

    return routes if routes else _fallback(start_lat, start_lng, goal_km)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  목적형 루트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_waypoint_routes(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    goal_km: float = 0.0,
) -> list[dict]:

    G = get_graph()
    start_node = get_nearest_node(start_lat, start_lng)
    end_node = get_nearest_node(end_lat, end_lng)

    # 최단 경로
    direct_path = nx.shortest_path(G, start_node, end_node, weight="length")
    direct_m = _calc_distance(G, direct_path)

    goal_m = max(goal_km * 1000, direct_m)
    extra_m = goal_m - direct_m

    routes = []

    if extra_m < 200:
        # 우회 없이 방향만 다른 3가지
        via_candidates = _nodes_near_midpoint(G, start_node, end_node, 300)
    else:
        via_candidates = _nodes_near_midpoint(G, start_node, end_node, extra_m / 2)

    used = set()
    for via in via_candidates:
        if len(routes) >= ROUTE_COUNT:
            break
        if via in used or via == start_node or via == end_node:
            continue
        used.add(via)

        try:
            path1 = nx.shortest_path(G, start_node, via, weight="length")
            path2 = nx.shortest_path(G, via, end_node, weight="length")
            full = path1 + path2[1:]

            dist_m = _calc_distance(G, full)
            minutes = round(dist_m / WALK_SPEED_MPS / 60)
            i = len(routes)

            routes.append(
                {
                    "id": f"route-{i+1}",
                    "name": f"코스 {['A','B','C'][i]}",
                    "color": _route_color(i),
                    "coords": _path_to_coords(G, full),
                    "distance_km": round(dist_m / 1000, 2),
                    "minutes": minutes,
                    "description": f"도보 · {round(dist_m/1000,1)}km",
                }
            )
        except nx.NetworkXNoPath:
            continue

    if not routes:
        dist_m = _calc_distance(G, direct_path)
        minutes = round(dist_m / WALK_SPEED_MPS / 60)
        routes = [
            {
                "id": "route-1",
                "name": "최단 코스",
                "color": "#39d353",
                "coords": _path_to_coords(G, direct_path),
                "distance_km": round(dist_m / 1000, 2),
                "minutes": minutes,
                "description": f"도보 · {round(dist_m/1000,1)}km",
            }
        ]

    return routes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  헬퍼: 그래프 거리로 노드 탐색
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _nodes_at_distance(G, source, target_m, tolerance=0.35):
    """
    source에서 target_m ± tolerance 거리에 있는 노드 목록 반환.
    그래프가 너무 작으면 가장 가까운 노드들 반환.
    """
    lo = target_m * (1 - tolerance)
    hi = target_m * (1 + tolerance)

    lengths = nx.single_source_dijkstra_path_length(
        G, source, cutoff=hi, weight="length"
    )

    candidates = [n for n, d in lengths.items() if lo <= d <= hi and n != source]

    # 너무 적으면 범위 확장
    if len(candidates) < 6:
        candidates = [n for n, d in lengths.items() if d >= lo * 0.5 and n != source]

    # 너무 많으면 거리 기준으로 균등 샘플링
    if len(candidates) > 60:
        candidates = sorted(candidates, key=lambda n: abs(lengths[n] - target_m))[:60]

    return candidates


def _nodes_near_midpoint(G, start_node, end_node, radius_m):
    """
    start~end 중간 지점 근처 노드 탐색.
    """
    sd = G.nodes[start_node]
    ed = G.nodes[end_node]
    mid_lat = (sd["y"] + ed["y"]) / 2
    mid_lng = (sd["x"] + ed["x"]) / 2

    mid_node = ox.distance.nearest_nodes(G, X=mid_lng, Y=mid_lat)

    lengths = nx.single_source_dijkstra_path_length(
        G, mid_node, cutoff=max(radius_m, 300), weight="length"
    )

    candidates = [n for n, d in lengths.items() if n not in (start_node, end_node)]

    # 방향별로 분산
    def angle_of(n):
        nd = G.nodes[n]
        return math.atan2(nd["y"] - mid_lat, nd["x"] - mid_lng)

    candidates.sort(key=angle_of)

    # 균등 간격으로 3개 선택
    if len(candidates) >= 3:
        step = len(candidates) // 3
        return [candidates[0], candidates[step], candidates[step * 2]]

    return candidates


def _clamp_goal(G, lat, lng, goal_m):
    """
    목표 거리를 그래프 실제 범위 내로 제한.
    그래프 최대 반경의 1.5배를 넘지 않도록.
    """
    nodes_data = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in list(G.nodes)[:500]]
    if not nodes_data:
        return goal_m

    max_dist = max(_haversine(lat, lng, nlat, nlng) for nlat, nlng in nodes_data)
    limit = max_dist * 1.5
    return min(goal_m, limit)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _path_to_coords(G, path):
    return [[G.nodes[n]["x"], G.nodes[n]["y"]] for n in path]


def _calc_distance(G, path):
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = G.get_edge_data(u, v)
        if data:
            total += next(iter(data.values())).get("length", 0)
    return total


def _haversine(lat1, lng1, lat2, lng2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _route_color(i):
    return ["#39d353", "#58a6ff", "#d2a8ff"][i % 3]


def _fallback(lat, lng, goal_km):
    return [
        {
            "id": "route-1",
            "name": "기본 코스",
            "color": "#39d353",
            "coords": [
                [lng, lat],
                [lng + 0.005, lat + 0.005],
                [lng + 0.01, lat],
                [lng, lat],
            ],
            "distance_km": goal_km,
            "minutes": round(goal_km * 15),
            "description": "기본 코스",
        }
    ]
