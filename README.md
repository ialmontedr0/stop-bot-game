# Stop Bot Game

Multiplayer Telegram word game bot. Players compete in rounds to write words for random categories starting with a given letter. Features fuzzy spell correction, AI-powered validation, XP/levels/streaks, and a weekly leaderboard.

Built with **Python 3.10+**, **aiogram 3.x**, **PostgreSQL**, and **Redis** (optional).

---

## Features

| Feature | Description |
|---|---|
| **Game lobby** | `/stop` creates a lobby; players join with inline buttons |
| **Round system** | Random letter + category, timer-driven, interactive STOP button |
| **Spell correction** | Fuzzy matching (rapidfuzz) + optional AI (Groq/OpenAI/Gemini) |
| **Scoring** | Deduplication, first-completer bonus, category completion bonus |
| **XP & levels** | Points per round, level-up milestones, streak bonuses |
| **Leaderboard** | Weekly reset via APScheduler, sorted by XP |
| **i18n** | Spanish (`es`), English (`en`), Portuguese (`pt`) via gettext/Babel |
| **Error tracking** | `/diagnose`, `/errors`, `/resolve` for admin troubleshooting |
| **Monitoring** | Prometheus metrics (`/metrics`) + health endpoint (`/health`) on port 9090 |
| **Graceful shutdown** | SIGTERM/SIGINT handlers cancel games, drain connections |

---

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 16+
- Redis 7+ (optional — falls back to `MemoryStorage`)
- Telegram bot token from [@BotFather](https://t.me/BotFather)

### Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

pip install -U pip
pip install -r requirements/requirements.txt
```

### Configuration

Create `backend/.env`:

```ini
BOT_TOKEN=your:token_from_botfather
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/stopbot
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO

# === Spell correction (optional) ===
SPELL_MODE=hybrid
SPELL_API_KEY=gsk_your_groq_key
SPELL_API_URL=https://api.groq.com/openai/v1
SPELL_API_LIMIT=20
SPELL_FUZZY_THRESHOLD=75
SPELL_AI_PROVIDER=openai
SPELL_AI_MODEL=llama-3.3-70b-versatile
```

### Database

```bash
alembic upgrade head
python -m scripts.seed_all_word_lists
```

### Run

```bash
python -m src.bot
```

---

## Tests

```bash
pytest -v
# 427 tests, 64% coverage
```

CI enforces `--cov-fail-under=85` (target).

---

## Project Structure

```
backend/
├── src/
│   ├── bot.py                     # Entry point, router registration, startup/shutdown
│   ├── core/
│   │   ├── config.py             # Pydantic Settings (reads .env)
│   │   └── text_utils.py         # Normalization helpers
│   ├── db/
│   │   ├── engine.py             # Async SQLAlchemy engine + session factory
│   │   ├── models.py             # ORM: Player, Game, GamePlayer, Answer, etc.
│   │   └── repositories/         # Data access layer (9 repos)
│   ├── handlers/
│   │   ├── start.py              # /start, /help
│   │   ├── group.py              # Group join/leave events
│   │   ├── admin/events.py       # Admin-only handlers
│   │   └── game/                 # Lobby, rounds, settings, stats, profile, leaderboard
│   ├── keyboards/                # Inline keyboard builders
│   ├── middlewares/
│   │   ├── throttling.py         # Rate limiter
│   │   └── user_exists.py        # Auto-create Player on first interaction
│   ├── monitoring/
│   │   ├── health_server.py      # HTTP server (port 9090)
│   │   └── metrics.py            # Prometheus counters
│   └── services/
│       ├── game_orchestrator.py  # Lobby, game lifecycle, cancellations
│       ├── round_manager.py      # Round timer, submissions, STOP logic
│       ├── score_engine.py       # Duplicate detection, bonuses
│       ├── spell_corrector.py    # Fuzzy + AI correction
│       ├── xp_service.py         # XP, levels, streaks
│       ├── leaderboard.py        # Weekly leaderboard
│       ├── error_tracker.py      # Error classification + /diagnose
│       └── event_service.py      # Game event bus
├── tests/                        # 427 tests, 29 test files
├── migrations/                   # Alembic (7 versions)
├── scripts/                      # Seed scripts, smoke tests
├── locales/                      # es/en/po translations
├── Docker/                       # Dockerfile + docker-compose.yml
├── docs/                         # ARCHITECTURE.md, CONTRIBUTING.md, DEPLOY_ALWAYSDATA.md
├── pyproject.toml                # mypy, ruff, coverage config
└── pytest.ini
```

---

## API / Commands

| Command | Description |
|---|---|
| `/start` | Welcome message with instructions |
| `/help` | Command list |
| `/stop` | Start a new game lobby |
| `/cancel` | Cancel ongoing game |
| `/settings` | Per-group validation mode |
| `/stats [@user]` | Player stats |
| `/profile` | XP, level, streak, badges |
| `/leaderboard` | Weekly top players |
| `/diagnose` | Admin: system health report |
| `/errors` | Admin: recent errors |
| `/resolve <id>` | Admin: mark error resolved |
| `/clear` | Admin: delete bot messages |
| `/clear_stats` | Admin: reset all stats |

---

## Deployment

- **Alwaysdata free tier**: see [`docs/DEPLOY_ALWAYSDATA.md`](backend/docs/DEPLOY_ALWAYSDATA.md)
- **Docker**: `cd backend/Docker && docker-compose up -d`

---

## Tech Stack

- **Runtime**: Python 3.10+ (3.13 tested)
- **Framework**: aiogram 3.x
- **Database**: PostgreSQL 16+ via SQLAlchemy 2.0 (async)
- **Cache**: Redis 7+ (optional, MemoryStorage fallback)
- **ORM**: SQLAlchemy 2.0 + Alembic
- **AI**: OpenAI SDK (Groq/Gemini/OpenAI)
- **Fuzzy**: rapidfuzz
- **Monitoring**: Prometheus client
- **Logging**: structlog (JSON in production)
- **CI**: GitHub Actions (ruff, mypy, pytest, Docker)
- **Quality**: pre-commit, mypy strict, ruff, pytest-cov
