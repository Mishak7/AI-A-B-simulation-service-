from app.models import (
    ConfidenceLevel,
    MappedVerdict,
    PresentedOrder,
    RawVerdict,
    SimulationResult,
    VisualQuality,
)
from app.services.aggregator import Aggregator


def make_result(
    persona_id: int,
    presented_order: PresentedOrder,
    raw_verdict: RawVerdict,
    mapped_verdict: MappedVerdict,
) -> SimulationResult:
    return SimulationResult(
        experiment_id=1,
        persona_id=persona_id,
        presented_order=presented_order,
        raw_verdict=raw_verdict,
        mapped_verdict=mapped_verdict,
        confidence=ConfidenceLevel.medium,
        visual_quality_image_1=VisualQuality.pass_,
        visual_quality_image_2=VisualQuality.pass_,
        visual_issues="",
        critical_visual_defect=False,
        rationale="Тестовая причина.",
    )


def test_aggregator_reports_positional_bias_metrics() -> None:
    results = [
        make_result(1, PresentedOrder.control_first, RawVerdict.image_1, MappedVerdict.control),
        make_result(1, PresentedOrder.challenger_first, RawVerdict.image_1, MappedVerdict.challenger),
        make_result(2, PresentedOrder.control_first, RawVerdict.image_2, MappedVerdict.challenger),
        make_result(2, PresentedOrder.challenger_first, RawVerdict.image_2, MappedVerdict.control),
    ]

    aggregation = Aggregator().aggregate(results)

    assert aggregation["image_1_votes"] == 2
    assert aggregation["image_2_votes"] == 2
    assert aggregation["positional_bias_score"] == 0.0
    assert aggregation["position_switch_rate"] == 1.0
    assert aggregation["stable_personas"] == 0
    assert aggregation["unstable_personas"] == 2
    assert aggregation["unstable_rate"] == 1.0


def test_aggregator_counts_only_stable_persona_votes() -> None:
    results = [
        make_result(1, PresentedOrder.control_first, RawVerdict.image_1, MappedVerdict.control),
        make_result(1, PresentedOrder.challenger_first, RawVerdict.image_2, MappedVerdict.control),
        make_result(2, PresentedOrder.control_first, RawVerdict.image_2, MappedVerdict.challenger),
        make_result(2, PresentedOrder.challenger_first, RawVerdict.image_1, MappedVerdict.challenger),
        make_result(3, PresentedOrder.control_first, RawVerdict.image_1, MappedVerdict.control),
        make_result(3, PresentedOrder.challenger_first, RawVerdict.image_1, MappedVerdict.challenger),
    ]

    aggregation = Aggregator().aggregate(results)

    assert aggregation["control_votes"] == 1
    assert aggregation["challenger_votes"] == 1
    assert aggregation["stable_personas"] == 2
    assert aggregation["unstable_personas"] == 1
    assert aggregation["unstable_rate"] == 0.3333
