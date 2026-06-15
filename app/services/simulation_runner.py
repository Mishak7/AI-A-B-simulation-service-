import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMClient
from app.models import (
    ConfidenceLevel,
    Experiment,
    MappedVerdict,
    Persona,
    PresentedOrder,
    RawVerdict,
    SimulationResult,
    VisualQuality,
)
from app.services.prompt_renderer import PromptRenderer


class SimulationRunner:
    def __init__(self, llm_client: LLMClient, prompt_renderer: PromptRenderer) -> None:
        self.llm_client = llm_client
        self.prompt_renderer = prompt_renderer

    async def run(
        self,
        session: AsyncSession,
        experiment: Experiment,
        personas: list[Persona],
        concurrency: int,
    ) -> list[SimulationResult]:
        semaphore = asyncio.Semaphore(concurrency)
        control_visual, challenger_visual = await asyncio.gather(
            self._assess_variant_visual_quality(experiment, "Control", experiment.control_image_path or ""),
            self._assess_variant_visual_quality(
                experiment, "Challenger", experiment.challenger_image_path or ""
            ),
        )

        async def simulate(index: int, persona: Persona) -> dict[str, Any]:
            async with semaphore:
                presented_order = (
                    PresentedOrder.control_first if index % 2 == 0 else PresentedOrder.challenger_first
                )
                if presented_order == PresentedOrder.control_first:
                    image_1_label, image_2_label = "Control", "Challenger"
                else:
                    image_1_label, image_2_label = "Challenger", "Control"

                persona_profile = {
                    "name": persona.name,
                    "age_range": persona.age_range,
                    "occupation": persona.occupation,
                    "income_level": persona.income_level,
                    "education": persona.education,
                    "location": persona.location,
                    "interests": persona.interests,
                    "goals": persona.goals,
                    "pain_points": persona.pain_points,
                    "technical_savviness": persona.technical_savviness,
                    "financial_literacy": persona.financial_literacy,
                    "digital_literacy": persona.digital_literacy,
                    "trust_in_online_banking": persona.trust_in_online_banking,
                    "fraud_anxiety": persona.fraud_anxiety,
                    "fee_sensitivity": persona.fee_sensitivity,
                    "privacy_sensitivity": persona.privacy_sensitivity,
                    "banking_channel_preference": persona.banking_channel_preference,
                    "decision_style": persona.decision_style,
                    "region_type": persona.region_type,
                    "income_stability": persona.income_stability,
                    "online_behavior": persona.online_behavior,
                    "browsing_context": persona.browsing_context,
                    "task_context": persona.task_context,
                }
                context = {
                    "persona_profile": persona_profile,
                    "conversion_goal": experiment.conversion_goal,
                    "target_audience": experiment.target_audience,
                    "image_1_label": image_1_label,
                    "image_2_label": image_2_label,
                    "presented_order": presented_order.value,
                    "evaluation_guidelines": "Evaluate which screenshot is more likely to convert.",
                    "control_visual_quality": control_visual.visual_quality,
                    "control_visual_issues": control_visual.visual_issues,
                    "challenger_visual_quality": challenger_visual.visual_quality,
                    "challenger_visual_issues": challenger_visual.visual_issues,
                    "experiment_context": {
                        "experiment_id": experiment.id,
                        "experiment_name": experiment.name,
                    },
                }
                prompt = self.prompt_renderer.render("persona_simulation.md", context)
                verdict = await self.llm_client.simulate_choice(
                    prompt=prompt,
                    control_image_path=experiment.control_image_path or "",
                    challenger_image_path=experiment.challenger_image_path or "",
                    context=context,
                )
                if presented_order == PresentedOrder.control_first:
                    image_1_visual = control_visual
                    image_2_visual = challenger_visual
                else:
                    image_1_visual = challenger_visual
                    image_2_visual = control_visual

                return {
                    "persona_id": persona.id,
                    "presented_order": presented_order,
                    "raw_verdict": RawVerdict(verdict.verdict),
                    "mapped_verdict": self.map_verdict(RawVerdict(verdict.verdict), presented_order),
                    "confidence": ConfidenceLevel(verdict.confidence),
                    "visual_quality_image_1": VisualQuality(image_1_visual.visual_quality),
                    "visual_quality_image_2": VisualQuality(image_2_visual.visual_quality),
                    "visual_issues": self._format_visual_issues(control_visual, challenger_visual),
                    "critical_visual_defect": (
                        image_1_visual.visual_quality == "fail" or image_2_visual.visual_quality == "fail"
                    ),
                    "rationale": verdict.rationale,
                }

        payloads = await asyncio.gather(*(simulate(index, persona) for index, persona in enumerate(personas)))
        results: list[SimulationResult] = []
        for payload in payloads:
            result = SimulationResult(experiment_id=experiment.id, **payload)
            session.add(result)
            results.append(result)
        await session.flush()
        return results

    async def _assess_variant_visual_quality(self, experiment: Experiment, label: str, image_path: str):
        context = {
            "image_label": label,
            "conversion_goal": experiment.conversion_goal,
            "target_audience": experiment.target_audience,
            "experiment_context": {
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
            },
        }
        prompt = self.prompt_renderer.render("visual_quality.md", context)
        return await self.llm_client.assess_visual_quality(prompt, image_path, label)

    @staticmethod
    def _format_visual_issues(control_visual, challenger_visual) -> str:
        return (
            f"Control visual quality: {control_visual.visual_quality}. "
            f"Control issues: {control_visual.visual_issues} "
            f"Challenger visual quality: {challenger_visual.visual_quality}. "
            f"Challenger issues: {challenger_visual.visual_issues}"
        )

    @staticmethod
    def map_verdict(raw_verdict: RawVerdict, presented_order: PresentedOrder) -> MappedVerdict:
        if raw_verdict == RawVerdict.none:
            return MappedVerdict.none
        if presented_order == PresentedOrder.control_first:
            return MappedVerdict.control if raw_verdict == RawVerdict.image_1 else MappedVerdict.challenger
        return MappedVerdict.challenger if raw_verdict == RawVerdict.image_1 else MappedVerdict.control
