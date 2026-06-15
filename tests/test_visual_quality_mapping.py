from app.models import MappedVerdict, PresentedOrder, RawVerdict, SimulationResult, VisualQuality
from app.services.report_generator import ReportGenerator


def test_visual_fail_rates_are_mapped_to_variants_not_positions() -> None:
    results = [
        SimulationResult(
            experiment_id=1,
            persona_id=1,
            presented_order=PresentedOrder.control_first,
            raw_verdict=RawVerdict.image_1,
            mapped_verdict=MappedVerdict.control,
            visual_quality_image_1=VisualQuality.pass_,
            visual_quality_image_2=VisualQuality.fail,
            visual_issues="Challenger is broken.",
            critical_visual_defect=True,
            rationale="Image 1 is clean and Image 2 is broken.",
        ),
        SimulationResult(
            experiment_id=1,
            persona_id=2,
            presented_order=PresentedOrder.challenger_first,
            raw_verdict=RawVerdict.image_2,
            mapped_verdict=MappedVerdict.control,
            visual_quality_image_1=VisualQuality.fail,
            visual_quality_image_2=VisualQuality.pass_,
            visual_issues="Challenger is broken.",
            critical_visual_defect=True,
            rationale="Image 2 is clean and Image 1 is broken.",
        ),
    ]

    stats = ReportGenerator._visual_stats(results)

    assert stats["image_1_visual_fail_rate"] == 0.5
    assert stats["image_2_visual_fail_rate"] == 0.5
    assert stats["control_visual_fail_rate"] == 0.0
    assert stats["challenger_visual_fail_rate"] == 1.0


def test_rationale_is_normalized_from_image_labels_to_variant_labels() -> None:
    result = SimulationResult(
        experiment_id=1,
        persona_id=1,
        presented_order=PresentedOrder.challenger_first,
        raw_verdict=RawVerdict.image_2,
        mapped_verdict=MappedVerdict.control,
        visual_quality_image_1=VisualQuality.fail,
        visual_quality_image_2=VisualQuality.pass_,
        visual_issues="Challenger is broken.",
        critical_visual_defect=True,
        rationale="Image 2 is clean and Image 1 is broken.",
    )

    assert (
        ReportGenerator._normalize_rationale(result)
        == "базовый вариант is clean and тестовый вариант is broken."
    )


def test_russian_screen_labels_are_normalized_to_variant_labels() -> None:
    result = SimulationResult(
        experiment_id=1,
        persona_id=1,
        presented_order=PresentedOrder.challenger_first,
        raw_verdict=RawVerdict.image_2,
        mapped_verdict=MappedVerdict.control,
        visual_quality_image_1=VisualQuality.pass_,
        visual_quality_image_2=VisualQuality.pass_,
        visual_issues="",
        critical_visual_defect=False,
        rationale="Второй экран более чистый, а на первом экране слишком много условий.",
    )

    assert (
        ReportGenerator._normalize_rationale(result)
        == "базовый вариант более чистый, а на тестовом варианте слишком много условий."
    )
