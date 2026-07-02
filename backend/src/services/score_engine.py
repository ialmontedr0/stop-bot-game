import logging
import re
import unicodedata
from collections import defaultdict
from typing import Optional

from src.db.models import Answer

logger = logging.getLogger(__name__)

UNIQUE_POINTS = 50
FIRST_COMPLETER_BONUS = 10


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def _is_valid_word(text: str) -> bool:
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) < 1:
        return False
    if not re.match(r"^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ\s\-']+$", stripped):
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
) -> dict[int, tuple[bool, int]]:
    norm_map: dict[str, list[int]] = {}
    answer_map: dict[int, Answer] = {}

    for pid, answer in player_answers:
        answer_map[pid] = answer
        txt = answer.raw_text.strip()
        if not txt or not _is_valid_word(txt):
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


class ScoreEngine:
    def evaluate(
        self,
        answers_by_player: dict[int, list[Answer]],
        num_categories: int,
        first_completer_id: Optional[int] = None,
    ) -> tuple[dict[int, int], dict[int, list[dict]]]:
        totals: dict[int, int] = defaultdict(int)
        details: dict[int, list[dict]] = defaultdict(list)

        if not answers_by_player:
            return dict(totals), dict(details)

        categories = _group_by_category(answers_by_player)

        for canonical_cat, player_answers in categories.items():
            answer_scores = _determine_answer_scores(player_answers)
            for pid, (is_unique, cat_score) in answer_scores.items():
                totals[pid] += cat_score
                for p_id, ans in player_answers:
                    if p_id == pid:
                        details[pid].append({
                            "answer_id": ans.id,
                            "word_slot": canonical_cat,
                            "raw_text": ans.raw_text,
                            "is_correct": cat_score > 0,
                            "score": cat_score,
                        })
                        break

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
    def is_answer_valid(raw_text: str) -> bool:
        return _is_valid_word(raw_text)
