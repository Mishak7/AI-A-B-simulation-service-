import json
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models import Experiment, ExperimentReport, MappedVerdict, PresentedOrder, SimulationResult, VisualQuality
from app.services.prompt_renderer import PromptRenderer


class ReportGenerator:
    def __init__(self, llm_client: LLMClient, prompt_renderer: PromptRenderer) -> None:
        self.llm_client = llm_client
        self.prompt_renderer = prompt_renderer

    async def generate(
        self,
        session: AsyncSession,
        experiment: Experiment,
        results: list[SimulationResult],
        aggregation: dict[str, Any],
    ) -> ExperimentReport:
        grouped: dict[MappedVerdict, list[str]] = defaultdict(list)
        for result in results:
            grouped[result.mapped_verdict].append(self._normalize_rationale(result))

        top_control = self._top_reasons(grouped[MappedVerdict.control])
        top_challenger = self._top_reasons(grouped[MappedVerdict.challenger])
        top_none = self._top_reasons(grouped[MappedVerdict.none])
        visual_stats = self._visual_stats(results)

        context = {
            "control_votes": aggregation["control_votes"],
            "challenger_votes": aggregation["challenger_votes"],
            "none_votes": aggregation["none_votes"],
            "rationales": {
                "control": top_control,
                "challenger": top_challenger,
                "none": top_none,
            },
            "winner": aggregation["winner"],
            "confidence_score": aggregation["confidence_score"],
            "visual_stats": visual_stats,
            "experiment_context": {
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
                "conversion_goal": experiment.conversion_goal,
                "target_audience": experiment.target_audience,
            },
        }
        prompt = self.prompt_renderer.render("report_summary.md", context)
        summary = await self.llm_client.summarize_report(prompt, context)

        report = ExperimentReport(
            experiment_id=experiment.id,
            control_votes=aggregation["control_votes"],
            challenger_votes=aggregation["challenger_votes"],
            none_votes=aggregation["none_votes"],
            winner=aggregation["winner"],
            confidence_score=aggregation["confidence_score"],
            image_1_visual_fail_rate=visual_stats["image_1_visual_fail_rate"],
            image_2_visual_fail_rate=visual_stats["image_2_visual_fail_rate"],
            control_visual_fail_rate=visual_stats["control_visual_fail_rate"],
            challenger_visual_fail_rate=visual_stats["challenger_visual_fail_rate"],
            top_control_reasons=json.dumps(top_control),
            top_challenger_reasons=json.dumps(top_challenger),
            top_none_reasons=json.dumps(top_none),
            recommendations=json.dumps(summary.get("recommendations", [])),
            limitations=summary.get(
                "limitations", "Синтетическая оценка не заменяет реальный A/B-тест."
            ),
        )
        report = await session.merge(report)
        await session.flush()
        return report

    @staticmethod
    def _normalize_rationale(result: SimulationResult) -> str:
        if result.presented_order == PresentedOrder.control_first:
            image_1_variant = "Control"
            image_2_variant = "Challenger"
        else:
            image_1_variant = "Challenger"
            image_2_variant = "Control"

        return (
            result.rationale.replace("Image 1", image_1_variant)
            .replace("image 1", image_1_variant)
            .replace("Image 2", image_2_variant)
            .replace("image 2", image_2_variant)
        )

    @staticmethod
    def _visual_stats(results: list[SimulationResult]) -> dict[str, float]:
        total = len(results)
        if total == 0:
            return {
                "image_1_visual_fail_rate": 0.0,
                "image_2_visual_fail_rate": 0.0,
                "control_visual_fail_rate": 0.0,
                "challenger_visual_fail_rate": 0.0,
            }

        image_1_fails = sum(result.visual_quality_image_1 == VisualQuality.fail for result in results)
        image_2_fails = sum(result.visual_quality_image_2 == VisualQuality.fail for result in results)
        control_fails = 0
        challenger_fails = 0

        for result in results:
            if result.presented_order == PresentedOrder.control_first:
                control_fails += result.visual_quality_image_1 == VisualQuality.fail
                challenger_fails += result.visual_quality_image_2 == VisualQuality.fail
            else:
                challenger_fails += result.visual_quality_image_1 == VisualQuality.fail
                control_fails += result.visual_quality_image_2 == VisualQuality.fail

        return {
            "image_1_visual_fail_rate": round(image_1_fails / total, 4),
            "image_2_visual_fail_rate": round(image_2_fails / total, 4),
            "control_visual_fail_rate": round(control_fails / total, 4),
            "challenger_visual_fail_rate": round(challenger_fails / total, 4),
        }

    @staticmethod
    def _top_reasons(reasons: list[str]) -> list[str]:
        seen: list[str] = []
        for reason in reasons:
            normalized = reason.strip()
            if normalized and normalized not in seen:
                seen.append(normalized)
            if len(seen) == 5:
                break
        return seen
