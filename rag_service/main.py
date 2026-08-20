from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import List, Optional, Any

from rag.pipeline import RAGPipeline
from rag.schema import Retrieved

app = FastAPI()

# Initialise pipeline once at startup using environment variables
pipeline = RAGPipeline.from_env()

class ChatRequest(BaseModel):
    question: str
    top_k: Optional[int] = None

    @validator('question')
    def question_must_be_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('question must be a non‑empty string')
        return v

    @validator('top_k')
    def top_k_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError('top_k must be a positive integer')
        return v

class Source(BaseModel):
    id: str
    text: str
    metadata: Optional[Any] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    try:
        # Retrieve relevant chunks
        retrieved: List[Retrieved] = pipeline.search(req.question, top_k=req.top_k)
        # Generate answer using the same pipeline
        answer: str = pipeline.answer(req.question, retrieved)
        # Transform retrieved objects into simple source dicts
        sources = [
            Source(
                id=getattr(r, "id", ""),
                text=getattr(r, "text", ""),
                metadata=getattr(r, "metadata", None),
            )
            for r in retrieved
        ]
        return ChatResponse(answer=answer, sources=sources)
    except ValueError as ve:
        # Validation errors from Pydantic validators
        raise HTTPException(status_code=400, detail={"error": str(ve), "code": "INVALID_REQUEST"})
    except Exception as e:
        # Return a clean JSON error without stack trace
        return JSONResponse(status_code=500, content={"error": str(e), "code": "RAG_ERROR"})

# Health / liveness endpoint (no RAG logic involved)
@app.get("/health")
async def health_check():
    return {"status": "ok"}
