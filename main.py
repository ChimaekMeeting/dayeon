from fastapi import FastAPI
from routers import chat
from services.rag import init_rag

app = FastAPI(title="Seoul Walking Path RAG Service")


@app.on_event("startup")
async def startup_event():
    init_rag()  # 서버 시작 시 벡터스토어 1회 초기화


app.include_router(chat.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}
