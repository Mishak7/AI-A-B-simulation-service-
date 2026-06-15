from collections import Counter, defaultdict

from app.config import get_settings
from app.models import MappedVerdict, PresentedOrder, RawVerdict, SimulationResult


class AggregationResult(dict):
    pass


class Aggregator:
    def aggregate(self, results: list[SimulationResult]) -> AggregationResult:
        counts = Counter(result.mapped_verdict for result in results)
        raw_counts = Counter(result.raw_verdict for result in results)
        control_votes = counts[MappedVerdict.control]
        challenger_votes = counts[MappedVerdict.challenger]
        none_votes = counts[MappedVerdict.none]
        valid_votes = control_votes + challenger_votes
        image_1_votes = raw_counts[RawVerdict.image_1]
        image_2_votes = raw_counts[RawVerdict.image_2]
        valid_raw_votes = image_1_votes + image_2_votes
        positional_bias_score = (
            round(abs(image_1_votes - image_2_votes) / valid_raw_votes, 4)
            if valid_raw_votes
            else 0.0
        )
        position_switch_rate = self._position_switch_rate(results)

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
            image_1_votes=image_1_votes,
            image_2_votes=image_2_votes,
            position_switch_rate=position_switch_rate,
            positional_bias_score=positional_bias_score,
        )

    @staticmethod
    def _position_switch_rate(results: list[SimulationResult]) -> float:
        by_persona: dict[int, dict] = defaultdict(dict)
        for result in results:
            by_persona[result.persona_id][result.presented_order] = result.mapped_verdict

        paired = [
            orders
            for orders in by_persona.values()
            if PresentedOrder.control_first in orders and PresentedOrder.challenger_first in orders
        ]
        if not paired:
            return 0.0

        switches = sum(
            orders[PresentedOrder.control_first] != orders[PresentedOrder.challenger_first]
            for orders in paired
        )
        return round(switches / len(paired), 4)
