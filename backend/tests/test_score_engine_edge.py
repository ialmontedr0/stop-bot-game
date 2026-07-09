from src.db.models import Answer
from src.services.score_engine import ScoreEngine


def _make_answer(
    player_id: int,
    word_slot: str,
    raw_text: str,
    is_correct: bool | None = None,
    score: int = 0,
    id: int = 0,
) -> Answer:
    return Answer(
        id=id,
        player_id=player_id,
        word_slot=word_slot,
        raw_text=raw_text,
        normalized_text=raw_text.lower() if raw_text else "",
        is_correct=is_correct,
        score=score,
    )


class TestScoreEngineEdgeCases:
    def test_all_answers_empty(self):
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", ""), _make_answer(1, "Color", "")]}
        totals, details = engine.evaluate(answers, 2)
        assert totals[1] == 0

    def test_single_category(self):
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana")]}
        totals, details = engine.evaluate(answers, 1)
        assert totals[1] == 50
        assert details[1][0]["is_correct"] is True

    def test_no_answers_empty_dict(self):
        engine = ScoreEngine()
        totals, details = engine.evaluate({}, 5)
        assert totals == {}
        assert details == {}

    def test_three_players_same_word(self):
        engine = ScoreEngine()
        answers = {
            1: [_make_answer(1, "Nombre", "Carlos")],
            2: [_make_answer(2, "Nombre", "Carlos")],
            3: [_make_answer(3, "Nombre", "Carlos")],
        }
        totals, details = engine.evaluate(answers, 1)
        assert totals[1] > 0
        assert totals[2] > 0
        assert totals[3] > 0
        assert totals[1] == totals[2] == totals[3]

    def test_first_completer_not_in_scores(self):
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana")]}
        totals, details = engine.evaluate(answers, 1, first_completer_id=999)
        assert totals[1] == 50

    def test_bonus_applied_correctly(self):
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana")]}
        totals, _ = engine.evaluate(answers, 1, first_completer_id=1)
        assert totals[1] == 60

    def test_invalid_word_scores_zero(self):
        engine = ScoreEngine()
        answers = {1: [_make_answer(1, "Nombre", "Ana123")]}
        totals, details = engine.evaluate(answers, 1)
        assert totals[1] == 0
        assert details[1][0]["is_correct"] is False

    def test_shared_and_unique_mixed(self):
        engine = ScoreEngine()
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
        assert totals[1] == 25 + 50
        assert totals[2] == 25 + 50

    def test_apply_bonus_static(self):
        scores = {1: 100, 2: 80}
        ScoreEngine.apply_bonus(1, scores)
        assert scores[1] == 110
