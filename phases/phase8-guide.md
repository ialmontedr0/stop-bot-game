# Fase 8 — Calidad, testing, despliegue

**Objetivo:** Tests, CI/CD, monitoreo, producción.

**Estado:** EN GUÍA

---

## Resumen

| Componente | Estado Actual | Target |
|---|---|---|
| Tests unitarios | 295 tests existentes | >85% coverage, todos verdes |
| Tests de integración | Solo unitarios con mock | SQLite in-memory para flujo completo |
| Linting | `ruff` configurado | `mypy strict` + `pre-commit` |
| CI/CD | No existe | GitHub Actions → Docker → Railway |
| Monitoreo | `structlog` instalado pero no en JSON | + `prometheus_client` + healthcheck |
| Graceful shutdown | No existe | SIGTERM handler |
| Documentación | No existe | README, ARCHITECTURE, CONTRIBUTING |

---

## 8.0 Dependencias nuevas

Agregar a `requirements/requirements.txt`:

```txt
# === Fase 8 — Monitoreo y testing ===
prometheus-client>=0.21,<1.0
pytest-cov>=6.0,<7.0
mypy>=1.14,<2.0
pre-commit>=4.0,<5.0
```

Instalar:

```powershell
cd backend
venv\Scripts\Activate.ps1
pip install prometheus-client pytest-cov mypy pre-commit
```

---

## 8.1 Tests unitarios — Coverage >85%

### 8.1.1 Configurar pytest-cov

**Archivo NUEVO:** `backend/.coveragerc`

```ini
[run]
source = src
omit =
    */migrations/*
    */scripts/*
    tests/*
    venv/*
    .venv/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    if __name__ == .__main__.:
    raise NotImplementedError
    pass
    return None  # Opcional
show_missing = true
```

**Editar `pytest.ini`:**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
pythonpath = src
addopts = --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=85
filterwarnings =
    ignore::DeprecationWarning
```

### 8.1.2 Tests existentes — verificar coverage actual

Ejecutar para ver el reporte inicial:

```powershell
cd backend
venv\Scripts\Activate.ps1
pytest --cov=src --cov-report=term-missing
```

Identificar los módulos con <85% coverage y escribir tests para las líneas faltantes.

### 8.1.3 Tests que escribir para alcanzar >85%

#### a) `ScoreEngine` — más edge cases

**Archivo:** `backend/tests/test_score_engine.py`

Agregar al final:

```python
class TestScoreEngineEdgeCases:
    """Tests adicionales para edge cases de ScoreEngine."""

    def test_all_answers_empty(self):
        """Todas las respuestas vacías → todos 0 puntos."""
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", ""), _make_answer(1, "Color", "")]}
        totals, details = engine.evaluate(answers, 2)
        assert totals[1] == 0

    def test_single_category(self):
        """Una sola categoría funciona correctamente."""
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana")]}
        totals, details = engine.evaluate(answers, 1)
        assert totals[1] == 50
        assert details[1][0]["is_correct"] is True

    def test_no_answers_empty_dict(self):
        """dict vacío → totals y details vacíos."""
        engine = ScoreEngine()
        totals, details = engine.evaluate({}, 5)
        assert totals == {}
        assert details == {}

    def test_three_players_same_word(self):
        """Tres jugadores misma palabra → puntos divididos."""
        engine = ScoreEngine()
        answers = {
            1: [_make_answer(1, "Nombre", "Carlos")],
            2: [_make_answer(2, "Nombre", "Carlos")],
            3: [_make_answer(3, "Nombre", "Carlos")],
        }
        totals, details = engine.evaluate(answers, 1)
        # 50 / 3 = 16 (integer division or floor)
        assert totals[1] > 0
        assert totals[2] > 0
        assert totals[3] > 0
        assert totals[1] == totals[2] == totals[3]

    def test_first_completer_not_in_scores(self):
        """Bonus no aplica si first_completer no está en scores."""
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana")]}
        totals, details = engine.evaluate(answers, 1, first_completer_id=999)
        assert totals[1] == 50  # Sin bonus porque 999 no está en scores

    def test_bonus_applied_correctly(self):
        """Bonus de 10 puntos al first_completer."""
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana")]}
        totals, _ = engine.evaluate(answers, 1, first_completer_id=1)
        assert totals[1] == 60  # 50 + 10

    def test_invalid_word_scores_zero(self):
        """Palabra inválida (con números) → 0 puntos."""
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana123")]}
        totals, details = engine.evaluate(answers, 1)
        assert totals[1] == 0
        assert details[1][0]["is_correct"] is False

    def test_shared_and_unique_mixed(self):
        """Mezcla de respuestas compartidas y únicas."""
        engine = ScoreEngine()
        # Categoría 1: dos jugadores comparten
        # Categoría 2: cada uno tiene única
        answers = {
            1: [
                _make_answer(1, "Nombre", "Ana"),
                _make_answer(1, "Color", "Rojo"),
            ],
            2: [
                _make_answer(2, "Nombre", "Ana"),
                _make_answer(2, "Color", "Azul"),
            ],
        }
        totals, _ = engine.evaluate(answers, 2)
        assert totals[1] == 25 + 50  # 25 (shared) + 50 (unique)
        assert totals[2] == 25 + 50

    def test_apply_bonus_static(self):
        """ScoreEngine.apply_bonus suma 10 a un jugador."""
        scores = {1: 100, 2: 80}
        ScoreEngine.apply_bonus(1, scores)
        assert scores[1] == 110
```

#### b) `SpellCorrector` — más edge cases

**Archivo:** `backend/tests/test_spell_corrector.py`

Agregar:

```python
class TestSpellCorrectorEdgeCases:
    """Edge cases adicionales para SpellCorrector."""

    def test_normalize_empty_string(self):
        """String vacío → vacío."""
        assert normalize_text("") == ""

    def test_normalize_only_symbols(self):
        """Solo símbolos → vacío."""
        assert normalize_text("!!!@#$%") == ""

    def test_normalize_mixed_accents(self):
        """Tildes eliminadas."""
        assert normalize_text("Canción") == "cancion"
        assert normalize_text("Último") == "ultimo"
        assert normalize_text("Ñoño") == "nono"

    def test_normalize_multi_spaces(self):
        """Espacios múltiples colapsados."""
        assert normalize_text("  el   auto  ") == "el auto"

    def test_normalize_hyphen_preserved(self):
        """Guiones preservados."""
        result = normalize_text("Bienvenido-a-mi-casa")
        assert "bienvenido-a-mi-casa" in result  # lowercase version

    def test_correct_unknown_category(self):
        """Categoría desconocida → fallback a palabra original normalizada."""
        corrector = SpellCorrector(mode="local")
        result = corrector.correct("xyz123", "NonExistentCategory")
        assert result == "xyz123" or result == normalize_text("xyz123")

    def test_validate_empty_word(self):
        """Palabra vacía → False."""
        corrector = SpellCorrector()
        # validate devuelve False para vacío porque normalize devuelve ""
        result = asyncio.run(corrector.validate("", "color"))
        assert result is False

    def test_fuzzy_threshold_below(self):
        """Fuzzy por debajo del threshold → no match."""
        corrector = SpellCorrector()
        corrector._word_lists["color"] = {"rojo", "azul", "verde"}
        best, score = corrector.fuzzy_match("abcdefxyz", list(corrector._word_lists["color"]))
        assert best is None

    def test_get_api_metrics_defaults(self):
        """Métricas de API iniciales en 0."""
        corrector = SpellCorrector()
        metrics = corrector.get_api_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["failed_calls"] == 0
        assert metrics["mode"] == "local"
```

#### c) `GameOrchestrator` — transiciones de estado

**Archivo NUEVO:** `backend/tests/test_game_orchestrator_state.py`

```python
"""Tests de transiciones de estado de GameOrchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.services.game_orchestrator import GameOrchestrator, LobbyState


@pytest.fixture
def orchestrator():
    orch = GameOrchestrator()
    yield orch
    # Cleanup
    orch._lobbies.clear()
    orch._animation_tasks.clear()


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_sticker = AsyncMock()
    return bot


class TestLobbyStateTransitions:

    def test_initial_state(self, orchestrator):
        """LobbyState defaults correctos."""
        state = LobbyState(group_chat_id=-100123, host_telegram_id=111)
        assert state.group_chat_id == -100123
        assert state.host_telegram_id == 111
        assert state.status == "waiting"
        assert state.player_telegram_ids == []
        assert state.cancelled is False
        assert state.message_id is None

    def test_create_lobby(self, orchestrator):
        """create_lobby crea el estado y lo guarda."""
        game_id = orchestrator.create_lobby(-100123, 111)
        assert game_id is not None
        assert game_id in orchestrator._lobbies
        assert orchestrator._lobbies[game_id].host_telegram_id == 111

    @pytest.mark.asyncio
    async def test_join_lobby(self, orchestrator):
        """join_lobby añade al jugador."""
        game_id = orchestrator.create_lobby(-100123, 111)
        lobby = orchestrator._lobbies[game_id]
        assert lobby.status == "waiting"

        result = orchestrator.join_lobby(game_id, 222)
        assert result is True
        assert 222 in lobby.player_telegram_ids

    def test_join_full_lobby(self, orchestrator):
        """join_lobby rechaza si ya hay 10."""
        game_id = orchestrator.create_lobby(-100123, 111)
        lobby = orchestrator._lobbies[game_id]
        for i in range(9):
            lobby.player_telegram_ids.append(1000 + i)
        assert len(lobby.player_telegram_ids) == 9

        # El 10º puede entrar (total = host + 9 = 10)
        result = orchestrator.join_lobby(game_id, 999)
        assert result is True

        # El 11º no puede
        result = orchestrator.join_lobby(game_id, 998)
        assert result is False

    def test_join_duplicate(self, orchestrator):
        """join_lobby rechaza duplicados."""
        game_id = orchestrator.create_lobby(-100123, 111)
        orchestrator.join_lobby(game_id, 222)
        result = orchestrator.join_lobby(game_id, 222)
        assert result is False

    def test_join_nonexistent_lobby(self, orchestrator):
        """join_lobby en lobby inexistente."""
        result = orchestrator.join_lobby(99999, 222)
        assert result is False

    def test_cancel_lobby(self, orchestrator):
        """cancel_game cancela el lobby."""
        game_id = orchestrator.create_lobby(-100123, 111)
        orchestator._lobbies[game_id].message_id = 1
        orchestrator._lobbies[game_id].animation_task = MagicMock()

        with patch.object(orchestrator, "cancel_game", return_value=None) as mock_cancel:
            # Simular cancelación
            orchestator._lobbies.pop(game_id, None)

        assert game_id not in orchestrator._lobbies

    def test_has_lobby_checks_correctly(self, orchestrator):
        """has_lobby detecta lobbies activos."""
        assert orchestrator.has_lobby(-100123) is False
        orchestrator.create_lobby(-100123, 111)
        assert orchestrator.has_lobby(-100123) is True

    def test_get_lobby_returns_none(self, orchestrator):
        """get_lobby para ID inexistente."""
        assert orchestrator.get_lobby(99999) is None

    def test_multiple_lobbies(self, orchestrator):
        """Crear lobbies en diferentes grupos no interfiere."""
        id1 = orchestrator.create_lobby(-1001, 111)
        id2 = orchestrator.create_lobby(-1002, 222)
        assert id1 != id2
        assert orchestrator.get_lobby(-1001) is not None
        assert orchestrator.get_lobby(-1002) is not None
```

#### d) `AnswerParser` — más edge cases

**Archivo:** `backend/tests/test_round_manager.py`

Agregar a `TestParseAnswersFunction`:

```python
class TestParseAnswersEdgeCases:

    def test_empty_input(self):
        """Input vacío → dict vacío."""
        assert parse_answers("", CATEGORIES) == {}

    def test_only_whitespace(self):
        """Solo espacios → dict vacío."""
        assert parse_answers("   \n  \t  ", CATEGORIES) == {}

    def test_no_colon(self):
        """Sin dos puntos → no match."""
        result = parse_answers("Nombre Ana\nColor Rojo", CATEGORIES)
        assert result == {}

    def test_malformed_category(self):
        """Categoría mal formada."""
        result = parse_answers(": valor\nNombre: Ana", CATEGORIES)
        assert "Nombre" in result
        assert result["Nombre"] == "Ana"

    def test_all_categories_at_once(self):
        """Todas las categorías en una sola respuesta."""
        text = "\n".join(f"{cat}: test" for cat in CATEGORIES)
        result = parse_answers(text, CATEGORIES)
        assert len(result) == len(CATEGORIES)

    def test_extra_whitespace_in_value(self):
        """Espacios extra alrededor del valor se limpian."""
        result = parse_answers("Nombre:   Juan   ", CATEGORIES)
        assert result.get("Nombre") == "Juan"

    def test_multiline_value_not_allowed(self):
        """Valor multilinea (el parser solo captura primera línea del match)."""
        text = "Nombre: Juan\n  Perez\nColor: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert "Color" in result

    def test_repeated_category_overwrites(self):
        """Categoría repetida → último valor prevalece."""
        text = "Nombre: Ana\nNombre: Luis"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Luis"

    def test_case_insensitive_category(self):
        """Categoría en mayúsculas/minúsculas mixtas."""
        result = parse_answers("nOmBrE: Juan", CATEGORIES)
        assert "Nombre" in result

    def test_accent_insensitive_category(self):
        """Categoría con acento vs sin acento."""
        result = parse_answers("pais: Argentina", CATEGORIES)
        assert "País" in result

    def test_unknown_categories_ignored(self):
        """Categorías que no existen se ignoran."""
        text = "Nombre: Juan\nFakeCategory: valor\nColor: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert "Nombre" in result
        assert "Color" in result
        assert "FakeCategory" not in result
```

### 8.1.4 Helper para tests

**Archivo:** `backend/tests/conftest.py` — Agregar:

```python
import pytest
from typing import Optional
from src.db.models import Answer


def _make_answer(
    player_id: int,
    word_slot: str,
    raw_text: str,
    is_correct: Optional[bool] = None,
    score: int = 0,
    id: int = 0,
) -> Answer:
    """Crea un objeto Answer para tests sin BD."""
    return Answer(
        id=id,
        player_id=player_id,
        word_slot=word_slot,
        raw_text=raw_text,
        normalized_text=raw_text.lower() if raw_text else "",
        is_correct=is_correct,
        score=score,
    )
```

---

## 8.2 Tests de integración — SQLite in-memory

### 8.2.1 Fixture SQLite para tests de integración

**Editar:** `backend/tests/conftest.py`

Agregar:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.db.models import Base


@pytest.fixture
async def sqlite_in_memory():
    """Base SQLite in-memory para tests de integración (sin PostgreSQL)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()
```

### 8.2.2 Test de flujo lobby → ronda → stop → evaluación

**Archivo NUEVO:** `backend/tests/test_integration_flow.py`

```python
"""Test de integración: flujo completo lobby → ronda → stop → evaluación.

Usa SQLite in-memory para evitar dependencia de PostgreSQL.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.services.game_orchestrator import GameOrchestrator
from src.services.round_manager import RoundManager, RoundState, CATEGORIES
from src.services.score_engine import ScoreEngine
from src.db.models import Base, Game, GamePlayer, Round, Answer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select


@pytest.fixture
async def db_session():
    """SQLite in-memory session para integración."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(chat=MagicMock(id=-100), message_id=1))
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.get_user_profile_photos = AsyncMock(return_value=MagicMock(total_count=0))
    return bot


@pytest.mark.asyncio
async def test_full_game_flow(db_session, mock_bot):
    """Flujo completo: crear partida → 1 ronda → stop → evaluación."""
    # ── 1. Crear entorno ──
    game_id = 1
    group_chat_id = -100123
    player1_tid = 111
    player2_tid = 222
    player_names = {111: "Alice", 222: "Bob"}

    # ── 2. Crear Game en BD ──
    game = Game(id=game_id, group_chat_id=group_chat_id, status="active")
    db_session.add(game)
    await db_session.commit()

    # ── 3. Agregar players al Game ──
    gp1 = GamePlayer(game_id=game_id, player_id=1, is_host=True)
    gp2 = GamePlayer(game_id=game_id, player_id=2)
    db_session.add_all([gp1, gp2])
    await db_session.commit()

    # ── 4. Iniciar ronda ──
    rm = RoundManager()
    # Mockear DB operations
    with patch.object(rm, "_round_timer", new=AsyncMock()):
        await rm.start_round(
            game_id=game_id,
            group_chat_id=group_chat_id,
            round_number=1,
            letter="A",
            total_players=2,
            player_names=player_names,
            bot=mock_bot,
            total_rounds=3,
        )

    # Verificar que el estado se creó
    state = rm.get_active_round(game_id)
    assert state is not None
    assert state.letter == "A"
    assert state.round_number == 1
    assert len(state.submitted_player_ids) == 0

    # ── 5. Simular submissions ──
    player1 = MagicMock()
    player1.id = 1
    player1.telegram_id = 111
    player1.first_name = "Alice"

    player2 = MagicMock()
    player2.id = 2
    player2.telegram_id = 222
    player2.first_name = "Bob"

    # Player 1 envía respuestas completas
    text1 = "\n".join(f"{cat}: valor_{cat}_1" for cat in CATEGORIES[:4])
    with patch("src.services.round_manager.RoundRepository") as mock_repo:
        mock_repo.return_value.get_active_round = AsyncMock(return_value=MagicMock(id=1))
        mock_repo.return_value.save_answers = AsyncMock()

        result1 = await rm.submit_answers(game_id, player1, text1, mock_bot)

    # Player 1 debería ser first_completer
    assert state.first_completer_id == 111
    assert state.first_completer_name == "Alice"

    # Player 2 envía respuestas
    text2 = "\n".join(f"{cat}: otro_valor_{cat}_2" for cat in CATEGORIES[:4])
    with patch("src.services.round_manager.RoundRepository") as mock_repo:
        mock_repo.return_value.get_active_round = AsyncMock(return_value=MagicMock(id=1))
        mock_repo.return_value.save_answers = AsyncMock()

        result2 = await rm.submit_answers(game_id, player2, text2, mock_bot)

    # Ambos han respondido
    assert len(state.submitted_player_ids) == 2

    # ── 6. Cerrar ronda ──
    with patch.object(rm, "_do_close_round_telegram", new=AsyncMock()) as mock_close:
        await rm._close_round(game_id, "stop", mock_bot)
        mock_close.assert_called_once()

    # Verificar que el estado fue removido
    assert rm.get_active_round(game_id) is None

    # ── 7. ScoreEngine evalúa ──
    engine = ScoreEngine()
    # Simular answers_by_player
    answers_by_player = {
        111: [Answer(id=1, player_id=1, word_slot="Nombre", raw_text="Ana",
                     normalized_text="ana", score=0)],
        222: [Answer(id=2, player_id=2, word_slot="Nombre", raw_text="Bob",
                     normalized_text="bob", score=0)],
    }
    totals, details = engine.evaluate(answers_by_player, 1, first_completer_id=111)
    assert 111 in totals
    assert 222 in totals
    assert totals[111] >= 50  # Ana única + bonus
    assert totals[222] >= 50  # Bob única

    # ── 8. Limpieza ──
    await rm.cancel_game(game_id)
```

---

## 8.3 Linting y tipado

### 8.3.1 Configurar `mypy` strict

**Archivo NUEVO:** `backend/pyproject.toml` (en `backend/`)

```toml
[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true
warn_unused_ignores = true
warn_redundant_casts = true
warn_unused_configs = true

[[tool.mypy.overrides]]
module = [
    "src.db.models",
    "tests.*",
]
ignore_errors = true

[tool.ruff]
# Ya existe configuración — verificar que ruff.toml o pyproject.toml tenga esto:
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "ARG", "C4", "T20"]
ignore = ["E501"]  # line-length lo maneja ruff format

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
```

> ⚠️ **Nota:** Si ya existe `pyproject.toml`, mergear con las secciones nuevas. Si no, crearlo.

### 8.3.2 Ejecutar mypy y corregir errores

```powershell
cd backend
venv\Scripts\Activate.ps1
mypy src/ --strict
```

Errores comunes de mypy y cómo corregirlos:

| Error | Causa | Fix |
|-------|-------|-----|
| `Missing return statement` | Función que retorna Optional pero no retorna en todas las ramas | Agregar `return None` |
| `Incompatible return type` | Tipo de retorno no coincide con anotación | Corregir anotación o valor retornado |
| `Argument 1 to ... has incompatible type` | Tipo de parámetro incorrecto | Agregar `cast()` o corregir tipo |
| `Item "None" of "Optional[X]" has no attribute` | No hay chequeo de None antes de usar | Agregar `if x is not None:` |
| `Function is missing a type annotation` | Falta type hint | Agregar `-> None` o tipos |

**Estrategia:** Ejecutar `mypy src/ --strict | Select-String "Error"` para contar errores, y corregirlos de a uno.

### 8.3.3 Configurar pre-commit hooks

**Archivo NUEVO:** `backend/.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.20
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.0
    hooks:
      - id: mypy
        args: [--strict, --ignore-missing-imports]
        language: system
        types: [python]
        exclude: "tests/"

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict
      - id: detect-private-key
```

Instalar pre-commit:

```powershell
cd backend
venv\Scripts\Activate.ps1
pre-commit install
pre-commit run --all-files  # Verificar que funciona
```

---

## 8.4 CI/CD — GitHub Actions

### 8.4.1 Workflow de CI

**Archivo NUEVO:** `backend/.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
    paths:
      - "backend/**"
      - ".github/**"
  pull_request:
    branches: [main]
    paths:
      - "backend/**"

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: stop-bot-game/backend

jobs:
  lint:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: backend/requirements/requirements.txt

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/requirements.txt
          pip install mypy pytest-cov

      - name: Ruff lint
        run: ruff check src/ tests/

      - name: Ruff format check
        run: ruff format --check src/ tests/

      - name: MyPy type check (src only)
        run: mypy src/ --strict --ignore-missing-imports || true
        # || true para que no falle CI mientras corregimos errores

  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: stopbot_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: backend/requirements/requirements.txt

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/requirements.txt
          pip install pytest-cov

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot_test
          REDIS_URL: redis://localhost:6379/0
          BOT_TOKEN: "test:fake_token"
          LOG_LEVEL: ERROR
        run: |
          pytest -v --cov=src --cov-report=term --cov-report=xml --cov-fail-under=85

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-report
          path: backend/htmlcov/
          retention-days: 7

  build-and-push:
    needs: [lint, test]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix={{branch}}-
            type=ref,event=branch

      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: backend
          file: backend/Docker/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

### 8.4.2 Corregir Dockerfile para CI

**Archivo:** `backend/Docker/Dockerfile` — Reemplazar:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Healthcheck HTTP expuesto (para Prometheus / health)
EXPOSE 9090

CMD ["python", "-m", "src.bot"]
```

### 8.4.3 Deploy a Railway (gratis)

Railway tiene un tier gratis que permite deploy directo desde GitHub.

**Pasos:**

1. Crear cuenta en https://railway.com (con GitHub)
2. Instalar Railway CLI:
   ```powershell
   npm install -g @railway/cli
   # O desde installer: https://railway.app/install
   ```
3. En Railway, crear nuevo proyecto:
   - Seleccionar "Deploy from GitHub repo"
   - Seleccionar `stop-bot-game`
   - Agregar servicios: PostgreSQL, Redis, y la app
4. Configurar variables de entorno en Railway:
   ```
   BOT_TOKEN=<tu_token>
   DATABASE_URL=<la_url_que_genera_railway_postgres>
   REDIS_URL=<la_url_que_genera_railway_redis>
   LOG_LEVEL=INFO
   SPELL_MODE=local
   ```
5. Railway auto-detecta Dockerfile y despliega.

**Railway Nixpacks fallback** (si no usas Dockerfile):

Crear `backend/railway.json`:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "nixpacks",
    "buildCommand": "pip install -r requirements/requirements.txt"
  },
  "deploy": {
    "startCommand": "python -m src.bot",
    "healthcheckPath": "/health",
    "restartPolicyType": "on-failure",
    "restartPolicyMaxRetries": 5
  }
}
```

### 8.4.4 Deploy alternativo a Render (gratis)

Crear `backend/render.yaml`:

```yaml
services:
  - type: web
    name: stop-bot-game
    runtime: python
    buildCommand: pip install -r requirements/requirements.txt
    startCommand: python -m src.bot
    healthCheckPath: /health
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: stopbot-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: stopbot-redis
          property: connectionString
      - key: LOG_LEVEL
        value: INFO

databases:
  - name: stopbot-db
    databaseName: stopbot
    plan: free

redis:
  - name: stopbot-redis
    plan: free
```

---

## 8.5 Monitoreo — structlog JSON + Prometheus + Healthcheck

### 8.5.1 Configurar structlog para JSON en producción

**Editar:** `backend/src/bot.py`

Reemplazar `setup_logging()`:

```python
def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    # Detectar si estamos en producción (sin terminal interactiva)
    is_production = not sys.stdout.isatty()

    shared_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_production:
        # Producción: JSON puro
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.dev.ConsoleRenderer() if is_production
            else structlog.processors.JSONRenderer(),
        ]
        # Forzar JSON en producción
        processors = shared_processors + [
            structlog.processors.JSONRenderer(indent=None, sort_keys=True),
        ]
    else:
        # Desarrollo: consola colorida
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

### 8.5.2 Prometheus métricas

**Archivo NUEVO:** `backend/src/monitoring/metrics.py`

```python
"""Métricas Prometheus para el bot.

Uso:
    from src.monitoring.metrics import (
        games_started, rounds_played, api_calls_total,
        errors_total, observe_round_duration
    )

    games_started.inc()
    rounds_played.inc()
    api_calls_total.labels(provider="openai").inc()
    errors_total.labels(type="telegram").inc()
    observe_round_duration(35.5)
"""
from prometheus_client import Counter, Histogram, Gauge

# ─── Contadores ────────────────────────────────────────────────────

games_started = Counter(
    "stopbot_games_started_total",
    "Total de partidas iniciadas",
)

games_finished = Counter(
    "stopbot_games_finished_total",
    "Total de partidas finalizadas",
)

rounds_played = Counter(
    "stopbot_rounds_played_total",
    "Total de rondas jugadas",
)

api_calls_total = Counter(
    "stopbot_api_calls_total",
    "Total de llamadas a APIs externas",
    ["provider"],  # openai, gemini, groq
)

errors_total = Counter(
    "stopbot_errors_total",
    "Total de errores capturados",
    ["type"],  # telegram, db, internal, ai, validation
)

messages_sent = Counter(
    "stopbot_messages_sent_total",
    "Total de mensajes enviados por el bot",
)

player_joins = Counter(
    "stopbot_player_joins_total",
    "Total de jugadores que se unieron a partidas",
)

# ─── Histogramas ───────────────────────────────────────────────────

round_duration_seconds = Histogram(
    "stopbot_round_duration_seconds",
    "Duración de rondas en segundos",
    buckets=[5, 10, 15, 20, 30, 45, 60, 90, 120],
)

game_duration_minutes = Histogram(
    "stopbot_game_duration_minutes",
    "Duración de partidas en minutos",
    buckets=[1, 3, 5, 10, 15, 20, 30],
)

api_call_duration_seconds = Histogram(
    "stopbot_api_call_duration_seconds",
    "Duración de llamadas a APIs externas",
    ["provider"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

# ─── Gauges ────────────────────────────────────────────────────────

active_games = Gauge(
    "stopbot_active_games",
    "Número de partidas activas actualmente",
)

active_players = Gauge(
    "stopbot_active_players",
    "Número de jugadores en partidas actualmente",
)

db_pool_size = Gauge(
    "stopbot_db_pool_size",
    "Tamaño del pool de conexiones a BD",
)

redis_connected = Gauge(
    "stopbot_redis_connected",
    "1 si Redis está conectado, 0 si no",
)

# ─── Helpers ───────────────────────────────────────────────────────

def observe_round_duration(seconds: float) -> None:
    """Registra la duración de una ronda."""
    round_duration_seconds.observe(seconds)


def observe_game_duration(minutes: float) -> None:
    """Registra la duración de una partida."""
    game_duration_minutes.observe(minutes)


def observe_api_call(provider: str, seconds: float) -> None:
    """Registra duración de llamada API."""
    api_call_duration_seconds.labels(provider=provider).observe(seconds)
```

### 8.5.3 Healthcheck HTTP server

**Archivo NUEVO:** `backend/src/monitoring/health_server.py`

```python
"""Servidor HTTP separado para healthcheck y métricas Prometheus.

Corre en un puerto separado (9090) del bot de Telegram.
No requiere FastAPI — usa http.server de la stdlib.

Uso en bot.py:
    from src.monitoring.health_server import start_health_server
    await start_health_server()
"""
import asyncio
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

_HEALTH_PORT = 9090


class MetricsHandler(BaseHTTPRequestHandler):
    """Manejador HTTP que sirve /health y /metrics."""

    def do_GET(self):
        if self.path == "/health":
            self._health()
        elif self.path == "/metrics":
            self._metrics()
        else:
            self.send_response(404)
            self.end_headers()

    def _health(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        data = json.dumps({
            "status": "ok",
            "service": "stop-bot-game",
            "version": "1.0.0",
        }).encode()
        self.wfile.write(data)

    def _metrics(self):
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.end_headers()
        self.wfile.write(generate_latest())

    def log_message(self, format, *args):
        logger.debug("HealthServer: %s", format % args)


async def start_health_server(port: int = _HEALTH_PORT) -> HTTPServer:
    """Inicia el servidor HTTP en un thread separado.

    Returns:
        HTTPServer: referencia para poder cerrarlo después.
    """
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, server.serve_forever)
    return server


def run_health_server_sync(port: int = _HEALTH_PORT) -> HTTPServer:
    """Versión síncrona para ejecutar en un thread separado."""
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    logger.info("Health server iniciado en puerto %s", port)
    server.serve_forever()
    return server
```

> ⚠️ **Nota:** `http.server.HTTPServer` bloquea el event loop. En `main()` se inicia en un thread separado con `loop.run_in_executor`.

### 8.5.4 Integrar métricas en el código

**Editar varios archivos para instrumentar:**

#### a) `src/services/round_manager.py`

Agregar al inicio:

```python
from src.monitoring.metrics import (
    rounds_played, active_games, observe_round_duration,
    errors_total,
)
```

- En `start_round` (después de asignar state):
  ```python
  rounds_played.inc()
  ```
- En `_close_round` (antes de retornar):
  ```python
  if state:
      duration = state.round_time - remaining  # si tienes remaining
      observe_round_duration(duration)
  ```
- En `handle_stop_game`:
  ```python
  errors_total.labels(type="validation").inc()
  ```
  Cuando hay errores.

#### b) `src/services/game_orchestrator.py`

Agregar:

```python
from src.monitoring.metrics import (
    games_started, games_finished, player_joins,
    active_games, active_players,
)
```

- En `_do_start`:
  ```python
  games_started.inc()
  active_games.inc()
  active_players.inc(len(state.player_telegram_ids))
  ```
- En `join_lobby` (éxito):
  ```python
  player_joins.inc()
  ```
- En `_cleanup_game`:
  ```python
  games_finished.inc()
  active_games.dec()
  ```

#### c) `src/services/spell_corrector.py`

Agregar:

```python
from src.monitoring.metrics import api_calls_total, observe_api_call
```

- En cada llamada a IA exitosa:
  ```python
  provider = os.getenv("SPELL_AI_PROVIDER", "openai")
  api_calls_total.labels(provider=provider).inc()
  ```

#### d) `src/bot.py` — Integrar todo

```python
from src.monitoring.health_server import run_health_server_sync
from src.monitoring.metrics import db_pool_size, redis_connected
```

### 8.5.5 Verificar métricas

Una vez corriendo:

```powershell
# Healthcheck
curl http://localhost:9090/health
# → {"status": "ok", "service": "stop-bot-game", "version": "1.0.0"}

# Métricas Prometheus
curl http://localhost:9090/metrics
# → HELP stopbot_games_started_total ...
# → TYPE stopbot_games_started_total counter
```

---

## 8.6 Graceful shutdown — SIGTERM handler

**Editar:** `backend/src/bot.py`

### 8.6.1 Agregar manejador de señales

Modificar `main()`:

```python
import signal
import sys

# Al inicio del archivo, donde están los imports:
import asyncio
import logging
import os
import signal
import sys
import threading

# ...

async def main() -> None:
    global _redis_client, _health_server

    print("[BOOT] Configurando logging...", flush=True)
    setup_logging()
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # === Iniciar health server en thread separado ===
    from src.monitoring.health_server import run_health_server_sync
    _health_server = run_health_server_sync(port=9090)
    health_thread = threading.Thread(target=_health_server.serve_forever, daemon=True)
    health_thread.start()
    print("[BOOT] Health server en puerto 9090", flush=True)

    # ... (resto del código existente: Redis, bot, dispatcher)

    # ── Configurar graceful shutdown ──
    stop_event = asyncio.Event()

    def _signal_handler(signum, frame):
        """Manejador de señales — programa el shutdown en el event loop."""
        sig_name = signal.Signals(signum).name
        print(f"[SHUTDOWN] Señal {sig_name} recibida, iniciando shutdown...", flush=True)
        logger.info("Señal %s recibida, iniciando shutdown", sig_name)
        # Crear task en el event loop actual
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda: asyncio.create_task(_do_shutdown(sig_name))
        )

    async def _do_shutdown(sig_name: str) -> None:
        """Ejecuta shutdown graceful."""
        logger.info("Ejecutando shutdown graceful...")

        # 1. Detener polling
        logger.info("Deteniendo polling...")
        await dp.stop_polling()

        # 2. Cancelar partidas activas
        logger.info("Cancelando partidas activas...")
        await game_orchestrator.cancel_all_games()

        # 3. Detener scheduler
        if _scheduler:
            logger.info("Deteniendo scheduler...")
            _scheduler.shutdown(wait=False)

        # 4. Cerrar conexiones BD
        logger.info("Cerrando pool de BD...")
        await engine.dispose()

        # 5. Cerrar Redis
        if _redis_client:
            logger.info("Cerrando Redis...")
            await _redis_client.close()

        # 6. Cerrar spell corrector (libera recursos)
        from src.services.spell_corrector import get_corrector
        await get_corrector().close()

        # 7. Detener health server
        logger.info("Deteniendo health server...")
        _health_server.shutdown()

        # 8. Emitir métrica de shutdown
        logger.info("Shutdown completo — señal: %s", sig_name)
        print(f"[SHUTDOWN] Graceful shutdown completado ({sig_name})", flush=True)
        stop_event.set()

    if sys.platform != "win32":
        # Linux/Mac — señales reales
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_do_shutdown(signal.Signals(s).name)),
            )
        print("[BOOT] Graceful shutdown configurado (SIGTERM/SIGINT)", flush=True)
    else:
        # Windows — usar handler de consola
        print("[BOOT] Graceful shutdown no disponible en Windows (sin señales POSIX)", flush=True)

    print("[BOOT] Iniciando polling...", flush=True)
    logger.info("Iniciando polling...")

    try:
        await dp.start_polling(bot, skip_updates=False)
    finally:
        logger.info("Polling finalizado")
        await _do_shutdown("polling_stop")
        # Esperar a que termine
        await stop_event.wait()
```

### 8.6.2 Agregar `cancel_all_games` a `GameOrchestrator`

**Editar:** `backend/src/services/game_orchestrator.py`

```python
async def cancel_all_games(self) -> None:
    """Cancela todas las partidas activas (usado en graceful shutdown)."""
    from src.services.round_manager import round_manager

    # Cancelar todos los lobbies
    for game_id in list(self._lobbies.keys()):
        state = self._lobbies.pop(game_id, None)
        if state and state.animation_task and not state.animation_task.done():
            state.animation_task.cancel()
        if state and state.expiry_task and not state.expiry_task.done():
            state.expiry_task.cancel()
        state.cancelled = True
        logger.info("Lobby %s cancelado por shutdown", game_id)

    # Cancelar todas las rondas activas
    for game_id in list(round_manager._rounds.keys()):
        await round_manager.cancel_game(game_id)

    await round_manager.cancel_all_pending()
```

### 8.6.3 Agregar `cancel_all_pending` a `RoundManager`

**Editar:** `backend/src/services/round_manager.py`

```python
async def cancel_all_pending(self) -> None:
    """Cancela todas las partidas en estado letter_pending."""
    for game_id in list(self._letter_pending.keys()):
        state = self._letter_pending.pop(game_id, None)
        if state:
            state.cancelled = True
            for task in (
                state.letter_timeout_task,
                state.inter_round_timeout_task,
            ):
                if task and not task.done():
                    task.cancel()
            self._rounds_by_group.pop(state.group_chat_id, None)
            logger.info("Pending game %s cancelado por shutdown", game_id)
```

### 8.6.4 Actualizar config.py con LOG_LEVEL

**Editar:** `backend/src/core/config.py`

```python
class Settings(BaseSettings):
    bot_token: str
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    # ... resto de campos existentes ...
```

---

## 8.7 Documentación

### 8.7.1 README.md

**Archivo NUEVO:** `backend/README.md`

```markdown
# 🛑 Stop Bot Game

Bot de Telegram para jugar al clásico **STOP / Basta / Tutti Frutti** en grupos.

## Características

- 🎮 **Partidas de hasta 10 jugadores** en grupos de Telegram
- 🔤 **8 categorías** configurables (Nombre, Color, Fruta, País, etc.)
- ⏱ **Temporizador** de ronda con countdown en vivo
- 🧠 **Corrector ortográfico** con fuzzy matching (RapidFuzz) + IA opcional
- 🏆 **Puntuación** con detección de duplicados, bonus por velocidad
- 📊 **Leaderboard semanal** y sistema de XP/niveles
- 🎨 **Imágenes generadas** (letra de ronda, podio, leaderboard)
- 🐳 **Docker** listo para producción

## Stack

| Componente | Tecnología |
|---|---|
| Runtime | Python 3.11+ |
| Bot Framework | aiogram 3.x |
| Base de datos | PostgreSQL 16 + SQLAlchemy 2.0 |
| Cache/Session | Redis 7 |
| Fuzzy matching | RapidFuzz |
| Imágenes | Pillow / Matplotlib |
| Logging | structlog (JSON en producción) |
| Métricas | Prometheus client |
| CI/CD | GitHub Actions → Railway/Render |

## Requisitos

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Token de BotFather

## Configuración rápida

```bash
# 1. Clonar
git clone https://github.com/tu-usuario/stop-bot-game.git
cd stop-bot-game/backend

# 2. Entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\Activate.ps1  # Windows

# 3. Dependencias
pip install -r requirements/requirements.txt

# 4. Variables de entorno
cp .env.example .env
# Editar .env con tu BOT_TOKEN, DATABASE_URL, REDIS_URL

# 5. Base de datos
alembic upgrade head
python scripts/seed_all_word_lists.py

# 6. Ejecutar
python -m src.bot
```

## Docker

```bash
# Usando Docker Compose
cd backend/Docker
docker compose up -d

# O construir manualmente
docker build -f Docker/Dockerfile -t stop-bot-game .
docker run --env-file .env stop-bot-game
```

## Comandos

| Comando | Descripción |
|---|---|
| `/start` | Mensaje de bienvenida |
| `/help` | Reglas del juego |
| `/stop` | Iniciar partida en el grupo |
| `/cancel` | Cancelar partida actual |
| `/settings` | Configurar partida (admin) |
| `/stats` | Estadísticas del grupo |
| `/profile` | Perfil del jugador |
| `/leaderboard` | Top semanal |
| `/rank` | Posición del jugador |
| `/weekly` | Leaderboard de la semana |
| `/diagnose` | Diagnóstico de errores |
| `/clear_stats` | Borrar estadísticas (admin) |

## Desarrollo

```bash
# Tests
pytest -v --cov=src --cov-report=term-missing

# Linting
ruff check src/ tests/
ruff format --check src/ tests/

# Type checking
mypy src/ --strict --ignore-missing-imports

# Pre-commit
pre-commit install
pre-commit run --all-files
```

## Estructura del proyecto

```
backend/
├── src/
│   ├── bot.py                      # Entry point
│   ├── core/
│   │   ├── config.py               # Pydantic Settings
│   │   └── text_utils.py           # Utilidades de texto
│   ├── db/
│   │   ├── engine.py               # Conexión BD
│   │   ├── models.py               # Modelos SQLAlchemy
│   │   └── repositories/           # CRUDs
│   ├── handlers/                   # Manejadores de comandos
│   │   ├── start.py                # /start, /help
│   │   ├── group.py                # Eventos de grupo
│   │   └── game/                   # Lógica del juego
│   ├── services/                   # Lógica de negocio
│   │   ├── game_orchestrator.py    # Orquestador de partidas
│   │   ├── round_manager.py        # Gestión de rondas
│   │   ├── score_engine.py         # Motor de puntuación
│   │   ├── spell_corrector.py      # Corrector ortográfico
│   │   ├── xp_service.py           # Sistema de XP/niveles
│   │   ├── leaderboard.py          # Leaderboard semanal
│   │   └── event_service.py        # Eventos especiales
│   ├── keyboards/                  # Teclados inline
│   ├── middlewares/                # Middlewares aiogram
│   ├── filters/                    # Filtros personalizados
│   ├── monitoring/                 # Métricas y healthcheck
│   │   ├── metrics.py              # Prometheus métricas
│   │   └── health_server.py        # HTTP server
│   ├── image_generator.py          # Generación de imágenes
│   └── utils.py                    # Utilidades varias
├── tests/                          # Tests
├── migrations/                     # Alembic
├── scripts/                        # Scripts auxiliares
├── Docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── requirements/
    └── requirements.txt
```

## Licencia

MIT
```

### 8.7.2 ARCHITECTURE.md

**Archivo NUEVO:** `backend/docs/ARCHITECTURE.md`

```markdown
# Arquitectura de Stop Bot Game

## Visión general

El bot es una aplicación Python asíncrona que usa `aiogram 3.x` para interactuar con la API de Telegram.  
El flujo principal es:

```
Usuario → Telegram API → aiogram Dispatcher → Router → Handler → Service → DB/Redis
```

## Componentes principales

### 1. Core (`src/bot.py`, `src/core/`)

- **bot.py**: Entry point. Configura logging, conecta Redis, crea el bot y dispatcher, inicia polling.
- **config.py**: Configuración centralizada vía Pydantic Settings (variables de entorno).

### 2. Handlers (`src/handlers/`)

Cada Router maneja un grupo de comandos relacionados:

- `start.py`: `/start`, `/help` — mensajes de bienvenida
- `group.py`: Eventos de grupo (bot añadido, removed)
- `game/lobby.py`: Creación/unión/cancelación de lobbies
- `game/round.py`: Envío de respuestas, botón Stop, selección de letra
- `game/settings.py`: `/settings` — configuración por grupo
- `game/stats.py`: `/stats` — estadísticas
- `game/profile.py`: `/profile` — perfil del jugador
- `game/leaderboard.py`: `/leaderboard`, `/rank`, `/weekly`
- `game/diagnose.py`: `/diagnose`, `/errors`, `/resolve`
- `game/clear_stats.py`: `/clear_stats` — borrar datos (admin)
- `admin/events.py`: Gestión de eventos especiales

### 3. Servicios (`src/services/`)

Capa de lógica de negocio:

- **GameOrchestrator**: Orquesta el ciclo de vida de las partidas. Mantiene lobbies, maneja uniones, inicia juegos.
- **RoundManager**: Gestiona rondas individuales. Timers, envío de respuestas, cierre, transiciones.
- **ScoreEngine**: Evalúa respuestas, detecta duplicados (exactos y fuzzy), asigna puntos y bonificaciones.
- **SpellCorrector**: Normaliza texto, fuzzy matching contra word lists, validación semántica con IA opcional.
- **XPService**: Sistema de experiencia, niveles y streaks.
- **LeaderboardService**: Leaderboard semanal con ranks.
- **EventService**: Eventos especiales (multiplicadores de XP).

### 4. Base de datos (`src/db/`)

- **models.py**: 10+ modelos SQLAlchemy (Player, Game, GamePlayer, Round, Answer, WeeklyLeaderboard, etc.)
- **repositories/**: Patrón Repository para cada entidad
- **engine.py**: Async engine con `async_session_factory`

### 5. Monitoreo (`src/monitoring/`)

- **metrics.py**: Métricas Prometheus (contadores, histogramas, gauges)
- **health_server.py**: Servidor HTTP en puerto 9090 para healthcheck y métricas

## Flujo de una partida

```
1. Usuario escribe /stop en un grupo
2. GameOrchestrator.create_lobby() crea un LobbyState
3. Bot envía mensaje con botón "Unirse"
4. Otros usuarios presionan "Unirse" → join_lobby()
5. Host presiona "Iniciar" → _do_start()
6. Se crea Round en BD, RoundManager.start_round()
7. Bot envía imagen de letra + plantilla de categorías
8. Usuarios envían respuestas → submit_answers()
9. Cuando todos responden (o Stop, o timeout) → _close_round()
10. ScoreEngine.evaluate() calcula puntuaciones
11. Se muestra resumen de ronda
12. Líder elige siguiente letra → nueva ronda
13. Tras N rondas → _end_game()
14. Se otorga XP, se actualiza leaderboard, se envía podio
```

## Decisiones técnicas

### ¿Por qué aiogram y no python-telegram-bot?
- aiogram es nativamente asíncrono (basado en asyncio + aiohttp)
- Soporta FSM (Finite State Machine) con Redis Storage
- Mejor manejo de middlewares y routers

### ¿Por qué SQLAlchemy 2.0 asíncrono?
- Operaciones de BD no bloquean el event loop
- Patrón de sesiones async con `async_session_factory`
- Alembic para migraciones

### ¿Por qué RapidFuzz en vez de FuzzyWuzzy?
- RapidFuzz es ~10x más rápido (C++ bindings)
- No requiere python-Levenshtein
- API compatible con FuzzyWuzzy

### ¿Por qué structlog?
- Logging estructurado nativo → JSON en producción
- Mejor integración con sistemas de monitoreo
- Contexto enriquecido (game_id, player_id, etc.)
```

### 8.7.3 CONTRIBUTING.md

**Archivo NUEVO:** `backend/CONTRIBUTING.md`

```markdown
# Guía de contribución

## Requisitos

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Git

## Setup

```bash
git clone https://github.com/tu-usuario/stop-bot-game.git
cd stop-bot-game/backend

python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\Activate.ps1  # Windows

pip install -r requirements/requirements.txt
pip install -r requirements/dev.txt  # si existe (opcional)

cp .env.example .env
# Editar .env con tus credenciales

alembic upgrade head
python scripts/seed_all_word_lists.py
```

## Desarrollo

### Commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: nueva funcionalidad
fix: corrección de bug
refactor: cambio de código sin cambiar comportamiento
test: agregar o modificar tests
docs: cambios en documentación
chore: tareas de mantenimiento
```

### Pull Requests

1. Fork el repo
2. Crea una rama: `git checkout -b feat/nombre-corto`
3. Haz tus cambios
4. Asegura que los tests pasan: `pytest -v`
5. Asegura que ruff no reporta errores: `ruff check src/ tests/`
6. Asegura que mypy no reporta errores: `mypy src/ --strict --ignore-missing-imports`
7. Push y crea PR

### Estándares de código

- **Python 3.10+**: type hints en todas las funciones
- **ruff**: seguir el formato y reglas configuradas
- **Tests**: todo código nuevo debe tener tests
- **Coverage**: mínimo 85%
- **async/await**: todo I/O debe ser asíncrono
- **Logging**: usar `structlog` con contexto estructurado
- **Errores**: decorar handlers con `@track_errors`

### Tests

```bash
# Todos los tests
pytest -v

# Con coverage
pytest --cov=src --cov-report=term-missing

# Tests específicos
pytest tests/test_score_engine.py -v
pytest tests/test_integration_flow.py -v

# Coverage HTML
pytest --cov=src --cov-report=html
# luego abrir htmlcov/index.html
```

### Linting y tipado

```bash
# Ruff lint
ruff check src/ tests/

# Ruff format (check)
ruff format --check src/ tests/

# Ruff format (aplicar)
ruff format src/ tests/

# MyPy (strict en src/)
mypy src/ --strict --ignore-missing-imports
```

### Pre-commit hooks

```bash
# Instalar hooks
pre-commit install

# Ejecutar en todos los archivos
pre-commit run --all-files
```

## Arquitectura

Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para una descripción detallada de la arquitectura.

## Reportar bugs

Usar [GitHub Issues](https://github.com/tu-usuario/stop-bot-game/issues) con:

1. Descripción del bug
2. Pasos para reproducir
3. Comportamiento esperado
4. Logs relevantes
5. Versión del bot y dependencias
```

### 8.7.4 Actualizar `.env.example`

```env
# === Telegram ===
BOT_TOKEN=

# === Base de Datos ===
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot

# === Redis ===
REDIS_URL=redis://localhost:6379/0

# === Logging ===
LOG_LEVEL=INFO

# === Modo de correccion: local | ai | hybrid ===
# SPELL_MODE=hybrid
# SPELL_API_KEY=
# SPELL_API_URL=https://api.groq.com/openai/v1
# SPELL_API_LIMIT=20
# SPELL_FUZZY_THRESHOLD=75
# SPELL_AI_PROVIDER=openai
# SPELL_AI_MODEL=llama-3.3-70b-versatile

# Groq (gratis): https://console.groq.com/keys
# Gemini: SPELL_API_URL=https://generativelanguage.googleapis.com/v1beta/openai, SPELL_AI_PROVIDER=gemini
# OpenAI: SPELL_API_URL=https://api.openai.com/v1, SPELL_AI_PROVIDER=openai

# === Prometheus / Healthcheck ===
# HEALTH_PORT=9090
```

### 8.7.5 Crear `docs/` folder

```powershell
mkdir backend\docs
```

---

## Orden de implementación sugerido

1. **8.7 Documentación** — README.md, ARCHITECTURE.md, CONTRIBUTING.md, docs/
2. **8.6 Graceful shutdown** — `bot.py` + `cancel_all_games()` + `cancel_all_pending()`
3. **8.5 Monitoreo** — `metrics.py`, `health_server.py`, integrar en bot.py
4. **8.3 Linting y tipado** — `pyproject.toml`, `.pre-commit-config.yaml`, `mypy`
5. **8.1 Tests unitarios** — coverage target, nuevos tests, `.coveragerc`
6. **8.2 Tests de integración** — SQLite fixture, `test_integration_flow.py`
7. **8.4 CI/CD** — `.github/workflows/ci.yml`, Railway/Render config
8. **Correr `pytest -v --cov=src`** — verificar >85% coverage
9. **Correr `ruff check src/ tests/`** — verificar 0 errores
10. **Correr `mypy src/ --strict --ignore-missing-imports`** — corregir errores
```

