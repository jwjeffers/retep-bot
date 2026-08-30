from __future__ import annotations
"""OpenAI LLM client wrapper for Retep bot."""

import logging
from openai import AsyncOpenAI
from core.config import Config

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Get or create the async OpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


async def generate_response(
    system_prompt: str,
    conversation: list[dict[str, str]],
    max_tokens: int = 300,
) -> str:
    """
    Generate a response given a system prompt and conversation history.

    Args:
        system_prompt: The personality system prompt.
        conversation: List of {"role": "user"/"assistant", "content": "..."} dicts.
        max_tokens: Maximum response length.

    Returns:
        The generated message text.
    """
    client = get_client()

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)

    try:
        response = await client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.9,  # Higher temp for more creative/varied personality
            presence_penalty=0.6,  # Encourage diverse topics
            frequency_penalty=0.3,  # Reduce repetition
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as e:
        logger.error("LLM generate_response failed: %s", e)
        return ""


async def generate_random_message(
    system_prompt: str,
    recent_context: list[dict[str, str]],
    max_tokens: int = 200,
) -> str:
    """
    Generate an unprompted message that fits naturally into the conversation.

    Args:
        system_prompt: The personality system prompt.
        recent_context: Recent channel messages for context.
        max_tokens: Maximum response length.

    Returns:
        The generated message text.
    """
    client = get_client()

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(recent_context)
    # Add a nudge to generate a natural contribution
    messages.append({
        "role": "system",
        "content": (
            "Now contribute to this conversation naturally. Say something relevant "
            "to what's being discussed, or bring up a new topic that fits the server's "
            "interests. Keep it short and casual like a real Discord message. "
            "Do NOT greet anyone or announce yourself."
        ),
    })

    try:
        response = await client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=1.0,  # Even higher temp for unprompted messages
            presence_penalty=0.7,
            frequency_penalty=0.4,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as e:
        logger.error("LLM generate_random_message failed: %s", e)
        return ""
