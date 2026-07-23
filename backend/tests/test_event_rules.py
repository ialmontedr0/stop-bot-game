"""Tests para EventRules — parseo, defaults, serialización y helpers."""

import json

from src.services.event_rules import EventRules

# ── Defaults ─────────────────────────────────────────────────────────


class TestDefaults:
    def test_default_instance(self):
        rules = EventRules()
        assert rules.time_override is None
        assert rules.forced_letter is None
        assert rules.categories_disabled == []
        assert rules.no_duplicates_bonus == 0
        assert rules.allow_dots_as_empty is True
        assert rules.sudden_death is False
        assert rules.collaborative is False
        assert rules.to_json() is None

    def test_default_categories_match_all_categories(self):
        from src.keyboards.settings import ALL_CATEGORIES

        rules = EventRules()
        assert rules.categories_enabled == list(ALL_CATEGORIES)


# ── from_json ────────────────────────────────────────────────────────


class TestFromJson:
    def test_none_returns_defaults(self):
        rules = EventRules.from_json(None)
        assert rules.time_override is None
        assert rules.to_json() is None

    def test_empty_string_returns_defaults(self):
        rules = EventRules.from_json("")
        assert rules.to_json() is None

    def test_invalid_json_returns_defaults(self):
        rules = EventRules.from_json("not json")
        assert rules.to_json() is None

    def test_invalid_type_returns_defaults(self):
        rules = EventRules.from_json("[]")
        assert rules.to_json() is None

    def test_parses_valid_json(self):
        rules = EventRules.from_json('{"time_override": 30}')
        assert rules.time_override == 30

    def test_parses_multiple_fields(self):
        data = {
            "time_override": 15,
            "speed_bonus": 30,
            "excluded_letters": ["A", "E"],
            "forced_letter": "M",
        }
        rules = EventRules.from_json(json.dumps(data))
        assert rules.time_override == 15
        assert rules.speed_bonus == 30
        assert rules.excluded_letters == ["A", "E"]
        assert rules.forced_letter == "M"

    def test_ignores_unknown_fields(self):
        rules = EventRules.from_json('{"time_override": 30, "foo": "bar"}')
        assert rules.time_override == 30
        assert not hasattr(rules, "foo")

    def test_invalid_type_coerces_to_default(self):
        # time_override debe ser int, no str
        rules = EventRules.from_json('{"time_override": "60"}')
        assert rules.time_override is None  # default

    def test_out_of_range_clamps(self):
        rules = EventRules.from_json('{"time_override": 999}')
        assert rules.time_override == 300  # max

        rules2 = EventRules.from_json('{"time_override": 2}')
        assert rules2.time_override == 5  # min

    def test_forced_letter_uppercased(self):
        rules = EventRules.from_json('{"forced_letter": "m"}')
        assert rules.forced_letter == "M"

    def test_forced_letter_invalid_length(self):
        rules = EventRules.from_json('{"forced_letter": "AB"}')
        assert rules.forced_letter is None

    def test_forced_letter_invalid_char(self):
        rules = EventRules.from_json('{"forced_letter": "1"}')
        assert rules.forced_letter is None

    def test_excluded_letters_uppercased(self):
        rules = EventRules.from_json('{"excluded_letters": ["a", "e"]}')
        assert rules.excluded_letters == ["A", "E"]

    def test_category_multipliers_valid(self):
        data = {"category_multipliers": {"País": 3.0, "Color": 1.5}}
        rules = EventRules.from_json(json.dumps(data))
        assert rules.category_multipliers["País"] == 3.0
        assert rules.category_multipliers["Color"] == 1.5

    def test_category_multipliers_invalid_category_ignored(self):
        data = {"category_multipliers": {"InvalidCat": 2.0, "País": 3.0}}
        rules = EventRules.from_json(json.dumps(data))
        assert "InvalidCat" not in rules.category_multipliers
        assert rules.category_multipliers["País"] == 3.0

    def test_category_multipliers_clamped(self):
        data = {"category_multipliers": {"País": 100.0}}
        rules = EventRules.from_json(json.dumps(data))
        assert rules.category_multipliers["País"] == 10.0  # max

    def test_elimination_rounds(self):
        data = {"elimination_rounds": [3, 5, 7]}
        rules = EventRules.from_json(json.dumps(data))
        assert rules.elimination_rounds == [3, 5, 7]

    def test_max_players_none(self):
        rules = EventRules.from_json('{"max_players": null}')
        assert rules.max_players is None


# ── to_json ──────────────────────────────────────────────────────────


class TestToJson:
    def test_all_default_returns_none(self):
        rules = EventRules()
        assert rules.to_json() is None

    def test_single_field(self):
        rules = EventRules(time_override=30)
        result = json.loads(rules.to_json())
        assert result == {"time_override": 30}

    def test_multiple_fields(self):
        rules = EventRules(time_override=15, speed_bonus=30)
        result = json.loads(rules.to_json())
        assert result["time_override"] == 15
        assert result["speed_bonus"] == 30
        # No debe incluir campos default
        assert "no_duplicates_bonus" not in result

    def test_roundtrip(self):
        data = {
            "time_override": 45,
            "excluded_letters": ["A", "E"],
            "forced_letter": "M",
            "categories_disabled": ["Fruta"],
        }
        json_str = json.dumps(data)
        rules = EventRules.from_json(json_str)
        output = rules.to_json()
        restored = EventRules.from_json(output)
        assert restored.time_override == 45
        assert restored.excluded_letters == ["A", "E"]
        assert restored.forced_letter == "M"
        assert restored.categories_disabled == ["Fruta"]

    def test_ensure_ascii_false(self):
        rules = EventRules(categories_disabled=["Fruta"])
        result = rules.to_json()
        assert "Fruta" in result  # no \uXXXX


# ── get_active_categories ────────────────────────────────────────────


class TestGetActiveCategories:
    def test_all_enabled(self):
        from src.keyboards.settings import ALL_CATEGORIES

        rules = EventRules()
        assert rules.get_active_categories() == list(ALL_CATEGORIES)

    def test_with_disabled(self):
        rules = EventRules(categories_disabled=["Fruta", "Color"])
        cats = rules.get_active_categories()
        assert "Fruta" not in cats
        assert "Color" not in cats
        assert len(cats) == 6

    def test_all_disabled_returns_empty(self):
        from src.keyboards.settings import ALL_CATEGORIES

        rules = EventRules(categories_disabled=list(ALL_CATEGORIES))
        assert rules.get_active_categories() == []


# ── get_category_multiplier ──────────────────────────────────────────


class TestGetCategoryMultiplier:
    def test_default_multiplier(self):
        rules = EventRules()
        assert rules.get_category_multiplier("País") == 1.0

    def test_custom_multiplier(self):
        rules = EventRules(category_multipliers={"País": 3.0})
        assert rules.get_category_multiplier("País") == 3.0

    def test_nonexistent_category(self):
        rules = EventRules(category_multipliers={"País": 3.0})
        assert rules.get_category_multiplier("Color") == 1.0


# ── get_round_time ───────────────────────────────────────────────────


class TestGetRoundTime:
    def test_no_override_uses_default(self):
        rules = EventRules()
        assert rules.get_round_time(60) == 60

    def test_override(self):
        rules = EventRules(time_override=30)
        assert rules.get_round_time(60) == 30

    def test_override_zero(self):
        # time_override=0 debe respetarse (0 no es None)
        rules = EventRules(time_override=5)
        assert rules.get_round_time(60) == 5


# ── get_round_time_for_number ────────────────────────────────────────


class TestGetRoundTimeForNumber:
    def test_no_decreasing(self):
        rules = EventRules(time_override=45)
        assert rules.get_round_time_for_number(1, 60) == 45
        assert rules.get_round_time_for_number(5, 60) == 45

    def test_decreasing(self):
        rules = EventRules(
            time_override=60, time_decreasing=True, time_decreasing_amount=5, time_minimum=15
        )
        assert rules.get_round_time_for_number(1, 60) == 55
        assert rules.get_round_time_for_number(5, 60) == 35

    def test_decreasing_hits_minimum(self):
        rules = EventRules(
            time_override=60, time_decreasing=True, time_decreasing_amount=10, time_minimum=15
        )
        assert rules.get_round_time_for_number(10, 60) == 15  # 60-100=-40 → 15

    def test_decreasing_no_override_uses_default(self):
        rules = EventRules(time_decreasing=True, time_decreasing_amount=5, time_minimum=15)
        result = rules.get_round_time_for_number(1, 60)
        assert result == 55  # 60 - (1*5)

    def test_first_round(self):
        rules = EventRules(
            time_override=60, time_decreasing=True, time_decreasing_amount=7, time_minimum=15
        )
        assert rules.get_round_time_for_number(1, 60) == 53


# ── get_letter_for_round ────────────────────────────────────────────


class TestGetLetterForRound:
    def test_no_letter_rules(self):
        rules = EventRules()
        assert rules.get_letter_for_round(1) is None

    def test_forced_letter(self):
        rules = EventRules(forced_letter="M")
        assert rules.get_letter_for_round(1) == "M"
        assert rules.get_letter_for_round(5) == "M"

    def test_letter_sequence(self):
        rules = EventRules(letter_sequence=["M", "R", "S"])
        assert rules.get_letter_for_round(1) == "M"
        assert rules.get_letter_for_round(2) == "R"
        assert rules.get_letter_for_round(3) == "S"
        assert rules.get_letter_for_round(4) == "M"  # cíclico

    def test_sequence_priority_over_forced(self):
        rules = EventRules(forced_letter="X", letter_sequence=["M", "R"])
        assert rules.get_letter_for_round(1) == "M"  # sequence gana

    def test_empty_sequence(self):
        rules = EventRules(letter_sequence=[])
        assert rules.get_letter_for_round(1) is None


# ── has_rules ────────────────────────────────────────────────────────


class TestHasRules:
    def test_default_no_rules(self):
        assert EventRules().has_rules() is False

    def test_with_override(self):
        assert EventRules(time_override=30).has_rules() is True

    def test_with_disabled_categories(self):
        assert EventRules(categories_disabled=["Fruta"]).has_rules() is True


# ── merge_with ───────────────────────────────────────────────────────


class TestMergeWith:
    def test_other_overrides_self(self):
        base = EventRules(time_override=60)
        override = EventRules(time_override=30)
        merged = base.merge_with(override)
        assert merged.time_override == 30

    def test_other_default_keeps_base(self):
        base = EventRules(time_override=60, speed_bonus=20)
        override = EventRules()  # all defaults
        merged = base.merge_with(override)
        assert merged.time_override == 60
        assert merged.speed_bonus == 20

    def test_partial_override(self):
        base = EventRules(time_override=60, speed_bonus=20)
        override = EventRules(speed_bonus=50)  # solo override speed_bonus
        merged = base.merge_with(override)
        assert merged.time_override == 60  # de base
        assert merged.speed_bonus == 50  # de override
