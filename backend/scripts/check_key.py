"""Check if the Gemini API key has quota available."""

import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()


async def check():
    key = os.getenv("SPELL_API_KEY")
    os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai")

    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}

    for model in ["gemini-2.0-flash", "gemini-2.5-flash"]:
        url2 = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url2, json=payload)
            if r.status_code == 200:
                data = r.json()
                data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                pass


asyncio.run(check())
