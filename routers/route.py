"""
routers/route.py

/api/route POST 엔드포인트.
루트 유형(loop / waypoint)에 따라 route_engine을 호출하고
GeoJSON 경로 후보를 반환한다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from services.route_engine import generate_loop_routes, generate_waypoint_routes

router = APIRouter()


# ── Request 스키마 ─────────────────────────────────


class Weights(BaseModel):
    safety: float = 0.15
    nature: float = 0.20
    accessibility: float = 0.20
    walking_comfort: float = 0.20
    distance: float = 0.15
    amenities: float = 0.10


class RouteRequest(BaseModel):
    type: str = Field(..., description="loop | waypoint")
    start_lat: float = Field(..., description="출발점 위도")
    start_lng: float = Field(..., description="출발점 경도")
    goal_km: Optional[float] = Field(
        None, description="목표 거리 (km) — loop/waypoint 공통"
    )
    goal_minutes: Optional[int] = Field(
        None, description="목표 시간 (분) — loop 전용, goal_km 없을 때 사용"
    )
    end_lat: Optional[float] = Field(None, description="도착점 위도 — waypoint 전용")
    end_lng: Optional[float] = Field(None, description="도착점 경도 — waypoint 전용")
    is_running: bool = False
    weights: Weights = Weights()


# ── Response 스키마 ───────────────────────────────


class RouteSummary(BaseModel):
    id: str
    name: str
    color: str
    coords: list[list[float]]
    distance_km: float
    minutes: int
    description: str


class RouteResponse(BaseModel):
    routes: list[RouteSummary]


# ── 엔드포인트 ────────────────────────────────────


@router.post("/route", response_model=RouteResponse)
async def create_route(req: RouteRequest):

    weights = req.weights.model_dump()

    # goal_km 없으면 goal_minutes로 환산 (4km/h 기준)
    goal_km = req.goal_km
    if goal_km is None:
        if req.goal_minutes:
            goal_km = round(req.goal_minutes * 4 / 60, 2)  # 분 → km
        else:
            goal_km = 3.0  # 기본값

    try:
        if req.type == "loop":
            routes = generate_loop_routes(
                start_lat=req.start_lat,
                start_lng=req.start_lng,
                goal_km=goal_km,
                weights=weights,
                is_running=req.is_running,
            )

        elif req.type == "waypoint":
            if req.end_lat is None or req.end_lng is None:
                raise HTTPException(
                    status_code=422,
                    detail="waypoint 유형은 end_lat, end_lng 가 필요해요.",
                )
            routes = generate_waypoint_routes(
                start_lat=req.start_lat,
                start_lng=req.start_lng,
                end_lat=req.end_lat,
                end_lng=req.end_lng,
                goal_km=goal_km,
                weights=weights,
            )

        else:
            raise HTTPException(
                status_code=422,
                detail=f"알 수 없는 type: {req.type}. 'loop' 또는 'waypoint' 를 사용하세요.",
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RouteResponse(routes=routes)
