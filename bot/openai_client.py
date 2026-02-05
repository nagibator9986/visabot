# openai_client.py
import os
import time
import logging
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Более дешёвая и современная модель по умолчанию
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL", "gpt-4o")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def generate_chat_completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    max_tokens: int = 400,      # было 700 — снизили без потери качества
    temperature: float = 0.2,
    retries: int = 3,
) -> str:
    """
    Универсальный враппер над OpenAI Chat Completions.

    messages — список словарей вида:
      [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY is not set in environment")
        return ""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "model": model or OPENAI_MODEL_DEFAULT,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "n": 1,
    }

    for attempt in range(retries):
        try:
            resp = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    logger.warning("OpenAI returned no choices: %s", data)
                    return ""
                msg = choices[0].get("message", {})
                content = msg.get("content") or ""
                return content.strip()

            # временные ошибки
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = (attempt + 1) * 2
                logger.warning(
                    "OpenAI transient error %s, retry in %ss (attempt %d/%d), body=%s",
                    resp.status_code,
                    wait,
                    attempt + 1,
                    retries,
                    resp.text[:200],
                )
                time.sleep(wait)
                continue

            # остальные — фатальные
            logger.error("OpenAI error %s: %s", resp.status_code, resp.text)
            return ""
        except requests.RequestException as e:
            logger.warning(
                "OpenAI request exception (attempt %d/%d): %s",
                attempt + 1,
                retries,
                e,
            )
            time.sleep(1 + attempt * 2)

    logger.error("OpenAI request failed after %d attempts", retries)
    return ""
