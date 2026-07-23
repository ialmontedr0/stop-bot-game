import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from src.db.models import Answer

if TYPE_CHECKING:
    from src.services.spell_corrector import SpellCorrector

import structlog
logger = structlog.get_logger(__name__)

UNIQUE_POINTS = 50
FIRST_COMPLETER_BONUS = 10


@dataclass
class _AnswerOverride:
    raw_text: str
    word_slot: str
    player_id: int
    is_correct: bool
    score: int
    id: int


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def _is_valid_word(text: str, letter: str | None = None) -> bool:
    if not text or not text.strip():
        return False
    stripped = text.strip()

    if len(stripped) < 2:
        return False

    if not re.match(r"^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ\s\-']+$", stripped):
        return False
    if letter:
        norm = _normalize(stripped)
        if not norm or not norm.startswith(letter.lower()):
            return False
    return True


def _group_by_category(
    answers_by_player: dict[int, list[Answer]],
) -> dict[str, list[tuple[int, Answer]]]:
    categories: dict[str, list[tuple[int, Answer]]] = {}
    for pid, answers in answers_by_player.items():
        for answer in answers:
            slot = answer.word_slot
            if slot not in categories:
                categories[slot] = []
            categories[slot].append((pid, answer))
    return categories


def _determine_answer_scores(
    player_answers: list[tuple[int, Answer]],
    spell_corrector: Optional["SpellCorrector"] = None,
    letter: str | None = None,
    category: str | None = None,
) -> dict[int, tuple[bool, int]]:
    if spell_corrector is not None:
        return _determine_answer_scores_fuzzy(
            player_answers, spell_corrector, letter=letter, category=category
        )

    # --- Original exact-matching logic (sin cambios) ---
    norm_map: dict[str, list[int]] = {}

    for pid, answer in player_answers:
        txt = answer.raw_text.strip()
        if not txt or not _is_valid_word(txt, letter=letter):
            continue
        norm = _normalize(txt)
        if norm:
            norm_map.setdefault(norm, []).append(pid)

    result: dict[int, tuple[bool, int]] = {}
    unique_players: set[int] = set()
    shared_groups: dict[int, int] = {}

    for norm, pids in norm_map.items():
        if len(pids) == 1:
            unique_players.add(pids[0])
        else:
            share = UNIQUE_POINTS // len(pids)
            for p in pids:
                shared_groups[p] = share

    all_pids = {pid for pid, _ in player_answers}
    for pid in all_pids:
        if pid in unique_players and pid not in shared_groups:
            result[pid] = (True, UNIQUE_POINTS)
        elif pid in shared_groups:
            result[pid] = (False, shared_groups[pid])
        else:
            result[pid] = (False, 0)

    return result


def _determine_answer_scores_fuzzy(
    player_answers: list[tuple[int, Answer]],
    spell_corrector: "SpellCorrector",
    letter: str | None = None,
    category: str | None = None,
) -> dict[int, tuple[bool, int]]:
    all_pids = {pid for pid, _ in player_answers}

    # ── Si es categoría con word list en BD, validar primero ──
    if category and spell_corrector.is_db_category(category):
        valid_answers: list[tuple[int, Answer]] = []
        for pid, ans in player_answers:
            txt = ans.raw_text.strip()
            if not _is_valid_word(txt, letter=letter):
                continue
            is_valid, corrected = spell_corrector.validate_against_list(txt, category)
            if is_valid:
                corrected_ans = _AnswerOverride(
                    raw_text=corrected,
                    word_slot=ans.word_slot,
                    player_id=ans.player_id,
                    is_correct=ans.is_correct,
                    score=ans.score,
                    id=ans.id,
                )
                valid_answers.append((pid, corrected_ans))

        if not valid_answers:
            return dict.fromkeys(all_pids, (False, 0))

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
            answer = next((ans for p, ans in player_answers if p == pid), None)
            txt = answer.raw_text.strip() if answer else ""
            if txt and _is_valid_word(txt, letter=letter):
                result[pid] = (True, UNIQUE_POINTS)
            else:
                result[pid] = (False, 0)
        else:
            # Verificar que al menos una respuesta en el cluster sea valida
            any_valid = False
            for pid in cluster:
                answer = next((ans for p, ans in player_answers if p == pid), None)
                txt = answer.raw_text.strip() if answer else ""
                if txt and _is_valid_word(txt, letter=letter):
                    any_valid = True
                    break
            if not any_valid:
                for pid in cluster:
                    result[pid] = (False, 0)
                continue
            share = UNIQUE_POINTS // count
            for pid in cluster:
                result[pid] = (False, share)

    for pid in all_pids:
        if pid not in result:
            answer = next((ans for p, ans in player_answers if p == pid), None)
            txt = answer.raw_text.strip() if answer else ""
            if txt and _is_valid_word(txt, letter=letter):
                result[pid] = (True, UNIQUE_POINTS)
            else:
                result[pid] = (False, 0)

    return result


class ScoreEngine:
    def evaluate(
        self,
        answers_by_player: dict[int, list[Answer]],
        num_categories: int,
        first_completer_id: int | None = None,
        spell_corrector: Optional["SpellCorrector"] = None,
        letter: str | None = None,
        game_id: int = 0,
        event_rules: dict | None = None,
        standings_before: dict[int, int] | None = None,
    ) -> tuple[dict[int, int], dict[int, list[dict]]]:
        totals: dict[int, int] = defaultdict(int)
        details: dict[int, list[dict]] = defaultdict(list)

        if not answers_by_player:
            return dict(totals), dict(details)

        categories = _group_by_category(answers_by_player)

        for canonical_cat, player_answers in categories.items():
            answer_scores = _determine_answer_scores(
                player_answers, spell_corrector, letter=letter, category=canonical_cat
            )
            answers_by_pid = dict(player_answers)
            for pid, (_is_unique, cat_score) in answer_scores.items():
                totals[pid] += cat_score
                ans = answers_by_pid.get(pid)
                if ans is not None:
                    detail_entry = {
                        "answer_id": ans.id,
                        "word_slot": canonical_cat,
                        "raw_text": ans.raw_text,
                        "is_correct": cat_score > 0,
                        "score": cat_score,
                    }
                    # Validation source tracking
                    if spell_corrector is not None and hasattr(
                        spell_corrector, "get_validation_source"
                    ):
                        norm = spell_corrector.normalize(ans.raw_text)
                        cat_norm = spell_corrector._normalize_category(canonical_cat)
                        source = spell_corrector.get_validation_source(game_id, f"{cat_norm}:{norm}")
                        detail_entry["validation_source"] = source
                    details[pid].append(detail_entry)

        for pid in answers_by_player:
            if pid not in totals:
                totals[pid] = 0
                details[pid] = [
                    {
                        "answer_id": ans.id,
                        "word_slot": ans.word_slot,
                        "raw_text": ans.raw_text,
                        "is_correct": False,
                        "score": 0,
                    }
                    for ans in answers_by_player[pid]
                ]

        if first_completer_id is not None and first_completer_id in totals:
            totals[first_completer_id] += FIRST_COMPLETER_BONUS

        # ── Event rule scoring modifiers ──
        event_bonuses: dict[int, list[str]] = defaultdict(list)
        if event_rules:
            self._apply_event_scoring(
                totals, details, event_rules, num_categories,
                answers_by_player, first_completer_id, standings_before,
                event_bonuses,
            )

        # ── Log estructurado de evaluación ──
        eval_results = []
        for pid, total in sorted(totals.items(), key=lambda x: x[1], reverse=True):
            cat_scores = {}
            for ad in details.get(pid, []):
                slot = ad["word_slot"]
                cat_scores[slot] = {
                    "text": ad["raw_text"],
                    "correct": ad["is_correct"],
                    "score": ad["score"],
                }
            eval_results.append({
                "player_id": pid,
                "total": total,
                "categories": cat_scores,
                "event_bonuses": event_bonuses.get(pid, []),
            })
        logger.info(
            "score_evaluation",
            extra={
                "num_players": len(answers_by_player),
                "num_categories": num_categories,
                "first_completer_id": first_completer_id,
                "results": eval_results,
            },
        )

        return dict(totals), dict(details)

    @staticmethod
    def _apply_event_scoring(
        totals: dict[int, int],
        details: dict[int, list[dict]],
        event_rules: dict,
        num_categories: int,
        answers_by_player: dict[int, list[Answer]],
        first_completer_id: int | None,
        standings_before: dict[int, int] | None,
        event_bonuses: dict[int, list[str]],
    ) -> None:
        cat_multipliers = event_rules.get("category_multipliers", {})
        no_dup_bonus = event_rules.get("no_duplicates_bonus", 0)
        all_filled_bonus = event_rules.get("bonus_all_filled", 0)
        penalty_empty = event_rules.get("penalty_empty", 0)
        shared_penalty = event_rules.get("shared_answer_penalty", 0)
        comeback_bonus = event_rules.get("comeback_bonus", 0)
        perfect_bonus = event_rules.get("perfect_round_bonus", 0)

        all_pids = set(answers_by_player.keys())

        # 1. Category multipliers
        if cat_multipliers:
            for pid in all_pids:
                for ad in details.get(pid, []):
                    cat = ad["word_slot"]
                    mult = cat_multipliers.get(cat, 1.0)
                    if mult != 1.0 and ad["score"] > 0:
                        old_score = ad["score"]
                        new_score = int(old_score * mult)
                        ad["score"] = new_score
                        totals[pid] += (new_score - old_score)
                        event_bonuses[pid].append(f"{cat} x{mult}")

        # 2. No duplicates bonus
        if no_dup_bonus > 0:
            for pid in all_pids:
                for ad in details.get(pid, []):
                    if ad["is_correct"] and ad["score"] >= UNIQUE_POINTS:
                        totals[pid] += no_dup_bonus
                        event_bonuses[pid].append(f"única +{no_dup_bonus}")

        # 3. Shared answer penalty
        if shared_penalty < 0:
            for canonical_cat, player_answers in _group_by_category(answers_by_player).items():
                norm_map: dict[str, list[int]] = {}
                for pid, ans in player_answers:
                    txt = ans.raw_text.strip()
                    if txt:
                        from src.services.score_engine import _normalize as _norm
                        norm = _norm(txt)
                        if norm:
                            norm_map.setdefault(norm, []).append(pid)
                for norm, pids in norm_map.items():
                    if len(pids) > 1:
                        for pid in pids:
                            totals[pid] += shared_penalty
                            event_bonuses[pid].append(f"duplicado {shared_penalty}")

        # 4. Bonus all filled
        if all_filled_bonus > 0:
            for pid in all_pids:
                filled = sum(
                    1 for ad in details.get(pid, []) if ad["is_correct"]
                )
                if filled >= num_categories:
                    totals[pid] += all_filled_bonus
                    event_bonuses[pid].append(f"llenas +{all_filled_bonus}")

        # 5. Penalty empty
        if penalty_empty < 0:
            for pid in all_pids:
                filled = sum(
                    1 for ad in details.get(pid, []) if ad["is_correct"]
                )
                empty_count = num_categories - filled
                if empty_count > 0:
                    penalty_total = penalty_empty * empty_count
                    totals[pid] += penalty_total
                    event_bonuses[pid].append(f"vacías {penalty_total}")

        # 6. Comeback bonus
        if comeback_bonus > 0 and standings_before:
            min_score = min(standings_before.values()) if standings_before else 0
            last_place_pids = [pid for pid, s in standings_before.items() if s == min_score]
            for pid in last_place_pids:
                if pid in totals:
                    totals[pid] += comeback_bonus
                    event_bonuses[pid].append(f"comeback +{comeback_bonus}")

        # 7. Perfect round bonus
        if perfect_bonus > 0 and len(all_pids) > 1:
            all_perfect = True
            for pid in all_pids:
                filled = sum(1 for ad in details.get(pid, []) if ad["is_correct"])
                if filled < num_categories:
                    all_perfect = False
                    break
            if all_perfect:
                for pid in all_pids:
                    totals[pid] += perfect_bonus
                    event_bonuses[pid].append(f"ronda perfecta +{perfect_bonus}")

    @staticmethod
    def apply_bonus(
        player_id: int,
        scores: dict[int, int],
    ) -> int:
        if player_id in scores:
            scores[player_id] += FIRST_COMPLETER_BONUS
            return FIRST_COMPLETER_BONUS
        return 0

    @staticmethod
    def is_answer_valid(raw_text: str, letter: str | None = None) -> bool:
        return _is_valid_word(raw_text, letter=letter)
