"""Test to verify .env loading in pytest context."""

from dotenv import load_dotenv


def test_dotenv_loading():
    loaded = load_dotenv(verbose=False)
    assert loaded, ".env not found!"
