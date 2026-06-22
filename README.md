# Synthetic AB Preflight

Local backend-first MVP for simulating an A/B test from two UI screenshots.

The service lets you create an experiment, upload Control and Challenger images, generate synthetic personas, run mock LLM/VLM evaluations with counterbalanced image order, aggregate votes, and produce a directional report.

## Stack

- Python 3.11+
- FastAPI
- Pydantic
- SQLAlchemy async
- SQLite via `aiosqlite`
- Jinja2 prompt templates
- Local image storage in `app/storage/`

No LangChain, CrewAI, AutoGen, RAG, browser automation, authentication, or production security is included in this MVP.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Agent LLM pipeline

The app runs directly with Uvicorn. There is no separate agent gateway or container:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Configure the OpenAI-compatible text/vision model and image-edit model in `.env`:

```env
SAB_LLM_PROVIDER=real
SAB_REAL_API_KEY=...
SAB_REAL_BASE_URL=https://api.vsellm.ru/v1
SAB_REAL_MODEL=google/gemini-2.5-flash
SAB_AGENT_PIPELINE_MODEL=openai/gpt-4.1-mini
SAB_AGENT_PIPELINE_MAX_TOKENS=8192
SAB_AGENT_PIPELINE_TIMEOUT_SECONDS=120
SAB_IMAGE_API_KEY=...
SAB_IMAGE_BASE_URL=https://api.vsellm.ru/v1
SAB_IMAGE_MODEL=google/gemini-3-pro-image-preview
SAB_IMAGE_SIZE=1536x1024
SAB_IMAGE_QUALITY=high
SAB_IMAGE_INPUT_FIDELITY=high
SAB_IMAGE_EDIT_ENDPOINT_PATH=/images/edits
```

The agent and scorer instructions are stored as standalone Markdown files:

```text
app/prompts/agents/product_manager.md
app/prompts/agents/ux_designer.md
app/prompts/agents/ux_researcher.md
app/prompts/skills/hypothesis_scorer.md
```

Variant generation uses this direct LLM pipeline:

```text
product_manager.md
ux_designer.md
ux_researcher.md
        ↓
hypothesis_scorer/SKILL.md
        ↓
user selects one of the top 3 hypotheses
        ↓
the control image + hypothesis + strict minimal-change prompt
        ↓
openai/gpt-image-1 image edit through api.vsellm.ru
        ↓
user approves generated challenger
        ↓
ready for synthetic A/B
```

The three specialist calls receive the same control screenshot independently. Their structured JSON outputs are passed to the scorer call, exactly as defined in the Markdown instructions. After the user selects a hypothesis, the control screenshot is sent directly as multipart `image` to `{SAB_IMAGE_BASE_URL}{SAB_IMAGE_EDIT_ENDPOINT_PATH}` with the existing strict minimal-change prompt. The response may contain either `data[0].b64_json` or `data[0].url`; both are saved as the challenger.

## API

- `POST /experiments` creates an experiment.
- `POST /experiments/{id}/upload` uploads `control` and `challenger` image files.
- `POST /experiments/{id}/run` runs the simulation.
- `POST /experiments/{id}/run-generation` runs the direct agent LLM pipeline for the experiment fields and control image.
- `POST /experiments/{id}/generate-variant-image` generates a challenger from the control image and selected hypothesis.
- `GET /experiments/{id}` returns experiment status.
- `GET /experiments/{id}/report` returns the final report.

Example run payload:

```json
{
  "num_personas": 50,
  "batch_size": 10,
  "early_stopping": false
}
```

## Prompts

Prompt templates live in `app/prompts/`:

- `persona_generation.md`
- `persona_simulation.md`
- `report_summary.md`

They are rendered with Jinja2 by `app/services/prompt_renderer.py`:

```python
renderer.render(
    template_name="persona_generation.md",
    context={"conversion_goal": "...", "target_audience": "..."}
)
```

The renderer accepts a single `context: dict[str, Any]`. You can add new variables to prompt files and pass them through context without changing the renderer API or service signatures. Replacing placeholder prompts with SimAB Appendix A prompts is intended to be a file-only change.

## LLM Clients

The default provider is `mock`, configured by:

```text
SAB_LLM_PROVIDER=mock
```

The mock client generates deterministic synthetic personas and verdicts so the pipeline works offline. `app/llm/real_client.py` is a placeholder for wiring a real LLM/VLM provider later behind the same interface.

To use a real model through an OpenAI-compatible gateway, for example `vsellm.ru`:

```bash
pip install -r requirements.txt
```

Set:

```env
SAB_LLM_PROVIDER=real
SAB_REAL_API_KEY=your_gateway_api_key
SAB_REAL_BASE_URL=https://api.vsellm.ru/v1
SAB_REAL_MODEL=google/gemini-2.5-flash
```

This matches the usual OpenAI-compatible client shape:

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-api-key",
    base_url="https://api.vsellm.ru/v1",
)
```

The real client lives in `app/llm/real_client.py` and uses the same `LLMClient` interface as the mock client, so the API endpoints and orchestration services do not change.

## Tests

```bash
pytest
```
