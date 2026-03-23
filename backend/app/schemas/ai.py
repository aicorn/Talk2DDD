from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)
    provider: Optional[Literal["openai", "deepseek", "minimax"]] = None


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str
