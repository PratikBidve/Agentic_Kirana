"""LLM singleton — instantiated once, shared across all graph nodes."""
from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.core.config import settings


@lru_cache
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=settings.OPENAI_TEMPERATURE,
    )
