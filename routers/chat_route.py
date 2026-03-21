"""
routers/chat_route.py

순환형: 현위치 → (경유) → 현위치
목적형: 현위치 → 목적지 (nkm 이상 돌아서)
"""

from fastapi import APIRouter
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from services.route_engine import generate_loop_routes, generate_waypoint_routes
import osmnx as ox

router = APIRouter()
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 기본 출발지 (구파발역) — 추후 GPS로 교체
DEFAULT_START = {"lat": 37.6347, "lng": 126.9203}


# ── 스키마 ────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    user_lat: float = DEFAULT_START["lat"]
    user_lng: float = DEFAULT_START["lng"]


class ChatResponse(BaseModel):
    reply: str
    routes: list | None = None


# ── 프롬프트 ──────────────────────────────────────

PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
너는 도보/러닝 경로 추천 서비스의 의도 파싱 에이전트야.
사용자 입력을 분석해서 JSON만 반환해. 다른 텍스트 없이.

반환 형식:
{{
  "is_route_request": true/false,
  "type": "loop" | "waypoint",
  "goal_km": 숫자 | null,
  "goal_minutes": 숫자 | null,
  "is_running": true/false,
  "destination": "장소명" | null
}}

규칙:
- 목적지가 명시되면 type = "waypoint", destination = 장소명
- 목적지 없이 거리/시간만 있으면 type = "loop"
- 달리기/러닝/뛰기 → is_running = true

예시:
- "5km 러닝" → {{"is_route_request":true,"type":"loop","goal_km":5.0,"goal_minutes":null,"is_running":true,"destination":null}}
- "30분 산책" → {{"is_route_request":true,"type":"loop","goal_km":null,"goal_minutes":30,"is_running":false,"destination":null}}
- "연신내역까지 걷고 싶어" → {{"is_route_request":true,"type":"waypoint","goal_km":null,"goal_minutes":null,"is_running":false,"destination":"연신내역"}}
- "연신내역까지 5km로 돌아서 가줘" → {{"is_route_request":true,"type":"waypoint","goal_km":5.0,"goal_minutes":null,"is_running":false,"destination":"연신내역"}}
""",
        ),
        ("human", "{message}"),
    ]
)

EXPLAIN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """너는 도보 경로 추천 도우미 루디야.
추천 경로를 친근하게 소개해줘.
규칙: 이모지 최대 2개, 2~3문장, ** ## __ 같은 마크다운 기호 절대 사용 금지.""",
        ),
        (
            "human",
            """
사용자 요청: {message}
경로 유형: {route_type}
{destination_info}
추천 경로:
{routes_summary}

위 경로들을 소개해줘.
""",
        ),
    ]
)


# ── 장소명 → 좌표 ─────────────────────────────────


def geocode_place(place_name: str) -> dict | None:
    """
    OSM geocode로 장소명 → 위경도 변환.
    실패 시 None 반환.
    """
    try:
        lat, lng = ox.geocode(f"{place_name}, 서울")
        return {"lat": lat, "lng": lng, "name": place_name}
    except Exception:
        try:
            # 서울 없이 재시도
            lat, lng = ox.geocode(place_name)
            return {"lat": lat, "lng": lng, "name": place_name}
        except Exception:
            return None


# ── 엔드포인트 ────────────────────────────────────


@router.post("/chat-route")
async def chat_route(req: ChatRequest):

    # 1. 의도 파싱
    parse_chain = PARSE_PROMPT | llm | JsonOutputParser()
    intent = await parse_chain.ainvoke({"message": req.message})

    # 경로 요청 아닌 경우
    if not intent.get("is_route_request"):
        casual = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "너는 도보 경로 추천 도우미 루디야. 마크다운 기호 사용 금지.",
                ),
                ("human", "{message}"),
            ]
        )
        reply = await (casual | llm).ainvoke({"message": req.message})
        return ChatResponse(reply=reply.content, routes=None)

    # 2. 목표 거리 결정
    goal_km = intent.get("goal_km")
    if not goal_km and intent.get("goal_minutes"):
        goal_km = round(intent["goal_minutes"] * 4 / 60, 1)

    route_type = intent.get("type", "loop")
    is_running = intent.get("is_running", False)
    destination = intent.get("destination")

    # 3. 루트 생성
    all_routes = []

    if route_type == "waypoint" and destination:
        # ── 목적형 ──────────────────────────────
        dest = geocode_place(destination)
        if not dest:
            return ChatResponse(
                reply=f"'{destination}' 위치를 찾을 수 없어요. 더 구체적인 장소명을 입력해주세요.",
                routes=None,
            )

        # goal_km 없으면 최단거리로 (알고리즘이 알아서 처리)
        target_km = goal_km or 0.0

        try:
            all_routes = generate_waypoint_routes(
                start_lat=req.user_lat,
                start_lng=req.user_lng,
                end_lat=dest["lat"],
                end_lng=dest["lng"],
                goal_km=target_km,
            )
        except Exception as e:
            return ChatResponse(
                reply="경로 생성에 실패했어요. 다시 시도해 주세요.", routes=None
            )

    else:
        # ── 순환형 ──────────────────────────────
        if not goal_km:
            goal_km = 3.0  # 기본값

        # 거리 변형 3가지 (각각 방향 다른 루트)
        variations = [
            (round(goal_km * 0.8, 1), "A", "#39d353"),
            (goal_km, "B", "#58a6ff"),
            (round(goal_km * 1.3, 1), "C", "#d2a8ff"),
        ]

        for target_km, label, color in variations:
            try:
                routes = generate_loop_routes(
                    start_lat=req.user_lat,
                    start_lng=req.user_lng,
                    goal_km=target_km,
                    is_running=is_running,
                )
                if routes:
                    r = routes[0]
                    r["id"] = f"route-{label}"
                    r["name"] = f"코스 {label}"
                    r["color"] = color
                    all_routes.append(r)
            except Exception:
                continue

    if not all_routes:
        return ChatResponse(
            reply="적합한 경로를 찾지 못했어요. 조건을 바꿔서 다시 시도해 주세요.",
            routes=None,
        )

    # 4. LLM 설명 생성
    routes_summary = "\n".join(
        [f"{r['name']}: {r['distance_km']}km, {r['minutes']}분" for r in all_routes]
    )

    destination_info = f"목적지: {destination}" if destination else ""
    route_type_kr = "목적지 경유형" if route_type == "waypoint" else "순환형"

    explain_chain = EXPLAIN_PROMPT | llm
    explanation = await explain_chain.ainvoke(
        {
            "message": req.message,
            "route_type": route_type_kr,
            "destination_info": destination_info,
            "routes_summary": routes_summary,
        }
    )

    return ChatResponse(reply=explanation.content, routes=all_routes)
