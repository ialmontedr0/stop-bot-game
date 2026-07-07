"""Quick Groq integration test."""
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

async def test():
    key = os.getenv("SPELL_API_KEY")
    url = os.getenv("SPELL_API_URL", "https://api.groq.com/openai/v1")
    model = os.getenv("SPELL_AI_MODEL", "llama-3.3-70b-versatile")

    print(f"Key: {'set' if key else 'NOT SET'}")
    print(f"URL: {url}")
    print(f"Model: {model}")

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
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = data["choices"][0]["message"]["content"]
            print(f"Content: {content!r}")
        else:
            print(f"Error: {data}")

asyncio.run(test())
