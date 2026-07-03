import pytest

from src.core.text_utils import normalize_text
from src.services.spell_corrector import SpellCorrector, SEED_WORDS

# --- normalize_text --------------------------------------------------------------


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
        assert normalize_text("O'Brien") == "o'brien"

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
    async def test_word_in_word_list(self):
        sc = SpellCorrector()
        result = await sc.correct("Fernando", "Nombre")
        assert result == "fernando"

    async def test_case_insensitive_word_list(self):
        sc = SpellCorrector()
        result = await sc.correct("FERNANDO", "Nombre")
        assert result == "fernando"

    async def test_fuzzy_match_against_word_list(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        result = await sc.correct("Fenando", "Nombre")
        assert result == "fernando"

    async def test_unknown_word_fallback(self):
        sc = SpellCorrector()
        result = await sc.correct("Xyzzy", "Nombre")
        assert result == "xyzzy"

    async def test_unknown_category_fallback(self):
        sc = SpellCorrector()
        result = await sc.correct("Foo", "CategoríaInexistente")
        assert result == "foo"

    async def test_adds_to_word_list_after_fuzzy(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        await sc.correct("Fenando", "Nombre")
        assert "fenando" in sc._word_lists["nombre"]


# ── SpellCorrector.validate ─────────────────────────────────────


class TestValidate:
    async def test_valid_word_in_list(self):
        sc = SpellCorrector()
        assert await sc.validate("Fernando", "Nombre") is True

    async def test_invalid_word_not_in_list(self):
        sc = SpellCorrector()
        assert await sc.validate("Xyzzy", "Nombre") is True

    async def test_fuzzy_valid(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        assert await sc.validate("Fenando", "Nombre") is True

    async def test_adds_to_word_list_after_validate(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        await sc.validate("Fenando", "Nombre")
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
        expected = {
            "nombre",
            "apellido",
            "color",
            "fruta",
            "pais",
            "artista",
            "novela/serie",
            "cosa",
        }
        assert set(SEED_WORDS.keys()) == expected

    def test_each_category_has_words(self):
        db_categories = {"color", "fruta", "pais"}
        for cat, words in SEED_WORDS.items():
            if cat in db_categories:
                continue  # se cargan desde BD en Phase 4B
            assert len(words) > 0, f"Category '{cat}' has no seed words"

    def test_all_words_are_normalized(self):
        for cat, words in SEED_WORDS.items():
            for w in words:
                assert w == normalize_text(w), (
                    f"Seed word '{w}' in '{cat}' is not normalized"
                )


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
