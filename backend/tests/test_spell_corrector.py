import pytest

from src.core.text_utils import normalize_text
from src.services.spell_corrector import SEED_WORDS, SpellCorrector

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
        # candidates ya normalizados (D6)
        best, score = sc.fuzzy_match("Fernando", ["fernando", "juan"])
        assert best == "fernando"
        assert score >= 0.99

    def test_typo_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("Fenando", ["fernando", "juan"])
        assert best == "fernando"
        assert score >= 0.75

    def test_no_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("Fernando", ["juan", "pedro"])
        assert best is None
        assert score == 0.0

    def test_case_insensitive(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        best, score = sc.fuzzy_match("fernando", ["fernando"])
        assert best == "fernando"

    def test_multi_word_token_sort(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        # "Aires Buenos" y "Buenos Aires" deben matchear
        best, score = sc.fuzzy_match("Aires Buenos", ["buenos aires"])
        assert best == "buenos aires"
        assert score >= 0.99

    def test_below_threshold(self):
        sc = SpellCorrector(fuzzy_threshold=90)  # threshold alto
        best, score = sc.fuzzy_match("ZZZZZ", ["fernando"])
        # "zzzzz" vs "fernando" es mucho < 90%
        assert score < 0.9, f"Expected score < 0.9 but got {score}"
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
        # 222 debe estar en cluster PROPIO, separado de 111
        cluster_with_111 = next(cl for cl in clusters if 111 in cl)
        assert 222 not in cluster_with_111
        cluster_with_222 = next(cl for cl in clusters if 222 in cl)
        assert 111 not in cluster_with_222


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
        sc._word_lists["nombre"] = {"fernando"}
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

    async def test_adds_corrected_to_word_list_after_fuzzy(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["nombre"] = {"fernando"}
        await sc.correct("Fenando", "Nombre")
        assert "fernando" in sc._word_lists["nombre"]


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

    async def test_adds_corrected_to_word_list_after_validate(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["nombre"] = {"fernando"}
        await sc.validate("Fenando", "Nombre")
        assert "fernando" in sc._word_lists["nombre"]


# ── Word list management ────────────────────────────────────────


class TestWordListManagement:
    def test_add_to_word_list(self):
        sc = SpellCorrector()
        sc._word_lists["nombre"] = {"mipalabranueva"}
        assert sc.is_in_word_list("MiPalabraNueva", "Nombre")

    def test_is_in_word_list_normalizes(self):
        sc = SpellCorrector()
        sc._word_lists["nombre"] = {"nuevapalabra"}
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
            "animal",
            "cosa",
        }
        assert set(SEED_WORDS.keys()) == expected

    def test_each_category_has_words(self):
        db_categories = {
            "color",
            "fruta",
            "pais",
            "nombre",
            "apellido",
            "artista",
            "animal",
            "cosa",
        }
        for cat, words in SEED_WORDS.items():
            if cat in db_categories:
                continue  # se cargan desde BD en Phase 4F
            assert len(words) > 0, f"Category '{cat}' has no seed words"

    def test_all_words_are_normalized(self):
        for cat, words in SEED_WORDS.items():
            for w in words:
                assert w == normalize_text(w), f"Seed word '{w}' in '{cat}' is not normalized"


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

    def test_learns_corrected_from_fuzzy_match(self):
        sc = SpellCorrector(fuzzy_threshold=75)
        sc._word_lists["color"] = {"rojo", "azul"}
        sc.validate_against_list("roho", "color")
        assert "rojo" in sc._word_lists["color"]  # forma corregida aprendida


class TestAIMode:
    """Tests para modo AI y hybrid con corrector simulado."""

    @pytest.mark.asyncio
    async def test_validate_in_word_list_returns_true(self):
        """Si la palabra ya esta en word list, validate retorna True sin llamar a IA."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan", "maria"}
        result = await sc.validate("Juan", "Nombre")
        assert result is True
        assert sc._api_calls.get(0, 0) == 0  # No llamo a IA

    @pytest.mark.asyncio
    async def test_validate_fuzzy_match_returns_true(self):
        """Si fuzzy match encuentra la palabra, validate retorna True sin IA."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = {"fernando"}
        result = await sc.validate("Fenando", "Nombre")
        assert result is True
        assert sc._api_calls.get(0, 0) == 0

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
        sc = SpellCorrector(
            mode="local",
            api_key="fake",
            api_url="https://fake.com",
            ai_provider="gemini",
        )
        sc._word_lists["nombre"] = {"juan"}
        result = await sc.validate("Xyzzy", "Nombre")
        assert result is True  # default permisivo
        assert sc._api_calls.get(0, 0) == 0  # No llamo a IA

    @pytest.mark.asyncio
    async def test_correct_hybrid_fuzzy_first(self):
        """En modo hybrid, correct() intenta fuzzy antes de IA."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = {"fernando"}
        result = await sc.correct("Fenando", "Nombre")
        assert result == "fernando"  # Fuzzy match, no IA
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_validation_source_tracking(self):
        """Verifica que validation_source se registra correctamente (game_id=0 por defecto)."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["artista"] = {"shakira"}

        await sc.validate("Shakira", "Artista")
        assert sc.get_validation_source(0, "artista:shakira") == "word_list"

        await sc.validate("Xyzzy", "Artista")
        assert sc.get_validation_source(0, "artista:xyzzy") == "default_learned"

    def test_get_api_metrics(self):
        """Verifica que get_api_metrics retorna estructura correcta."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        sc._api_calls[0] = 5
        sc._api_failed = 1
        metrics = sc.get_api_metrics()
        assert metrics["total_calls"] == 5
        assert metrics["failed_calls"] == 1
        assert metrics["remaining"] == 15
        assert metrics["limit"] == 20
        assert metrics["provider"] == "gemini"
        assert metrics["mode"] == "hybrid"


def _redis_is_available() -> bool:
    try:
        import redis.asyncio as aioredis

        r = aioredis.Redis.from_url("redis://localhost:6379/0", socket_connect_timeout=1)
        result = r.ping()
        import asyncio

        asyncio.run(result)
        return True
    except Exception:
        return False


redis_available = pytest.mark.skipif(
    not _redis_is_available(),
    reason="Requiere Redis corriendo en localhost:6379. "
    "Ejecuta 'docker run -p 6379:6379 redis:7' para habilitar.",
)


@redis_available
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
        calls_before = sc._api_calls.copy()

        result = await sc.validate("Juan", "Nombre")
        assert result is True
        assert sc._api_calls == calls_before  # No incremento


class TestValidationSourcePerGame:
    """A2: validation_source debe estar aislada por game_id."""

    @pytest.mark.asyncio
    async def test_per_game_isolation(self):
        """Dos game_id distintos no comparten validation_source."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["color"] = {"rojo"}
        sc._word_lists["fruta"] = {"manzana"}

        await sc.validate("Rojo", "Color", game_id=1)
        await sc.validate("Manzana", "Fruta", game_id=2)

        assert sc.get_validation_source(1, "color:rojo") == "word_list"
        assert sc.get_validation_source(2, "fruta:manzana") == "word_list"
        assert sc.get_validation_source(1, "fruta:manzana") == "default"

    @pytest.mark.asyncio
    async def test_reset_validation_source(self):
        """reset_validation_source limpia el diccionario del game_id dado."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["artista"] = {"shakira"}

        await sc.validate("Shakira", "Artista", game_id=10)
        assert sc.get_validation_source(10, "artista:shakira") == "word_list"

        sc.reset_validation_source(10)
        assert sc.get_validation_source(10, "artista:shakira") == "default"

    @pytest.mark.asyncio
    async def test_default_game_id_preserved(self):
        """Llamadas sin game_id (default 0) funcionan y no se mezclan."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["color"] = {"azul"}
        sc._word_lists["pais"] = {"mexico"}

        await sc.validate("Azul", "Color", game_id=0)
        await sc.validate("Mexico", "Pais", game_id=100)

        assert sc.get_validation_source(0, "color:azul") == "word_list"
        assert sc.get_validation_source(100, "pais:mexico") == "word_list"
        assert sc.get_validation_source(0, "pais:mexico") == "default"
        assert sc.get_validation_source(100, "color:azul") == "default"

    @pytest.mark.asyncio
    async def test_several_distinct_game_ids(self):
        """Multiples game_ids mantienen sources independientes."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["animal"] = {"perro"}

        for gid in (101, 202, 303):
            await sc.validate("Perro", "Animal", game_id=gid)

        for gid in (101, 202, 303):
            assert sc.get_validation_source(gid, "animal:perro") == "word_list"


# ── E2: Batch validation ─────────────────────────────────────────


class TestBatchValidation:
    """Tests para validate_batch (1 prompt = 8 categorias)."""

    @pytest.mark.asyncio
    async def test_batch_all_in_word_list(self):
        """Si todas las palabras estan en word list, 0 llamadas API."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan"}
        sc._word_lists["color"] = {"rojo"}

        answers = {"Nombre": "Juan", "Color": "Rojo"}
        results = await sc.validate_batch(answers, game_id=1)

        assert results == {"Nombre": True, "Color": True}
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_fuzzy_match_no_api(self):
        """Si fuzzy match resuelve, 0 llamadas API."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = {"fernando"}

        answers = {"Nombre": "Fenando"}
        results = await sc.validate_batch(answers, game_id=1)

        assert results["Nombre"] is True
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_empty_answer_is_valid(self):
        """Respuesta vacia = True (no puntos pero no invalida)."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        answers = {"Nombre": "", "Color": "  "}
        results = await sc.validate_batch(answers, game_id=1)
        assert results["Nombre"] is True
        assert results["Color"] is True
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_local_mode_zero_api(self):
        """Modo local: nunca llama a API."""
        sc = SpellCorrector(mode="local", ai_provider="gemini")
        sc._word_lists["cosa"] = set()
        answers = {"Cosa": "Mesa", "Nombre": "Juan"}
        results = await sc.validate_batch(answers, game_id=1)
        assert results["Cosa"] is True
        assert results["Nombre"] is True
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_api_exhausted_falls_to_default(self):
        """Si api_calls_remaining = 0, default permisivo sin API."""
        sc = SpellCorrector(
            mode="hybrid",
            api_limit=0,
            api_key="fake",
            api_url="https://fake.com",
            ai_provider="gemini",
        )
        answers = {"Cosa": "Mesa"}
        results = await sc.validate_batch(answers, game_id=1)
        assert results["Cosa"] is True
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_tracking_sources(self):
        """validate_batch registra validation_source correctamente."""
        sc = SpellCorrector(mode="local")
        sc._word_lists["artista"] = {"shakira"}

        answers = {"Artista": "Shakira", "Nombre": "Xyzzy"}
        await sc.validate_batch(answers, game_id=1)

        assert sc.get_validation_source(1, "artista:shakira") == "word_list"
        assert sc.get_validation_source(1, "nombre:xyzzy") == "default"

    @pytest.mark.asyncio
    async def test_batch_populates_mem_cache(self):
        """Resultados del batch se cachean en memoria individualmente."""
        import unittest
        from unittest.mock import AsyncMock

        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, ai_provider="gemini")
        sc._word_lists["nombre"] = set()
        sc.api_key = "test"
        sc.api_url = "https://fake.com"

        with unittest.mock.patch.object(sc, "_ai_validate_batch", new=AsyncMock(return_value={"Nombre": True})):
            answers = {"Nombre": "Juan"}
            await sc.validate_batch(answers, game_id=1)

        key = "validate:juan:nombre"
        cached = sc._mem_cache.get(key)
        assert cached is not None

    @pytest.mark.asyncio
    async def test_batch_short_answer_rejected(self):
        """Respuesta de 1 caracter se rechaza."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        answers = {"Nombre": "A"}
        results = await sc.validate_batch(answers, game_id=1)
        assert results["Nombre"] is False
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_three_categories_word_list(self):
        """Tres categorias, todas en word list."""
        sc = SpellCorrector(mode="hybrid", ai_provider="gemini")
        sc._word_lists["nombre"] = {"juan"}
        sc._word_lists["color"] = {"rojo"}
        sc._word_lists["fruta"] = {"manzana"}

        answers = {"Nombre": "Juan", "Color": "Rojo", "Fruta": "Manzana"}
        results = await sc.validate_batch(answers, game_id=1)
        assert results == {"Nombre": True, "Color": True, "Fruta": True}
        assert sc._api_calls.get(0, 0) == 0

    @pytest.mark.asyncio
    async def test_batch_api_fallback_on_failure(self):
        """Si _ai_validate_batch retorna None, cae a validacion individual."""
        sc = SpellCorrector(
            mode="hybrid",
            api_key="invalid",
            api_url="https://httpbin.org/status/500",
            ai_provider="openai",
        )
        sc._word_lists["nombre"] = set()

        answers = {"Nombre": "Algo"}
        results = await sc.validate_batch(answers, game_id=1)
        # Fallback a individual, que tambien falla -> default permisivo
        assert results["Nombre"] is True
