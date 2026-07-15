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
        invalid_pids: set[int] = set()
        for pid, ans in player_answers:
            txt = ans.raw_text.strip()
            if not _is_valid_word(txt, letter=letter):
                invalid_pids.add(pid)
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
            else:
                invalid_pids.add(pid)

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
                        source = spell_corrector.get_validation_source(f"{cat_norm}:{norm}")
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
            eval_results.append({"player_id": pid, "total": total, "categories": cat_scores})
        logger.info(
            "score_evaluation",
            num_players=len(answers_by_player),
            num_categories=num_categories,
            first_completer_id=first_completer_id,
            results=eval_results,
        )

        return dict(totals), dict(details)

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
