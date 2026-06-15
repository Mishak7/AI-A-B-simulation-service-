import logging
from collections import Counter, defaultdict

from app.config import get_settings
from app.models import MappedVerdict, PresentedOrder, RawVerdict, SimulationResult

logger = logging.getLogger(__name__)


class AggregationResult(dict):
    pass


class Aggregator:
    def aggregate(self, results: list[SimulationResult]) -> AggregationResult:
        paired_decisions = self._paired_decisions(results)
        counts = Counter(
            decision
            for decision in paired_decisions.values()
            if decision is not None
        )
        raw_counts = Counter(result.raw_verdict for result in results)
        control_votes = counts[MappedVerdict.control]
        challenger_votes = counts[MappedVerdict.challenger]
        none_votes = counts[MappedVerdict.none]
        valid_votes = control_votes + challenger_votes
        total_personas = len(paired_decisions)
        stable_personas = control_votes + challenger_votes + none_votes
        unstable_personas = total_personas - stable_personas
        unstable_rate = round(unstable_personas / total_personas, 4) if total_personas else 0.0
        image_1_votes = raw_counts[RawVerdict.image_1]
        image_2_votes = raw_counts[RawVerdict.image_2]
        valid_raw_votes = image_1_votes + image_2_votes
        positional_bias_score = (
            round(abs(image_1_votes - image_2_votes) / valid_raw_votes, 4)
            if valid_raw_votes
            else 0.0
        )
        position_switch_rate = unstable_rate

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
            if diff >= 0.20 and stable_personas >= 30:
                confidence_label = "high"
            elif diff >= 0.10:
                confidence_label = "medium"
            else:
                confidence_label = "low"

        logger.info(
            "Aggregation result total_personas=%s stable=%s unstable=%s control=%s challenger=%s none=%s "
            "winner=%s confidence_score=%s confidence_label=%s image_1_votes=%s image_2_votes=%s",
            total_personas,
            stable_personas,
            unstable_personas,
            control_votes,
            challenger_votes,
            none_votes,
            winner,
            confidence_score,
            confidence_label,
            image_1_votes,
            image_2_votes,
        )
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
            stable_personas=stable_personas,
            unstable_personas=unstable_personas,
            unstable_rate=unstable_rate,
        )

    @staticmethod
    def _paired_decisions(results: list[SimulationResult]) -> dict[int, MappedVerdict | None]:
        by_persona: dict[int, dict] = defaultdict(dict)
        for result in results:
            by_persona[result.persona_id][result.presented_order] = result.mapped_verdict

        decisions: dict[int, MappedVerdict | None] = {}
        for persona_id, orders in by_persona.items():
            if PresentedOrder.control_first not in orders or PresentedOrder.challenger_first not in orders:
                decisions[persona_id] = None
                continue
            control_first = orders[PresentedOrder.control_first]
            challenger_first = orders[PresentedOrder.challenger_first]
            decisions[persona_id] = control_first if control_first == challenger_first else None
        return decisions
