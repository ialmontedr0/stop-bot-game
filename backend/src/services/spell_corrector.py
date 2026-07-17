from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Coroutine

import httpx
from cachetools import TTLCache

from src.core.text_utils import normalize_text
from src.db.models import Answer
from src.services.score_engine import _is_valid_word

logger = logging.getLogger(__name__)

# --- Word lists semilla por categoria ----------------------------

# Se autoexpanden con respuestas validadas durante el juego.

SEED_WORDS: dict[str, set[str]] = {
    "nombre": set(),
    "apellido": set(),
    "color": set(),
    "fruta": set(),
    "pais": set(),
    "artista": set(),
    "animal": set(),
    "cosa": set(),
}


class SpellCorrector:
    """Corrector ortografico con fuzzy matching y opcional para validacion por IA.

    Tres modos:
    - local: solo fuzzy matching + word lists
    - ai: siempre consulta IA para correccion y validacion
    - hybrid: intenta fuzzy matching primero, cae a IA si no hay match.
    """

    MODE_LOCAL = "local"
    MODE_AI = "ai"
    MODE_HYBRID = "hybrid"
    DB_CATEGORIES = {
        "color",
        "fruta",
        "pais",
        "nombre",
        "apellido",
        "artista",
        "animal",
        "cosa",
    }
    PROVIDER_OPENAI = "openai"

    def __init__(
        self,
        mode: str = MODE_LOCAL,
        redis_url: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        api_limit: int = 20,
        fuzzy_threshold: int = 75,
        ai_provider: str = "openai",
        ai_model: str | None = None,
    ) -> None:
        self.mode = mode
        self._redis_url = redis_url
        self._redis = None
        self.api_key = api_key
        self.api_url = api_url
        self.api_limit = api_limit
        self.fuzzy_threshold = fuzzy_threshold
        self.ai_provider = ai_provider
        self.ai_model = ai_model or self._default_model()
        self._api_calls: dict[int, int] = {}
        self._api_failed: int = 0
        self._validation_source: dict[int, dict[str, str]] = {}
        # Deep-copy seed words para evitar mutacion global
        self._word_lists: dict[str, set[str]] = {
            cat: set(words) for cat, words in SEED_WORDS.items()
        }
        self._mem_cache: TTLCache = TTLCache(maxsize=2000, ttl=3600)
        self._http_client: httpx.AsyncClient | None = None
        self._pending_tasks: set[asyncio.Task] = set()
        self._word_list_lock: asyncio.Lock = asyncio.Lock()

    def _track_task(self, coro: Coroutine) -> asyncio.Task:
        async def _wrapped() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Fire-and-forget task falló en spell_corrector")
            finally:
                self._pending_tasks.discard(task)

        task = asyncio.create_task(_wrapped())
        self._pending_tasks.add(task)
        return task

    async def flush_pending_tasks(self) -> None:
        """Espera a que todas las tareas de persistencia pendientes terminen."""
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)

    def _default_model(self) -> str:
        return "gpt-4o-mini"

    # --- API calls tracking --------------------------------------------------------

    def _get_api_calls(self, group_chat_id: int = 0) -> int:
        return self._api_calls.get(group_chat_id, 0)

    def _inc_api_calls(self, group_chat_id: int = 0) -> None:
        self._api_calls[group_chat_id] = self._api_calls.get(group_chat_id, 0) + 1

    def reset_api_counter(self, group_chat_id: int = 0, game_id: int = 0) -> None:
        self._api_calls[group_chat_id] = 0
        if game_id:
            self._validation_source[game_id] = {}

    def reset_validation_source(self, game_id: int) -> None:
        self._validation_source[game_id] = {}

    def api_calls_remaining(self, group_chat_id: int = 0) -> int:
        return max(0, self.api_limit - self._api_calls.get(group_chat_id, 0))

    def api_calls_total(self, group_chat_id: int = 0) -> int:
        return self._api_calls.get(group_chat_id, 0)

    @property
    def api_calls_failed(self) -> int:
        return self._api_failed

    def get_validation_source(self, game_id: int, key: str) -> str:
        game_sources = self._validation_source.get(game_id)
        if game_sources is None:
            return "default"
        return game_sources.get(key, "default")

    # --- Redis ----------------------------------------------------------------------

    async def close(self) -> None:
        await self.flush_pending_tasks()
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _get_redis(self):
        if self._redis is None and self._redis_url:
            try:
                from redis.asyncio import Redis as AsyncRedis

                self._redis = AsyncRedis.from_url(
                    self._redis_url,
                    connection_kwargs={"socket_connect_timeout": 2},
                )
                await self._redis.ping()
            except Exception:
                logger.warning("Redis no disponible, usando cache en memoria")
                self._redis = None
        return self._redis

    # --- Normalizacion --------------------------------------------------------------

    @staticmethod
    def normalize(raw: str) -> str:
        return normalize_text(raw)

    # --- Fuzzy matching -------------------------------------------------------------

    def fuzzy_match(
        self,
        word: str,
        candidates: list[str],
    ) -> tuple[str | None, float]:
        """Busca el mejor match >= threshold.

        Los candidates deben estar pre-normalizados (D6). Se normaliza
        solo `word` para la comparación.

        Args:
            word (str): palabra
            candidates (list[str]): listado de candidatos (ya normalizados)

        Returns:
            tuple[Optional[str], float]: (Candidato, score 0-1)
        """
        from rapidfuzz import fuzz

        word_norm = self.normalize(word)
        best: str | None = None
        best_score: float = 0.0

        for c in candidates:
            # candidates ya están normalizados (D6)
            score = fuzz.token_sort_ratio(word_norm, c) / 100.0
            if score > best_score:
                best_score = score
                best = c

        if best_score >= self.fuzzy_threshold / 100.0:
            return best, best_score
        return None, 0.0

    # --- Clustering de respuestas para score engine ------------------------------------

    def cluster_answers(
        self,
        answers: list[tuple[int, Answer]],  # noqa: E401
    ) -> list[set[int]]:
        """Agrupa player_ids por respuestas consideradas iguales via fuzzy matching.

        1. Normaliza cada respuesta valida.
        2. Primero agrupa por exact match del normalized_text.
        3. Luego fusiona clusteres con fuzzy match >= threshold.

        Args:
            answers (list[tuple[int, &quot;Answer&quot;]]): _description_

        Returns:
            list[set[int]]: _description_
        """
        # (pid, answer, normalized_text)
        valid = [
            (pid, ans, self.normalize(ans.raw_text))
            for pid, ans in answers
            if _is_valid_word(ans.raw_text)
        ]
        if not valid:
            return [{pid} for pid, _ in answers]

        # Fase 1: exact match clusters
        exact: dict[str, set[int]] = {}
        for pid, _, norm in valid:
            exact.setdefault(norm, set()).add(pid)

        # Fase 2: fuzzy merge de clusters con union-find (O(n²))
        from rapidfuzz import fuzz

        norm_map = {pid: norm for pid, _, norm in valid}
        cluster_list: list[set[int]] = list(exact.values())
        n = len(cluster_list)
        if n > 1:
            parent = list(range(n))

            def _find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def _union(x: int, y: int) -> None:
                rx, ry = _find(x), _find(y)
                if rx != ry:
                    parent[ry] = rx

            norm_reps = [norm_map[next(iter(cl))] for cl in cluster_list]
            for i in range(n):
                for j in range(i + 1, n):
                    if fuzz.token_sort_ratio(norm_reps[i], norm_reps[j]) >= 85:
                        _union(i, j)

            merged: dict[int, set[int]] = {}
            for i, cl in enumerate(cluster_list):
                root = _find(i)
                if root in merged:
                    merged[root] |= cl
                else:
                    merged[root] = cl
            cluster_list = list(merged.values())

        invalid_pids = {pid for pid, _ in answers} - {pid for pid, _, _ in valid}
        for pid in invalid_pids:
            cluster_list.append({pid})

        return cluster_list

    # --- Correccion ortografica --------------------------------------------------------

    async def correct(
        self, word: str, category: str, mode: str | None = None, group_chat_id: int = 0
    ) -> str:
        """Devuelve la forma corregida/normalizada de la palabra.

        Pipeline:
        1. Normalizar
        2. Si esta en word list -> OK
        3. Fuzzy match contra word list -> si match >= threshold, OK
        4. [hybrid/ai] -> IA correccion(cacheado en Redis)
        5. Fallback -> normalized form

        Args:
            word (str): _description_
            category (str): _description_

        Returns:
            str: _description_
        """
        effective_mode = mode or self.mode
        norm = self.normalize(word)
        cat_lower = self._normalize_category(category)
        cat_words = self._word_lists.setdefault(cat_lower, set())

        # 1 - Ya esta en word list
        if norm in cat_words:
            return norm

        # 2 - Fuzzy match contra word list
        if cat_words and effective_mode != self.MODE_AI:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                best_norm = self.normalize(best)
                cat_words.add(best_norm)
                self._track_task(
                    self.add_to_word_list_persistent(best, category)
                )
                return best_norm

        # 3 - AI correccion (solo en modo AI o hybryd)
        if (
            effective_mode in (self.MODE_AI, self.MODE_HYBRID)
            and self.api_calls_remaining(group_chat_id) > 0
        ):
            mem_cache_key = f"correct:{norm}:{cat_lower}"
            mem_cached = self._mem_cache.get(mem_cache_key)
            if mem_cached is not None:
                cat_words.add(mem_cached)
                self._track_task(
                    self.add_to_word_list_persistent(mem_cached, category)
                )
                return mem_cached

            redis = await self._get_redis()
            cache_key = f"spell:correct:{norm}:{cat_lower}"
            if redis:
                cached = await redis.get(cache_key)
                if cached is not None:
                    decoded = cached.decode() if isinstance(cached, bytes) else cached
                    if decoded:
                        cat_words.add(decoded)
                        self._track_task(
                            self.add_to_word_list_persistent(decoded, category)
                        )
                        return decoded

            corrected = await self._ai_correct(word)
            if corrected:
                self._inc_api_calls(group_chat_id)
                corrected_norm = self.normalize(corrected)
                cat_words.add(corrected_norm)
                self._track_task(
                    self.add_to_word_list_persistent(corrected_norm, category)
                )
                self._mem_cache[mem_cache_key] = corrected_norm
                if redis:
                    await redis.setex(cache_key, 3600, corrected_norm)
                return corrected_norm
            else:
                self._api_failed += 1

        # 4 - Fallback
        return norm

    async def _ai_correct(self, word: str) -> str | None:
        """Corrige una palabra usando API de OpenAI (o compatible)

        Args:
            word (str): _description_

        Returns:
            Optional[str]: _description_
        """
        if not self.api_key or not self.api_url:
            logger.warning("AI correction llamada sin API key/URL configurada")
            return None

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            model = self.ai_model
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente de lengua española. "
                        "Corrige la palabra al español correcto. "
                        "Devuelve SOLO la palabra corregida, nada mas. "
                        "Si la palabra ya es correcta, devuelvela igual. "
                    ),
                },
                {"role": "user", "content": word},
            ]

            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 20,
            }

            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

            resp = await self._http_client.post(
                f"{self.api_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            choices = data.get("choices")
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content")

            if content is None:
                return None
            corrected = content.strip()
            corrected = re.sub(r"[^\w\s\-áéíóúüñÁÉÍÓÚÜÑ]", "", corrected)
            if corrected and len(corrected) < 100:
                return corrected
            return None
        except httpx.TimeoutException:
            logger.warning("Timeout en AI correction para '%s'", word)
            self._api_failed += 1
            return None
        except Exception:
            logger.exception("Error en AI correction para '%s'", word)
            self._api_failed += 1
            return None

    # --- Validacion semantica ----------------------------------------------------------

    async def validate(
        self,
        word: str,
        category: str,
        mode: str | None = None,
        game_id: int = 0,
        group_chat_id: int = 0,
    ) -> bool:
        """La palabra pertenece a la categoria?

        Pipeline:
        1. Check word list
        2. Fuzzy match contra word list
        3. [hybrid/ai] -> IA validation
        4. True por defecto (mejor ser permisivo)

        Args:
            word (str): _description_
            category (str): _description_

        Returns:
            bool: _description_
        """
        effective_mode = mode or self.mode
        norm = self.normalize(word)
        cat_lower = self._normalize_category(category)
        cat_words = self._word_lists.setdefault(cat_lower, set())
        game_sources = self._validation_source.setdefault(game_id, {})

        # 0 - Rechazar respuestas de 1 solo caracter (letra suelta)
        if len(norm) < 2:
            game_sources[f"{cat_lower}:{norm}"] = "too_short"
            return False

        # 1 - En word list
        if norm in cat_words:
            game_sources[f"{cat_lower}:{norm}"] = "word_list"
            return True

        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                best_norm = self.normalize(best)
                cat_words.add(best_norm)
                self._track_task(
                    self.add_to_word_list_persistent(best, category)
                )
                game_sources[f"{cat_lower}:{norm}"] = "fuzzy"
                return True

        # 3 - AI validation
        if (
            effective_mode in (self.MODE_AI, self.MODE_HYBRID)
            and self.api_calls_remaining(group_chat_id) > 0
        ):
            mem_cache_key = f"validate:{norm}:{cat_lower}"
            mem_cached = self._mem_cache.get(mem_cache_key)
            if mem_cached is not None:
                val = mem_cached
                if val == "true":
                    cat_words.add(norm)
                    self._track_task(
                        self.add_to_word_list_persistent(norm, category)
                    )
                game_sources[f"{cat_lower}:{norm}"] = "mem_cache"
                return val == "true"

            redis = await self._get_redis()
            cache_key = f"spell:validate:{norm}:{cat_lower}"
            if redis:
                cached = await redis.get(cache_key)
                if cached is not None:
                    val = cached.decode() if isinstance(cached, bytes) else cached
                    if val == "true":
                        cat_words.add(norm)
                        self._track_task(
                            self.add_to_word_list_persistent(norm, category)
                        )
                    game_sources[f"{cat_lower}:{norm}"] = "ai_cache"
                    return val == "true"

            result = await self._ai_validate(word, category)
            if result is not None:
                self._inc_api_calls(group_chat_id)
                self._mem_cache[mem_cache_key] = str(result).lower()
                if redis:
                    await redis.setex(cache_key, 3600, str(result).lower())
                if result:
                    cat_words.add(norm)
                    self._track_task(
                        self.add_to_word_list_persistent(norm, category)
                    )
                    game_sources[f"{cat_lower}:{norm}"] = "ai"
                    return True
                else:
                    game_sources[f"{cat_lower}:{norm}"] = "ai_rejected"
                    return False

            else:
                self._api_failed += 1

        # 4 - Default permisivo (API agotada o modo local)
        # Solo aprender en modo local; en hybrid/ai con API agotada,
        # aceptamos la palabra pero no la aprendemos (D7)
        if effective_mode == self.MODE_LOCAL:
            cat_words.add(norm)
            self._track_task(self.add_to_word_list_persistent(norm, category))
            game_sources[f"{cat_lower}:{norm}"] = "default_learned"
        else:
            game_sources[f"{cat_lower}:{norm}"] = "default_temp"
        return True

    async def validate_batch(
        self,
        answers: dict[str, str],
        game_id: int = 0,
        mode: str | None = None,
        group_chat_id: int = 0,
    ) -> dict[str, bool]:
        """Valida hasta 8 categorias en una sola llamada API.

        Pipeline por categoria:
        1. Word list exact match
        2. Fuzzy match contra word list
        3. Cache (memoria + Redis)
        4. Batch AI call unico para las pendientes
        5. Fallback permisivo

        Args:
            answers: {category_name: raw_text}
            game_id: para validation_source tracking
            mode: "local" | "ai" | "hybrid"

        Returns:
            {category_name: is_valid}
        """
        effective_mode = mode or self.mode
        game_sources = self._validation_source.setdefault(game_id, {})
        result: dict[str, bool] = {}
        ai_candidates: dict[str, str] = {}

        for category, raw_text in answers.items():
            if not raw_text or not raw_text.strip():
                result[category] = True
                continue

            norm = self.normalize(raw_text)
            cat_lower = self._normalize_category(category)
            cat_words = self._word_lists.setdefault(cat_lower, set())

            # 0 - Rechazar respuestas de 1 caracter
            if len(norm) < 2:
                game_sources[f"{cat_lower}:{norm}"] = "too_short"
                result[category] = False
                continue

            # 1 - Word list exact match
            if norm in cat_words:
                game_sources[f"{cat_lower}:{norm}"] = "word_list"
                result[category] = True
                continue

            # 2 - Fuzzy match contra word list
            if cat_words:
                best, score = self.fuzzy_match(raw_text, list(cat_words))
                if best is not None:
                    best_norm = self.normalize(best)
                    cat_words.add(best_norm)
                    self._track_task(
                        self.add_to_word_list_persistent(best, category)
                    )
                    game_sources[f"{cat_lower}:{norm}"] = "fuzzy"
                    result[category] = True
                    continue

            # 3 - Cache (memoria + Redis)
            if (
                effective_mode in (self.MODE_AI, self.MODE_HYBRID)
                and self.api_calls_remaining(group_chat_id) > 0
            ):
                mem_cache_key = f"validate:{norm}:{cat_lower}"
                mem_cached = self._mem_cache.get(mem_cache_key)
                if mem_cached is not None:
                    val = mem_cached == "true"
                    if val:
                        cat_words.add(norm)
                        self._track_task(
                            self.add_to_word_list_persistent(norm, category)
                        )
                    game_sources[f"{cat_lower}:{norm}"] = "mem_cache"
                    result[category] = val
                    continue

                redis = await self._get_redis()
                cache_key = f"spell:validate:{norm}:{cat_lower}"
                if redis:
                    cached = await redis.get(cache_key)
                    if cached is not None:
                        val = (cached.decode() if isinstance(cached, bytes) else cached) == "true"
                        if val:
                            cat_words.add(norm)
                            self._track_task(
                                self.add_to_word_list_persistent(norm, category)
                            )
                        game_sources[f"{cat_lower}:{norm}"] = "ai_cache"
                        result[category] = val
                        continue

                # Pendiente de IA
                ai_candidates[category] = raw_text
            else:
                # Default permisivo (API agotada o modo local)
                cat_words.add(norm)
                self._track_task(
                    self.add_to_word_list_persistent(norm, category)
                )
                game_sources[f"{cat_lower}:{norm}"] = "default"
                result[category] = True

        # 4 - Batch AI call
        if ai_candidates:
            if self.api_calls_remaining(group_chat_id) > 0:
                ai_results = await self._ai_validate_batch(ai_candidates)
                if ai_results is not None:
                    self._inc_api_calls(group_chat_id)
                    for cat, is_valid in ai_results.items():
                        raw = answers[cat]
                        n = self.normalize(raw)
                        cl = self._normalize_category(cat)
                        if is_valid:
                            self._mem_cache[f"validate:{n}:{cl}"] = "true"
                            cat_words = self._word_lists.setdefault(cl, set())
                            cat_words.add(n)
                            self._track_task(
                                self.add_to_word_list_persistent(n, cat)
                            )
                            game_sources[f"{cl}:{n}"] = "ai"
                        else:
                            game_sources[f"{cl}:{n}"] = "ai_rejected"
                        result[cat] = is_valid
                else:
                    # Fallback: validar cada una individualmente
                    self._api_failed += 1
                    for cat, raw_text in ai_candidates.items():
                        is_valid = await self.validate(
                            raw_text,
                            cat,
                            mode=effective_mode,
                            game_id=game_id,
                            group_chat_id=group_chat_id,
                        )
                        result[cat] = is_valid
            else:
                # API agotada - default permisivo
                for cat, raw_text in ai_candidates.items():
                    n = self.normalize(raw_text)
                    cl = self._normalize_category(cat)
                    cat_words = self._word_lists.setdefault(cl, set())
                    cat_words.add(n)
                    self._track_task(self.add_to_word_list_persistent(n, cat))
                    game_sources[f"{cl}:{n}"] = "default"
                    result[cat] = True

        return result

    async def _ai_validate(self, word: str, category: str) -> bool | None:
        """Pregunta a la IA si la palabra pertenece a la categoria.

        Args:
            word (str): _description_
            category (str): _description_

        Returns:
            Optional[bool]: _description_
        """
        if not self.api_key or not self.api_url:
            return None

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            model = self.ai_model
            system_prompt = (
                "Eres un asistente de un juego de Stop. "
                "Responde solo 'si' o 'no' a si la palabra "
                "pertenece a la categoria indicada.\n\n"
                "Reglas:\n"
                "- Nombres: acepta cualquier nombre propio, "
                "incluyendo diminutivos (Gaby, Pepe), "
                "nombres indigenas (Huascar, Yáhuar), "
                "extranjeros (John, Fatima) y poco comunes.\n"
                "- Apellidos: acepta cualquier apellido real "
                "o possible, incluyendo extranjeros, "
                "compuestos (Del Toro, Da Silva) "
                "y poco comunes.\n"
                "- Frutas: acepta toda fruta comestible, "
                "incluyendo variedades regionales, "
                "exoticas (Mangostan, Carambola) "
                "y frutos secos (Almendra, Nuez).\n"
                "- Artistas: acepta cualquier musico, "
                "cantante o banda, actores/actrices, escritores, incluyendo famosos, "
                "locales y emergentes.\n"
                "- Animales: acepta cualquier animal "
                "real, incluyendo razas, variedades y "
                "nombres cientificos.\n"
                "- Cosas: acepta cualquier objeto, "
                "instrumento, herramienta, mueble, "
                "prenda, electrodomestico, juguete.\n\n"
                "IMPORTANTE: Responde 'no' si no estas SEGURO de que existe. "
                "No aceptes nombres inventados aunque suenen plausibles."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Categoria:'{category}'\nPalabra: '{word}'",
                },
            ]

            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 5,
            }

            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
            resp = await self._http_client.post(
                f"{self.api_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices")
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content")
            if content is None:
                return None
            answer = content.strip().lower()
            return answer.startswith("si") or answer.startswith("sí")
        except httpx.TimeoutException:
            logger.warning("Timeout en AI validation para '%s' en %s", word, category)
            return None
        except Exception:
            logger.exception("Error en AI validation para '%s' en %s", word, category)
            return None

    async def _ai_validate_batch(self, answers: dict[str, str]) -> dict[str, bool] | None:
        """Valida multiples categorias en una sola llamada API.

        Envia todas las categorias y palabras en un unico prompt.
        Espera respuesta: "si, no, si, si, no, ..." en el mismo orden.

        Args:
            answers: {category_name: raw_text}

        Returns:
            dict {category_name: is_valid} o None si fallo
        """
        if not self.api_key or not self.api_url:
            return None

        try:
            lines = [f"{i + 1}. {cat}: {word}" for i, (cat, word) in enumerate(answers.items())]
            categories_text = "\n".join(lines)
            category_count = len(answers)

            system_prompt = (
                "Eres un asistente de un juego de Stop. "
                "Para cada categoria, responde SOLO 'si' o 'no' "
                "si la palabra pertenece a la categoria indicada.\n\n"
                "Reglas:\n"
                "- Nombres: acepta cualquier nombre propio, "
                "incluyendo diminutivos (Gaby, Pepe), "
                "nombres indigenas (Huascar, Yahuar), "
                "extranjeros (John, Fatima) y poco comunes.\n"
                "- Apellidos: acepta cualquier apellido real "
                "o possible, incluyendo extranjeros, "
                "compuestos (Del Toro, Da Silva) "
                "y poco comunes.\n"
                "- Frutas: acepta toda fruta comestible, "
                "incluyendo variedades regionales, "
                "exoticas (Mangostan, Carambola) "
                "y frutos secos (Almendra, Nuez).\n"
                "- Artistas: acepta cualquier musico, "
                "cantante o banda, actores/actrices, escritores, "
                "incluyendo famosos, locales y emergentes.\n"
                "- Animales: acepta cualquier animal "
                "real, incluyendo razas, variedades y "
                "nombres cientificos.\n"
                "- Cosas: acepta cualquier objeto, "
                "instrumento, herramienta, mueble, "
                "prenda, electrodomestico, juguete.\n\n"
                "IMPORTANTE: Responde 'no' si no estas SEGURO de que existe.\n\n"
                "Categorias y palabras:\n"
                f"{categories_text}\n\n"
                "Responde SOLO con 'si' o 'no' para cada una, "
                "en el mismo orden, separado por comas.\n"
                "Ejemplo: si, no, si, si, no, si, no, si"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Valida estas {category_count} categorias.",
                },
            ]

            payload = {
                "model": self.ai_model,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 50,
            }

            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

            resp = await self._http_client.post(
                f"{self.api_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            choices = data.get("choices")
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content")

            if not content:
                return None

            # Parsear respuesta: "si, no, si, ..."
            parts = [p.strip().lower().rstrip(".,;") for p in content.split(",")]
            categories_list = list(answers.keys())
            result: dict[str, bool] = {}
            for i, cat in enumerate(categories_list):
                if i < len(parts):
                    result[cat] = parts[i].startswith("si") or parts[i].startswith("sí")
                else:
                    result[cat] = True  # default permisivo si faltan

            return result

        except httpx.TimeoutException:
            logger.warning("Timeout en batch AI validation para %d categorias", len(answers))
            return None
        except Exception:
            logger.exception("Error en batch AI validation para %d categorias", len(answers))
            return None

    # Copia el set de palabras para evitar race condition
    def _get_word_list_safe(self, category: str) -> set[str]:
        """RETORNA COPIA del set de palabras para evitar race condition."""
        cat_lower = self._normalize_category(category)
        return set(self._word_lists.get(cat_lower, set()))

    # --- Word list management ----------------------------------------------------------
    async def add_to_word_list_persistent(
        self, word: str, category: str, source: str = "learned"
    ) -> None:
        """Añade una palabra a la word list de una categoria.

        Args:
            word (str): _description_
            category (str): _description_
        """
        norm = self.normalize(word)
        cat_lower = self._normalize_category(category)

        # Memoria (protegido por lock)
        async with self._word_list_lock:
            self._word_lists.setdefault(cat_lower, set()).add(norm)

        # BD
        try:
            from src.db.engine import async_session_factory
            from src.db.repositories.word_list_repository import WordListRepository

            async with async_session_factory() as session:
                repo = WordListRepository(session)
                exists = await repo.word_exists(norm, cat_lower)

                if not exists:
                    from src.db.models import WordListItem

                    session.add(
                        WordListItem(
                            category=cat_lower,
                            word=word.strip(),
                            normalized=norm,
                            source=source,
                        )
                    )
                    await session.commit()
        except Exception:
            logger.exception("Error persistiendo palabra aprendida: %s -> %s", word, cat_lower)

    def is_in_word_list(self, word: str, category: str) -> bool:
        norm = self.normalize(word)
        cat_lower = self._normalize_category(category)
        return norm in self._word_lists.get(cat_lower, set())

    # --- Carga desde base de datos -----------------------------------------------------
    async def load_db_word_lists(self) -> None:
        """Carga color/fruta/pais desde la BD y los fusiona en _word_lists.
        Debe llamarse una vez al iniciar el bot, cuando la BD este disponible.

        Si falla la conexion, mantiene las listas vacias (todo se rechazara
        hasta el proximo reinicio).
        """
        from src.db.engine import async_session_factory
        from src.db.repositories.word_list_repository import WordListRepository

        try:
            async with async_session_factory() as session:
                repo = WordListRepository(session)
                for category in self.DB_CATEGORIES:
                    words = await repo.get_words_by_category(category)
                    self._word_lists[category] = set(words)
                    logger.info(
                        "Word List cargada desde DB: %s = %d palabras",
                        category,
                        len(words),
                    )
        except Exception:
            logger.exception("Error cargando word lists desde DB — las listas quedan vacias")

    @staticmethod
    def _normalize_category(category: str) -> str:
        """Normaliza nombre de categoria: lowercase + sin acentos."""
        return normalize_text(category)

    def is_db_category(self, category: str) -> bool:
        """Retorna True si la categoria es valida contra la BD."""
        return self._normalize_category(category) in self.DB_CATEGORIES

    def validate_against_list(self, word: str, category: str) -> tuple[bool, str]:
        """Valida una palabra contra la word list de su categoria.

        Args:
            word (str): palabra a validar
            category (str): Categoria (ej: 'Pais', 'Color')

        Returns:
            tuple[bool, str]: (es_valida, forma_normalizada_corregida)
            Si no es valida, la forma normalizada es la original sin correccion.
        """
        norm = self.normalize(word)
        cat_words = self._get_word_list_safe(category)

        # 1 - Exact match en word list
        if norm in cat_words:
            return True, norm

        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                corrected_norm = self.normalize(best)
                cat_words.add(corrected_norm)
                return True, corrected_norm

        # 3 - No valido
        return False, norm

    def get_api_metrics(self, group_chat_id: int = 0) -> dict:
        """Retorna metricas de llamadas a API para el reporte de ErrorTracker.

        Returns:
            dict:
            - total_calls = total de llamadas
            - failed_calls = llamadas fallidas
            - remaining = cantidad de llamadas a la API restantes
            - limit = limite de llamadas a la API
            - provider = proveedor de AI
            - modo = modo
        """
        return {
            "total_calls": self._api_calls.get(group_chat_id, 0),
            "failed_calls": self._api_failed,
            "remaining": self.api_calls_remaining(group_chat_id),
            "limit": self.api_limit,
            "provider": self.ai_provider,
            "mode": self.mode,
        }


# --- Lazy singleton (evita circular imports) ---------------------------------

_corrector_instance: SpellCorrector | None = None


def get_corrector() -> SpellCorrector:
    global _corrector_instance
    if _corrector_instance is None:
        from src.core.config import settings

        _corrector_instance = SpellCorrector(
            mode=settings.spell_mode,
            redis_url=settings.redis_url,
            api_key=settings.spell_api_key,
            api_url=settings.spell_api_url,
            api_limit=settings.spell_api_limit,
            fuzzy_threshold=settings.spell_fuzzy_threshold,
            ai_provider=settings.spell_ai_provider,
            ai_model=settings.spell_ai_model,
        )
    return _corrector_instance
