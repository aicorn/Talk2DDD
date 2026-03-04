from fastapi import APIRouter, HTTPException, status
import openai

from app.schemas.ai import ChatRequest, ChatResponse
from app.services.ai_service import chat_completion, get_ai_client
from app.config import settings

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, status_code=200)
async def ai_chat(request: ChatRequest):
    """Send messages to the selected AI provider and return the reply."""
    provider = request.provider or settings.AI_PROVIDER
    _, model = get_ai_client(provider)

    try:
        reply = await chat_completion(
            messages=[m.model_dump() for m in request.messages],
            provider=provider,
        )
    except (openai.OpenAIError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider error: {exc}",
        ) from exc

    return ChatResponse(reply=reply, provider=provider, model=model)
