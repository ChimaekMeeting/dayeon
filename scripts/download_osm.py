"""
scripts/download_osm.py

은평구 보행 도로망을 OSM에서 다운로드해서
data/eunpyeong_walk.graphml 로 저장하는 1회성 스크립트.

실행 방법:
    python scripts/download_osm.py
"""

import osmnx as ox
import os

# ── 설정 ──────────────────────────────────────────
PLACE = "은평구, 서울특별시, South Korea"
OUTDIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTFILE = os.path.join(OUTDIR, "eunpyeong_walk.graphml")
# ──────────────────────────────────────────────────


def download():
    print(f"[1/3] OSM에서 보행 도로망 다운로드 중: {PLACE}")

    G = ox.graph_from_place(
        PLACE,
        network_type="walk",  # 보행 가능한 도로만
        simplify=True,  # 교차점 사이 중간 노드 제거 (용량 절감)
    )

    nodes, edges = ox.graph_to_gdfs(G)
    print(f"[2/3] 다운로드 완료")
    print(f"      노드(교차점) : {len(nodes):,}개")
    print(f"      엣지(도로구간): {len(edges):,}개\n")

    os.makedirs(OUTDIR, exist_ok=True)
    ox.save_graphml(G, OUTFILE)
    print(f"[3/3] 저장 완료 → {OUTFILE}")
    print(f"      파일 크기   : {os.path.getsize(OUTFILE) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    download()
