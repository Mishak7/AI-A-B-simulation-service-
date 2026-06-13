from collections import Counter

from app.config import get_settings
from app.models import MappedVerdict, SimulationResult


class AggregationResult(dict):
    pass


class Aggregator:
    def aggregate(self, results: list[SimulationResult]) -> AggregationResult:
        counts = Counter(result.mapped_verdict for result in results)
        control_votes = counts[MappedVerdict.control]
        challenger_votes = counts[MappedVerdict.challenger]
        none_votes = counts[MappedVerdict.none]
        valid_votes = control_votes + challenger_votes

        if valid_votes == 0:
            winner = "inconclusive"
            confidence_score = 0.0
            confidence_label = "low"
        else:
            control_share = control_votes / valid_votes
            challenger_share = challenger_votes / valid_votes
            diff = abs(control_share - challenger_share)
            threshold = get_settings().winner_threshold
            if diff < threshold:
                winner = "inconclusive"
            else:
                winner = "control" if control_votes > challenger_votes else "challenger"
            confidence_score = round(diff, 4)
            if diff >= 0.20 and valid_votes >= 30:
                confidence_label = "high"
            elif diff >= 0.10:
                confidence_label = "medium"
            else:
                confidence_label = "low"

        return AggregationResult(
            control_votes=control_votes,
            challenger_votes=challenger_votes,
            none_votes=none_votes,
            winner=winner,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            valid_votes=valid_votes,
        )
