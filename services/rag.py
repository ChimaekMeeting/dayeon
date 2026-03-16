from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from dotenv import load_dotenv
import os

load_dotenv()

qa_chain = None

DATA_PATH = os.path.join(os.path.dirname(__file__), "../data/extracted_text.txt")

PROMPT_TEMPLATE = """당신은 서울 산책로 추천 전문가입니다.
아래 컨텍스트를 참고하여 사용자 질문에 친절하게 답변하세요.
컨텍스트에 없는 정보는 모른다고 말하세요.

컨텍스트:
{context}

질문: {question}
답변:"""


def init_rag():
    global qa_chain

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw_text = f.read()

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = splitter.create_documents([raw_text])

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = FAISS.from_documents(docs, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    # LCEL 방식 체인
    qa_chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    print("RAG initialized")


def ask(question: str) -> str:
    if qa_chain is None:
        raise RuntimeError("RAG가 초기화되지 않았습니다.")
    return qa_chain.invoke(question)
