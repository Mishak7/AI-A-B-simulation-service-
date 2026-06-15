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
      "task_context": "Deciding whether the interface gives enough confidence to convert"
    }
  ]
}
