import logging
import unicodedata
import re
from collections import defaultdict
from typing import Optional

from src.db.models import Answer

logger = logging.getLogger(__name__)

UNIQUE_POINTS = 10
SHARED_POINTS = 5
FIRST_COMPLETER_BONUS = 5


class ScoreEngine:
    def calculate(
        self,
        answers_by_player: dict[int, list[Answer]],
        num_categories: int,
        first_completer_id: Optional[int] = None,
    ) -> dict[int, int]:
        scores: dict[int, int] = defaultdict(int)

        if not answers_by_player:
            return dict(scores)

        categories = self._group_by_category(answers_by_player)

        for canonical_cat, player_answers in categories.items():
            uniqueness = self._determine_uniqueness(player_answers)
            for pid, is_unique in uniqueness.items():
                scores[pid] += UNIQUE_POINTS if is_unique else SHARED_POINTS

        for pid in answers_by_player:
            if pid not in scores:
                scores[pid] = 0

        if first_completer_id is not None and first_completer_id in scores:
            scores[first_completer_id] += FIRST_COMPLETER_BONUS

        return dict(scores)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^a-z0-9]", "", text)
        return text

    @staticmethod
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

    @staticmethod
    def _determine_uniqueness(
        player_answers: list[tuple[int, Answer]],
    ) -> dict[int, bool]:
        norm_map: dict[str, list[int]] = {}
        for pid, answer in player_answers:
            txt = answer.raw_text.strip()
            if not txt:
                continue
            norm = ScoreEngine._normalize(txt)
            if norm:
                norm_map.setdefault(norm, []).append(pid)

        unique_players: set[int] = set()
        shared_players: set[int] = set()
        for norm, pids in norm_map.items():
            if len(pids) == 1:
                unique_players.add(pids[0])
            else:
                shared_players.update(pids)

        result: dict[int, bool] = {}
        all_pids = {pid for pid, _ in player_answers}
        for pid in all_pids:
            if pid in unique_players and pid not in shared_players:
                result[pid] = True
            else:
                result[pid] = False
        return result
