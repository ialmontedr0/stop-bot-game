import time
from io import BytesIO
from pathlib import Path

from cachetools import TTLCache
from PIL import Image

from aiogram import Bot

_NO_PHOTO = ""
_MEM_MAXSIZE = 1000
_DEFAULT_TTL = 3600
_CACHE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "assets"
    / "cache"
    / "profile_photos"
)


class PhotoCache:
    """Two-tier (memory + disk) cache for Telegram profile photos.

    Usage::

        photo = await photo_cache.get_photo(bot, telegram_id)
        # => PIL Image (RGBA) or None
    """

    def __init__(
        self,
        cache_dir: str | Path = _CACHE_DIR,
        ttl: int = _DEFAULT_TTL,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem: TTLCache[int, str] = TTLCache(maxsize=_MEM_MAXSIZE, ttl=ttl)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_photo(self, bot: Bot, telegram_id: int) -> Image.Image | None:
        """Return cached profile photo or download a fresh one.

        Returns ``None`` when the user has no profile photo, or on any
        error (network, decoding …).  The "no photo" answer is also
        cached for *ttl* seconds.
        """
        cached = self._mem.get(telegram_id)
        if cached is not None:
            if cached == _NO_PHOTO:
                return None
            path = Path(cached)
            if self._is_fresh(path):
                img = self._read_img(path)
                if img is not None:
                    return img

        disk_path = self._path(telegram_id)
        if self._is_fresh(disk_path):
            img = self._read_img(disk_path)
            if img is not None:
                self._mem[telegram_id] = str(disk_path)
                return img

        return await self._download(bot, telegram_id)

    def clear_expired(self) -> int:
        """Remove expired cache files from disk.  Returns count removed."""
        now = time.time()
        count = 0
        for child in self.cache_dir.iterdir():
            if child.is_file() and (now - child.stat().st_mtime) > self.ttl:
                try:
                    child.unlink()
                    count += 1
                except OSError:
                    pass
        return count

    def clear_all(self) -> int:
        """Remove **all** cached photo files and clear the memory cache."""
        count = 0
        for child in self.cache_dir.iterdir():
            if child.is_file():
                try:
                    child.unlink()
                    count += 1
                except OSError:
                    pass
        self._mem.clear()
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _path(self, telegram_id: int) -> Path:
        return self.cache_dir / f"{telegram_id}.jpg"

    def _is_fresh(self, path: Path) -> bool:
        try:
            return path.exists() and (time.time() - path.stat().st_mtime) < self.ttl
        except OSError:
            return False

    @staticmethod
    def _read_img(path: Path) -> Image.Image | None:
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return None

    async def _download(self, bot: Bot, telegram_id: int) -> Image.Image | None:
        try:
            photos = await bot.get_user_profile_photos(user_id=telegram_id, limit=1)
            if photos.total_count == 0:
                self._mem[telegram_id] = _NO_PHOTO
                return None

            file_id = photos.photos[0][-1].file_id
            file = await bot.get_file(file_id)
            buf = await bot.download_file(file.file_path)
            data = buf.read()

            img = Image.open(BytesIO(data)).convert("RGBA")
            disk_path = self._path(telegram_id)
            img.convert("RGB").save(disk_path, "JPEG", quality=85)
            self._mem[telegram_id] = str(disk_path)
            return img
        except Exception:
            return None


photo_cache = PhotoCache()
