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

## Docker Compose

To run the main app together with the official OpenClaw Gateway container:

```bash
docker compose up --build
```

Open the app at:

```text
http://127.0.0.1:8011
```

Compose starts two services:

- `web`: the SimAB FastAPI app.
- `openclaw-gateway`: a thin project image built `FROM ghcr.io/openclaw/openclaw:latest` with `openclaw/openclaw.json5` copied in.

The `web` service calls OpenClaw through:

```env
SAB_OPENCLAW_BASE_URL=http://openclaw-gateway:18789
SAB_OPENCLAW_MODEL=openclaw/product_manager
SAB_OPENCLAW_GATEWAY_TOKEN=<same value as OPENCLAW_GATEWAY_TOKEN when auth is enabled>
SAB_IMAGE_API_KEY=<vsellm API key; falls back to SAB_REAL_API_KEY>
SAB_IMAGE_BASE_URL=https://api.vsellm.ru/v1
SAB_IMAGE_MODEL=openai/gpt-image-1
SAB_IMAGE_SIZE=1536x1024
SAB_IMAGE_QUALITY=high
SAB_IMAGE_INPUT_FIDELITY=high
SAB_IMAGE_EDIT_ENDPOINT_PATH=/images/edits
```

Compose uses `simab-dev-openclaw-token` as a local fallback token because OpenClaw refuses to bind the Gateway to `0.0.0.0` without auth. Set `OPENCLAW_GATEWAY_TOKEN` in `.env` to replace it.

By default, the Gateway is published on host port `18791` to avoid clashing with a separately installed local OpenClaw Gateway on `18789`. Keep the internal compose URL unchanged and only move the host port when needed:

```env
OPENCLAW_GATEWAY_HOST_PORT=18792
```

OpenClaw Gateway exposes OpenAI-compatible endpoints, including `/v1/chat/completions`. The minimal project config lives in `openclaw/openclaw.json5` and enables `gateway.http.endpoints.chatCompletions.enabled`. The Compose container also starts with `--allow-unconfigured` so it can still boot while you iterate on the OpenClaw setup. Configure agents and richer Gateway behavior in that OpenClaw config as the agent system grows. The Compose file also passes through these model env vars for convenience:

```env
SAB_REAL_API_KEY=...
SAB_REAL_BASE_URL=https://api.vsellm.ru/v1
SAB_REAL_MODEL=google/gemini-2.5-flash
```

The OpenClaw image copies these project files at build time:

```text
openclaw/agents -> /home/node/.openclaw/agents
openclaw/skills -> /home/node/.openclaw/skills
```

For live editing without rebuilding, run Compose with the workspace override:

```bash
docker compose -f docker-compose.yml -f docker-compose.openclaw-workspace.yml up --build
```

On Docker Desktop for macOS, bind mounts require File Sharing access to this project path. If you see `operation not permitted` for `/Users/.../Documents/...`, add `/Users/mikhailkozyrev/Documents` in Docker Desktop Settings -> Resources -> File Sharing, then restart Docker Desktop.

Current empty agent and OpenClaw-native skill scaffolds:

```text
openclaw/agents/product_manager.md
openclaw/agents/ux_designer.md
openclaw/agents/ux_researcher.md
openclaw/skills/hypothesis_scorer/SKILL.md
```

Variant generation uses this OpenClaw pipeline:

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

OpenClaw is used only for hypothesis discussion and ranking. After the user selects a hypothesis, the control screenshot is sent directly as multipart `image` to `{SAB_IMAGE_BASE_URL}{SAB_IMAGE_EDIT_ENDPOINT_PATH}` with a short prompt containing only the exact requested change and a minimal preservation constraint. There is no visual planner, overlay renderer, crop router, or image generation through chat completions. The image endpoint may return either `data[0].b64_json` or `data[0].url`; both are saved as the challenger. Request, response-shape, and output-path events are logged without API keys or image payloads.

Smoke checks:

```bash
curl -H "Authorization: Bearer simab-dev-openclaw-token" http://127.0.0.1:18791/v1/models
curl -H "Authorization: Bearer simab-dev-openclaw-token" \
  -H "Content-Type: application/json" \
  -d '{"model":"openclaw/product_manager","messages":[{"role":"user","content":"Return {\"ok\":true} as JSON."}]}' \
  http://127.0.0.1:18791/v1/chat/completions
```

Useful logs:

```bash
docker compose logs -f openclaw-gateway
docker compose logs -f web
```

In the `web` logs, look for:

- `Sending OpenClaw Gateway request`
- `OpenClaw Gateway response status=...`
- `OpenClaw Gateway response parsed`

In the `openclaw-gateway` logs, use the Gateway's own startup, model, auth, and request logs to verify whether the model request is accepted.

## API

- `POST /experiments` creates an experiment.
- `POST /experiments/{id}/upload` uploads `control` and `challenger` image files.
- `POST /experiments/{id}/run` runs the simulation.
- `POST /experiments/{id}/run-generation` sends the experiment fields and control image to OpenClaw.
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
