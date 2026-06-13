Analyze feedback from synthetic personas who evaluated two interface variants.
Each persona chose Control, Challenger, or None.

Control votes:
{{ control_votes }}

Challenger votes:
{{ challenger_votes }}

None votes:
{{ none_votes }}

Winner:
{{ winner }}

Confidence score:
{{ confidence_score }}

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

This MVP already computes vote counts, winner, confidence, and top rationale
groups locally. Your job is to provide concise recommendations and limitations
only.

Return strictly valid JSON. Do not include Markdown fences or explanatory text.

Required response shape:
{
  "recommendations": [
    "Actionable recommendation 1",
    "Actionable recommendation 2",
    "Actionable recommendation 3"
  ],
  "limitations": "Synthetic evaluation is not a replacement for real A/B testing."
}

The limitations field must explicitly include this sentence:
Synthetic evaluation is not a replacement for real A/B testing.
