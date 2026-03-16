from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.rag import ask

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")
    try:
        answer = ask(req.message)
        return ChatResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
