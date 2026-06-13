You are performing a strict visual integrity QA review for one interface
screenshot. Evaluate only the screenshot shown in this request.

Image label:
{{ image_label }}

Conversion goal:
{{ conversion_goal }}

Target audience:
{{ target_audience or "General audience" }}

Experiment context:
{{ experiment_context or "None" }}

Assess whether the screenshot appears visually usable and production-ready.
Serious visual integrity problems include:
- overlapping blocks or text
- cropped or unreadable CTA buttons
- inconsistent font sizes that look accidental
- broken layout or elements placed on top of each other
- unreadable text due to contrast, size, or positioning
- form fields, buttons, or labels that appear visually broken
- confusing visual hierarchy caused by layout defects

Return strictly valid JSON. Do not compare this screenshot to any other image.
Do not include Markdown fences or explanatory text.

Required response shape:
{
  "visual_quality": "pass",
  "visual_issues": "Short description of visual defects, or say no serious visual issues were detected."
}

Allowed values:
- visual_quality: "pass" | "minor_issues" | "fail"
