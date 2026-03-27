from __future__ import annotations

from typing import List, Tuple

from search.search_models import EvidenceBundle, SearchResponse


class SearchSelfCheck:
    def validate(self, bundle: EvidenceBundle) -> Tuple[Tuple[str, ...], str]:
        notes: List[str] = []
        disclaimer = ""
        if not bundle.items:
            notes.append("Нет подтверждающих источников.")
            disclaimer = "Надёжных внешних источников не найдено."
        elif len(bundle.items) < 2:
            notes.append("Подтверждение ограничено одним источником.")
            disclaimer = "Ответ опирается на ограниченное число источников."
        weak_sources = [item for item in bundle.items if item.reliability_score < 0.45]
        if weak_sources:
            notes.append("Часть источников имеет низкий reliability score.")
            if not disclaimer:
                disclaimer = "Некоторые источники слабые, выводы стоит перепроверить."
        return tuple(notes), disclaimer

