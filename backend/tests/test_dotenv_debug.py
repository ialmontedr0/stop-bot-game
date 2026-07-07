"""Test to verify .env loading in pytest context."""
import os
from dotenv import load_dotenv, find_dotenv

def test_dotenv_loading():
    print(f"\nfind_dotenv()={find_dotenv()!r}")
    loaded = load_dotenv(verbose=False)
    print(f"load_dotenv()={loaded}")
    print(f"SPELL_MODE={os.getenv('SPELL_MODE')!r}")
    print(f"SPELL_AI_PROVIDER={os.getenv('SPELL_AI_PROVIDER')!r}")
    print(f"SPELL_API_KEY={'set' if os.getenv('SPELL_API_KEY') else 'not set'}")
    assert loaded, ".env not found!"
