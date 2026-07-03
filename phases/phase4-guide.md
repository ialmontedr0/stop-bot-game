# Phase 4 — Corrector ortográfico con IA / Fuzzy Matching

**Objetivo:** El bot entiende variaciones ortográficas, normaliza respuestas y detecta duplicados mediante fuzzy matching, con validación semántica opcional por IA.

---

## Arquitectura

### Flujo de normalización y validación

```
submit_answers()
  └─ save_answers()
       ├─ normalize_text() a cada valor (strip, lower, sin tildes, conserva espacios)
       └─ guarda raw_text + normalized_text en Answer

_persist_round_scores()
  └─ ScoreEngine.evaluate()
       ├─ _group_by_category()  [sin cambios]
       └─ _determine_answer_scores()
            ├─ Si NO hay SpellCorrector → exact matching (comportamiento original)
            └─ Si hay SpellCorrector → fuzzy clustering con rapidfuzz
                 ├─ cluster_answers() agrupa respuestas similares (≥75%)
                 └─ puntúa clústeres: único = 50, compartido = 50/N
```

### Nuevo pipeline de SpellCorrector

```
normalize_text(raw)
  ├─ strip, lower
  ├─ NFKD + ASCII → quita tildes
  └─ conserva [a-z0-9 ], espacios colapsados

cluster_answers(answers)
  ├─ normalize_text() cada respuesta
  ├─ exact match first (mismo normalized_text)
  ├─ fuzzy match between clusters (token_sort_ratio ≥ 75)
  └─ devuelve lista de sets de player_ids

correct(word, category)
  ├─ normalize()
  ├─ check word list → si está, OK
  ├─ fuzzy match against word list → si ≥ 75%, OK
  ├─ [hybrid/ai] → AI correction (OpenAI/Gemini)
  └─ fallback → normalized form

validate(word, category)
  ├─ check word list
  ├─ [hybrid/ai] → AI validation
  └─ return True/False
```

---

## Cambios respecto a Fase 3

| Aspecto | Fase 3 | Phase 4 |
|---------|--------|---------|
| Normalización | `_normalize()`: quita todo menos `[a-z0-9]` | `normalize_text()`: conserva espacios, mantiene estructura de palabras |
| Dedup de respuestas | Exact match de `_normalize()` (case+accent insensitive) | Fuzzy clustering con `rapidfuzz.token_sort_ratio ≥ 75` |
| `normalized_text` en Answer | `NULL` siempre | Se llena al guardar respuestas |
| SpellCorrector | Placeholder `pass` | Implementación completa con fuzzy matching, word lists, y opcional IA |
| Validación semántica | Solo formato (`_is_valid_word`) | Word lists por categoría + opcional IA |
| Configuración | — | `SPELL_MODE`, `SPELL_API_KEY`, `SPELL_API_LIMIT` |
| Redis | Solo para FSM storage | Caché de correcciones AI |

---

## Archivos a modificar

| # | Archivo | Cambio |
|---|---------|--------|
| 1 | `requirements/requirements.txt` | Añadir `rapidfuzz` |
| 2 | `src/core/config.py` | Añadir settings de spell correction |
| 3 | `src/services/spell_corrector.py` | Reescribir completamente |
| 4 | `src/services/score_engine.py` | Añadir fuzzy matching en `_determine_answer_scores()` |
| 5 | `src/services/round_manager.py` | Pasar `spell_corrector` a score engine |
| 6 | `src/db/repositories/round_repository.py` | Guardar `normalized_text` |
| 7 | `src/services/__init__.py` | Crear singleton `spell_corrector` |
| 8 | `.env` | Añadir variables de spell correction |

## Archivos nuevos

| # | Archivo | Propósito |
|---|---------|-----------|
| 9 | `tests/test_spell_corrector.py` | Tests para normalize, fuzzy, correct |

---

## 1. Dependencias — `requirements/requirements.txt`

Añadir al final:

```
rapidfuzz>=3.9,<4.0
openai>=1.55,<2.0      # Opcional: solo si usas modo ai/hybrid
```

Instalar:

```powershell
cd backend
pip install rapidfuzz
# Opcional:
pip install openai
```

> **Nota:** `openai` solo es necesaria si usas `SPELL_MODE=ai` o `hybrid`. El modo `local` funciona sin ella.
> Para usar Gemini gratis, configura `SPELL_API_URL` apuntando a la API compatible de Google AI Studio.

---

## 2. Configuración — `src/core/config.py`

Añadir campos al `Settings`:

```python
# === Spell Correction (Phase 4) ===
spell_mode: str = "local"          # local | ai | hybrid
spell_api_key: Optional[str] = None
spell_api_url: Optional[str] = None  # Ej: https://api.openai.com/v1
spell_api_limit: int = 20          # Max llamadas API por ronda
spell_fuzzy_threshold: int = 75    # 0-100, umbral fuzzy match
```

**.env** (nuevas variables):

```
SPELL_MODE=local
SPELL_API_KEY=
SPELL_API_URL=https://api.openai.com/v1
SPELL_API_LIMIT=20
SPELL_FUZZY_THRESHOLD=75
```

> Para Gemini gratis: `SPELL_API_URL=https://generativelanguage.googleapis.com/v1beta/openai/`

---

## 3. `SpellCorrector` — `src/services/spell_corrector.py`

Reemplazar el contenido completo:

```python
import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# ── Word lists semilla por categoría ──────────────────────────────
# Se auto-expanden con respuestas validadas durante el juego.

SEED_WORDS: dict[str, set[str]] = {
    "nombre": {
        "juan", "maria", "carlos", "ana", "pedro", "laura", "diego", "sofia",
        "pablo", "elena", "fernando", "luis", "carmen", "javier", "isabel",
        "miguel", "rosa", "antonio", "marta", "jose", "francisco", "manuel",
        "dolores", "jesus", "margarita", "ricardo", "patricia", "roberto",
        "monica", "alejandro", "silvia", "andres", "veronica", "sergio",
        "claudia", "jorge", "beatriz", "raul", "gloria", "alberto", "alicia",
    },
    "apellido": {
        "garcia", "rodriguez", "martinez", "lopez", "gonzalez", "hernandez",
        "perez", "sanchez", "ramirez", "torres", "flores", "rivera", "gomez",
        "diaz", "moreno", "jimenez", "ruiz", "alvarez", "romero", "navarro",
        "castro", "ortega", "mendoza", "delgado", "reyes", "vargas", "herrera",
        "medina", "cruz", "morales", "ortiz", "marin", "campos", "nunez",
        "ibanez", "vega", "soto", "munoz", "rivas", "aguilar",
    },
    "color": {
        "rojo", "azul", "verde", "amarillo", "negro", "blanco", "gris",
        "marron", "naranja", "violeta", "rosa", "celeste", "turquesa",
        "dorado", "plateado", "magenta", "cian", "beige", "coral", "lila",
        "escarlata", "bermellon", "carmesi", "purpura", "fucsia", "salmon",
        "oliva", "granate", "cobre", "bronce",
    },
    "fruta": {
        "manzana", "banana", "naranja", "pera", "uva", "sandia", "melon",
        "fresa", "cereza", "durazno", "mango", "pina", "kiwi", "limon",
        "mandarina", "papaya", "ciruela", "platano", "frambuesa", "arandano",
        "higo", "granada", "coco", "aguacate", "toronja", "maracuya",
        "guanabana", "carambola", "lichi", "tamarindo",
    },
    "pais": {
        "argentina", "mexico", "espana", "colombia", "peru", "chile", "brasil",
        "estados unidos", "canada", "inglaterra", "francia", "alemania",
        "italia", "japon", "china", "australia", "rusia", "india", "egipto",
        "portugal", "uruguay", "venezuela", "cuba", "ecuador", "bolivia",
        "paraguay", "guatemala", "honduras", "el salvador", "nicaragua",
        "costa rica", "panama", "puerto rico", "republica dominicana",
        "belgica", "holanda", "suiza", "suecia", "noruega", "grecia",
    },
    "artista": {
        "shakira", "botero", "dali", "picasso", "van gogh", "frida kahlo",
        "monet", "rembrandt", "da vinci", "miguel angel", "velazquez",
        "goya", "matisse", "pollock", "warhol", "klimt", "cesar", "cerati",
        "mercedes sosa", "atahualpa yupanqui", "gardel", "cortazar",
        "borges", "neruda", "garcia marquez", "messi", "maradona",
    },
    "novela/serie": {
        "cien anos de soledad", "don quijote", "la casa de los espiritus",
        "rayuela", "el amor en los tiempos del colera", "los simpson",
        "friends", "breaking bad", "game of thrones", "stranger things",
        "la casa de papel", "el chavo", "el principito", "1984", "crimen y castigo",
        "orgullo y prejuicio", "matar a un ruisenor", "harry potter",
        "el senor de los anillos", "cancion de hielo y fuego",
    },
    "cosa": {
        "mesa", "silla", "cama", "coche", "casa", "libro", "lapiz",
        "computadora", "telefono", "reloj", "zapato", "camisa", "plato",
        "vaso", "llave", "bolsa", "ventana", "puerta", "lampara", "cuchara",
        "tenedor", "cuchillo", "tv", "television", "radio", "bicicleta",
        "moto", "avion", "barco", "tren", "pelota", "guitarra", "piano",
        "bateria", "cama", "sofa", "armario", "estante", "cuadro", "espejo",
    },
}


def normalize_text(text: str) -> str:
    """Normalización básica: strip, lower, quita tildes, colapsa espacios.
    Conserva letras, dígitos, espacios, guiones y apóstrofes.
    """
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s\-']", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SpellCorrector:
    """Corrector ortográfico con fuzzy matching y opcional validación por IA.

    Tres modos:
      - local: solo fuzzy matching + word lists
      - ai:    siempre consulta IA para corrección y validación
      - hybrid: intenta fuzzy matching primero, cae a IA si no hay match
    """

    MODE_LOCAL = "local"
    MODE_AI = "ai"
    MODE_HYBRID = "hybrid"

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
        # Deep-copy seed words para evitar mutación global
        self._word_lists: dict[str, set[str]] = {
            cat: set(words) for cat, words in SEED_WORDS.items()
        }

    # ── API calls tracking ─────────────────────────────────────────────

    def reset_api_counter(self) -> None:
        self._api_calls = 0

    @property
    def api_calls_remaining(self) -> int:
        return max(0, self.api_limit - self._api_calls)

    # ── Redis ───────────────────────────────────────────────────────────

    async def _get_redis(self):
        if self._redis is None and self._redis_url:
            from redis.asyncio import Redis as AsyncRedis
            self._redis = AsyncRedis.from_url(self._redis_url)
        return self._redis

    # ── Normalization ──────────────────────────────────────────────────

    @staticmethod
    def normalize(raw: str) -> str:
        return normalize_text(raw)

    # ── Fuzzy matching ─────────────────────────────────────────────────

    def fuzzy_match(
        self,
        word: str,
        candidates: list[str],
    ) -> tuple[Optional[str], float]:
        """Busca el mejor match >= threshold. Devuelve (candidato, score 0-1)."""
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

    # ── Clustering de respuestas para score engine ─────────────────────

    def cluster_answers(
        self,
        answers: list[tuple[int, "Answer"]],  # noqa: F821
    ) -> list[set[int]]:
        """Agrupa player_ids por respuestas consideradas iguales vía fuzzy matching.

        1. Normaliza cada respuesta válida.
        2. Primero agrupa por exact match del normalized_text.
        3. Luego fusiona clústeres con fuzzy match >= threshold.
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

        # Fase 2: fuzzy merge de clusters con representante único
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

        return cluster_list

    # ── Corrección ortográfica ────────────────────────────────────────

    async def correct(self, word: str, category: str) -> str:
        """Devuelve la forma corregida/normalizada de la palabra.

        Pipeline:
          1. Normalizar
          2. Si está en word list → OK
          3. Fuzzy match contra word list → si match ≥ threshold, OK
          4. [hybrid/ai] → IA correction (cacheado en Redis)
          5. Fallback → normalized form
        """
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        cat_words = self._word_lists.get(cat_lower, set())

        # 1 — Ya está en word list
        if norm in cat_words:
            return norm

        # 2 — Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                best_norm = self.normalize(best)
                # Aprendizaje: añadir a word list
                cat_words.add(norm)
                return best_norm

        # 3 — AI correction (solo en modo ai o hybrid)
        if self.mode in (self.MODE_AI, self.MODE_HYBRID) and self.api_calls_remaining > 0:
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

        # 4 — Fallback
        return norm

    async def _ai_correct(self, word: str) -> Optional[str]:
        """Corrige una palabra usando API de OpenAI (o compatible)."""
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
                            "Devuelve SOLO la palabra corregida, nada más. "
                            "Si la palabra ya es correcta, devuélvela igual."
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
                corrected = re.sub(r'[^\w\s\-áéíóúüñ]', '', corrected)
                if corrected and len(corrected) < 100:
                    return corrected
                return None
        except Exception:
            logger.exception("Error en AI correction para '%s'", word)
            return None

    # ── Validación semántica ──────────────────────────────────────────

    async def validate(self, word: str, category: str) -> bool:
        """¿La palabra pertenece a la categoría?

        Pipeline:
          1. Check word list
          2. Fuzzy match contra word list
          3. [hybrid/ai] → IA validation
          4. True por defecto (mejor ser permisivo)
        """
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        cat_words = self._word_lists.get(cat_lower, set())

        # 1 — En word list
        if norm in cat_words:
            return True

        # 2 — Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                cat_words.add(norm)  # aprender
                return True

        # 3 — AI validation
        if self.mode in (self.MODE_AI, self.MODE_HYBRID) and self.api_calls_remaining > 0:
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

        # 4 — Default permisivo
        return True

    async def _ai_validate(self, word: str, category: str) -> Optional[bool]:
        """Pregunta a la IA si la palabra pertenece a la categoría."""
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
                            "Responde solo 'sí' o 'no' a si la palabra "
                            "pertenece a la categoría indicada."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Categoría: '{category}'\nPalabra: '{word}'",
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
                return answer == "sí"
        except Exception:
            logger.exception("Error en AI validation para '%s' en %s", word, category)
            return None

    # ── Word list management ──────────────────────────────────────────

    def add_to_word_list(self, word: str, category: str) -> None:
        """Añade una palabra a la word list de una categoría."""
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        self._word_lists.setdefault(cat_lower, set()).add(norm)

    def is_in_word_list(self, word: str, category: str) -> bool:
        norm = self.normalize(word)
        cat_lower = category.lower().strip()
        return norm in self._word_lists.get(cat_lower, set())
```

---

## 4. Modificaciones a `ScoreEngine` — `src/services/score_engine.py`

### 4.1 Cambiar `_determine_answer_scores` para soportar fuzzy matching

```python
def _determine_answer_scores(
    player_answers: list[tuple[int, Answer]],
    spell_corrector: Optional["SpellCorrector"] = None,  # type: ignore
) -> dict[int, tuple[bool, int]]:
    if spell_corrector is not None:
        return _determine_answer_scores_fuzzy(player_answers, spell_corrector)

    # ── Original exact-matching logic (sin cambios) ──
    norm_map: dict[str, list[int]] = {}
    answer_map: dict[int, Answer] = {}

    for pid, answer in player_answers:
        answer_map[pid] = answer
        txt = answer.raw_text.strip()
        if not txt or not _is_valid_word(txt):
            continue
        norm = _normalize(txt)
        if norm:
            norm_map.setdefault(norm, []).append(pid)

    result: dict[int, tuple[bool, int]] = {}
    unique_players: set[int] = set()
    shared_groups: dict[int, int] = {}

    for norm, pids in norm_map.items():
        if len(pids) == 1:
            unique_players.add(pids[0])
        else:
            share = UNIQUE_POINTS // len(pids)
            for p in pids:
                shared_groups[p] = share

    all_pids = {pid for pid, _ in player_answers}
    for pid in all_pids:
        if pid in unique_players and pid not in shared_groups:
            result[pid] = (True, UNIQUE_POINTS)
        elif pid in shared_groups:
            result[pid] = (False, shared_groups[pid])
        else:
            result[pid] = (False, 0)

    return result


def _determine_answer_scores_fuzzy(
    player_answers: list[tuple[int, Answer]],
    spell_corrector: "SpellCorrector",  # type: ignore
) -> dict[int, tuple[bool, int]]:
    """Versión con fuzzy matching: agrupa respuestas similares como duplicados."""
    from src.services.spell_corrector import SpellCorrector

    clusters = spell_corrector.cluster_answers(player_answers)

    result: dict[int, tuple[bool, int]] = {}
    all_pids = {pid for pid, _ in player_answers}

    for cluster in clusters:
        count = len(cluster)
        if count == 1:
            pid = next(iter(cluster))
            answer = next(ans for p, ans in player_answers if p == pid)
            txt = answer.raw_text.strip()
            if txt and _is_valid_word(txt):
                result[pid] = (True, UNIQUE_POINTS)
            else:
                result[pid] = (False, 0)
        else:
            share = UNIQUE_POINTS // count
            for pid in cluster:
                result[pid] = (False, share)

    # Asegurar que todos los jugadores tengan entrada
    for pid in all_pids:
        if pid not in result:
            answer = next(ans for p, ans in player_answers if p == pid)
            txt = answer.raw_text.strip()
            if txt and _is_valid_word(txt):
                result[pid] = (True, UNIQUE_POINTS)
            else:
                result[pid] = (False, 0)

    return result
```

### 4.2 Cambiar `ScoreEngine.evaluate` para aceptar `spell_corrector`

```python
class ScoreEngine:
    def evaluate(
        self,
        answers_by_player: dict[int, list[Answer]],
        num_categories: int,
        first_completer_id: Optional[int] = None,
        spell_corrector: Optional["SpellCorrector"] = None,  # type: ignore
    ) -> tuple[dict[int, int], dict[int, list[dict]]]:
        totals: dict[int, int] = defaultdict(int)
        details: dict[int, list[dict]] = defaultdict(list)

        if not answers_by_player:
            return dict(totals), dict(details)

        categories = _group_by_category(answers_by_player)

        for canonical_cat, player_answers in categories.items():
            # ── El cambio está aquí: pasar spell_corrector ──
            answer_scores = _determine_answer_scores(
                player_answers, spell_corrector=spell_corrector
            )
            for pid, (is_unique, cat_score) in answer_scores.items():
                totals[pid] += cat_score
                for p_id, ans in player_answers:
                    if p_id == pid:
                        details[pid].append({
                            "answer_id": ans.id,
                            "word_slot": canonical_cat,
                            "raw_text": ans.raw_text,
                            "is_correct": cat_score > 0,
                            "score": cat_score,
                        })
                        break

        for pid in answers_by_player:
            if pid not in totals:
                totals[pid] = 0
                details[pid] = [
                    {
                        "answer_id": ans.id,
                        "word_slot": ans.word_slot,
                        "raw_text": ans.raw_text,
                        "is_correct": False,
                        "score": 0,
                    }
                    for ans in answers_by_player[pid]
                ]

        if first_completer_id is not None and first_completer_id in totals:
            totals[first_completer_id] += FIRST_COMPLETER_BONUS

        return dict(totals), dict(details)
```

**Importante:** Añadir import lazy de `SpellCorrector` dentro de `_determine_answer_scores_fuzzy`. O puedes importar al inicio del archivo si prefieres (no hay riesgo de circular imports porque `spell_corrector.py` no importa `score_engine.py`).

```python
# Al inicio de score_engine.py, añadir:
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.spell_corrector import SpellCorrector
```

---

## 5. Modificaciones a `RoundRepository` — `src/db/repositories/round_repository.py`

### 5.1 Guardar `normalized_text` en `save_answers`

Añadir import y modificar el método:

```python
from src.services.spell_corrector import normalize_text as _normalize_text

# ── Dentro de save_answers, en el loop ──

async def save_answers(
    self,
    round_id: int,
    game_id: int,
    player_id: int,
    answers: dict[str, str],
) -> list[Answer]:
    stmt = select(GamePlayer).where(
        GamePlayer.game_id == game_id,
        GamePlayer.player_id == player_id,
    )
    gp = (await self.session.execute(stmt)).scalar_one_or_none()
    if not gp:
        raise ValueError(
            f"GamePlayer not found for game={game_id} player={player_id}"
        )

    old = await self.session.execute(
        select(Answer).where(
            Answer.round_id == round_id,
            Answer.player_id == player_id,
        )
    )
    for a in old.scalars():
        await self.session.delete(a)
    await self.session.flush()

    result = []
    for slot, value in answers.items():
        a = Answer(
            round_id=round_id,
            player_id=player_id,
            game_player_id=gp.id,
            word_slot=slot,
            raw_text=value,
            normalized_text=_normalize_text(value),  # ← NUEVO
        )
        self.session.add(a)
        result.append(a)
    await self.session.commit()
    for a in result:
        await self.session.refresh(a)
    return result
```

---

## 6. Modificaciones a `RoundManager` — `src/services/round_manager.py`

### 6.1 Pasar `spell_corrector` a ScoreEngine.evaluate

En `_persist_round_scores` (línea ~567):

```python
async def _persist_round_scores(
    self,
    round_id: int,
    state: RoundState,
) -> None:
    async with async_session_factory() as session:
        repo = RoundRepository(session)
        answers_by_player = await repo.get_answers_by_player(round_id)

        engine = ScoreEngine()
        totals, details = engine.evaluate(
            answers_by_player,
            len(state.categories),
            first_completer_id=state.first_completer_id,
            spell_corrector=spell_corrector,  # ← NUEVO
        )
        # ... resto igual ...
```

Y en `_build_summary` (línea ~605):

```python
scores, _ = engine.evaluate(
    all_rounds_answers,
    len(state.categories),
    first_completer_id=state.first_completer_id,
    spell_corrector=spell_corrector,  # ← NUEVO
)
```

### 6.2 Importar `spell_corrector`

```python
# Al inicio del archivo, junto a los otros imports:
from src.services import spell_corrector  # o import directo
from src.services.spell_corrector import SpellCorrector
```

> **Nota:** Revisa la importación. Si el singleton se crea en `__init__.py`, solo haz `from src.services import spell_corrector`.

---

## 7. Singleton — `src/services/__init__.py`

Reemplazar el contenido:

```python
from .game_orchestrator import LobbyManager
from .score_engine import ScoreEngine
from .spell_corrector import SpellCorrector
from .leaderboard import LeaderboardService
from .round_manager import RoundManager, round_manager
from src.core.config import settings

# Singleton del corrector ortográfico
spell_corrector = SpellCorrector(
    mode=settings.spell_mode,
    redis_url=settings.redis_url,
    api_key=settings.spell_api_key,
    api_url=settings.spell_api_url,
    api_limit=settings.spell_api_limit,
    fuzzy_threshold=settings.spell_fuzzy_threshold,
)

__all__ = [
    "LobbyManager",
    "ScoreEngine",
    "SpellCorrector",
    "LeaderboardService",
    "RoundManager",
    "round_manager",
    "spell_corrector",
]
```

---

## 8. Tests — `tests/test_spell_corrector.py`

Crear nuevo archivo:

```python
import pytest

from src.services.spell_corrector import SpellCorrector, normalize_text, SEED_WORDS


# ── normalize_text ────────────────────────────────────────────────


class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("HOLA") == "hola"

    def test_remove_accents(self):
        assert normalize_text("Canción") == "cancion"

    def test_preserves_spaces(self):
        assert normalize_text("Buenos Aires") == "buenos aires"

    def test_collapses_spaces(self):
        assert normalize_text("  Buenos   Aires  ") == "buenos aires"

    def test_preserves_hyphen(self):
        assert normalize_text("María-José") == "maria-jose"

    def test_removes_punctuation(self):
        assert normalize_text("¡Hola, mundo!") == "hola mundo"

    def test_removes_symbols(self):
        assert normalize_text("Perro#1") == "perro1"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_only_spaces(self):
        assert normalize_text("   ") == ""

    def test_apostrophe(self):
        assert normalize_text("O'Brien") == "obrien"

    def test_n_with_tilde(self):
        assert normalize_text("Muñoz") == "munoz"


# ── SpellCorrector.normalize ──────────────────────────────────────


class TestSpellCorrectorNormalize:
    def test_delegates_to_normalize_text(self):
        sc = SpellCorrector()
        assert sc.normalize("HOLA") == normalize_text("HOLA")


# ── SpellCorrector.fuzzy_match ───────────────────────────────────


class TestFuzzyMatch:
    def test_exact_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("Fernando", ["Fernando", "Juan"])
        assert best == "Fernando"
        assert score >= 0.99

    def test_typo_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("Fenando", ["Fernando", "Juan"])
        assert best == "Fernando"
        assert score >= 0.75

    def test_no_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("Fernando", ["Juan", "Pedro"])
        assert best is None
        assert score == 0.0

    def test_case_insensitive(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("fernando", ["Fernando"])
        assert best == "Fernando"

    def test_multi_word_token_sort(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        # "Aires Buenos" y "Buenos Aires" deben matchear
        best, score = sc.fuzzy_match("Aires Buenos", ["Buenos Aires"])
        assert best == "Buenos Aires"
        assert score >= 0.99

    def test_below_threshold(self):
        sc = SpellCorrector(fuzzy_threshold=90)  # threshold alto
        best, score = sc.fuzzy_match("Fenando", ["Fernando"])
        # "fenando" vs "fernando" es ~89%, < 90%
        if score < 0.9:
            assert best is None


# ── SpellCorrector.cluster_answers ───────────────────────────────


def _make_ans(txt: str, pid: int = 1):
    """Simplified answer mock for testing."""
    from src.db.models import Answer
    a = Answer(
        id=pid,
        round_id=1,
        player_id=pid,
        game_player_id=pid,
        word_slot="Nombre",
        raw_text=txt,
    )
    a.id = pid
    return a


class TestClusterAnswers:
    def test_single_player(self):
        sc = SpellCorrector()
        answers = [(111, _make_ans("Fernando", 1))]
        clusters = sc.cluster_answers(answers)
        assert len(clusters) == 1
        assert clusters[0] == {111}

    def test_exact_duplicates(self):
        sc = SpellCorrector()
        answers = [
            (111, _make_ans("Fernando", 1)),
            (222, _make_ans("Fernando", 2)),
        ]
        clusters = sc.cluster_answers(answers)
        assert len(clusters) == 1
        assert clusters[0] == {111, 222}

    def test_fuzzy_duplicates(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = [
            (111, _make_ans("Fernando", 1)),
            (222, _make_ans("Fenando", 2)),  # typo
        ]
        clusters = sc.cluster_answers(answers)
        # Deberían estar en el mismo clúster
        assert any(cl == {111, 222} for cl in clusters), f"Clusters: {clusters}"

    def test_different_words(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = [
            (111, _make_ans("Juan", 1)),
            (222, _make_ans("Pedro", 2)),
        ]
        clusters = sc.cluster_answers(answers)
        assert len(clusters) == 2  # dos clústeres separados

    def test_case_difference(self):
        sc = SpellCorrector()
        answers = [
            (111, _make_ans("juan", 1)),
            (222, _make_ans("JUAN", 2)),
        ]
        clusters = sc.cluster_answers(answers)
        assert clusters[0] == {111, 222}

    def test_accent_difference(self):
        sc = SpellCorrector()
        answers = [
            (111, _make_ans("Canción", 1)),
            (222, _make_ans("cancion", 2)),
        ]
        clusters = sc.cluster_answers(answers)
        assert clusters[0] == {111, 222}

    def test_multi_word_reordered(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = [
            (111, _make_ans("Estados Unidos", 1)),
            (222, _make_ans("Unidos Estados", 2)),
        ]
        clusters = sc.cluster_answers(answers)
        assert clusters[0] == {111, 222}

    def test_invalid_word_excluded_from_clustering(self):
        sc = SpellCorrector()
        answers = [
            (111, _make_ans("Fernando", 1)),
            (222, _make_ans("123!!!", 2)),  # inválido
        ]
        clusters = sc.cluster_answers(answers)
        # 222 debería estar en su propio clúster (invalid)
        pids_in_clusters = set()
        for cl in clusters:
            pids_in_clusters |= cl
        assert 111 in pids_in_clusters
        assert 222 in pids_in_clusters


# ── SpellCorrector.correct ──────────────────────────────────────


class TestCorrect:
    def test_word_in_word_list(self):
        sc = SpellCorrector()
        result = sc.correct("Fernando", "Nombre")
        assert result == "fernando"  # normalized form

    def test_case_insensitive_word_list(self):
        sc = SpellCorrector()
        result = sc.correct("FERNANDO", "Nombre")
        assert result == "fernando"

    def test_fuzzy_match_against_word_list(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        result = sc.correct("Fenando", "Nombre")
        assert result == "fernando"  # fuzzy matched

    def test_unknown_word_fallback(self):
        sc = SpellCorrector()
        result = sc.correct("Xyzzy", "Nombre")
        assert result == "xyzzy"  # fallback normalized

    def test_unknown_category_fallback(self):
        sc = SpellCorrector()
        result = sc.correct("Foo", "CategoríaInexistente")
        assert result == "foo"

    def test_adds_to_word_list_after_fuzzy(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc.correct("Fenando", "Nombre")
        assert "fenando" in sc._word_lists["nombre"]


# ── SpellCorrector.validate ─────────────────────────────────────


class TestValidate:
    def test_valid_word_in_list(self):
        sc = SpellCorrector()
        assert sc.validate("Fernando", "Nombre") is True

    def test_invalid_word_not_in_list(self):
        sc = SpellCorrector()
        # Sin fuzzy match ni IA, debería devolver True (default permisivo)
        assert sc.validate("Xyzzy", "Nombre") is True

    def test_fuzzy_valid(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        assert sc.validate("Fenando", "Nombre") is True

    def test_adds_to_word_list_after_validate(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc.validate("Fenando", "Nombre")
        assert "fenando" in sc._word_lists["nombre"]


# ── Word list management ────────────────────────────────────────


class TestWordListManagement:
    def test_add_to_word_list(self):
        sc = SpellCorrector()
        sc.add_to_word_list("MiPalabraNueva", "Nombre")
        assert sc.is_in_word_list("MiPalabraNueva", "Nombre")

    def test_is_in_word_list_normalizes(self):
        sc = SpellCorrector()
        sc.add_to_word_list("NuevaPalabra", "Nombre")
        assert sc.is_in_word_list("nuevaPalabra", "Nombre")

    def test_not_in_word_list(self):
        sc = SpellCorrector()
        assert sc.is_in_word_list("AlgoQueNoExiste", "Nombre") is False

    def test_unknown_category(self):
        sc = SpellCorrector()
        assert sc.is_in_word_list("Foo", "NoExiste") is False


# ── Seed words structure ────────────────────────────────────────


class TestSeedWords:
    def test_all_categories_present(self):
        expected = {"nombre", "apellido", "color", "fruta", "pais",
                     "artista", "novela/serie", "cosa"}
        assert set(SEED_WORDS.keys()) == expected

    def test_each_category_has_words(self):
        for cat, words in SEED_WORDS.items():
            assert len(words) > 0, f"Category '{cat}' has no seed words"

    def test_all_words_are_normalized(self):
        for cat, words in SEED_WORDS.items():
            for w in words:
                assert w == normalize_text(w), (
                    f"Seed word '{w}' in '{cat}' is not normalized"
                )
```

---

## 9. Tests adicionales para ScoreEngine — `tests/test_score_engine.py`

Añadir al final del archivo:

```python
# ── ScoreEngine con fuzzy matching ──────────────────────────────


class TestScoreEngineFuzzyMatching:
    def test_fuzzy_clusters_typo(self):
        """'Fernando' y 'Fenando' deben tratarse como duplicados."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = {
            111: [make_answer(1, "Nombre", "Fernando")],
            222: [make_answer(2, "Nombre", "Fenando")],  # typo
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 25  # compartido
        assert totals[222] == 25  # compartido

    def test_fuzzy_different_words_separate(self):
        """Palabras diferentes deben puntuar por separado."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = {
            111: [make_answer(1, "Nombre", "Juan")],
            222: [make_answer(2, "Nombre", "Pedro")],
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 50  # único
        assert totals[222] == 50  # único

    def test_fuzzy_mixed_scenario(self):
        """Mezcla de exacto, fuzzy y único."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = {
            111: [make_answer(1, "Nombre", "Fernando")],
            222: [make_answer(2, "Nombre", "Fenando")],  # fuzzy = Fernando
            333: [make_answer(3, "Nombre", "Juan")],     # único
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 25  # compartido con 222
        assert totals[222] == 25  # compartido con 111
        assert totals[333] == 50  # único

    def test_fuzzy_unchanged_without_corrector(self):
        """Sin SpellCorrector, el comportamiento es el clásico exacto."""
        engine = ScoreEngine()
        answers = {
            111: [make_answer(1, "Nombre", "Fernando")],
            222: [make_answer(2, "Nombre", "Fenando")],  # diferentes para exact match
        }
        totals, details = engine.evaluate(answers, 1)
        # Sin fuzzy: son palabras diferentes → 50 c/u
        assert totals[111] == 50
        assert totals[222] == 50

    def test_fuzzy_bonus_still_applies(self):
        """El bonus de first completer debe seguir funcionando con fuzzy."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = {
            111: [make_answer(1, "Nombre", "Fernando")],
            222: [make_answer(2, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, first_completer_id=111,
                                          spell_corrector=sc)
        assert totals[111] == UNIQUE_POINTS + FIRST_COMPLETER_BONUS  # 60
        assert totals[222] == UNIQUE_POINTS  # 50

    def test_fuzzy_with_empty_answers(self):
        """Respuestas vacías deben puntuar 0 incluso con fuzzy."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        answers = {
            111: [make_answer(1, "Nombre", "")],
            222: [make_answer(2, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 0
        assert totals[222] == 50
```

---

## 10. Resumen de todos los cambios

### Orden de implementación sugerido

1. **Actualizar `requirements.txt`** — Añadir `rapidfuzz`
2. **Actualizar `config.py`** — Añadir settings de spell
3. **Reescribir `spell_corrector.py`** — Implementación completa
4. **Actualizar `round_repository.py`** — Guardar `normalized_text`
5. **Actualizar `score_engine.py`** — Añadir `_determine_answer_scores_fuzzy` y modificar `evaluate`
6. **Actualizar `__init__.py`** — Singleton `spell_corrector`
7. **Actualizar `round_manager.py`** — Pasar `spell_corrector` a evaluaciones
8. **Actualizar `.env`** — Variables de entorno
9. **Crear `tests/test_spell_corrector.py`** — Tests del corrector
10. **Añadir tests a `test_score_engine.py`** — Tests fuzzy integration
11. **Ejecutar tests** — Verificar que todos pasan

### Comandos de verificación

```powershell
# Instalar dependencias
pip install rapidfuzz

# Ejecutar todos los tests
cd backend
pytest -v

# Solo tests nuevos
pytest -v tests/test_spell_corrector.py

# Tests de score engine (incluyendo los nuevos fuzzy)
pytest -v tests/test_score_engine.py -k "fuzzy"

# Linting
ruff check src/ tests/

# Type checking
mypy src/
```

### Verificación manual del bot (opcional)

```powershell
cd backend
python -m src.bot
```

En un grupo de Telegram:
1. Iniciar partida con `/stop`
2. Completar una ronda
3. Verificar que respuestas similares se agrupan como duplicados
4. Para modo IA: configurar `.env` con `SPELL_MODE=hybrid` y `SPELL_API_KEY`

---

## 11. Notas sobre el modo IA

### OpenAI

```
SPELL_MODE=hybrid
SPELL_API_KEY=sk-...
SPELL_API_URL=https://api.openai.com/v1
```

Usa `gpt-4o-mini` (económico, ~$0.15/1M input tokens). Cada corrección son ~200 tokens → 20 llamadas cuestan ~$0.0006.

### Gemini (gratis)

```
SPELL_MODE=ai
SPELL_API_KEY=...(Google AI Studio API key)
SPELL_API_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

100+ llamadas/día gratis. Sin costo para desarrollo.

### Sin IA (recomendado para empezar)

```
SPELL_MODE=local
```

El fuzzy matching local ya cubre la mayoría de casos (tildes, typos, mayúsculas, reordenamiento de palabras). La IA es opcional para casos límite.

---

## 12. Mecanismo de aprendizaje

Las `_word_lists` del `SpellCorrector` se auto-expanden:

1. Cuando `correct()` encuentra un fuzzy match, añade la forma normalizada a la word list
2. Cuando `validate()` confirma una palabra vía IA, la añade
3. Pero **solo en memoria** — al reiniciar el bot, se pierden las adiciones

Para persistencia permanente, se podría añadir una tabla `CategoryWord(word, category)` en Fase 5 o 6. Por ahora el aprendizaje es volátil, que es suficiente para el juego en sesión.

---

## 13. Nota importante sobre tipos

El tipo `Answer` usado en `cluster_answers` es de `src.db.models.Answer`. Para evitar circular imports, se usa `"Answer"` como string literal (forward reference) con `from __future__ import annotations` o se importa solo para TYPE_CHECKING. El código de `spell_corrector.py` usa un comentario `# noqa: F821` para ignorar el error de tipo.

Si quieres evitar esto completamente, cambia la firma a usar `Any` o un `Protocol`:

```python
from typing import Any

def cluster_answers(self, answers: list[tuple[int, Any]]) -> list[set[int]]:
    ...
```

Esto es válido porque solo accede a `ans.raw_text` que existe en cualquier objeto con ese atributo.
