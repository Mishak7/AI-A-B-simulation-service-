import hashlib
from typing import Any

from app.llm.base import LLMClient
from app.schemas.persona import PersonaProfile
from app.schemas.simulation import SimulationVerdict, VisualAssessment


class MockLLMClient(LLMClient):
    occupations = [
        "Product manager",
        "Small business owner",
        "Student",
        "Marketing specialist",
        "Software engineer",
        "Operations lead",
        "Freelance designer",
        "Customer support manager",
    ]
    locations = ["New York", "Austin", "Berlin", "London", "Toronto", "Warsaw", "Madrid", "Amsterdam"]

    async def generate_personas(self, prompt: str, num_personas: int) -> list[PersonaProfile]:
        personas: list[PersonaProfile] = []
        offset = prompt.count("Synthetic Persona")
        for index in range(num_personas):
            absolute_index = offset + index
            occupation = self.occupations[absolute_index % len(self.occupations)]
            location = self.locations[absolute_index % len(self.locations)]
            savviness = ["low", "medium", "high"][absolute_index % 3]
            personas.append(
                PersonaProfile(
                    name=f"Synthetic Persona {absolute_index + 1}",
                    age_range=["18-24", "25-34", "35-44", "45-54", "55+"][absolute_index % 5],
                    occupation=occupation,
                    income_level=["low", "middle", "upper-middle", "high"][absolute_index % 4],
                    education=["High school", "Bachelor's", "Master's", "Professional training"][
                        absolute_index % 4
                    ],
                    location=location,
                    interests=f"Convenience, trust signals, clear pricing, and {occupation.lower()} workflows",
                    goals="Complete the task quickly with low uncertainty.",
                    pain_points="Confusing navigation, unclear value proposition, and excessive form friction.",
                    technical_savviness=savviness,
                    financial_literacy=["low", "medium", "high"][absolute_index % 3],
                    digital_literacy=["low", "medium", "high"][absolute_index % 3],
                    trust_in_online_banking=["low", "medium", "high"][(absolute_index + 1) % 3],
                    fraud_anxiety=["low", "medium", "high"][(absolute_index + 2) % 3],
                    fee_sensitivity=["low", "medium", "high"][(absolute_index + 1) % 3],
                    privacy_sensitivity=["low", "medium", "high"][(absolute_index + 2) % 3],
                    banking_channel_preference=["mobile-first", "web", "branch support"][
                        absolute_index % 3
                    ],
                    decision_style=["quick scanner", "careful comparer", "advice-seeking"][
                        absolute_index % 3
                    ],
                    region_type=["large city", "small city", "rural area"][absolute_index % 3],
                    income_stability=["unstable", "moderate", "stable"][absolute_index % 3],
                    online_behavior="Compares options, scans headings, and looks for proof before acting.",
                    browsing_context="Short focused session on desktop or mobile during a busy day.",
                    task_context="Evaluating which interface better supports the stated conversion goal.",
                )
            )
        return personas

    async def simulate_choice(
        self,
        prompt: str,
        control_image_path: str,
        challenger_image_path: str,
        context: dict[str, Any],
    ) -> SimulationVerdict:
        persona_profile = str(context.get("persona_profile", ""))
        digest = hashlib.sha256(f"{prompt}|{persona_profile}".encode()).hexdigest()
        bucket = int(digest[:2], 16) % 10
        if bucket in {0, 1, 2, 3}:
            verdict = "image_1"
        elif bucket in {4, 5, 6}:
            verdict = "image_2"
        else:
            verdict = "none"
        confidence = ["low", "medium", "high"][int(digest[2:4], 16) % 3]
        rationale = (
            "The selected option appears more aligned with the persona's need for clarity, "
            "reduced friction, and confidence before converting."
        )
        return SimulationVerdict(
            verdict=verdict,
            confidence=confidence,
            rationale=rationale,
        )

    async def assess_visual_quality(self, prompt: str, image_path: str, image_label: str) -> VisualAssessment:
        return VisualAssessment(
            visual_quality="pass",
            visual_issues=f"{image_label} has no visual integrity issues detected by the mock client.",
        )

    async def summarize_report(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        winner = context.get("winner", "inconclusive")
        return {
            "recommendations": [
                f"Use the {winner} direction as a hypothesis for real user validation."
                if winner != "inconclusive"
                else "Treat the result as directional only and test clearer differentiation.",
                "Review the most common rationale themes before changing production UI.",
                "Run a real A/B test with production traffic before making final decisions.",
            ],
            "limitations": "Synthetic evaluation is not a replacement for real A/B testing.",
        }
