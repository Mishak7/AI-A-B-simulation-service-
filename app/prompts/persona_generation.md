You are an expert in user research and persona development. Generate realistic,
diverse synthetic personas for a lightweight A/B preflight simulation based on
two uploaded interface screenshots.

Conversion goal:
{{ conversion_goal }}

Target audience:
{{ target_audience or "General audience" }}

Number of personas to generate:
{{ num_personas }}

Existing personas in this experiment batch:
{{ existing_personas or "None" }}

Control image description:
{{ control_image_description or "Local uploaded control screenshot." }}

Challenger image description:
{{ challenger_image_description or "Local uploaded challenger screenshot." }}

Experiment context:
{{ experiment_context or "None" }}

Generate personas with meaningful diversity across:
- privacy orientation, from strict to relaxed
- tolerance for initial friction, from low to high
- time sensitivity, from rushed to leisurely
- comfort with personalization, from low to high
- purchase or conversion intent, from casual browsing to active decision-making
- risk tolerance, decisiveness, technical literacy, age, and lifestyle

Personas may arrive from different channels such as social media, ads, organic
search, direct traffic, recommendations, or LLM/chat discovery. Most personas
should be plausibly interested in the product or service, but they should not
all be ready to convert before seeing the interface.

Do not assume uniform behavior. Make sure each persona has a life, constraints,
goals, and needs beyond this specific product category. Personas may reject ads,
cookies, promotions, confusing claims, or aggressive flows if they feel fishy.

Return strictly valid JSON with a top-level "personas" array. Do not include
Markdown fences or explanatory text.

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
      "online_behavior": "Compares several options before acting",
      "browsing_context": "Arrived from search during a short work break",
      "task_context": "Deciding whether the interface gives enough confidence to convert"
    }
  ]
}
