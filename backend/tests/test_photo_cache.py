import os
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.services.photo_cache import PhotoCache


@pytest.fixture
def cache(tmp_path: Path) -> PhotoCache:
    return PhotoCache(cache_dir=tmp_path / "profile_photos", ttl=3600)


# ── Happy path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_photo_downloads_and_caches(cache: PhotoCache):
    """E5: primera llamada descarga de Telegram y guarda en disco+memoria."""
    bot = AsyncMock()
    bot.get_user_profile_photos.return_value = MagicMock(
        total_count=1,
        photos=[[MagicMock(file_id="abc123")]],
    )
    bot.get_file.return_value = MagicMock(file_path="photos/abc123.jpg")
    bot.download_file.return_value = _fake_jpeg_bytes()

    img = await cache.get_photo(bot, 111)

    assert img is not None
    assert img.mode == "RGBA"
    bot.get_user_profile_photos.assert_awaited_once()
    bot.get_file.assert_awaited_once()
    bot.download_file.assert_awaited_once()

    # Archivo en disco
    disk_path = cache._path(111)
    assert disk_path.exists()

    # Memoria poblada
    assert cache._mem.get(111) == str(disk_path)


@pytest.mark.asyncio
async def test_get_photo_returns_cached(cache: PhotoCache):
    """E5: segunda llamada usa caché sin llamar a Telegram."""
    bot = AsyncMock()
    bot.get_user_profile_photos.return_value = MagicMock(
        total_count=1,
        photos=[[MagicMock(file_id="abc123")]],
    )
    bot.get_file.return_value = MagicMock(file_path="photos/abc123.jpg")
    bot.download_file.return_value = _fake_jpeg_bytes()

    # Primera llamada — descarga
    await cache.get_photo(bot, 222)

    bot.reset_mock()

    # Segunda llamada — debe venir de caché
    img = await cache.get_photo(bot, 222)
    assert img is not None
    bot.get_user_profile_photos.assert_not_called()


# ── Sin foto ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_photo_no_photo(cache: PhotoCache):
    """E5: usuario sin foto de perfil → None + caché 'no photo'."""
    bot = AsyncMock()
    bot.get_user_profile_photos.return_value = MagicMock(total_count=0)

    img = await cache.get_photo(bot, 333)
    assert img is None

    # Se cacheó como "no photo"
    assert cache._mem.get(333) == ""


@pytest.mark.asyncio
async def test_get_photo_no_photo_cached(cache: PhotoCache):
    """E5: segunda llamada para usuario sin foto no va a Telegram."""
    bot = AsyncMock()
    bot.get_user_profile_photos.return_value = MagicMock(total_count=0)

    await cache.get_photo(bot, 444)
    bot.reset_mock()

    img = await cache.get_photo(bot, 444)
    assert img is None
    bot.get_user_profile_photos.assert_not_called()


# ── Errores ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_photo_error_returns_none(cache: PhotoCache):
    """E5: error de red → None, no crashea."""
    bot = AsyncMock()
    bot.get_user_profile_photos.side_effect = RuntimeError("API down")

    img = await cache.get_photo(bot, 555)
    assert img is None


# ── Limpieza ────────────────────────────────────────────────────────


def test_clear_expired(cache: PhotoCache):
    """E5: clear_expired elimina archivos con mtime + ttl < now."""
    path = cache._path(999)
    _create_dummy_jpeg(path)

    # Recién creado — no se limpia
    assert cache.clear_expired() == 0
    assert path.exists()

    # Simular tiempo expirado
    old_mtime = time.time() - 7200  # 2h atrás
    os.utime(path, (old_mtime, old_mtime))

    assert cache.clear_expired() == 1
    assert not path.exists()


def test_clear_all(cache: PhotoCache):
    """E5: clear_all elimina todos los archivos y vacía memoria."""
    for tid in [101, 102, 103]:
        _create_dummy_jpeg(cache._path(tid))
    cache._mem[101] = str(cache._path(101))

    assert cache.clear_all() == 3
    assert not any(cache._path(tid).exists() for tid in [101, 102, 103])
    assert 101 not in cache._mem


# ── Helpers ─────────────────────────────────────────────────────────


def _fake_jpeg_bytes() -> BytesIO:
    """Return a BytesIO containing a tiny valid JPEG."""
    from io import BytesIO

    img = Image.new("RGB", (10, 10), (255, 0, 0))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=50)
    buf.seek(0)
    return buf


def _create_dummy_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (20, 20), (0, 255, 0))
    img.save(path, "JPEG", quality=50)
