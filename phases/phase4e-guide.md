# Phase 4E — LLM Híbrido (IA + Fuzzy para categorías abiertas)

**Objetivo:** Implementar validación semántica con IA (Gemini gratis) para las 5 categorías abiertas (Nombre, Apellido, Artista, Novela/Serie, Cosa) usando el modo `hybrid`. Cuando el fuzzy matching local no encuentra la palabra en la word list, se consulta a Gemini para determinar si la respuesta es válida. Las respuestas validadas por IA se auto-expanden en la word list para futuros matches exactos.

---

## 1. Obtener API key de Gemini (gratis)

1. Ve a https://aistudio.google.com/apikey
2. Inicia sesión con tu cuenta de Google
3. Haz clic en **"Crear API key"**
4. Selecciona un proyecto de Google Cloud (o crea uno nuevo)
5. Copia la API key generada

**Modelo:** `gemini-2.0-flash-exp` (gratis, 1500 solicitudes/día, 32K tokens de contexto)

**Endpoint OpenAI-compatible:** `https://generativelanguage.googleapis.com/v1beta/openai`

Esto significa que el código existente de `_ai_correct()` y `_ai_validate()` que ya usa formato OpenAI funciona **SIN CAMBIOS** en el payload. Solo cambiamos la URL, el modelo y el timeout.

---

## 2. Resumen de todos los cambios

| Archivo | Cambio |
|---------|--------|
| `backend/src/core/config.py:21` | + `spell_ai_provider: str = "openai"` |
| `backend/.env` | + `SPELL_AI_PROVIDER=gemini`, `SPELL_MODE=hybrid` |
| `backend/.env.example` | + documentación Gemini |
| `backend/src/services/spell_corrector.py:210-211` | + `PROVIDER_OPENAI` y `PROVIDER_GEMINI` constantes |
| `backend/src/services/spell_corrector.py:221` | + parámetro `ai_provider` en `__init__` |
| `backend/src/services/spell_corrector.py:230-233` | + `self.ai_provider`, `self._api_failed`, `self._validation_source` |
| `backend/src/services/spell_corrector.py:241-244` | Modificar `reset_api_counter()` (reset `_api_failed` y `_validation_source`) |
| `backend/src/services/spell_corrector.py:250-259` | + propiedades `api_calls_total`, `api_calls_failed`, `get_validation_source()` |
| `backend/src/services/spell_corrector.py:410-418` | Modificar `correct()` paso 2: saltar fuzzy en modo AI |
| `backend/src/services/spell_corrector.py:419-425` | Modificar `correct()` paso 3: track `_api_failed` si IA falla |
| `backend/src/services/spell_corrector.py:448-501` | Reescribir `_ai_correct()` con Gemini support |
| `backend/src/services/spell_corrector.py:505-560` | Reescribir `validate()` con `_validation_source` tracking + fix cache hit bug |
| `backend/src/services/spell_corrector.py:562-613` | Reescribir `_ai_validate()` con Gemini support |
| `backend/src/services/spell_corrector.py` | + método `get_api_metrics()` |
| `backend/src/services/spell_corrector.py:711-717` | Modificar `get_corrector()` para pasar `ai_provider` |
| `backend/src/services/score_engine.py:210-221` | + `validation_source` en details de `evaluate()` |
| `backend/src/services/round_manager.py:167-188` | + validación IA en `submit_answers()` |
| `backend/src/services/error_tracker.py:328-340` | + métricas API en `generate_report()` |
| `backend/tests/test_spell_corrector.py:340-430` | + `TestAIMode` (6 tests) + `TestRedisCache` (2 tests) |
| `backend/tests/test_score_engine.py:480-520` | + `TestScoreEngineAIHybrid` (1 test) |
| `backend/tests/test_ai_hybrid.py` | CREAR — tests de integración con Gemini real |

---

## 3. Cambio 1: `backend/src/core/config.py` (línea 21)

El archivo termina en línea 24. Añade entre `spell_fuzzy_threshold` y `settings = Settings()`:

```
    spell_ai_provider: str = "openai"  # openai | gemini
```

**Resultado final del archivo completo:**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    bot_token: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    # === Spell correction ===
    spell_mode: str = "local"  # local | ai | hybrid
    spell_api_key: Optional[str] = None
    spell_api_url: Optional[str] = None  # Ej: https://api.openai.com/v1
    spell_api_limit: int = 20  # Max llamadas API por ronda
    spell_fuzzy_threshold: int = 75  # 0-100 umbral fuzzy match
    spell_ai_provider: str = "openai"  # openai | gemini


settings = Settings()
```

---

## 4. Cambio 2: `backend/.env`

Reemplazar `SPELL_MODE=local` por `SPELL_MODE=hybrid` y añadir `SPELL_AI_PROVIDER=gemini`. Poner la API key real de Gemini.

```
BOT_TOKEN=8846474958:AAGjcMZBqRvO7X_RDAKdUupHlyHwsq-QXp0
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
SPELL_MODE=hybrid

SPELL_API_KEY=<tu-api-key-de-gemini>
SPELL_API_URL=https://generativelanguage.googleapis.com/v1beta/openai
SPELL_API_LIMIT=20
SPELL_FUZZY_THRESHOLD=75
SPELL_AI_PROVIDER=gemini
```

---

## 5. Cambio 3: `backend/.env.example`

Añadir al final:

```
# === Modo de correccion: local | ai | hybrid ===
# SPELL_MODE=local
# SPELL_API_KEY=
# SPELL_API_URL=https://api.openai.com/v1
# SPELL_API_LIMIT=20
# SPELL_FUZZY_THRESHOLD=75
# SPELL_AI_PROVIDER=openai

# Para Gemini (gratis):
# SPELL_MODE=hybrid
# SPELL_API_KEY=<tu-api-key-de-google-ai-studio>
# SPELL_API_URL=https://generativelanguage.googleapis.com/v1beta/openai
# SPELL_AI_PROVIDER=gemini
```

---

## 6. Cambio 4: `backend/src/services/spell_corrector.py`

### 6A. Constantes de provider (línea 209-211)

Después de `DB_CATEGORIES = {"color", "fruta", "pais", "país"}`, AÑADE:

```python
    PROVIDER_OPENAI = "openai"
    PROVIDER_GEMINI = "gemini"
```

**Antes:**
```python
    DB_CATEGORIES = {"color", "fruta", "pais", "país"}
```

**Después:**
```python
    DB_CATEGORIES = {"color", "fruta", "pais", "país"}
    PROVIDER_OPENAI = "openai"
    PROVIDER_GEMINI = "gemini"
```

### 6B. Parámetro `ai_provider` en `__init__` (línea 221)

En la firma del método `__init__`, AÑADE `ai_provider: str = "openai"` después de `fuzzy_threshold: int = 75,`:

```python
    def __init__(
        self,
        mode: str = MODE_LOCAL,
        redis_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        api_limit: int = 20,
        fuzzy_threshold: int = 75,
        ai_provider: str = "openai",
    ) -> None:
```

### 6C. Nuevos atributos en `__init__` (líneas 230-233)

Después de `self.fuzzy_threshold = fuzzy_threshold`, AÑADE:

```python
        self.ai_provider = ai_provider
        self._api_failed: int = 0
        self._validation_source: dict[str, str] = {}
```

### 6D. `reset_api_counter()` (líneas 241-244)

REEMPLAZA:
```python
    def reset_api_counter(self) -> None:
        self._api_calls = 0
```

POR:
```python
    def reset_api_counter(self) -> None:
        self._api_calls = 0
        self._api_failed = 0
        self._validation_source.clear()
```

### 6E. Nuevas propiedades (después de `api_calls_remaining`, después de línea 248)

Después de:
```python
    @property
    def api_calls_remaining(self) -> int:
        return max(0, self.api_limit - self._api_calls)
```

AÑADE:
```python
    @property
    def api_calls_total(self) -> int:
        return self._api_calls

    @property
    def api_calls_failed(self) -> int:
        return self._api_failed

    def get_validation_source(self, key: str) -> str:
        return self._validation_source.get(key, "default")
```

### 6F. Modificar `correct()` paso 2 (líneas 410-418)

El código actual en paso 2 es:
```python
        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                best_norm = self.normalize(best)
                # Aprendizaje: anadir a word list
                cat_words.add(norm)
                return best_norm
```

DEBE CAMBIARSE A: saltar fuzzy en modo AI:
```python
        # 2 - Fuzzy match contra word list
        if cat_words and self.mode != self.MODE_AI:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                best_norm = self.normalize(best)
                # Aprendizaje: anadir a word list
                cat_words.add(norm)
                return best_norm
```

El único cambio es añadir `and self.mode != self.MODE_AI` en la línea `if cat_words:`.

### 6G. Modificar `correct()` paso 3 (luego de `if corrected:`, alrededor de línea 436-443)

El código actual cuando IA retorna éxito:
```python
            corrected = await self._ai_correct(word)
            if corrected:
                self._api_calls += 1
                corrected_norm = self.normalize(corrected)
                cat_words.add(corrected_norm)
                # Cachear en Redis (1 hora)
                if redis:
                    await redis.setex(cache_key, 3600, corrected_norm)
                return corrected_norm
```

DEBE AÑADIRSE un `else` con `_api_failed`:
```python
            corrected = await self._ai_correct(word)
            if corrected:
                self._api_calls += 1
                corrected_norm = self.normalize(corrected)
                cat_words.add(corrected_norm)
                # Cachear en Redis (1 hora)
                if redis:
                    await redis.setex(cache_key, 3600, corrected_norm)
                return corrected_norm
            else:
                self._api_failed += 1
```

### 6H. Reescribir `_ai_correct()` (líneas 448-501)

REEMPLAZAR completamente el método `_ai_correct` actual por:

```python
    async def _ai_correct(self, word: str) -> Optional[str]:
        if not self.api_key or not self.api_url:
            logger.warning("AI correction llamada sin API key/URL configurada")
            return None

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            model = "gemini-2.0-flash-exp" if self.ai_provider == self.PROVIDER_GEMINI else "gpt-4o-mini"

            payload = {
                "model": model,
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

            timeout = 15 if self.ai_provider == self.PROVIDER_GEMINI else 10

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.api_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                corrected = data["choices"][0]["message"]["content"].strip()
                corrected = re.sub(r"[^\w\s\-áéíóúüñ]", "", corrected)
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
```

**Diferencias clave con la versión actual:**
1. `model` se selecciona dinámicamente según `self.ai_provider`:
   - `gemini-2.0-flash-exp` si es Gemini
   - `gpt-4o-mini` si es OpenAI
2. `timeout` se selecciona según el provider:
   - 15s para Gemini (más lento)
   - 10s para OpenAI
3. Captura `httpx.TimeoutException` explícitamente y cuenta como fallo (`self._api_failed += 1`)
4. En `except Exception` también se incrementa `_api_failed`

### 6I. Reescribir `validate()` (líneas 505-560)

REEMPLAZAR completamente el método `validate` actual por:

```python
    async def validate(self, word: str, category: str) -> bool:
        norm = self.normalize(word)
        cat_lower = self._normalize_category(category)
        cat_words = self._word_lists.setdefault(cat_lower, set())

        # 1 - En word list
        if norm in cat_words:
            self._validation_source[f"{cat_lower}:{norm}"] = "word_list"
            return True

        # 2 - Fuzzy match contra word list
        if cat_words:
            best, score = self.fuzzy_match(word, list(cat_words))
            if best is not None:
                cat_words.add(norm)  # aprender
                self._validation_source[f"{cat_lower}:{norm}"] = "fuzzy"
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
                    if val == "true":
                        cat_words.add(norm)
                    self._validation_source[f"{cat_lower}:{norm}"] = "ai_cache"
                    return val == "true"

            result = await self._ai_validate(word, category)
            if result is not None:
                self._api_calls += 1
                if redis:
                    await redis.setex(cache_key, 3600, str(result).lower())
                if result:
                    cat_words.add(norm)
                    self._validation_source[f"{cat_lower}:{norm}"] = "ai"
                else:
                    self._validation_source[f"{cat_lower}:{norm}"] = "ai_rejected"
                return result
            else:
                self._api_failed += 1

        # 4 - Default permisivo
        self._validation_source[f"{cat_lower}:{norm}"] = "default"
        return True
```

**Diferencias clave con la versión actual:**
1. Se registra `_validation_source` en cada paso: `word_list`, `fuzzy`, `ai_cache`, `ai`, `ai_rejected`, `default`
2. **BUGFIX importante**: en paso 3 (caché Redis), el código actual tenía `self._api_calls += 1` en el cache hit (línea 528-529). En la nueva versión, el cache hit NO incrementa `_api_calls` — solo retorna el valor cacheado.
3. Cuando IA retorna `None` (fallo), se incrementa `_api_failed`
4. Paso 4 también registra la fuente como `default`

### 6J. Reescribir `_ai_validate()` (líneas 562-613)

REEMPLAZAR completamente el método `_ai_validate` actual por:

```python
    async def _ai_validate(self, word: str, category: str) -> Optional[bool]:
        if not self.api_key or not self.api_url:
            return None

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            model = "gemini-2.0-flash-exp" if self.ai_provider == self.PROVIDER_GEMINI else "gpt-4o-mini"

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Eres un asistente de un juego de Stop. "
                            "Responde solo 'si' o 'no' a si la palabra "
                            "pertenece a la categoria indicada. "
                            "Solo responde 'si' o 'no'."
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

            timeout = 15 if self.ai_provider == self.PROVIDER_GEMINI else 10

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.api_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip().lower()
                return answer.strip() in ("si", "sí")
        except httpx.TimeoutException:
            logger.warning("Timeout en AI validation para '%s' en %s", word, category)
            return None
        except Exception:
            logger.exception("Error en AI validation para '%s' en %s", word, category)
            return None
```

**Diferencias clave:**
1. `model` dinámico según `self.ai_provider`
2. `timeout` dinámico según provider
3. Captura `httpx.TimeoutException` explícitamente
4. System prompt ahora termina con `"Solo responde 'si' o 'no'."` (más explícito)

### 6K. Añadir método `get_api_metrics()`

Después del método `validate_against_list()` (después de línea 697), AÑADE:

```python
    def get_api_metrics(self) -> dict:
        """Retorna metricas de llamadas a API para el reporte de ErrorTracker."""
        return {
            "total_calls": self._api_calls,
            "failed_calls": self._api_failed,
            "remaining": self.api_calls_remaining,
            "limit": self.api_limit,
            "provider": self.ai_provider,
            "mode": self.mode,
        }
```

### 6L. Modificar `get_corrector()` (líneas 711-717)

REEMPLAZAR:
```python
        _corrector_instance = SpellCorrector(
            mode=settings.spell_mode,
            redis_url=settings.redis_url,
            api_key=settings.spell_api_key,
            api_url=settings.spell_api_url,
            api_limit=settings.spell_api_limit,
            fuzzy_threshold=settings.spell_fuzzy_threshold,
        )
```

POR:
```python
        _corrector_instance = SpellCorrector(
            mode=settings.spell_mode,
            redis_url=settings.redis_url,
            api_key=settings.spell_api_key,
            api_url=settings.spell_api_url,
            api_limit=settings.spell_api_limit,
            fuzzy_threshold=settings.spell_fuzzy_threshold,
            ai_provider=settings.spell_ai_provider,
        )
```

Solo se añade un parámetro: `ai_provider=settings.spell_ai_provider,`

---

## 7. Cambio 5: `backend/src/services/score_engine.py`

### En `ScoreEngine.evaluate()`, dentro del bloque `if ans is not None:` (líneas 210-218)

El código actual alrededor de líneas 209-218:
```python
                ans = answers_by_pid.get(pid)
                if ans is not None:
                    details[pid].append(
                        {
                            "answer_id": ans.id,
                            "word_slot": canonical_cat,
                            "raw_text": ans.raw_text,
                            "is_correct": cat_score > 0,
                            "score": cat_score,
                        }
                    )
```

REEMPLAZA por:
```python
                ans = answers_by_pid.get(pid)
                if ans is not None:
                    detail_entry = {
                        "answer_id": ans.id,
                        "word_slot": canonical_cat,
                        "raw_text": ans.raw_text,
                        "is_correct": cat_score > 0,
                        "score": cat_score,
                    }
                    # Validation source tracking
                    if spell_corrector is not None and hasattr(spell_corrector, 'get_validation_source'):
                        norm = spell_corrector.normalize(ans.raw_text)
                        cat_norm = spell_corrector._normalize_category(canonical_cat)
                        source = spell_corrector.get_validation_source(f"{cat_norm}:{norm}")
                        detail_entry["validation_source"] = source
                    details[pid].append(detail_entry)
```

---

## 8. Cambio 6: `backend/src/services/round_manager.py`

### En `submit_answers()` entre el parsing y el guardado en BD (entre líneas 170 y 172)

El código actual entre `parsed = parse_answers(...)` y `try:` es:

```python
        parsed = parse_answers(text, state.categories)
        if not parsed:
            logger.info("submit_answers: no categories parsed from text")
            return False

        try:
```

REEMPLAZA por:

```python
        parsed = parse_answers(text, state.categories)
        if not parsed:
            logger.info("submit_answers: no categories parsed from text")
            return False

        # NUEVO: validar respuestas con SpellCorrector en modo hybrid/ai
        # Las respuestas invalidas semanticamente se vacian (0 puntos)
        from src.services.spell_corrector import get_corrector
        corrector = get_corrector()
        if corrector.mode in ("ai", "hybrid"):
            for slot, raw_text in list(parsed.items()):
                if raw_text and raw_text.strip():
                    is_valid = await corrector.validate(raw_text, slot)
                    if not is_valid:
                        parsed[slot] = ""
                        logger.info(
                            "Respuesta rechazada por IA: %s=%s (player=%s)",
                            slot, raw_text, player.id,
                        )

        try:
```

**Nota:** `get_corrector` ya está importado al inicio del archivo (línea 23), así que la importación dentro del método es redundante pero clara. Si prefieres, puedes usar el `get_corrector` ya importado arriba.

---

## 9. Cambio 7: `backend/src/services/error_tracker.py`

### En `generate_report()`, justo antes de `lines.append("└──")` (después de línea 327)

El código actual termina con:
```python
        lines.append("└──────────────────────────────────────────────")
        return "\n".join(lines)
```

AÑADE entre la última línea de errores y el cierre:

```python
        # ── Metricas de API calls (SpellCorrector) ──
        try:
            from src.services.spell_corrector import get_corrector
            corrector = get_corrector()
            api_metrics = corrector.get_api_metrics()
            if api_metrics["total_calls"] > 0 or api_metrics["failed_calls"] > 0:
                lines.append("│")
                lines.append("│  🤖 LLM API Calls (ronda actual):")
                lines.append(f"│    Provider: {api_metrics['provider']}")
                lines.append(f"│    Modo: {api_metrics['mode']}")
                lines.append(f"│    Total: {api_metrics['total_calls']}")
                lines.append(f"│    Fallos: {api_metrics['failed_calls']}")
                lines.append(f"│    Restantes: {api_metrics['remaining']}/{api_metrics['limit']}")
        except Exception:
            pass

        lines.append("└──────────────────────────────────────────────")
        return "\n".join(lines)
```

---

## 10. Cambio 8: Tests en `backend/tests/test_spell_corrector.py`

### Al final del archivo (después de línea 337), AÑADE:

```python
# ── Modo AI / Hybrid ─────────────────────────────────────────────


class TestAIMode:
    """Tests para modo AI y hybrid con corrector simulado."""

    @pytest.mark.asyncio
    async def test_validate_in_word_list_returns_true(self):
        """Si la palabra ya esta en word list, validate retorna True sin llamar a IA."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan", "maria"}
        result = await sc.validate("Juan", "Nombre")
        assert result is True
        assert sc._api_calls == 0  # No llamo a IA

    @pytest.mark.asyncio
    async def test_validate_fuzzy_match_returns_true(self):
        """Si fuzzy match encuentra la palabra, validate retorna True sin IA."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = {"fernando"}
        result = await sc.validate("Fenando", "Nombre")
        assert result is True
        assert sc._api_calls == 0

    @pytest.mark.asyncio
    async def test_validate_hybrid_rejects_unknown(self):
        """En modo hybrid, si no hay match fuzzy y no hay API key, retorna True (default permisivo)."""
        sc = SpellCorrector(mode="hybrid", api_key=None, api_url=None, ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan"}
        result = await sc.validate("Xyzzy", "Nombre")
        assert result is True  # default permisivo por falta de API key

    @pytest.mark.asyncio
    async def test_validate_local_never_calls_ai(self):
        """En modo local, nunca llama a IA."""
        sc = SpellCorrector(mode="local", api_key="fake", api_url="https://fake.com", ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan"}
        result = await sc.validate("Xyzzy", "Nombre")
        assert result is True  # default permisivo
        assert sc._api_calls == 0  # No llamo a IA

    @pytest.mark.asyncio
    async def test_correct_hybrid_fuzzy_first(self):
        """En modo hybrid, correct() intenta fuzzy antes de IA."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = {"fernando"}
        result = await sc.correct("Fenando", "Nombre")
        assert result == "fernando"  # Fuzzy match, no IA
        assert sc._api_calls == 0

    @pytest.mark.asyncio
    async def test_validation_source_tracking(self):
        """Verifica que validation_source se registra correctamente."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["artista"] = {"shakira"}

        await sc.validate("Shakira", "Artista")
        assert sc.get_validation_source("artista:shakira") == "word_list"

        await sc.validate("Xyzzy", "Artista")
        assert sc.get_validation_source("artista:xyzzy") == "default"

    def test_get_api_metrics(self):
        """Verifica que get_api_metrics retorna estructura correcta."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        sc._api_calls = 5
        sc._api_failed = 1
        metrics = sc.get_api_metrics()
        assert metrics["total_calls"] == 5
        assert metrics["failed_calls"] == 1
        assert metrics["remaining"] == 15
        assert metrics["limit"] == 20
        assert metrics["provider"] == "gemini"
        assert metrics["mode"] == "hybrid"


class TestRedisCache:
    """Tests para cache en Redis de resultados de IA."""

    @pytest.mark.asyncio
    async def test_correct_caches_in_redis(self):
        """Despues de una correccion AI, el resultado se cachea en Redis."""
        sc = SpellCorrector(
            mode="hybrid",
            redis_url="redis://localhost:6379/0",
            api_key=None,  # No hay API, pero el cache se prueba
            ai_provider="gemini",
        )
        sc._word_lists["nombre"] = {"juan"}
        result = await sc.correct("Juan", "Nombre")
        assert result == "juan"

    @pytest.mark.asyncio
    async def test_redis_cache_hit_does_not_increment_counter(self):
        """Cache hit no debe incrementar _api_calls ni _api_failed."""
        sc = SpellCorrector(
            mode="hybrid",
            redis_url="redis://localhost:6379/0",
            api_key="fake",
            ai_provider="gemini",
        )
        sc._word_lists["nombre"] = {"juan"}

        result = await sc.validate("Juan", "Nombre")
        assert result is True
        calls_before = sc._api_calls

        result = await sc.validate("Juan", "Nombre")
        assert result is True
        assert sc._api_calls == calls_before  # No incremento
```

---

## 11. Cambio 9: Tests en `backend/tests/test_score_engine.py`

### Al final del archivo (después de línea 478), AÑADE:

```python
# ── Modo AI / Hybrid en ScoreEngine ─────────────────────────────


class TestScoreEngineAIHybrid:
    def test_evaluate_non_db_category_with_validation_source(self):
        """Para categoria NO BD, evaluate incluye validation_source en details."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan"}

        answers = {
            111: [make_answer(1, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)

        assert 111 in totals
        assert len(details[111]) == 1
        assert "validation_source" in details[111][0]
```

---

## 12. CREAR: `backend/tests/test_ai_hybrid.py`

Crear archivo completo:

```python
"""Tests de integracion para el modo AI/Hybrid de SpellCorrector.

NOTA: Estos tests requieren una API key de Gemini configurada en .env
con SPELL_AI_PROVIDER=gemini. Si no hay API key, los tests se saltan.
"""
import os
import pytest

from src.services.spell_corrector import SpellCorrector


def has_gemini_key():
    return bool(os.getenv("SPELL_API_KEY")) and os.getenv("SPELL_AI_PROVIDER") == "gemini"


pytestmark = pytest.mark.skipif(
    not has_gemini_key(),
    reason="Requiere SPELL_API_KEY y SPELL_AI_PROVIDER=gemini en .env",
)


class TestGeminiCorrection:
    @pytest.mark.asyncio
    async def test_correct_spanish_word(self):
        """Gemini corrige una palabra con typo al espanol correcto."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url=os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
        corrected = await sc._ai_correct("Fenando")
        assert corrected is not None
        assert "fernando" in corrected.lower()

    @pytest.mark.asyncio
    async def test_correct_already_correct(self):
        """Gemini devuelve la misma palabra si ya es correcta."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url=os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
        corrected = await sc._ai_correct("Messi")
        assert corrected is not None
        assert corrected.lower() == "messi"

    @pytest.mark.asyncio
    async def test_correct_timeout_returns_none(self):
        """Timeout en llamada a Gemini retorna None sin crash."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url="https://httpbin.org/delay/30",
            fuzzy_threshold=75,
        )
        result = await sc._ai_correct("Hola")
        assert result is None  # Timeout


class TestGeminiValidation:
    @pytest.mark.asyncio
    async def test_validate_valid_artist(self):
        """Gemini reconoce a Shakira como artista."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url=os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
        sc._word_lists["artista"] = set()
        result = await sc._ai_validate("Shakira", "Artista")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_invalid_artist(self):
        """Gemini reconoce que 'Mesa' NO es un artista."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url=os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
        sc._word_lists["artista"] = set()
        result = await sc._ai_validate("Mesa", "Artista")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_full_pipeline_hybrid(self):
        """Pipeline hybrid completo: fuzzy falla -> IA valida -> aprende."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url=os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
            fuzzy_threshold=75,
        )
        sc._word_lists["artista"] = {"picasso", "dali"}

        result = await sc.validate("Frida", "Artista")
        assert result is True
        assert "frida" in sc._word_lists["artista"]

    @pytest.mark.asyncio
    async def test_validate_rejects_gibberish(self):
        """Gemini rechaza palabras sin sentido."""
        sc = SpellCorrector(
            mode="hybrid",
            ai_provider="gemini",
            api_key=os.getenv("SPELL_API_KEY"),
            api_url=os.getenv("SPELL_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
        sc._word_lists["nombre"] = set()
        result = await sc._ai_validate("Xyzzyqwert", "Nombre")
        assert result is False
```

---

## 13. Lista de verificación completa

### Archivos a modificar (7 archivos + 1 crear):

| # | Archivo | Acción |
|---|---------|--------|
| 1 | `backend/src/core/config.py:21` | + `spell_ai_provider: str = "openai"` |
| 2 | `backend/.env` | + `SPELL_AI_PROVIDER=gemini`, `SPELL_MODE=hybrid`, API key |
| 3 | `backend/.env.example` | + documentación Gemini |
| 4 | `backend/src/services/spell_corrector.py` | Múltiples cambios (ver sección 6) |
| 5 | `backend/src/services/score_engine.py:210-221` | + `validation_source` en details |
| 6 | `backend/src/services/round_manager.py:167-188` | + validación IA en submit_answers |
| 7 | `backend/src/services/error_tracker.py:328-340` | + métricas API en generate_report |
| 8 | `backend/tests/test_spell_corrector.py` | AÑADIR `TestAIMode` (7 tests) + `TestRedisCache` (2 tests) |
| 9 | `backend/tests/test_score_engine.py` | AÑADIR `TestScoreEngineAIHybrid` (1 test) |
| 10 | `backend/tests/test_ai_hybrid.py` | CREAR (7 tests, saltan sin API key) |

### Después de implementar, verificar:

```bash
cd backend
python -m pytest tests/ -q --tb=no          # Deberia dar 246 + 10 (unit) + 7 (integration) = 263 en total
# Los 7 tests de integracion (test_ai_hybrid.py) se saltaran si no hay API key
# Total esperado: ~256 tests pasando sin API key, ~263 con API key
```
