from fastapi import APIRouter
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel as LCBaseModel

router = APIRouter()


# ── 입력/출력 스키마 ──────────────────────────────────────

class WeightRequest(BaseModel):
    request: str  # "70대 부모님과 잠깐 걷다 오려고 해"

class WeightResponse(BaseModel):
    안전성: float
    자연친화: float
    접근성: float
    보행쾌적성: float
    거리최적화: float
    편의시설: float
    reasoning: str
    user_type: str


# ── LangChain 파이프라인 ──────────────────────────────────

class WeightOutput(LCBaseModel):
    안전성: float = Field(description="사고율, 범죄율, 가로등")
    자연친화: float = Field(description="녹지비율, 공원, 하천")
    접근성: float = Field(description="경사도, 유모차/휠체어 적합성")
    보행쾌적성: float = Field(description="보도폭, 소음, 혼잡도")
    거리최적화: float = Field(description="목표 거리/시간 달성")
    편의시설: float = Field(description="벤치, 화장실, 카페")
    reasoning: str = Field(description="가중치 결정 이유 2-3문장")
    user_type: str = Field(description="예: 고령자 동반, 유아 동반, 러너, 반려동물")

parser = JsonOutputParser(pydantic_object=WeightOutput)

examples = [
    {
        "request": "70대 부모님과 잠깐 걷다 오려고 해",
        "output": '{"안전성":0.25,"자연친화":0.15,"접근성":0.30,"보행쾌적성":0.15,"거리최적화":0.10,"편의시설":0.05,"reasoning":"고령자 동반으로 접근성과 안전성을 최우선 고려했습니다.","user_type":"고령자 동반"}',
    },
    {
        "request": "5km 러닝 코스 추천해줘",
        "output": '{"안전성":0.10,"자연친화":0.15,"접근성":0.05,"보행쾌적성":0.20,"거리최적화":0.40,"편의시설":0.10,"reasoning":"러닝 목적이므로 거리 달성이 가장 중요합니다.","user_type":"러너"}',
    },
    {
        "request": "유모차 끌고 3살 아이와 산책",
        "output": '{"안전성":0.25,"자연친화":0.15,"접근성":0.35,"보행쾌적성":0.10,"거리최적화":0.05,"편의시설":0.10,"reasoning":"유모차 이동을 위해 접근성과 안전성을 높게 설정했습니다.","user_type":"유아 동반"}',
    },
]

example_prompt = ChatPromptTemplate.from_messages([
    ("human", "{request}"),
    ("ai", "{output}"),
])

fewshot = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", """당신은 서울 도보 경로 추천 시스템의 가중치 분석 AI입니다.
6개 레이어 가중치(합=1.0, 각 값 0.05 단위)를 결정하세요.

{format_instructions}"""),
    fewshot,
    ("human", "{request}"),
])

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

weight_chain = prompt | llm | parser


# ── 엔드포인트 ────────────────────────────────────────────

@router.post("/set-weight", response_model=WeightResponse)
async def set_weight(body: WeightRequest):
    result = await weight_chain.ainvoke({
        "request": body.request,
        "format_instructions": parser.get_format_instructions(),
    })
    return result