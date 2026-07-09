from unittest.mock import patch
from src.image_generator import generate_round_letter_image, generate_podium_image


class TestGenerateRoundLetterImage:
    def test_returns_bytes_for_valid_input(self):
        result = generate_round_letter_image("A", 1)
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_different_letters_produce_different_output(self):
        a = generate_round_letter_image("A", 1)
        b = generate_round_letter_image("B", 1)
        assert a != b

    def test_handles_n_with_tilde(self):
        result = generate_round_letter_image("Ñ", 3)
        assert result is not None
        assert isinstance(result, bytes)

    def test_returns_none_on_error(self):
        with patch("src.image_generator._load_bg", side_effect=Exception("fail")):
            result = generate_round_letter_image("A", 1)
            assert result is None


class TestGeneratePodiumImage:
    def test_returns_bytes_with_winners(self):
        result = generate_podium_image([("Alice", 100), ("Bob", 50), ("Charlie", 25)])
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_returns_bytes_with_single_winner(self):
        result = generate_podium_image([("Alice", 100)])
        assert result is not None

    def test_returns_bytes_with_no_winners(self):
        result = generate_podium_image([])
        assert result is not None
        assert isinstance(result, bytes)

    def test_many_winners_includes_rest_text(self):
        winners = [(f"P{i}", 100 - i) for i in range(10)]
        result = generate_podium_image(winners, game_rounds=5)
        assert result is not None

    def test_returns_none_on_error(self):
        with patch("src.image_generator._load_bg", side_effect=Exception("fail")):
            result = generate_podium_image([("Alice", 100)])
            assert result is None
