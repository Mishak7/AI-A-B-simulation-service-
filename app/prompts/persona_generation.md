You are an expert in user research and persona development. Generate realistic,
diverse synthetic personas for a lightweight A/B preflight simulation based on
two uploaded interface screenshots.

Conversion goal:
{{ conversion_goal }}

Target audience:
{{ target_audience or "General audience" }}

Number of personas to generate exactly:
{{ num_personas }}

Existing personas in this experiment batch:
{{ existing_personas or "None" }}

Image 1 description:
{{ image_1_description or "Local uploaded interface screenshot." }}

Image 2 description:
{{ image_2_description or "Local uploaded interface screenshot." }}

Experiment context:
{{ experiment_context or "None" }}

Generate personas for Russian retail banking, ensure diversity across:
- age and digital literacy
- trust in online banking
- sensitivity to fraud and scams
- financial literacy
- income stability
- region: large city / small city / rural area
- product context: credit, savings, payments, investments
- channel preference: mobile-first / web / branch support
- tolerance for forms and personal data requests
- time sensitivity, from rushed to leisurely
- purchase or conversion intent, from casual browsing to active decision-making
- tolerance for initial friction, from low to high

Personas may arrive from different channels such as social media, ads, organic
search, direct traffic, recommendations, or LLM/chat discovery. Most personas
should be plausibly interested in the product or service, but they should not
all be ready to convert before seeing the interface.

Do not assume uniform behavior. Make sure each persona has a life, constraints,
goals, and needs beyond this specific product category. Personas may reject ads,
cookies, promotions, confusing claims, or aggressive flows if they feel fishy.

Assign every persona to exactly one of these five interface-behavior cohorts.
Use the cohort name and its four descriptions exactly as written; do not invent,
rename, combine, or translate cohort names or descriptions:

1. Целевой пользователь
- cohort_motivation: Быстро решить конкретную задачу
- information_discovery_style: Ищет нужную кнопку, форму, цену, вход или конкретную услугу
- typical_behavior: Быстро скроллит до целевого блока, кликает по очевидным CTA, мало изучает второстепенные разделы
- funnel_exit_risk: Нет понятного следующего шага, слишком много лишней информации, длинный путь до действия

2. Сканирующий пользователь
- cohort_motivation: Быстро понять, подходит продукт или нет
- information_discovery_style: Читает заголовки, первые строки, визуальные акценты
- typical_behavior: Короткие резкие скроллы, быстрые переходы, мало времени на странице
- funnel_exit_risk: Слабый первый экран, длинные тексты, неясное ценностное предложение

3. Исследователь
- cohort_motivation: Сравнить варианты и выбрать оптимальный
- information_discovery_style: Изучает карточки, тарифы, преимущества, FAQ, примеры
- typical_behavior: Много скроллит, возвращается назад, открывает несколько разделов, сравнивает условия
- funnel_exit_risk: Нет сравнения, фильтров, структуры, понятных различий между вариантами

4. Осторожный пользователь
- cohort_motivation: Убедиться, что продукту можно доверять
- information_discovery_style: Ищет условия, ограничения, безопасность, отзывы, контакты, юридическую информацию
- typical_behavior: Часто открывает FAQ, футер, документы, условия, страницы поддержки
- funnel_exit_risk: Скрытые комиссии, неполные условия, нет контактов, нет сигналов доверия

5. Неуверенный пользователь
- cohort_motivation: Выполнить действие без ошибки
- information_discovery_style: Внимательно читает подсказки, инструкции, пояснения к полям
- typical_behavior: Медленные действия, паузы перед кликом, возвраты назад, ошибки в формах
- funnel_exit_risk: Непонятные термины, агрессивная форма, плохая обработка ошибок, нет подсказок

Distribute cohorts as evenly as mathematically possible across the requested
personas and the existing personas listed above. When fewer than five personas
are requested, use different cohorts without repetition where possible. Cohort
describes interface behavior only; keep the other fields focused on the
persona's independent social, financial, and life context.

Return strictly valid JSON with a top-level "personas" array containing exactly
{{ num_personas }} persona objects. Do not include Markdown fences or
explanatory text.

Each persona object must include exactly these string fields:
- name
- age_range
- occupation
- income_level
- education
- location
- interests
- goals
- pain_points
- technical_savviness
- financial_literacy
- digital_literacy
- trust_in_online_banking
- fraud_anxiety
- fee_sensitivity
- privacy_sensitivity
- banking_channel_preference
- decision_style
- region_type
- income_stability
- online_behavior
- browsing_context
- task_context
- cohort
- cohort_motivation
- information_discovery_style
- typical_behavior
- funnel_exit_risk

Example response shape:
{
  "personas": [
    {
      "name": "Budget-Conscious Researcher",
      "age_range": "25-34",
      "occupation": "Marketing specialist",
      "income_level": "Medium",
      "education": "Bachelor's",
      "location": "Urban area",
      "interests": "Clear pricing, practical tools, peer reviews",
      "goals": "Find a trustworthy option without wasting time",
      "pain_points": "Hidden fees, unclear claims, long forms",
      "technical_savviness": "Medium",
      "financial_literacy": "Medium",
      "digital_literacy": "High",
      "trust_in_online_banking": "Medium",
      "fraud_anxiety": "High",
      "fee_sensitivity": "High",
      "privacy_sensitivity": "Medium",
      "banking_channel_preference": "Mobile-first with web backup",
      "decision_style": "Careful comparer",
      "region_type": "Large city",
      "income_stability": "Stable monthly income",
      "online_behavior": "Compares several options before acting",
      "browsing_context": "Arrived from search during a short work break",
      "task_context": "Deciding whether the interface gives enough confidence to convert",
      "cohort": "Исследователь",
      "cohort_motivation": "Сравнить варианты и выбрать оптимальный",
      "information_discovery_style": "Изучает карточки, тарифы, преимущества, FAQ, примеры",
      "typical_behavior": "Много скроллит, возвращается назад, открывает несколько разделов, сравнивает условия",
      "funnel_exit_risk": "Нет сравнения, фильтров, структуры, понятных различий между вариантами"
    }
  ]
}
