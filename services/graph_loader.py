"""
services/graph_loader.py

eunpyeong_walk.graphml 을 로딩해서 NetworkX 그래프를 반환.
서버 시작 시 1회 로딩 후 메모리에 캐싱.
"""

import os
import osmnx as ox
import networkx as nx

# ── 경로 설정 ──────────────────────────────────────
_BASE = os.path.dirname(__file__)
_GRAPHML = os.path.join(_BASE, "..", "data", "eunpyeong_walk.graphml")
# ──────────────────────────────────────────────────

_graph: nx.MultiDiGraph | None = None


def get_graph() -> nx.MultiDiGraph:
    """
    그래프를 반환. 최초 호출 시 파일에서 로딩, 이후엔 캐싱된 객체 반환.
    """
    global _graph
    if _graph is None:
        _graph = _load()
    return _graph


def _load() -> nx.MultiDiGraph:
    path = os.path.abspath(_GRAPHML)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"graphml 파일이 없어.\n"
            f"먼저 실행: python scripts/download_osm.py\n"
            f"찾은 경로: {path}"
        )

    print(f"[graph_loader] 도로망 로딩 중... ({path})")
    G = ox.load_graphml(path)

    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    print(f"[graph_loader] 로딩 완료 — 노드 {nodes:,}개 / 엣지 {edges:,}개")

    return G


def get_nearest_node(lat: float, lng: float) -> int:
    """
    주어진 위경도에서 가장 가까운 노드 ID 반환.
    """
    G = get_graph()
    return ox.distance.nearest_nodes(G, X=lng, Y=lat)
