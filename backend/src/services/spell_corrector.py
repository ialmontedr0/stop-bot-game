import logging
import re
from typing import Optional

from src.core.text_utils import normalize_text

logger = logging.getLogger(__name__)

# --- Word lists semilla por categoria ----------------------------

# Se autoexpanden con respuestas validadas durante el juego.

SEED_WORDS: dict[str, set[str]] = {
    "nombre": {
        "juan",
        "maria",
        "carlos",
        "ana",
        "pedro",
        "laura",
        "diego",
        "sofia",
        "pablo",
        "elena",
        "fernando",
        "luis",
        "carmen",
        "javier",
        "isabel",
        "miguel",
        "rosa",
        "antonio",
        "marta",
        "jose",
        "francisco",
        "manuel",
        "dolores",
        "jesus",
        "margarita",
        "ricardo",
        "patricia",
        "roberto",
        "monica",
        "alejandro",
        "silvia",
        "andres",
        "veronica",
        "sergio",
        "claudia",
        "jorge",
        "beatriz",
        "raul",
        "gloria",
        "alberto",
        "alicia",
    },
    "apellido": {
        "garcia",
        "rodriguez",
        "martinez",
        "lopez",
        "gonzalez",
        "hernandez",
        "perez",
        "sanchez",
        "ramirez",
        "torres",
        "flores",
        "rivera",
        "gomez",
        "diaz",
        "moreno",
        "jimenez",
        "ruiz",
        "alvarez",
        "romero",
        "navarro",
        "castro",
        "ortega",
        "mendoza",
        "delgado",
        "reyes",
        "vargas",
        "herrera",
        "medina",
        "cruz",
        "morales",
        "ortiz",
        "marin",
        "campos",
        "nunez",
        "ibanez",
        "vega",
        "soto",
        "munoz",
        "rivas",
        "aguilar",
    },
    "color": set(),
    "fruta": set(),
    "pais": set(),
    "artista": {
        "shakira",
        "botero",
        "dali",
        "picasso",
        "van gogh",
        "frida kahlo",
        "monet",
        "rembrandt",
        "da vinci",
        "miguel angel",
        "velazquez",
        "goya",
        "matisse",
        "pollock",
        "warhol",
        "klimt",
        "cesar",
        "cerati",
        "mercedes sosa",
        "atahualpa yupanqui",
        "gardel",
        "cortazar",
        "borges",
        "neruda",
        "garcia marquez",
        "messi",
        "maradona",
    },
    "novela/serie": {
        "cien anos de soledad",
        "don quijote",
        "la casa de los espiritus",
        "rayuela",
        "el amor en los tiempos del colera",
        "los simpson",
        "friends",
        "breaking bad",
        "game of thrones",
        "stranger things",
        "la casa de papel",
        "el chavo",
        "el principito",
        "1984",
        "crimen y castigo",
        "orgullo y prejuicio",
        "matar a un ruisenor",
        "harry potter",
        "el senor de los anillos",
        "cancion de hielo y fuego",
    },
    "cosa": {
        "mesa",
        "silla",
        "cama",
        "coche",
        "casa",
        "libro",
        "lapiz",
        "computadora",
        "telefono",
        "reloj",
        "zapato",
        "camisa",
        "plato",
        "vaso",
        "llave",
        "bolsa",
        "ventana",
        "puerta",
        "lampara",
        "cuchara",
        "tenedor",
        "cuchillo",
        "tv",
        "television",
        "radio",
        "bicicleta",
        "moto",
        "avion",
        "barco",
        "tren",
        "pelota",
        "guitarra",
        "piano",
        "bateria",
        "sofa",
        "armario",
        "estante",
        "cuadro",
        "espejo",
    },
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
    DB_CATEGORIES = {"color", "fruta", "pais", "país"}

    def __init__(
        self,
        mode: str = MODE_LOCAL,
        redis_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        api_limit: int = 20,
        fuzzy_threshold: int = 75,
    ) -> None:
        self.mode = mode
        self._redis_url = redis_url
        self._redis = None
        self.api_key = api_key
        self.api_url = api_url
        self.api_limit = api_limit
        self.fuzzy_threshold = fuzzy_threshold
        self._api_calls: int = 0
        # Deep-copy seed words para evitar mutacion global
        self._word_lists: dict[str, set[str]] = {
            cat: set(words) for cat, words in SEED_WORDS.items()
        }

    # --- API calls tracking --------------------------------------------------------

    def reset_api_counter(self) -> None:
        self._api_calls = 0

    @property
    def api_calls_remaining(self) -> int:
        return max(0, self.api_limit - self._api_calls)

    # --- Redis ----------------------------------------------------------------------

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def _get_redis(self):
        if self._redis is None and self._redis_url:
            from redis.asyncio import Redis as AsyncRedis

            self._redis = AsyncRedis.from_url(self._redis_url)
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
    ) -> tuple[Optional[str], float]:
        """Busca el mejor match >= threshold.

        Args:
            word (str): palabra
            candidates (list[str]): listado de candidatos

        Returns:
            tuple[Optional[str], float]: (Candidato, score 0-1)
        """
        from rapidfuzz import fuzz

        word_norm = self.normalize(word)
        best: Optional[str] = None
        best_score: float = 0.0

        for c in candidates:
            c_norm = self.normalize(c)
            # token_sort_ratio maneja reordenamiento de palabras
            score = fuzz.token_sort_ratio(word_norm, c_norm) / 100.0
            if score > best_score:
                best_score = score
                best = c

        if best_score >= self.fuzzy_threshold / 100.0:
            return best, best_score
        return None, 0.0

    # --- Clustering de respuestas para score engine ------------------------------------

    def cluster_answers(
        self,
        answers: list[tuple[int, "Answer"]],  # noqa: F821
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
        from src.services.score_engine import _is_valid_word

        # (pid, answer, normalized_text)
        valid = [
            (pid, ans, self.normalize(ans.raw_text))
            for pid, ans in answers
            if _is_valid_word(ans.raw_text)
        ]
        if not valid:
            return [{pid for pid, _, _ in answers}]

        # Fase 1: exact match clusters
        exact: dict[str, set[int]] = {}
        for pid, _, norm in valid:
            exact.setdefault(norm, set()).add(pid)

        # Fase 2: fuzzy merge de clusters con representante unico
        from rapidfuzz import fuzz

        cluster_list: list[set[int]] = list(exact.values())
        merged = True
        while merged:
            merged = False
            new_clusters: list[set[int]] = []
            used = [False] * len(cluster_list)
            for i, cl in enumerate(cluster_list):
                if used[i]:
                    continue
                rep_i = next(iter(cl))
                norm_i = next(n for p, _, n in valid if p == rep_i)
                for j in range(i + 1, len(cluster_list)):
                    if used[j]:
                        continue
                    rep_j = next(iter(cluster_list[j]))
                    norm_j = next(n for p, _, n in valid if p == rep_j)
                    ratio = fuzz.token_sort_ratio(norm_i, norm_j)
                    if ratio >= self.fuzzy_threshold:
                        cl |= cluster_list[j]
                        used[j] = True
                        merged = True
                new_clusters.append(cl)
                used[i] = True
            cluster_list = new_clusters

        invalid_pids = {pid for pid, _ in answers} - {pid for pid, _, _ in valid}
        for pid in invalid_pids:
            cluster_list.append({pid})

        return cluster_list

    # --- Correccion ortografica --------------------------------------------------------

    async def correct(self, word: str, category: str) -> str:
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
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        cat_words = self._word_lists.setdefault(cat_lower, set())

        # 1 - Ya esta en word list
        if norm in cat_words:
            return norm

        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                best_norm = self.normalize(best)
                # Aprendizaje: anadir a word list
                cat_words.add(norm)
                return best_norm

        # 3 - AI correccion (solo en modo AI o hybryd)
        if (
            self.mode in (self.MODE_AI, self.MODE_HYBRID)
            and self.api_calls_remaining > 0
        ):
            # Check Redis cache
            redis = await self._get_redis()
            cache_key = f"spell:correct:{norm}:{cat_lower}"
            if redis:
                cached = await redis.get(cache_key)
                if cached is not None:
                    decoded = cached.decode() if isinstance(cached, bytes) else cached
                    if decoded:
                        cat_words.add(decoded)
                        return decoded

            corrected = await self._ai_correct(word)
            if corrected:
                self._api_calls += 1
                corrected_norm = self.normalize(corrected)
                cat_words.add(corrected_norm)
                # Cachear en Redis (1 hora)
                if redis:
                    await redis.setex(cache_key, 3600, corrected_norm)
                return corrected_norm

        # 4 - Fallback
        return norm

    async def _ai_correct(self, word: str) -> Optional[str]:
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
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
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
                ],
                "temperature": 0.0,
                "max_tokens": 20,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.api_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                corrected = data["choices"][0]["message"]["content"].strip()
                # Limpiar posibles caracteres extra
                corrected = re.sub(r"[^\w\s\-áéíóúüñ]", "", corrected)
                if corrected and len(corrected) < 100:
                    return corrected
                return None
        except Exception:
            logger.exception("Error en AI correction para '%s'", word)
            return None

    # --- Validacion semantica ----------------------------------------------------------

    async def validate(self, word: str, category: str) -> bool:
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
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        cat_words = self._word_lists.setdefault(cat_lower, set())

        # 1 - En word list
        if norm in cat_words:
            return True

        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                cat_words.add(norm)  # aprender
                return True

        # 3 - AI validation
        if (
            self.mode in (self.MODE_AI, self.MODE_HYBRID)
            and self.api_calls_remaining > 0
        ):
            redis = await self._get_redis()
            cache_key = f"spell:validate:{norm}:{cat_lower}"
            if redis:
                cached = await redis.get(cache_key)
                if cached is not None:
                    val = cached.decode() if isinstance(cached, bytes) else cached
                    self._api_calls += 1
                    return val == "true"

            result = await self._ai_validate(word, category)
            if result is not None:
                self._api_calls += 1
                if redis:
                    await redis.setex(cache_key, 3600, str(result).lower())
                    if result:
                        cat_words.add(norm)
                    return result

        # 4 - Default permisivo
        return True

    async def _ai_validate(self, word: str, category: str) -> Optional[bool]:
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
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Eres un asistente de un juego de Stop. "
                            "Responde solo 'si' o 'no' a si la palabra "
                            "pertenece a la categoria indicada."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Categoria:'{category}'\nPalabra: '{word}'",
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 5,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.api_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip().lower()
                return answer.strip() in ("si", "sí")
        except Exception:
            logger.exception("Error en AI validation para '%s' en %s", word, category)
            return None

    # --- Word list management ----------------------------------------------------------
    def add_to_word_list(self, word: str, category: str) -> None:
        """Añade una palabra a la word list de una categoria.

        Args:
            word (str): _description_
            category (str): _description_
        """
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        self._word_lists.setdefault(cat_lower, set()).add(norm)

    def is_in_word_list(self, word: str, category: str) -> bool:
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
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
                        category, len(words),
                    )
        except Exception:
            logger.exception(
                "Error cargando word lists desde DB — las listas quedan vacias"
            )

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
        cat_key = self._normalize_category(category)
        cat_words = self._word_lists.get(cat_key, set())

        # 1 - Exact match en word list
        if norm in cat_words:
            return True, norm

        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                corrected_norm = self.normalize(best)

                # Aprender: anadir a word list para futuros matches exactos
                cat_words.add(norm)
                return True, corrected_norm

        # 3 - No valido
        return False, norm


# --- Lazy singleton (evita circular imports) ---------------------------------

_corrector_instance: Optional[SpellCorrector] = None


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
        )
    return _corrector_instance
