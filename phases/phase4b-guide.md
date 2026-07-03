# Phase 4B — Word Lists en Base de Datos (Colores, Frutas, Países)

**Objetivo:** Migrar las listas de palabras de `color`, `fruta` y `pais` desde `SEED_WORDS` hardcodeado a la base de datos PostgreSQL, cargándolas en memoria al iniciar el bot. Así se garantiza persistencia, escalabilidad y la base para futuras expansiones comunitarias.

**Relación con otras fases:**
- Fase 4A implementó `SpellCorrector` con fuzzy matching y `SEED_WORDS` en memoria.
- Fase 4B reemplaza 3 de las 8 categorías (color, fruta, país) con datos desde BD.
- Las otras 5 categorías (nombre, apellido, artista, novela/serie, cosa) permanecen en `SEED_WORDS` sin cambios.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                   bot.py (startup)                   │
│  on_startup():                                       │
│    await get_corrector().load_db_word_lists()         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              SpellCorrector._word_lists                │
│  nombre → SEED_WORDS (memoria)                        │
│  apellido → SEED_WORDS (memoria)                      │
│  artista → SEED_WORDS (memoria)                       │
│  novela/serie → SEED_WORDS (memoria)                  │
│  cosa → SEED_WORDS (memoria)                          │
│  color → DB → `word_list_items`                       │
│  fruta → DB → `word_list_items`                       │
│  pais → DB → `word_list_items`                        │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              Scoring flow (score_engine.py)            │
│                                                       │
│  _determine_answer_scores_fuzzy():                     │
│    1. Para color/fruta/pais:                           │
│       a. Validar contra word list (exacto o fuzzy)     │
│       b. Si no es válido → 0 puntos                    │
│       c. Si es válido → clustering normal              │
│    2. Para otras categorías: mismo comportamiento      │
└──────────────────────────────────────────────────────┘
```

### Flujo de validación para color/fruta/pais

```
respuesta_usuario ("colombia", categoría="pais")
  │
  ├─ normalize() → "colombia"
  │
  ├─ ¿Está en word_list["pais"]?
  │   ├─ Sí → válido, usar para clustering
  │   └─ No →
  │        └─ fuzzy_match contra word_list["pais"]
  │            ├─ match >= threshold → válido (usar forma corregida)
  │            └─ no match → inválido → 0 puntos
  │
  └─ Resultado: sigue a cluster_answers() o se marca 0
```

---

## Archivos a modificar/crear

| # | Archivo | Acción |
|---|---------|--------|
| 1 | `src/db/models.py` | Añadir modelo `WordListItem` |
| 2 | `migrations/versions/0002_word_list_items.py` | Nueva migración Alembic |
| 3 | `src/db/repositories/word_list_repository.py` | Nuevo repositorio |
| 4 | `src/db/repositories/__init__.py` | Exportar `WordListRepository` |
| 5 | `scripts/seed_word_lists.py` | Nuevo script de seed |
| 6 | `src/services/spell_corrector.py` | Añadir `validate_against_db()`, `load_db_word_lists()`, quitar color/fruta/pais de `SEED_WORDS` |
| 7 | `src/services/score_engine.py` | Añadir validación contra word list en `_determine_answer_scores_fuzzy` |
| 8 | `src/bot.py` | Llamar `load_db_word_lists()` en `on_startup` |
| 9 | `src/core/config.py` | *(sin cambios)* |
| 10 | `tests/test_word_list_repository.py` | Tests del repositorio |
| 11 | `tests/test_score_engine.py` | Tests de validación contra word list |

---

## 1. Modelo `WordListItem` — `src/db/models.py`

Añadir al final del archivo, antes de la última línea:

```python
class WordListItem(Base):
    __tablename__ = "word_list_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    word: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    def __repr__(self) -> str:
        return f"<WordListItem id={self.id} cat={self.category} word={self.word}>"
```

No se necesita `UniqueConstraint` porque puede haber variantes regionales (ej: "palta" y "aguacate" para la misma fruta). Cada row es una entrada independiente.

---

## 2. Migración Alembic

```powershell
cd backend
alembic revision --autogenerate -m "add_word_list_items"
```

Esto generará un archivo en `migrations/versions/`. Verificar que contenga:

```python
"""add_word_list_items

Revision ID: xxxxxx
Revises: 0001_initial
Create Date: ...
"""
from alembic import op
import sqlalchemy as sa

revision = "xxxxxx"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "word_list_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("word", sa.String(128), nullable=False),
        sa.Column("normalized", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_word_list_items_category"), "word_list_items", ["category"])
    op.create_index(op.f("ix_word_list_items_normalized"), "word_list_items", ["normalized"])


def downgrade() -> None:
    op.drop_index(op.f("ix_word_list_items_normalized"), table_name="word_list_items")
    op.drop_index(op.f("ix_word_list_items_category"), table_name="word_list_items")
    op.drop_table("word_list_items")
```

Ejecutar:

```powershell
alembic upgrade head
```

---

## 3. Repositorio `WordListRepository`

Crear `src/db/repositories/word_list_repository.py`:

```python
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import WordListItem


class WordListRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_words_by_category(self, category: str) -> list[str]:
        stmt = (
            select(WordListItem.normalized)
            .where(WordListItem.category == category)
            .order_by(WordListItem.normalized)
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result]

    async def get_words_with_originals(self, category: str) -> list[tuple[str, str]]:
        """Retorna (normalized, original_word) para cada entrada."""
        stmt = (
            select(WordListItem.normalized, WordListItem.word)
            .where(WordListItem.category == category)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result]

    async def word_exists(self, normalized: str, category: str) -> bool:
        stmt = select(WordListItem.id).where(
            WordListItem.category == category,
            WordListItem.normalized == normalized,
        ).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def bulk_insert(
        self, category: str, words: list[tuple[str, str]]
    ) -> int:
        """Inserta múltiples palabras. Cada tupla es (normalized, original).
        Returns cantidad de inserts.
        """
        existing = set(await self.get_words_by_category(category))
        count = 0
        for norm, word in words:
            if norm not in existing:
                self.session.add(WordListItem(
                    category=category,
                    word=word,
                    normalized=norm,
                ))
                count += 1
        if count:
            await self.session.commit()
        return count

    async def clear_category(self, category: str) -> int:
        """Elimina todas las palabras de una categoría. Retorna cantidad eliminada."""
        stmt = delete(WordListItem).where(WordListItem.category == category)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def count_by_category(self, category: str) -> int:
        stmt = select(WordListItem.id).where(WordListItem.category == category)
        result = await self.session.execute(stmt)
        return len(result.all())
```

Actualizar `src/db/repositories/__init__.py`:

```python
from .base import BaseRepository
from .player_repository import PlayerRepository
from .game_repository import GameRepository
from .round_repository import RoundRepository
from .word_list_repository import WordListRepository

__all__ = [
    "BaseRepository",
    "PlayerRepository",
    "GameRepository",
    "RoundRepository",
    "WordListRepository",
]
```

---

## 4. Datos semilla

### 4.1 Estructura de datos

Crear `scripts/word_list_data.py` — **archivo de datos puro**, sin dependencias de la BD. Contiene las listas completas de colores, frutas y países con todas las variantes regionales.

```python
"""
Listas completas de palabras para validación en Stop Bot.
Cada entrada es el nombre tal como se escribe (con tildes, mayúsculas, etc.),
el sistema las normalizará al insertar en BD.

Organización:
  - color: lista plana de ~100 colores con variantes ES/LATAM
  - fruta: lista plana de ~90 frutas con variantes ES/LATAM
  - pais: lista plana de ~200 países + variantes ortográficas
"""

COLORS: list[str] = [
    # ── Básicos ──
    "Blanco",
    "Negro",
    "Gris",
    "Rojo",
    "Azul",
    "Amarillo",
    "Verde",
    "Naranja",
    "Anaranjado",
    "Morado",
    "Púrpura",
    "Violeta",
    "Rosa",
    "Rosado",
    "Marrón",
    "Café",
    # ── Cálidos ──
    "Carmesí",
    "Carmín",
    "Escarlata",
    "Bermellón",
    "Granate",
    "Vino",
    "Burdeos",
    "Coral",
    "Salmón",
    "Terracota",
    "Ladrillo",
    "Cobre",
    "Caoba",
    "Óxido",
    "Melocotón",
    "Durazno",
    "Albaricoque",
    "Ámbar",
    "Mostaza",
    "Dorado",
    "Oro",
    "Ocre",
    "Arena",
    "Beige",
    "Crema",
    "Marfil",
    "Hueso",
    # ── Azules ──
    "Celeste",
    "Turquesa",
    "Aguamarina",
    "Cian",
    "Índigo",
    "Añil",
    "Cerúleo",
    "Cobalto",
    "Ultramar",
    "Zafiro",
    # ── Verdes ──
    "Lima",
    "Oliva",
    "Esmeralda",
    "Jade",
    "Menta",
    "Musgo",
    "Pino",
    "Pistacho",
    "Caqui",
    # ── Amarillos ──
    "Canario",
    "Pastel",
    # ── Violetas y rosas ──
    "Lila",
    "Lavanda",
    "Malva",
    "Magenta",
    "Fucsia",
    "Orquídea",
    # ── Marrones ──
    "Chocolate",
    "Canela",
    "Avellana",
    "Castaño",
    "Tabaco",
    "Siena",
    "Tierra",
    "Habano",
    # ── Metálicos ──
    "Plata",
    "Plateado",
    "Bronce",
    "Latón",
    "Platino",
    "Titanio",
    # ── Especiales ──
    "Rubí",
    "Perla",
    "Nácar",
    "Ébano",
    "Humo",
    "Carbón",
    "Grafito",
    "Neón",
    "Fluorescente",
]

FRUITS: list[str] = [
    # A
    "Abiu",
    "Abiú",
    "Aceituna",
    "Acerola",
    "Aguacate",
    "Palta",
    "Akebia",
    "Albaricoque",
    "Damasco",
    "Chabacano",
    "Almendra",
    "Ananá",
    "Piña",
    "Arándano",
    "Arándano rojo",
    "Atemoya",
    "Avellana",
    "Açaí",
    # B
    "Babaco",
    "Badea",
    "Banana",
    "Plátano",
    "Banano",
    "Guineo",
    "Cambur",
    "Bergamota",
    "Borojó",
    # C
    "Cacao",
    "Caimito",
    "Carambola",
    "Cereza",
    "Guinda",
    "Chirimoya",
    "Ciruela",
    "Ciruela pasa",
    "Coco",
    # D
    "Dátil",
    "Durián",
    # E
    "Endrina",
    "Escaramujo",
    # F
    "Feijoa",
    "Frambuesa",
    "Fresa",
    "Frutilla",
    # G
    "Granada",
    "Granadilla",
    "Grosella",
    "Guanábana",
    "Guaraná",
    "Guayaba",
    # H
    "Higo",
    # I
    "Icaco",
    "Ilama",
    # J
    "Jaboticaba",
    "Jambo",
    "Jujuba",
    "Azufaifa",
    # K
    "Kaki",
    "Caqui",
    "Kiwi",
    "Kumquat",
    "Quinoto",
    # L
    "Limón",
    "Lima",
    "Lichi",
    "Longan",
    "Lúcuma",
    "Lulo",
    "Naranjilla",
    # M
    "Mamey",
    "Mamoncillo",
    "Quenepa",
    "Limoncillo",
    "Mandarina",
    "Mango",
    "Mangostán",
    "Manzana",
    "Maracuyá",
    "Parcha",
    "Fruta de la pasión",
    "Melocotón",
    "Melón",
    "Membrillo",
    "Mirabel",
    "Mora",
    "Zarzamora",
    # N
    "Naranja",
    "Naranja sanguina",
    "Naranja roja",
    "Nectarina",
    "Níspero",
    "Noni",
    # P
    "Papaya",
    "Lechosa",
    "Pera",
    "Persimón",
    "Physalis",
    "Uchuva",
    "Aguaymanto",
    "Pitanga",
    "Pitahaya",
    "Fruta del dragón",
    "Pomelo",
    "Toronja",
    # R
    "Rambután",
    # S
    "Sandía",
    "Patilla",
    "Sapote",
    "Zapote",
    # T
    "Tamarillo",
    "Tomate de árbol",
    "Tamarindo",
    "Tuna",
    "Higo chumbo",
    # U
    "Uva",
    "Uva espina",
    # Y
    "Yaca",
    "Jackfruit",
    "Yuzu",
    # Z
    "Zarzamora",
    # Las frutas duplicadas con nombres diferentes ya están incluidas arriba
    # con sus variantes (ej: "Palta" y "Aguacate")
]

COUNTRIES: list[str] = [
    "Afganistán",
    "Albania",
    "Alemania",
    "Andorra",
    "Angola",
    "Antigua y Barbuda",
    "Arabia Saudita",
    "Argelia",
    "Argentina",
    "Armenia",
    "Australia",
    "Austria",
    "Azerbaiyán",
    # B
    "Bahamas",
    "Baréin",
    "Bangladés",
    "Barbados",
    "Bélgica",
    "Belice",
    "Benín",
    "Bielorrusia",
    "Birmania",
    "Myanmar",
    "Bolivia",
    "Bosnia y Herzegovina",
    "Botsuana",
    "Brasil",
    "Brunéi",
    "Bulgaria",
    "Burkina Faso",
    "Burundi",
    "Bután",
    # C
    "Cabo Verde",
    "Camboya",
    "Camerún",
    "Canadá",
    "Catar",
    "Qatar",
    "Chad",
    "Chile",
    "China",
    "Chipre",
    "Ciudad del Vaticano",
    "Vaticano",
    "Colombia",
    "Comoras",
    "Corea del Norte",
    "Corea del Sur",
    "Costa de Marfil",
    "Costa Rica",
    "Croacia",
    "Cuba",
    # D
    "Dinamarca",
    "Dominica",
    # E
    "Ecuador",
    "Egipto",
    "El Salvador",
    "Emiratos Árabes Unidos",
    "Eritrea",
    "Eslovaquia",
    "Eslovenia",
    "España",
    "Estados Unidos",
    "Estado de Palestina",
    "Palestina",
    "Estonia",
    "Esuatini",
    "Etiopía",
    # F
    "Filipinas",
    "Finlandia",
    "Fiyi",
    "Francia",
    # G
    "Gabón",
    "Gambia",
    "Georgia",
    "Ghana",
    "Granada",
    "Grecia",
    "Guatemala",
    "Guinea",
    "Guinea-Bisáu",
    "Guinea Ecuatorial",
    "Guyana",
    # H
    "Haití",
    "Honduras",
    "Hungría",
    # I
    "India",
    "Indonesia",
    "Irak",
    "Irán",
    "Irlanda",
    "Islandia",
    "Islas Marshall",
    "Islas Salomón",
    "Israel",
    "Italia",
    # J
    "Jamaica",
    "Japón",
    "Jordania",
    # K
    "Kazajistán",
    "Kenia",
    "Kirguistán",
    "Kiribati",
    "Kuwait",
    # L
    "Laos",
    "Lesoto",
    "Letonia",
    "Líbano",
    "Liberia",
    "Libia",
    "Liechtenstein",
    "Lituania",
    "Luxemburgo",
    # M
    "Macedonia del Norte",
    "Madagascar",
    "Malasia",
    "Malaui",
    "Maldivas",
    "Malí",
    "Malta",
    "Marruecos",
    "Mauricio",
    "Mauritania",
    "México",
    "Micronesia",
    "Moldavia",
    "Moldova",
    "Mónaco",
    "Mongolia",
    "Montenegro",
    "Mozambique",
    # N
    "Namibia",
    "Nauru",
    "Nepal",
    "Nicaragua",
    "Níger",
    "Nigeria",
    "Noruega",
    "Nueva Zelanda",
    # O
    "Omán",
    # P
    "Países Bajos",
    "Pakistán",
    "Palaos",
    "Panamá",
    "Papúa Nueva Guinea",
    "Paraguay",
    "Perú",
    "Polonia",
    "Portugal",
    # R
    "Reino Unido",
    "República Centroafricana",
    "República Checa",
    "Chequia",
    "República del Congo",
    "República Democrática del Congo",
    "República Dominicana",
    "Ruanda",
    "Rumanía",
    "Rusia",
    # S
    "Samoa",
    "San Cristóbal y Nieves",
    "San Marino",
    "San Vicente y las Granadinas",
    "Santa Lucía",
    "Santo Tomé y Príncipe",
    "Senegal",
    "Serbia",
    "Seychelles",
    "Sierra Leona",
    "Singapur",
    "Siria",
    "Somalia",
    "Sri Lanka",
    "Sudáfrica",
    "Sudán",
    "Sudán del Sur",
    "Suecia",
    "Suiza",
    "Surinam",
    # T
    "Tailandia",
    "Tanzania",
    "Tayikistán",
    "Timor Oriental",
    "Togo",
    "Tonga",
    "Trinidad y Tobago",
    "Túnez",
    "Turkmenistán",
    "Turquía",
    "Türkiye",
    "Tuvalu",
    # U
    "Ucrania",
    "Uganda",
    "Uruguay",
    "Uzbekistán",
    # V
    "Vanuatu",
    "Venezuela",
    "Vietnam",
    # Y
    "Yemen",
    "Yibuti",
    # Z
    "Zambia",
    "Zimbabue",
]

# ── Mapa de categorías para el seed ──────────────────────────────────

WORD_LIST_DATA: dict[str, list[str]] = {
    "color": COLORS,
    "fruta": FRUITS,
    "pais": COUNTRIES,
}
```

### 4.2 Script de seed

Crear `scripts/seed_word_lists.py`:

```python
#!/usr/bin/env python
"""
Script para poblar la tabla word_list_items con colores, frutas y países.

Uso:
    cd backend
    python -m scripts.seed_word_lists

Es idempotente: limpia cada categoría antes de reinsertar.
"""

import asyncio
import sys
import os

# Asegurar que podemos importar desde src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.text_utils import normalize_text
from src.db.engine import async_session_factory
from src.db.repositories.word_list_repository import WordListRepository
from scripts.word_list_data import WORD_LIST_DATA


async def seed_category(repo: WordListRepository, category: str, words: list[str]) -> None:
    """Inserta todas las palabras de una categoría, limpiando primero."""
    deleted = await repo.clear_category(category)
    print(f"  Limpiadas {deleted} entradas existentes en '{category}'")

    items = [(normalize_text(w), w.strip()) for w in words if w.strip()]
    # Eliminar duplicados normalizados dentro de la misma categoría
    seen: set[str] = set()
    unique_items: list[tuple[str, str]] = []
    for norm, orig in items:
        if norm not in seen:
            seen.add(norm)
            unique_items.append((norm, orig))

    count = await repo.bulk_insert(category, unique_items)
    print(f"  Insertadas {count} palabras en '{category}' ({len(unique_items)} únicas normalizadas)")
    total = await repo.count_by_category(category)
    print(f"  Total en BD para '{category}': {total}")


async def main() -> None:
    print("=== Seed de Word Lists ===")
    print()

    for category, words in WORD_LIST_DATA.items():
        print(f"Procesando categoría: {category}")
        async with async_session_factory() as session:
            repo = WordListRepository(session)
            await seed_category(repo, category, words)
        print()

    # Mostrar resumen final
    print("=== Resumen final ===")
    async with async_session_factory() as session:
        repo = WordListRepository(session)
        for cat in WORD_LIST_DATA:
            total = await repo.count_by_category(cat)
            print(f"  {cat}: {total} palabras")
    print("=== Seed completado ===")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. Modificaciones a `SpellCorrector` — `src/services/spell_corrector.py`

### 5.1 Quitar color/fruta/pais de `SEED_WORDS`

Reemplazar las entradas de `color`, `fruta` y `pais` en `SEED_WORDS` con sets **vacíos**. Ya no se cargan desde código, se cargarán desde BD.

```python
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
    "color": set(),       # ← Ahora se carga desde BD
    "fruta": set(),       # ← Ahora se carga desde BD
    "pais": set(),        # ← Ahora se carga desde BD
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
        "la casa de papel", "el chavo", "el principito", "1984",
        "crimen y castigo", "orgullo y prejuicio", "matar a un ruisenor",
        "harry potter", "el senor de los anillos", "cancion de hielo y fuego",
    },
    "cosa": {
        "mesa", "silla", "cama", "coche", "casa", "libro", "lapiz",
        "computadora", "telefono", "reloj", "zapato", "camisa", "plato",
        "vaso", "llave", "bolsa", "ventana", "puerta", "lampara", "cuchara",
        "tenedor", "cuchillo", "tv", "television", "radio", "bicicleta",
        "moto", "avion", "barco", "tren", "pelota", "guitarra", "piano",
        "bateria", "sofa", "armario", "estante", "cuadro", "espejo",
    },
}
```

### 5.2 Añadir `load_db_word_lists()` a `SpellCorrector`

Añadir estos métodos a la clase `SpellCorrector`:

```python
# ── Carga desde base de datos ──────────────────────────────────────

DB_CATEGORIES = {"color", "fruta", "pais"}

async def load_db_word_lists(self) -> None:
    """Carga color/fruta/pais desde la BD y los fusiona en _word_lists.
    Debe llamarse una vez al iniciar el bot, cuando la BD está disponible.
    """
    from src.db.engine import async_session_factory
    from src.db.repositories.word_list_repository import WordListRepository

    async with async_session_factory() as session:
        repo = WordListRepository(session)
        for category in self.DB_CATEGORIES:
            words = await repo.get_words_by_category(category)
            self._word_lists[category] = set(words)
            logger.info(
                "Word list cargada desde BD: %s = %d palabras",
                category, len(words),
            )

def is_db_category(self, category: str) -> bool:
    """Retorna True si la categoría se valida contra la BD."""
    return category.lower().strip() in self.DB_CATEGORIES
```

### 5.3 Añadir `validate_against_list()` a `SpellCorrector` (método sync)

Este es el corazón de la validación: comprueba si una palabra es válida para una categoría usando la word list (exact match + fuzzy). Es **síncrono** (sin IA), para poder usarlo dentro del scoring sin async.

```python
def validate_against_list(
    self, word: str, category: str
) -> tuple[bool, str]:
    """Valida una palabra contra la word list de su categoría.

    Args:
        word: Palabra a validar.
        category: Categoría (normalizada, ej: 'color').

    Returns:
        Tuple[bool, str]: (es_válida, forma_normalizada_corregida).
        Si no es válida, la forma normalizada es la original sin corrección.
    """
    norm = self.normalize(word)
    cat_lower = category.lower().strip()
    cat_words = self._word_lists.get(cat_lower, set())

    # 1 — Exact match en word list
    if norm in cat_words:
        return True, norm

    # 2 — Fuzzy match contra word list
    if cat_words:
        best, score = self.fuzzy_match(word, list(cat_words))
        if best is not None:
            corrected_norm = self.normalize(best)
            # Aprender: añadir a word list para futuros matches exactos
            cat_words.add(norm)
            return True, corrected_norm

    # 3 — No válido
    return False, norm
```

### 5.4 Nota importante sobre el `__init__`

No cambiar el `__init__`. El deep-copy de `SEED_WORDS` sigue funcionando igual. Las categorías `color`, `fruta` y `pais` arrancan vacías y se llenan cuando `load_db_word_lists()` se ejecuta. Si por algún motivo la BD no está disponible al inicio, esas categorías simplemente tendrán lista vacía (todo será inválido = 0 puntos) hasta que se carguen.

---

## 6. Modificaciones a ScoreEngine — `src/services/score_engine.py`

### 6.1 Pasar `category` a `_determine_answer_scores`

```python
def _determine_answer_scores(
    player_answers: list[tuple[int, Answer]],
    spell_corrector: Optional["SpellCorrector"] = None,
    letter: Optional[str] = None,
    category: Optional[str] = None,              # ← NUEVO
) -> dict[int, tuple[bool, int]]:
    if spell_corrector is not None:
        return _determine_answer_scores_fuzzy(
            player_answers, spell_corrector,
            letter=letter,
            category=category,                    # ← NUEVO
        )
    # ... resto igual ...
```

### 6.2 Modificar `_determine_answer_scores_fuzzy`

```python
def _determine_answer_scores_fuzzy(
    player_answers: list[tuple[int, Answer]],
    spell_corrector: "SpellCorrector",
    letter: Optional[str] = None,
    category: Optional[str] = None,               # ← NUEVO
) -> dict[int, tuple[bool, int]]:
    from src.services.spell_corrector import SpellCorrector

    all_pids = {pid for pid, _ in player_answers}

    # ── Si es categoría con word list en BD, validar primero ──
    if category and spell_corrector.is_db_category(category):
        valid_answers: list[tuple[int, Answer]] = []
        invalid_pids: set[int] = set()
        for pid, ans in player_answers:
            txt = ans.raw_text.strip()
            if not _is_valid_word(txt, letter=letter):
                invalid_pids.add(pid)
                continue
            is_valid, corrected = spell_corrector.validate_against_list(txt, category)
            if is_valid:
                # Usar la forma corregida para clustering
                # Creamos una copia temporal modificando el raw_text
                # para que cluster_answers use la forma corregida
                from copy import copy
                corrected_ans = copy(ans)
                corrected_ans.raw_text = corrected
                valid_answers.append((pid, corrected_ans))
            else:
                invalid_pids.add(pid)

        if not valid_answers:
            return {pid: (False, 0) for pid in all_pids}

        clusters = spell_corrector.cluster_answers(valid_answers)
        result: dict[int, tuple[bool, int]] = {}

        for cluster in clusters:
            if not cluster:
                continue
            count = len(cluster)
            if count == 1:
                pid = next(iter(cluster))
                result[pid] = (True, UNIQUE_POINTS)
            else:
                share = UNIQUE_POINTS // count
                for pid in cluster:
                    result[pid] = (False, share)

        for pid in all_pids:
            if pid not in result:
                result[pid] = (False, 0)

        return result

    # ── Comportamiento original para categorías sin BD ──
    clusters = spell_corrector.cluster_answers(player_answers)

    result: dict[int, tuple[bool, int]] = {}

    for cluster in clusters:
        if not cluster:
            continue
        count = len(cluster)
        if count == 1:
            pid = next(iter(cluster))
            answer = next(ans for p, ans in player_answers if p == pid)
            txt = answer.raw_text.strip()
            if txt and _is_valid_word(txt, letter=letter):
                result[pid] = (True, UNIQUE_POINTS)
            else:
                result[pid] = (False, 0)
        else:
            share = UNIQUE_POINTS // count
            for pid in cluster:
                result[pid] = (False, share)

    for pid in all_pids:
        if pid not in result:
            answer = next(ans for p, ans in player_answers if p == pid)
            txt = answer.raw_text.strip()
            if txt and _is_valid_word(txt, letter=letter):
                result[pid] = (True, UNIQUE_POINTS)
            else:
                result[pid] = (False, 0)

    return result
```

### 6.3 Modificar `ScoreEngine.evaluate` para pasar `category`

```python
def evaluate(
    self,
    answers_by_player: dict[int, list[Answer]],
    num_categories: int,
    first_completer_id: Optional[int] = None,
    spell_corrector: Optional["SpellCorrector"] = None,
    letter: Optional[str] = None,
) -> tuple[dict[int, int], dict[int, list[dict]]]:
    totals: dict[int, int] = defaultdict(int)
    details: dict[int, list[dict]] = defaultdict(list)

    if not answers_by_player:
        return dict(totals), dict(details)

    categories = _group_by_category(answers_by_player)

    for canonical_cat, player_answers in categories.items():
        answer_scores = _determine_answer_scores(
            player_answers,
            spell_corrector,
            letter=letter,
            category=canonical_cat,       # ← NUEVO: pasar categoría
        )
        # ... resto igual ...
```

---

## 7. Actualizar `bot.py` — Cargar word lists al inicio

Modificar `on_startup()` en `src/bot.py`:

```python
async def on_startup() -> None:
    logger.info("Bot iniciado", version="1.0.0")
    await game_orchestrator.cleanup_stale_games()
    # Cargar word lists de color/fruta/pais desde BD
    from src.services.spell_corrector import get_corrector
    await get_corrector().load_db_word_lists()
    logger.info("Word lists cargadas desde BD")
```

---

## 8. Tests

### 8.1 Tests del repositorio — `tests/test_word_list_repository.py`

```python
"""Tests para WordListRepository."""

import pytest

from src.db.models import WordListItem
from src.db.repositories.word_list_repository import WordListRepository


class TestWordListRepository:
    async def test_bulk_insert_and_get(self, db_session):
        repo = WordListRepository(db_session)
        words = [("rojo", "Rojo"), ("azul", "Azul")]
        count = await repo.bulk_insert("color", words)
        assert count == 2

        retrieved = await repo.get_words_by_category("color")
        assert sorted(retrieved) == ["azul", "rojo"]

    async def test_bulk_insert_skips_duplicates(self, db_session):
        repo = WordListRepository(db_session)
        words = [("rojo", "Rojo"), ("rojo", "Rojo")]
        count = await repo.bulk_insert("color", words)
        assert count == 1  # Solo uno se inserta

    async def test_clear_category(self, db_session):
        repo = WordListRepository(db_session)
        await repo.bulk_insert("color", [("rojo", "Rojo")])
        deleted = await repo.clear_category("color")
        assert deleted >= 1
        assert await repo.count_by_category("color") == 0

    async def test_word_exists(self, db_session):
        repo = WordListRepository(db_session)
        await repo.bulk_insert("color", [("rojo", "Rojo")])
        assert await repo.word_exists("rojo", "color") is True
        assert await repo.word_exists("azul", "color") is False

    async def test_count_by_category(self, db_session):
        repo = WordListRepository(db_session)
        await repo.bulk_insert("color", [("rojo", "Rojo"), ("azul", "Azul")])
        assert await repo.count_by_category("color") == 2
```

### 8.2 Tests de validación contra word list — `tests/test_score_engine.py`

Añadir al final:

```python
# ── ScoreEngine con validación contra word list ─────────────────


class TestScoreEngineWordListValidation:
    def test_valid_word_in_db_list_scores(self):
        """Palabra válida en word list de BD debe puntuar normal."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        # Simular carga desde BD
        sc._word_lists["color"] = {"rojo", "azul", "verde"}

        answers = {
            111: [make_answer(1, "Color", "Rojo")],
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 50

    def test_invalid_word_not_in_db_list_scores_zero(self):
        """Palabra NO válida en word list de BD debe dar 0."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["color"] = {"rojo", "azul", "verde"}

        answers = {
            111: [make_answer(1, "Color", "Naguara")],  # No es un color
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 0

    def test_fuzzy_valid_word_against_db_list(self):
        """Palabra con typo que fuzzy matchea contra word list debe ser válida."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["pais"] = {"venezuela", "colombia", "argentina"}

        answers = {
            111: [make_answer(1, "País", "Venezula")],  # typo
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 50  # fuzzy match → válido

    def test_mixed_valid_and_invalid_in_db_category(self):
        """Jugadores válidos e inválidos en misma categoría BD."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["fruta"] = {"manzana", "pera", "uva"}

        answers = {
            111: [make_answer(1, "Fruta", "Manzana")],   # válido
            222: [make_answer(2, "Fruta", "Pera")],       # válido
            333: [make_answer(3, "Fruta", "Tractor")],    # inválido
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 25  # compartido con 222
        assert totals[222] == 25  # compartido con 111
        assert totals[333] == 0   # inválido

    def test_non_db_category_unchanged(self):
        """Categorías sin BD (ej: nombre) deben seguir comportamiento original."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)

        answers = {
            111: [make_answer(1, "Nombre", "Naguara")],  # no está en word list pero no es BD
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 50  # comportamiento original: se permite
```

### 8.3 Tests de `validate_against_list` — `tests/test_spell_corrector.py`

Añadir al final:

```python
# ── validate_against_list (Phase 4B) ────────────────────────────


class TestValidateAgainstList:
    def test_exact_match(self):
        sc = SpellCorrector()
        sc._word_lists["color"] = {"rojo", "azul"}
        valid, corrected = sc.validate_against_list("rojo", "color")
        assert valid is True
        assert corrected == "rojo"

    def test_fuzzy_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["color"] = {"rojo", "azul"}
        valid, corrected = sc.validate_against_list("roho", "color")
        assert valid is True
        assert corrected == "rojo"

    def test_no_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["color"] = {"rojo", "azul"}
        valid, corrected = sc.validate_against_list("xyzzy", "color")
        assert valid is False
        assert corrected == "xyzzy"

    def test_empty_word_list(self):
        sc = SpellCorrector()
        sc._word_lists["color"] = set()
        valid, corrected = sc.validate_against_list("rojo", "color")
        assert valid is False

    def test_learns_from_fuzzy_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["color"] = {"rojo", "azul"}
        sc.validate_against_list("roho", "color")
        assert "roho" in sc._word_lists["color"]  # aprendido
```

---

## 9. Orden de implementación

1. **Modelo** — Añadir `WordListItem` a `src/db/models.py`
2. **Migración** — `alembic revision --autogenerate -m "add_word_list_items"` y `alembic upgrade head`
3. **Repositorio** — Crear `src/db/repositories/word_list_repository.py`, actualizar `__init__.py`
4. **Datos semilla** — Crear `scripts/word_list_data.py` con COLORS, FRUITS, COUNTRIES
5. **Script seed** — Crear `scripts/seed_word_lists.py` y ejecutar
6. **SpellCorrector** — Quitar color/fruta/pais de SEED_WORDS, añadir `load_db_word_lists()`, `validate_against_list()`, `is_db_category()`
7. **ScoreEngine** — Pasar `category` a `_determine_answer_scores` y `_determine_answer_scores_fuzzy`, añadir validación contra word list
8. **bot.py** — Llamar `load_db_word_lists()` en `on_startup`
9. **Tests** — Crear tests para repositorio, validate_against_list y score engine con validación
10. **Ejecutar tests** — Verificar que todos pasan

---

## 10. Comandos de verificación

```powershell
# 1. Migración
cd backend
alembic upgrade head

# 2. Seed
python -m scripts.seed_word_lists

# 3. Tests
pytest -v

# 4. Tests específicos
pytest -v tests/test_word_list_repository.py
pytest -v tests/test_spell_corrector.py -k "validate_against_list"
pytest -v tests/test_score_engine.py -k "word_list_validation"

# 5. Verificar datos en BD
python -c "
import asyncio
from src.db.engine import async_session_factory
from src.db.repositories.word_list_repository import WordListRepository
async def check():
    async with async_session_factory() as session:
        repo = WordListRepository(session)
        for cat in ['color', 'fruta', 'pais']:
            count = await repo.count_by_category(cat)
            print(f'{cat}: {count} palabras')
            words = await repo.get_words_by_category(cat)
            print(f'  Ejemplos: {words[:5]}')
asyncio.run(check())
"

# 6. Verificar carga en SpellCorrector
python -c "
import asyncio
from src.services.spell_corrector import get_corrector, SpellCorrector

async def check():
    sc = get_corrector()
    print('Antes de load_db_word_lists:')
    for cat in ['color', 'fruta', 'pais']:
        print(f'  {cat}: {len(sc._word_lists.get(cat, set()))} palabras')
    await sc.load_db_word_lists()
    print('Después de load_db_word_lists:')
    for cat in ['color', 'fruta', 'pais']:
        print(f'  {cat}: {len(sc._word_lists.get(cat, set()))} palabras')

asyncio.run(check())
"

# 7. Iniciar bot y probar en grupo
python -m src.bot
```

---

## 11. Notas importantes

### 11.1 Rendimiento

- Las word lists se cargan **una vez al iniciar el bot** (en `on_startup`).
- Durante el juego, la validación es puramente en memoria (dict lookup + fuzzy match).
- 0 queries a BD durante el scoring.

### 11.2 Fallback si BD no disponible

Si `load_db_word_lists()` falla o no se llama, las categorías `color`, `fruta` y `pais` tienen `set()` vacío en `_word_lists`. En ese caso:
- `validate_against_list()` devolverá `(False, norm)` para cualquier palabra.
- Todas las respuestas en esas categorías darán 0 puntos.
- Las otras 5 categorías funcionan normal (datos de `SEED_WORDS`).

Para evitar esto, el bot **debe** llamar `load_db_word_lists()` en startup. Si falla, loguear un error crítico.

### 11.3 Actualizar las listas

Para agregar/quitar palabras:
1. Editar `scripts/word_list_data.py`
2. Ejecutar `python -m scripts.seed_word_lists` (es idempotente, reemplaza todo)
3. Opcional: reiniciar el bot para que `SpellCorrector` recoja los cambios
   - O alternativamente: llamar `get_corrector().load_db_word_lists()` en caliente

### 11.4 Expansión futura a otras categorías

Si en el futuro se quiere migrar `nombre`, `apellido`, etc. a BD:
1. Añadir datos a `scripts/word_list_data.py`
2. Agregar la categoría a `SpellCorrector.DB_CATEGORIES`
3. Re-ejecutar seed
4. Listo — la validación ya funciona genérica para cualquier categoría en `DB_CATEGORIES`

### 11.5 Diferencia entre `validate_against_list` y `correct`

| Método | Sync/Async | Usa IA | Se usa en scoring | Propósito |
|--------|-----------|--------|-------------------|-----------|
| `correct()` | Async | Sí | No | Corrección general con IA |
| `validate_against_list()` | Sync | No | Sí | Validación rápida en scoring |
| `validate()` | Async | Sí | No | Validación completa con IA |

`validate_against_list()` es la única que se usa en el scoring (porque es sync). Las otras son para uso externo (comandos, AI, etc.).

---

## 12. Resumen de cambios por archivo

| Archivo | Líneas aprox. | Cambio |
|---------|--------------|--------|
| `src/db/models.py` | +8 | Nuevo modelo `WordListItem` |
| `migrations/versions/0002_*.py` | ~40 | Nueva migración |
| `src/db/repositories/word_list_repository.py` | ~80 | Nuevo repositorio |
| `src/db/repositories/__init__.py` | +2 | Exportar `WordListRepository` |
| `scripts/word_list_data.py` | ~340 | Datos semilla (colores, frutas, países) |
| `scripts/seed_word_lists.py` | ~55 | Script de seed |
| `src/services/spell_corrector.py` | +40 | `load_db_word_lists()`, `validate_against_list()`, `is_db_category()`, quitar 3 categorías de `SEED_WORDS` |
| `src/services/score_engine.py` | +60 | Pasar `category`, validar contra word list en fuzzy |
| `src/bot.py` | +3 | Llamar `load_db_word_lists()` en startup |
| `tests/test_word_list_repository.py` | ~55 | Tests del repositorio |
| `tests/test_spell_corrector.py` | +50 | Tests de `validate_against_list` |
| `tests/test_score_engine.py` | +80 | Tests de validación contra word list |
