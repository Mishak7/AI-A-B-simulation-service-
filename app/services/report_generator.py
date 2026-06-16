import json
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models import (
    Experiment,
    ExperimentReport,
    MappedVerdict,
    PresentedOrder,
    SimulationResult,
    VisualQuality,
)
from app.services.prompt_renderer import PromptRenderer

logger = logging.getLogger(__name__)


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
        stable_decisions = self._stable_decisions(results)
        grouped: dict[MappedVerdict, list[str]] = defaultdict(list)
        for result in results:
            stable_decision = stable_decisions.get(result.persona_id)
            if stable_decision is not None:
                grouped[stable_decision].append(self._normalize_rationale(result))

        top_control = self._top_reasons(grouped[MappedVerdict.control])
        top_challenger = self._top_reasons(grouped[MappedVerdict.challenger])
        top_none = self._top_reasons(grouped[MappedVerdict.none])
        visual_stats = self._visual_stats(results)
        logger.info(
            "Report generation started experiment_id=%s results=%s stable=%s unstable=%s winner=%s",
            experiment.id,
            len(results),
            aggregation["stable_personas"],
            aggregation["unstable_personas"],
            aggregation["winner"],
        )

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
            "image_1_votes": aggregation["image_1_votes"],
            "image_2_votes": aggregation["image_2_votes"],
            "position_switch_rate": aggregation["position_switch_rate"],
            "positional_bias_score": aggregation["positional_bias_score"],
            "stable_personas": aggregation["stable_personas"],
            "unstable_personas": aggregation["unstable_personas"],
            "unstable_rate": aggregation["unstable_rate"],
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
        final_sections = await self._final_sections(
            summary=summary,
            top_control=top_control,
            top_challenger=top_challenger,
            top_none=top_none,
            visual_stats=visual_stats,
            aggregation=aggregation,
            experiment=experiment,
        )

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
            image_1_votes=aggregation["image_1_votes"],
            image_2_votes=aggregation["image_2_votes"],
            position_switch_rate=aggregation["position_switch_rate"],
            positional_bias_score=aggregation["positional_bias_score"],
            stable_personas=aggregation["stable_personas"],
            unstable_personas=aggregation["unstable_personas"],
            unstable_rate=aggregation["unstable_rate"],
            top_control_reasons=json.dumps(top_control),
            top_challenger_reasons=json.dumps(top_challenger),
            top_none_reasons=json.dumps(top_none),
            recommendations=json.dumps(summary.get("recommendations", [])),
            limitations=summary.get(
                "limitations", "Синтетическая оценка не заменяет реальный A/B-тест."
            ),
            text_findings=json.dumps(final_sections["text_findings"]),
            visual_findings=json.dumps(final_sections["visual_findings"]),
            combined_conclusion=final_sections["combined_conclusion"],
        )
        report = await session.merge(report)
        await session.flush()
        logger.info(
            "Report generation finished experiment_id=%s recommendations=%s limitations_chars=%s",
            experiment.id,
            len(summary.get("recommendations", [])),
            len(report.limitations or ""),
        )
        return report

    async def _final_sections(
        self,
        summary: dict[str, Any],
        top_control: list[str],
        top_challenger: list[str],
        top_none: list[str],
        visual_stats: dict[str, float],
        aggregation: dict[str, Any],
        experiment: Experiment,
    ) -> dict[str, Any]:
        recommendations = summary.get("recommendations", [])
        limitations = summary.get(
            "limitations", "Синтетическая оценка не заменяет реальный A/B-тест."
        )
        combined_report = {
            "experiment": {
                "name": experiment.name,
                "conversion_goal": experiment.conversion_goal,
                "target_audience": experiment.target_audience,
            },
            "winner": aggregation["winner"],
            "confidence_score": aggregation["confidence_score"],
            "votes": {
                "control": aggregation["control_votes"],
                "challenger": aggregation["challenger_votes"],
                "none": aggregation["none_votes"],
            },
            "stable_personas": aggregation["stable_personas"],
            "unstable_personas": aggregation["unstable_personas"],
            "unstable_rate": aggregation["unstable_rate"],
            "top_reasons": {
                "control": top_control,
                "challenger": top_challenger,
                "none": top_none,
            },
            "visual_stats": visual_stats,
            "recommendations": recommendations,
            "limitations": limitations,
        }
        context = {
            "combined_report": json.dumps(
                combined_report, ensure_ascii=False, indent=2
            ),
        }
        prompt = self.prompt_renderer.render("final_report_sections.md", context)
        try:
            payload = await self.llm_client.summarize_report(prompt, context)
        except Exception:
            logger.exception(
                "Final report section generation failed experiment_id=%s", experiment.id
            )
            payload = {}

        return {
            "text_findings": self._short_list(payload.get("text_findings")),
            "visual_findings": self._short_list(payload.get("visual_findings")),
            "combined_conclusion": self._combined_conclusion(
                payload, recommendations, limitations
            ),
        }

    @staticmethod
    def _short_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        findings: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in findings:
                findings.append(text)
            if len(findings) == 3:
                break
        return findings

    @staticmethod
    def _combined_conclusion(
        payload: dict[str, Any],
        recommendations: list[str],
        limitations: str,
    ) -> str:
        conclusion = str(payload.get("combined_conclusion") or "").strip()
        if conclusion:
            return conclusion
        recommendation_text = " ".join(
            str(item).strip() for item in recommendations if str(item).strip()
        )
        return recommendation_text or limitations

    @staticmethod
    def _stable_decisions(
        results: list[SimulationResult],
    ) -> dict[int, MappedVerdict | None]:
        by_persona: dict[int, dict[PresentedOrder, MappedVerdict]] = defaultdict(dict)
        for result in results:
            by_persona[result.persona_id][
                result.presented_order
            ] = result.mapped_verdict

        decisions: dict[int, MappedVerdict | None] = {}
        for persona_id, orders in by_persona.items():
            if (
                PresentedOrder.control_first not in orders
                or PresentedOrder.challenger_first not in orders
            ):
                decisions[persona_id] = None
                continue
            control_first = orders[PresentedOrder.control_first]
            challenger_first = orders[PresentedOrder.challenger_first]
            decisions[persona_id] = (
                control_first if control_first == challenger_first else None
            )
        return decisions

    @staticmethod
    def _normalize_rationale(result: SimulationResult) -> str:
        if result.presented_order == PresentedOrder.control_first:
            image_1_variant = {
                "nom": "базовый вариант",
                "gen": "базового варианта",
                "loc": "базовом варианте",
            }
            image_2_variant = {
                "nom": "тестовый вариант",
                "gen": "тестового варианта",
                "loc": "тестовом варианте",
            }
        else:
            image_1_variant = {
                "nom": "тестовый вариант",
                "gen": "тестового варианта",
                "loc": "тестовом варианте",
            }
            image_2_variant = {
                "nom": "базовый вариант",
                "gen": "базового варианта",
                "loc": "базовом варианте",
            }

        replacements = {
            "Image 1": image_1_variant["nom"],
            "image 1": image_1_variant["nom"],
            "Image 2": image_2_variant["nom"],
            "image 2": image_2_variant["nom"],
            "Изображение 1": image_1_variant["nom"],
            "изображение 1": image_1_variant["nom"],
            "Изображение 2": image_2_variant["nom"],
            "изображение 2": image_2_variant["nom"],
            "Первый экран": image_1_variant["nom"],
            "первый экран": image_1_variant["nom"],
            "первом экране": image_1_variant["loc"],
            "Первом экране": image_1_variant["loc"],
            "первого экрана": image_1_variant["gen"],
            "Первого экрана": image_1_variant["gen"],
            "Второй экран": image_2_variant["nom"],
            "второй экран": image_2_variant["nom"],
            "втором экране": image_2_variant["loc"],
            "Втором экране": image_2_variant["loc"],
            "второго экрана": image_2_variant["gen"],
            "Второго экрана": image_2_variant["gen"],
        }
        normalized = result.rationale
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        return normalized

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

        image_1_fails = sum(
            result.visual_quality_image_1 == VisualQuality.fail for result in results
        )
        image_2_fails = sum(
            result.visual_quality_image_2 == VisualQuality.fail for result in results
        )
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
