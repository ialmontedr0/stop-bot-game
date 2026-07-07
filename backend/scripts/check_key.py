"""Check if the Gemini API key has quota available."""
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

async def check():
    key = os.getenv("SPELL_API_KEY")
    url = os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    
    print(f"Key loaded: {'YES' if key else 'NO'}")
    print(f"Key prefix: {(key or '')[:15]}...")
    print(f"URL: {url}")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
    
    for model in ["gemini-2.0-flash", "gemini-2.5-flash"]:
        url2 = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url2, json=payload)
            print(f"\nNative {model}: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"  Response: {text[:100]}")
            else:
                print(f"  Body: {r.text[:400]}")

asyncio.run(check())
