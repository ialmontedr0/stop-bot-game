from src.db.models import Answer
from src.services.score_engine import (
    FIRST_COMPLETER_BONUS,
    UNIQUE_POINTS,
    ScoreEngine,
    _determine_answer_scores,
    _group_by_category,
    _is_valid_word,
    _normalize,
)


def make_answer(
    answer_id: int,
    word_slot: str,
    raw_text: str,
    player_id: int = 1,
) -> Answer:
    ans = Answer(
        id=answer_id,
        round_id=1,
        player_id=player_id,
        game_player_id=player_id,
        word_slot=word_slot,
        raw_text=raw_text,
    )
    ans.id = answer_id
    return ans


# ── _normalize ───────────────────────────────────────────────────────


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("HOLA") == "hola"

    def test_remove_accents(self):
        assert _normalize("Canción") == "cancion"

    def test_remove_non_alphanumeric(self):
        assert _normalize("¡Hola, mundo!") == "holamundo"

    def test_strip_spaces(self):
        assert _normalize("  Perro  ") == "perro"

    def test_handle_n(self):
        assert _normalize("Muñoz") == "munoz"

    def test_empty_string(self):
        assert _normalize("") == ""


# ── _is_valid_word ───────────────────────────────────────────────────


class TestIsValidWord:
    def test_valid_word(self):
        assert _is_valid_word("Fernando") is True

    def test_valid_with_spaces(self):
        assert _is_valid_word("Buenos Aires") is True

    def test_valid_with_hyphen(self):
        assert _is_valid_word("María-José") is True

    def test_valid_with_accents(self):
        assert _is_valid_word("Canción") is True

    def test_valid_with_n(self):
        assert _is_valid_word("Muñoz") is True

    def test_valid_with_apostrophe(self):
        assert _is_valid_word("O'Brien") is True

    def test_invalid_with_numbers(self):
        assert _is_valid_word("Juan123") is False

    def test_invalid_with_symbols(self):
        assert _is_valid_word("Hola!!!") is False

    def test_invalid_empty(self):
        assert _is_valid_word("") is False

    def test_invalid_whitespace_only(self):
        assert _is_valid_word("   ") is False

    def test_valid_single_char(self):
        assert _is_valid_word("A") is True  # una letra es válida


# ── _group_by_category ──────────────────────────────────────────────


class TestGroupByCategory:
    def test_groups_by_word_slot(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Color", "Rojo", 1)
        a3 = make_answer(3, "Nombre", "María", 2)
        grouped = _group_by_category({111: [a1, a2], 222: [a3]})
        assert "Nombre" in grouped
        assert "Color" in grouped
        assert len(grouped["Nombre"]) == 2
        assert len(grouped["Color"]) == 1


# ── _determine_answer_scores ────────────────────────────────────────


class TestDetermineAnswerScores:
    def test_unique_answer_gets_50(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        result = _determine_answer_scores([(111, a1)])
        assert result[111] == (True, UNIQUE_POINTS)

    def test_shared_answer_splits_50(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "Juan", 2)
        result = _determine_answer_scores([(111, a1), (222, a2)])
        # 50 / 2 = 25
        assert result[111] == (False, 25)
        assert result[222] == (False, 25)

    def test_shared_among_three(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "Juan", 2)
        a3 = make_answer(3, "Nombre", "Juan", 3)
        result = _determine_answer_scores([(111, a1), (222, a2), (333, a3)])
        # 50 / 3 = 16 (truncado a entero)
        assert result[111] == (False, 16)
        assert result[222] == (False, 16)
        assert result[333] == (False, 16)

    def test_empty_answer_gets_0(self):
        a1 = make_answer(1, "Nombre", "", 1)
        result = _determine_answer_scores([(111, a1)])
        assert result[111] == (False, 0)

    def test_invalid_answer_gets_0(self):
        a1 = make_answer(1, "Nombre", "123!!!", 1)
        result = _determine_answer_scores([(111, a1)])
        assert result[111] == (False, 0)

    def test_mixed_unique_and_shared(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "Pedro", 2)
        a3 = make_answer(3, "Nombre", "Pedro", 3)
        result = _determine_answer_scores([(111, a1), (222, a2), (333, a3)])
        assert result[111] == (True, 50)  # único
        assert result[222] == (False, 25)  # compartido con 333
        assert result[333] == (False, 25)  # compartido con 222

    def test_case_insensitive_matching(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "juan", 2)  # mismo normalizado
        result = _determine_answer_scores([(111, a1), (222, a2)])
        assert result[111] == (False, 25)
        assert result[222] == (False, 25)

    def test_accent_insensitive_matching(self):
        a1 = make_answer(1, "Nombre", "Canción", 1)
        a2 = make_answer(2, "Nombre", "cancion", 2)
        result = _determine_answer_scores([(111, a1), (222, a2)])
        assert result[111] == (False, 25)
        assert result[222] == (False, 25)


# ── ScoreEngine.evaluate ────────────────────────────────────────────


class TestScoreEngineEvaluate:
    def test_empty_answers(self):
        engine = ScoreEngine()
        totals, details = engine.evaluate({}, 8)
        assert totals == {}
        assert details == {}

    def test_single_player_all_unique(self):
        engine = ScoreEngine()
        answers = {
            111: [
                make_answer(1, "Nombre", "Juan"),
                make_answer(2, "Color", "Rojo"),
                make_answer(3, "Fruta", "Manzana"),
            ],
        }
        totals, details = engine.evaluate(answers, 3)
        assert totals[111] == UNIQUE_POINTS * 3  # 150
        assert len(details[111]) == 3
        assert all(d["is_correct"] is True for d in details[111])
        assert all(d["score"] == UNIQUE_POINTS for d in details[111])

    def test_two_players_all_shared(self):
        engine = ScoreEngine()
        answers = {
            111: [
                make_answer(1, "Nombre", "Juan"),
                make_answer(2, "Color", "Rojo"),
            ],
            222: [
                make_answer(3, "Nombre", "Juan"),
                make_answer(4, "Color", "Rojo"),
            ],
        }
        totals, details = engine.evaluate(answers, 2)
        # Cada jugador: 25 + 25 = 50
        assert totals[111] == 50
        assert totals[222] == 50

    def test_first_completer_bonus(self):
        engine = ScoreEngine()
        answers = {
            111: [make_answer(1, "Nombre", "Juan")],
            222: [make_answer(2, "Nombre", "Pedro")],
        }
        totals, details = engine.evaluate(answers, 1, first_completer_id=111)
        assert totals[111] == UNIQUE_POINTS + FIRST_COMPLETER_BONUS  # 60
        assert totals[222] == UNIQUE_POINTS  # 50

    def test_bonus_only_if_player_in_scores(self):
        engine = ScoreEngine()
        answers = {
            111: [make_answer(1, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, first_completer_id=999)
        assert totals[111] == UNIQUE_POINTS  # 50, bonus no aplica porque 999 no está

    def test_complex_scenario(self):
        """3 jugadores, 3 categorías, mezcla de único/compartido/vacío."""
        engine = ScoreEngine()
        answers = {
            111: [
                make_answer(1, "Nombre", "Juan"),
                make_answer(2, "Color", "Rojo"),
                make_answer(3, "Fruta", "Manzana"),
            ],
            222: [
                make_answer(4, "Nombre", "María"),
                make_answer(5, "Color", "Rojo"),
                make_answer(6, "Fruta", "Pera"),
            ],
            333: [
                make_answer(7, "Nombre", "Juan"),
                make_answer(8, "Color", ""),
                make_answer(9, "Fruta", "Manzana"),
            ],
        }
        totals, details = engine.evaluate(answers, 3, first_completer_id=111)

        # Nombre: 111 y 333 comparten "Juan" → 25 c/u, 222 único "María" → 50
        # Color: 111 y 222 comparten "Rojo" → 25 c/u, 333 vacío → 0
        # Fruta: 111 y 333 comparten "Manzana" → 25 c/u, 222 único "Pera" → 50
        esperado_111 = 25 + 25 + 25 + FIRST_COMPLETER_BONUS  # 100
        esperado_222 = 50 + 25 + 50  # 125
        esperado_333 = 25 + 0 + 25  # 50

        assert totals[111] == esperado_111
        assert totals[222] == esperado_222
        assert totals[333] == esperado_333

        # Verificar detalles
        assert details[333][1]["is_correct"] is False  # Color vacío
        assert details[333][1]["score"] == 0

    def test_per_answer_details_shape(self):
        engine = ScoreEngine()
        answers = {
            111: [make_answer(42, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1)
        entry = details[111][0]
        assert "answer_id" in entry
        assert "word_slot" in entry
        assert "raw_text" in entry
        assert "is_correct" in entry
        assert "score" in entry
        assert entry["answer_id"] == 42
        assert entry["word_slot"] == "Nombre"
        assert entry["raw_text"] == "Juan"


# ── ScoreEngine.apply_bonus ─────────────────────────────────────────


class TestApplyBonus:
    def test_apply_bonus_adds_points(self):
        scores = {111: 100, 222: 50}
        result = ScoreEngine.apply_bonus(111, scores)
        assert result == FIRST_COMPLETER_BONUS
        assert scores[111] == 100 + FIRST_COMPLETER_BONUS

    def test_apply_bonus_unknown_player(self):
        scores = {111: 100}
        result = ScoreEngine.apply_bonus(999, scores)
        assert result == 0
        assert scores[111] == 100


# ── ScoreEngine.is_answer_valid ─────────────────────────────────────


class TestIsAnswerValid:
    def test_valid(self):
        assert ScoreEngine.is_answer_valid("Buenos Aires") is True

    def test_invalid_with_numbers(self):
        assert ScoreEngine.is_answer_valid("Perro123") is False

    def test_invalid_empty(self):
        assert ScoreEngine.is_answer_valid("") is False


class TestScoreEngineFuzzyMatching:
    def test_fuzzy_clusters_typo(self):
        """'Fernando' y 'Fenando' deben tratarse como duplicados."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["nombre"] = {"fernando", "juan", "pedro"}
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
        sc._word_lists["nombre"] = {"juan", "pedro", "fernando"}
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
        sc._word_lists["nombre"] = {"fernando", "juan"}
        answers = {
            111: [make_answer(1, "Nombre", "Fernando")],
            222: [make_answer(2, "Nombre", "Fenando")],  # fuzzy = Fernando
            333: [make_answer(3, "Nombre", "Juan")],  # único
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
        sc._word_lists["nombre"] = {"fernando", "juan"}
        answers = {
            111: [make_answer(1, "Nombre", "Fernando")],
            222: [make_answer(2, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, first_completer_id=111, spell_corrector=sc)
        assert totals[111] == UNIQUE_POINTS + FIRST_COMPLETER_BONUS  # 60
        assert totals[222] == UNIQUE_POINTS  # 50

    def test_fuzzy_with_empty_answers(self):
        """Respuestas vacías deben puntuar 0 incluso con fuzzy."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["nombre"] = {"juan"}
        answers = {
            111: [make_answer(1, "Nombre", "")],
            222: [make_answer(2, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 0
        assert totals[222] == 50


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
        """Válidos duplicados e inválido en misma categoría BD."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["fruta"] = {"manzana", "pera", "uva"}

        answers = {
            111: [make_answer(1, "Fruta", "Manzana")],  # válido
            222: [make_answer(2, "Fruta", "Manzana")],  # válido, duplicado
            333: [make_answer(3, "Fruta", "Tractor")],  # inválido
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 25  # compartido con 222
        assert totals[222] == 25  # compartido con 111
        assert totals[333] == 0  # inválido

    def test_non_db_category_unchanged(self):
        """Categoría sin word list en BD: se permite cualquier palabra."""
        from src.services.spell_corrector import SpellCorrector

        engine = ScoreEngine()
        sc = SpellCorrector(fuzzy_threshold=75)

        answers = {
            111: [make_answer(1, "Inventada", "CualquierCosa")],
        }
        totals, details = engine.evaluate(answers, 1, spell_corrector=sc)
        assert totals[111] == 50  # comportamiento original: se permite


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
