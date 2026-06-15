Analyze feedback from synthetic personas who evaluated two interface variants.
Each simulation chose baseline variant, test variant, or none.

Baseline variant votes:
{{ control_votes }}

Test variant votes:
{{ challenger_votes }}

None votes:
{{ none_votes }}

Winner:
{{ winner }}

Confidence score:
{{ confidence_score }}

Stable personas:
{{ stable_personas }}

Unstable personas:
{{ unstable_personas }}

Unstable rate:
{{ unstable_rate }}

Grouped rationales:
{{ rationales }}

Visual quality statistics:
{{ visual_stats or "None" }}

Experiment context:
{{ experiment_context or "None" }}

Identify the main decision patterns and provide actionable insights for the
experiment. Focus on conversion factors such as product presentation,
trustworthiness, ease of use, pricing clarity, navigation, visual hierarchy,
mobile-friendliness, cognitive load, and conversion optimization. 
If visual defects are present, prioritize fixing layout/readability issues before optimizing copy or conversion wording.

This MVP already computes stable-persona vote counts, winner, confidence,
unstable-persona rate, and top rationale groups locally. Your job is to provide
concise recommendations and limitations only.

Return strictly valid JSON. Do not include Markdown fences or explanatory text.
All human-readable string values in the response, including recommendations and
limitations, must be written in Russian. Keep JSON field names exactly as
specified.

Required response shape:
{
  "recommendations": [
    "Практическая рекомендация 1",
    "Практическая рекомендация 2",
    "Практическая рекомендация 3"
  ],
  "limitations": "Синтетическая оценка не заменяет реальный A/B-тест."
}

The limitations field must explicitly include this Russian sentence:
Синтетическая оценка не заменяет реальный A/B-тест.
