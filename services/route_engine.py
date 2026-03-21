"""
services/route_engine.py

가중치 없이 순수 도보 경로만 생성.
가중치 반영은 PostGIS + H3 구축 후 추가 예정.
"""

import math
import networkx as nx
import osmnx as ox
from services.graph_loader import get_graph, get_nearest_node


WALK_SPEED_MPS = 4 * 1000 / 3600  # 4 km/h → m/s
RUN_SPEED_MPS = 8 * 1000 / 3600  # 8 km/h → m/s
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
    goal_m = goal_km * 1000

    start_node = get_nearest_node(start_lat, start_lng)
    start_data = G.nodes[start_node]
    slat, slng = start_data["y"], start_data["x"]

    # 목표 거리의 1/3 지점에 경유지 2개를 서로 다른 방향으로 배치
    r = goal_m / 3
    delta_lat = r / 111_000
    delta_lng = r / (111_000 * math.cos(math.radians(slat)))

    # 서로 다른 방향 쌍으로 루트 후보 생성
    angle_pairs = [
        (0, 2 * math.pi / 3),
        (math.pi / 4, math.pi),
        (math.pi / 2, 3 * math.pi / 2),
        (math.pi, 5 * math.pi / 3),
        (math.pi / 6, math.pi * 4 / 3),
        (math.pi / 3, math.pi * 5 / 4),
        (math.pi * 2 / 3, math.pi * 7 / 4),
        (math.pi * 3 / 2, math.pi / 5),
    ]

    routes = []

    for angle1, angle2 in angle_pairs:
        if len(routes) >= ROUTE_COUNT:
            break
        try:
            mid1 = ox.distance.nearest_nodes(
                G,
                X=slng + delta_lng * math.cos(angle1),
                Y=slat + delta_lat * math.sin(angle1),
            )
            mid2 = ox.distance.nearest_nodes(
                G,
                X=slng + delta_lng * math.cos(angle2),
                Y=slat + delta_lat * math.sin(angle2),
            )

            if mid1 == mid2 or mid1 == start_node or mid2 == start_node:
                continue

            path1 = nx.shortest_path(G, start_node, mid1, weight="length")
            path2 = nx.shortest_path(G, mid1, mid2, weight="length")
            path3 = nx.shortest_path(G, mid2, start_node, weight="length")
            full = path1 + path2[1:] + path3[1:]

            dist_m = _calc_distance(G, full)
            minutes = round(dist_m / speed / 60)

            routes.append(
                {
                    "id": f"route-{len(routes)+1}",
                    "name": ["추천 코스 A", "추천 코스 B", "추천 코스 C"][len(routes)],
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
#  경유 루트 (A → B)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_waypoint_routes(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    goal_km: float,
    weights: dict = {},
) -> list[dict]:

    G = get_graph()
    start_node = get_nearest_node(start_lat, start_lng)
    end_node = get_nearest_node(end_lat, end_lng)

    mid_lat = (start_lat + end_lat) / 2
    mid_lng = (start_lng + end_lng) / 2
    goal_m = goal_km * 1000

    direct_path = nx.shortest_path(G, start_node, end_node, weight="length")
    direct_m = _calc_distance(G, direct_path)
    extra_r = max((goal_m - direct_m) / 2, 200)

    delta_lat = extra_r / 111_000
    delta_lng = extra_r / (111_000 * math.cos(math.radians(mid_lat)))
    angles = [i * (2 * math.pi / ROUTE_COUNT) for i in range(ROUTE_COUNT)]

    routes = []

    for i, angle in enumerate(angles):
        try:
            via = ox.distance.nearest_nodes(
                G,
                X=mid_lng + delta_lng * math.cos(angle),
                Y=mid_lat + delta_lat * math.sin(angle),
            )
            path1 = nx.shortest_path(G, start_node, via, weight="length")
            path2 = nx.shortest_path(G, via, end_node, weight="length")
            full = path1 + path2[1:]

            dist_m = _calc_distance(G, full)
            minutes = round(dist_m / WALK_SPEED_MPS / 60)

            routes.append(
                {
                    "id": f"route-{i+1}",
                    "name": ["추천 코스 A", "추천 코스 B", "추천 코스 C"][i],
                    "color": _route_color(i),
                    "coords": _path_to_coords(G, full),
                    "distance_km": round(dist_m / 1000, 2),
                    "minutes": minutes,
                    "description": f"도보 · {round(dist_m/1000,1)}km",
                }
            )

        except nx.NetworkXNoPath:
            continue

    return routes if routes else _fallback(start_lat, start_lng, goal_km)


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
