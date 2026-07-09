# Guia de contribucion

## Requisitos

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Poetry o pip + venv

## Setup

```bash
git clone https://github.com/ialmontedr0/stop-bot-game.git
cd stop-bot-game/backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\Activate.ps1  # Windows
pip install -r requirements/requirements.txt
cp .env.example .env
# Editar .env con BOT_TOKEN, DATABASE_URL, REDIS_URL
alembic upgrade head
python scripts/seed_all_word_lists.py
```

## Tests

```bash
pytest -v --cov=src --cov-report=term-missing
```

Apunta a >85% de coverage. Los tests de integracion usan SQLite in-memory.

## Linting

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/ --strict --ignore-missing-imports
```

## Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

## Estructura de ramas

- `main`: Produccion.
- `develop`: Integracion.
- `feature/*`: Nuevas features.
- `fix/*`: Correcciones.

## Pull Requests

1. Rama desde `develop`.
2. Tests pasando y coverage >85%.
3. Ruff y mypy sin errores.
4. Descripcion clara de cambios.
