"""Quick Groq integration test."""

import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()


async def test():
    key = os.getenv("SPELL_API_KEY")
    url = os.getenv("SPELL_API_URL", "https://api.groq.com/openai/v1")
    model = os.getenv("SPELL_AI_MODEL", "llama-3.3-70b-versatile")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Responde solo con una palabra."},
            {"role": "user", "content": "Corrige: Fenando"},
        ],
        "temperature": 0.0,
        "max_tokens": 20,
    }

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{url.rstrip('/')}/chat/completions", headers=headers, json=payload)
        data = r.json()
        if r.status_code == 200:
            data["choices"][0]["message"]["content"]
        else:
            pass


asyncio.run(test())
