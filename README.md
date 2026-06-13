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

## API

- `POST /experiments` creates an experiment.
- `POST /experiments/{id}/upload` uploads `control` and `challenger` image files.
- `POST /experiments/{id}/run` runs the simulation.
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
