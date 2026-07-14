"""
SIMULACION DE PARTIDA COMPLETA: 2 jugadores, 5 rondas, 8 categorias, 80 respuestas.

Flujo real simulado:
  1. Cada respuesta pasa por SpellCorrector.validate()   ← lo que hace submit_answers()
     - Busca en word_list (exacto)
     - Si no, fuzzy match contra word_list
     - Si no, IA (en modo hybrid)
     - Si no, default permisivo
     - Guarda la fuente en _validation_source
  2. Luego ScoreEngine.evaluate()                        ← lo que hace close_round()
     - Para categorias DB usa validate_against_list()
     - Las word lists ya fueron expandidas por validate()

Casos cubiertos (80 slots):
  Unica (50pts), duplicado exacto (25pts), fuzzy match (25pts),
  vacio (0), puntos suspensivos (0), invalido numeros (0),
  palabra en word_list, palabra NO en word_list,
  acento se normaliza, bonus 1er completador (+10),
  compound name no en word_list, typo corregido por fuzzy,
  respuesta aceptada por IA (hybrid), respuesta cae a default.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import Answer
from src.services.score_engine import FIRST_COMPLETER_BONUS, UNIQUE_POINTS, ScoreEngine
from src.services.spell_corrector import SpellCorrector

# ── IDs ─────────────────────────────────────────────────────────────────────
A_ID, B_ID = 111, 222

# ── Word lists semilla (simula BD precargada) ───────────────────────────────
SEED_LISTS = {
    "nombre": {"raul", "ana", "maria", "sara", "carlos", "alicia", "roberto"},
    "apellido": {
        "rodriguez",
        "ramirez",
        "alvarez",
        "martinez",
        "sanchez",
        "perez",
        "garcia",
        "lopez",
    },
    "color": {"rojo", "azul", "verde", "marron", "negro", "blanco", "amarillo", "rosa", "naranja"},
    "fruta": {"manzana", "pera", "uva", "naranja", "platano", "sandia", "fresa", "aguacate"},
    "pais": {
        "rusia",
        "argentina",
        "mexico",
        "espana",
        "chile",
        "colombia",
        "peru",
        "rumania",
        "suecia",
        "suiza",
    },
    "artista": {"romeo santos", "madonna", "carla morrison", "cerati", "shakira"},
    "animal": {
        "rata",
        "raton",
        "arana",
        "abeja",
        "mariposa",
        "serpiente",
        "caballo",
        "cebra",
        "conejo",
        "aguila",
    },
    "cosa": {"reloj", "avion", "mesa", "mueble", "silla", "cama", "coche", "lapiz", "cuchara"},
}


# ── Helper ──────────────────────────────────────────────────────────────────


def ans(aid: int, slot: str, text: str, pid: int, rid: int = 1) -> Answer:
    return Answer(
        id=aid,
        round_id=rid,
        player_id=pid,
        game_player_id=pid,
        word_slot=slot,
        raw_text=text,
        normalized_text=SpellCorrector.normalize(text) if text else "",
    )


# ── Datos de rondas ─────────────────────────────────────────────────────────
# (round_num, letter, [(slot, text_A, text_B, caso, expected_A, expected_B), ...])

ROUND_DATA: list[tuple[int, str, list[tuple[str, str, str, str, int, int]]]] = [
    (
        1,
        "R",
        [
            ("Nombre", "Raul", "Raul", "duplicado exacto word_list", 25, 25),
            ("Apellido", "Rodriguez", "Ramirez", "unicos c/u en word_list", 50, 50),
            ("Color", "Rojo", "Rojo", "duplicado exacto word_list", 25, 25),
            ("Fruta", "...", "", "ambos vacios", 0, 0),
            ("Pais", "Rusia", "Rusia", "duplicado exacto word_list", 25, 25),
            ("Artista", "Romeo Santos", "Romeo Santos", "duplicado exacto word_list", 25, 25),
            ("Animal", "Rata", "Raton", "unicos c/u en word_list", 50, 50),
            ("Cosa", "Reloj", "12345", "word_list + invalido nums", 50, 0),
        ],
    ),
    (
        2,
        "A",
        [
            ("Nombre", "Ana", "Ana Maria", "word_list + AI accept unique", 50, 50),
            ("Apellido", "Alvarez", "Alvarez", "duplicado exacto word_list", 25, 25),
            ("Color", "Azul", "Azuuul", "word_list + fuzzy -> cluster", 25, 25),
            ("Fruta", "Aguacate", "", "word_list + vacio", 50, 0),
            ("Pais", "Argentina", "Argentina", "duplicado exacto word_list", 25, 25),
            ("Artista", "...", "", "ambos vacios", 0, 0),
            ("Animal", "Arana", "Abeja", "unicos c/u en word_list", 50, 50),
            ("Cosa", "Avion", "", "word_list + vacio", 50, 0),
        ],
    ),
    (
        3,
        "M",
        [
            ("Nombre", "Maria", "Maria", "duplicado exacto word_list", 25, 25),
            ("Apellido", "Martinez", "Martinez", "duplicado exacto word_list", 25, 25),
            ("Color", "Marron", "Marron", "duplicado exacto word_list", 25, 25),
            ("Fruta", "Manzana", "Manzana", "duplicado exacto word_list", 25, 25),
            ("Pais", "Mexico", "Mexico", "duplicado exacto word_list", 25, 25),
            ("Artista", "Madonna", "Madonna", "duplicado exacto word_list", 25, 25),
            ("Animal", "Mariposa", "", "word_list + vacio", 50, 0),
            ("Cosa", "Mesa", "Mueble", "unicos c/u en word_list", 50, 50),
        ],
    ),
    (
        4,
        "S",
        [
            ("Nombre", "Sara", "Sara", "duplicado exacto word_list", 25, 25),
            ("Apellido", "Sanchez", "Sanchez", "duplicado exacto word_list", 25, 25),
            ("Color", "", "Salmon", "AI accept + vacio", 0, 50),
            ("Fruta", "Sandia", "...", "word_list + elipsis", 50, 0),
            ("Pais", "Suiza", "Suiza", "duplicado exacto word_list", 25, 25),
            ("Artista", "", "", "ambos vacios", 0, 0),
            ("Animal", "Serpiente", "", "word_list + vacio", 50, 0),
            ("Cosa", "Silla", "Silla", "duplicado exacto word_list", 25, 25),
        ],
    ),
    (
        5,
        "C",
        [
            ("Nombre", "Carlos", "Carlos", "duplicado exacto word_list", 25, 25),
            ("Apellido", "", "", "ambos vacios", 0, 0),
            ("Color", "Celeste", "", "AI accept + vacio", 50, 0),
            ("Fruta", "...", "", "ambos vacios", 0, 0),
            ("Pais", "Chile", "Colombia", "unicos c/u en word_list", 50, 50),
            ("Artista", "Carla Morrison", "...", "word_list + elipsis", 50, 0),
            ("Animal", "Cebra", "Conejo", "unicos c/u en word_list", 50, 50),
            ("Cosa", "Cuchara", "Coche", "unicos c/u en word_list", 50, 50),
        ],
    ),
]

FIRST_COMPLETERS: dict[int, int | None] = {1: A_ID, 2: A_ID, 3: A_ID, 4: None, 5: None}

# ── Build answers dict ──────────────────────────────────────────────────────


def _build_answers(rid: int, slots: list) -> dict:
    answers_a, answers_b = [], []
    for i, (slot, ta, tb, *_) in enumerate(slots):
        answers_a.append(ans(rid * 100 + i * 2, slot, ta, A_ID, rid))
        answers_b.append(ans(rid * 100 + i * 2 + 1, slot, tb, B_ID, rid))
    return {A_ID: answers_a, B_ID: answers_b}


# ============================================================================
#  TEST PRINCIPAL
# ============================================================================


class TestSimulacionPartidaCompleta:
    """5 rondas, 2 jugadores, 80 respuestas, flujo hybrid real."""

    # ── Config de IA ────────────────────────────────────────────────────────
    # Por defecto: IA mockeada (deterministico).
    # Para IA real (Groq/OpenAI): setear SPELL_API_KEY y SPELL_API_URL en .env
    USE_REAL_AI = bool(os.environ.get("SPELL_API_KEY") and os.environ.get("SPELL_API_URL"))

    @pytest.mark.asyncio
    async def test_partida_completa_hybrid(self, capsys):
        sc = SpellCorrector(
            mode="hybrid",
            fuzzy_threshold=75,
            api_key=os.environ.get("SPELL_API_KEY", "sk-test"),
            api_url=os.environ.get("SPELL_API_URL", "https://api.openai.com/v1"),
            ai_provider=os.environ.get("SPELL_AI_PROVIDER", "openai"),
            ai_model=os.environ.get("SPELL_AI_MODEL", "gpt-4o-mini"),
        )
        sc._word_lists = {k: set(v) for k, v in SEED_LISTS.items()}
        sc.api_limit = 200

        engine = ScoreEngine()
        all_ok = True
        global_a, global_b = 0, 0
        pid_label = {A_ID: "A", B_ID: "B"}

        # ── Mock IA (solo si no hay credenciales reales) ──
        ctx = (
            patch.object(sc, "_ai_validate", AsyncMock(return_value=True)),
            patch.object(sc, "_ai_correct", AsyncMock(side_effect=lambda w: w)),
        )
        if not self.USE_REAL_AI:
            ctx[0].start()
            ctx[1].start()

        try:
            for rid, letter, slots in ROUND_DATA:
                raw_answers = _build_answers(rid, slots)

                # ── PASO 1: Simular submit_answers → validate() ──
                #    Cada respuesta pasa por corrector.validate()
                #    Esto expande _word_lists y guarda _validation_source
                for pid in [A_ID, B_ID]:
                    for answer in raw_answers[pid]:
                        txt = answer.raw_text.strip()
                        if not txt or txt in ("...", "…"):
                            continue
                        await sc.validate(txt, answer.word_slot, mode="hybrid")

                # ── PASO 2: Simular close_round → evaluate() ──
                totals, details = engine.evaluate(
                    raw_answers,
                    num_categories=8,
                    first_completer_id=FIRST_COMPLETERS[rid],
                    spell_corrector=sc,
                    letter=letter,
                )

                # ── Mostrar y verificar ──
                round_ok = self._print_round(
                    rid,
                    letter,
                    slots,
                    totals,
                    details,
                    FIRST_COMPLETERS[rid],
                    pid_label,
                    capsys,
                )
                if not round_ok:
                    all_ok = False
                global_a += totals.get(A_ID, 0)
                global_b += totals.get(B_ID, 0)
        finally:
            if not self.USE_REAL_AI:
                ctx[0].stop()
                ctx[1].stop()

        # ── Resumen global ──
        exp_a = sum(sum(s[4] for s in slots) for _, _, slots in ROUND_DATA)
        exp_b = sum(sum(s[5] for s in slots) for _, _, slots in ROUND_DATA)
        for rid in FIRST_COMPLETERS:
            if FIRST_COMPLETERS[rid] == A_ID:
                exp_a += FIRST_COMPLETER_BONUS
            elif FIRST_COMPLETERS[rid] == B_ID:
                exp_b += FIRST_COMPLETER_BONUS

        print(f"\n{'=' * 72}")
        print(f"  GLOBAL - A: {global_a} pts  |  B: {global_b} pts")
        print(f"  Esperado - A: {exp_a} pts  |  B: {exp_b} pts")
        print(f"  Diferencia - A: {global_a - exp_a}  |  B: {global_b - exp_b}")
        print(f"  Modo IA: {'REAL (Groq/OpenAI)' if self.USE_REAL_AI else 'MOCK (deterministico)'}")
        print(f"{'=' * 72}")

        assert global_a == exp_a, f"Score A: {global_a} != {exp_a}"
        assert global_b == exp_b, f"Score B: {global_b} != {exp_b}"
        assert all_ok, "[FAIL] Una o mas aserciones fallaron"

    # ── Mostrar resultados ──────────────────────────────────────────────

    def _print_round(
        self, rid, letter, slots, totals, details, first_id, pid_label, capsys
    ) -> bool:
        print(f"\n{'-' * 72}")
        bonus_str = pid_label[first_id] if first_id else "-"
        print(
            f"  RONDA {rid} - Letra {letter}  |  "
            f"1er completador: {bonus_str}  |  "
            f"Bonus: +{FIRST_COMPLETER_BONUS if first_id else 0}"
        )
        print(f"{'-' * 72}")
        print(
            f"  {'OK?':4s} {'SLOT':11s} {'J':2s} {'RESPUESTA':18s} "
            f"{'PTS':>4s} {'ESP':>4s} {'FUENTE':12s} {'EXPLICACION'}"
        )
        print(f"  {'-' * 72}")

        all_ok = True
        exp_lookup = {}
        exp_case = {}
        for slot, _, _, caso, ea, eb in slots:
            exp_lookup[(A_ID, slot)] = ea
            exp_lookup[(B_ID, slot)] = eb
            exp_case[(A_ID, slot)] = caso
            exp_case[(B_ID, slot)] = caso

        for pid in [A_ID, B_ID]:
            label = pid_label[pid]
            for entry in details.get(pid, []):
                raw = entry["raw_text"]
                slot = entry["word_slot"]
                got = entry["score"]
                src = entry.get("validation_source", "default")
                esp = exp_lookup.get((pid, slot), 0)
                caso = exp_case.get((pid, slot), "?")
                ok = got == esp
                if not ok:
                    all_ok = False
                display = raw if raw else "(vacio)"
                estado = "OK" if ok else "XX"
                print(
                    f"  {estado:4s} {slot:11s} {label:2s} {display:18s} "
                    f"{got:4d} {esp:4d} {src:12s} {caso}"
                )

        for pid in [A_ID, B_ID]:
            if first_id == pid:
                print(f"       * {pid_label[pid]} bonus +{FIRST_COMPLETER_BONUS}")

        exp_a = sum(s[4] for s in slots)
        exp_b = sum(s[5] for s in slots)
        ba = FIRST_COMPLETER_BONUS if first_id == A_ID else 0
        bb = FIRST_COMPLETER_BONUS if first_id == B_ID else 0
        ga = totals.get(A_ID, 0)
        gb = totals.get(B_ID, 0)
        print(f"  {'-' * 42}")
        print(f"  TOTAL  A: {ga:3d} (esp {exp_a + ba:3d})  B: {gb:3d} (esp {exp_b + bb:3d})")
        return all_ok
