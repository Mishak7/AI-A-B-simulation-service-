You will receive an already generated combined A/B-test report.
Do not inspect images and do not invent evidence outside this combined report.

Combined report:
{{ combined_report }}

Create three final sections for quick reading:

1. text_findings
Very short conclusions about text/content only: offer clarity, CTA wording,
conditions, trust wording, risk wording, pricing wording, next-step wording.

2. visual_findings
Very short conclusions about visual/interface only: layout, hierarchy,
readability, visual trust, visual defects, mobile friendliness, overload.

3. combined_conclusion
The joint conclusion that preserves the overall meaning of the combined report.

Important rules:
- If the combined report does not clearly contain a text/content-specific
  conclusion, return an empty text_findings array.
- If the combined report does not clearly contain a visual/interface-specific
  conclusion, return an empty visual_findings array.
- Do not force both sections to be non-empty.
- Do not treat a text-only push/message as a visual design conclusion unless
  the report explicitly mentions visual layout, readability, hierarchy, or
  defects.
- Do not treat a textless image/layout conclusion as a content conclusion unless
  the report explicitly mentions wording, offer, CTA, terms, price, trust copy,
  or next-step text.
- Keep text_findings and visual_findings extremely short: 0-3 bullets each,
  each no longer than 12 words.
- Write all human-readable values in Russian.
- Return strictly valid JSON. Do not include Markdown fences.

Required response shape:
{
  "text_findings": [
    "Короткий вывод по тексту"
  ],
  "visual_findings": [
    "Короткий вывод по визуалу"
  ],
  "combined_conclusion": "Совместный вывод по эксперименту."
}
