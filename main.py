from fastapi import FastAPI
from routers import chat, weight, route
from services.rag import init_rag
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager


app = FastAPI(title="Seoul Walking Path RAG Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_rag()
    yield


app.include_router(chat.router, prefix="/api")
app.include_router(weight.router, prefix="/api")
app.include_router(route.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
