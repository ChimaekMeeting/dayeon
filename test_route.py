from services.route_engine import generate_loop_routes

routes = generate_loop_routes(
    start_lat=37.6347,
    start_lng=126.9203,
    goal_km=3.0,
    weights={
        "safety": 0.15, "nature": 0.30, "accessibility": 0.20,
        "walking_comfort": 0.20, "distance": 0.10, "amenities": 0.05
    }
)

for r in routes:
    print(r["name"], r["distance_km"], "km", r["minutes"], "분")
