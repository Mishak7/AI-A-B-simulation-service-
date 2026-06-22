import hashlib
from typing import Any

from app.llm.base import LLMClient
from app.schemas.persona import PersonaProfile
from app.schemas.simulation import SimulationVerdict, VisualAssessment


class MockLLMClient(LLMClient):
    cohorts = [
        {
            "cohort": "Целевой пользователь",
            "cohort_motivation": "Быстро решить конкретную задачу",
            "information_discovery_style": "Ищет нужную кнопку, форму, цену, вход или конкретную услугу",
            "typical_behavior": "Быстро скроллит до целевого блока, кликает по очевидным CTA, мало изучает второстепенные разделы",
            "funnel_exit_risk": "Нет понятного следующего шага, слишком много лишней информации, длинный путь до действия",
        },
        {
            "cohort": "Сканирующий пользователь",
            "cohort_motivation": "Быстро понять, подходит продукт или нет",
            "information_discovery_style": "Читает заголовки, первые строки, визуальные акценты",
            "typical_behavior": "Короткие резкие скроллы, быстрые переходы, мало времени на странице",
            "funnel_exit_risk": "Слабый первый экран, длинные тексты, неясное ценностное предложение",
        },
        {
            "cohort": "Исследователь",
            "cohort_motivation": "Сравнить варианты и выбрать оптимальный",
            "information_discovery_style": "Изучает карточки, тарифы, преимущества, FAQ, примеры",
            "typical_behavior": "Много скроллит, возвращается назад, открывает несколько разделов, сравнивает условия",
            "funnel_exit_risk": "Нет сравнения, фильтров, структуры, понятных различий между вариантами",
        },
        {
            "cohort": "Осторожный пользователь",
            "cohort_motivation": "Убедиться, что продукту можно доверять",
            "information_discovery_style": "Ищет условия, ограничения, безопасность, отзывы, контакты, юридическую информацию",
            "typical_behavior": "Часто открывает FAQ, футер, документы, условия, страницы поддержки",
            "funnel_exit_risk": "Скрытые комиссии, неполные условия, нет контактов, нет сигналов доверия",
        },
        {
            "cohort": "Неуверенный пользователь",
            "cohort_motivation": "Выполнить действие без ошибки",
            "information_discovery_style": "Внимательно читает подсказки, инструкции, пояснения к полям",
            "typical_behavior": "Медленные действия, паузы перед кликом, возвраты назад, ошибки в формах",
            "funnel_exit_risk": "Непонятные термины, агрессивная форма, плохая обработка ошибок, нет подсказок",
        },
    ]
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
    locations = [
        "New York",
        "Austin",
        "Berlin",
        "London",
        "Toronto",
        "Warsaw",
        "Madrid",
        "Amsterdam",
    ]

    async def generate_personas(
        self, prompt: str, num_personas: int
    ) -> list[PersonaProfile]:
        personas: list[PersonaProfile] = []
        offset = prompt.count("Synthetic Persona")
        for index in range(num_personas):
            absolute_index = offset + index
            occupation = self.occupations[absolute_index % len(self.occupations)]
            location = self.locations[absolute_index % len(self.locations)]
            savviness = ["low", "medium", "high"][absolute_index % 3]
            cohort = self.cohorts[absolute_index % len(self.cohorts)]
            personas.append(
                PersonaProfile(
                    name=f"Synthetic Persona {absolute_index + 1}",
                    age_range=["18-24", "25-34", "35-44", "45-54", "55+"][
                        absolute_index % 5
                    ],
                    occupation=occupation,
                    income_level=["low", "middle", "upper-middle", "high"][
                        absolute_index % 4
                    ],
                    education=[
                        "High school",
                        "Bachelor's",
                        "Master's",
                        "Professional training",
                    ][absolute_index % 4],
                    location=location,
                    interests=f"Convenience, trust signals, clear pricing, and {occupation.lower()} workflows",
                    goals="Complete the task quickly with low uncertainty.",
                    pain_points="Confusing navigation, unclear value proposition, and excessive form friction.",
                    technical_savviness=savviness,
                    financial_literacy=["low", "medium", "high"][absolute_index % 3],
                    digital_literacy=["low", "medium", "high"][absolute_index % 3],
                    trust_in_online_banking=["low", "medium", "high"][
                        (absolute_index + 1) % 3
                    ],
                    fraud_anxiety=["low", "medium", "high"][(absolute_index + 2) % 3],
                    fee_sensitivity=["low", "medium", "high"][(absolute_index + 1) % 3],
                    privacy_sensitivity=["low", "medium", "high"][
                        (absolute_index + 2) % 3
                    ],
                    banking_channel_preference=[
                        "mobile-first",
                        "web",
                        "branch support",
                    ][absolute_index % 3],
                    decision_style=[
                        "quick scanner",
                        "careful comparer",
                        "advice-seeking",
                    ][absolute_index % 3],
                    region_type=["large city", "small city", "rural area"][
                        absolute_index % 3
                    ],
                    income_stability=["unstable", "moderate", "stable"][
                        absolute_index % 3
                    ],
                    online_behavior="Compares options, scans headings, and looks for proof before acting.",
                    browsing_context="Short focused session on desktop or mobile during a busy day.",
                    task_context="Evaluating which interface better supports the stated conversion goal.",
                    **cohort,
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
            "Выбранный вариант лучше соответствует потребности персоны в ясности, "
            "низком трении и уверенности перед конверсией."
        )
        return SimulationVerdict(
            verdict=verdict,
            confidence=confidence,
            rationale=rationale,
        )

    async def assess_visual_quality(
        self, prompt: str, image_path: str, image_label: str
    ) -> VisualAssessment:
        return VisualAssessment(
            visual_quality="pass",
            visual_issues=f"Для изображения {image_label} mock-клиент не обнаружил серьезных визуальных проблем.",
        )

    async def summarize_report(
        self, prompt: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        if "combined_report" in context:
            return {
                "text_findings": [
                    "Оффер должен быть яснее.",
                    "CTA требует быстрой проверки.",
                ],
                "visual_findings": [],
                "combined_conclusion": (
                    "Совместный вывод указывает направление для проверки на реальных "
                    "пользователях без замены полноценного A/B-теста."
                ),
            }
        winner = context.get("winner", "inconclusive")
        return {
            "recommendations": [
                (
                    f"Используйте направление {winner} как гипотезу для проверки на реальных пользователях."
                    if winner != "inconclusive"
                    else "Считайте результат только направлением для размышления и проверьте более явное различие вариантов."
                ),
                "Перед изменением продакшен-интерфейса изучите самые частые причины выбора.",
                "Перед финальным решением запустите реальный A/B-тест на продуктовой аудитории.",
            ],
            "limitations": "Синтетическая оценка не заменяет реальный A/B-тест.",
        }
