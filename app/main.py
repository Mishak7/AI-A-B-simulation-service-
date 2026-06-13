from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.experiments import router as experiments_router
from app.config import get_settings
from app.db.base import Base
from app.db.session import engine

from app import models as _models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Starting %s llm_provider=%s database_url=%s storage_dir=%s",
        settings.app_name,
        settings.llm_provider,
        settings.database_url,
        settings.storage_dir,
    )
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _run_sqlite_migrations(connection)
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(experiments_router)


async def _run_sqlite_migrations(connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    def migrate(sync_connection) -> None:
        def columns(table_name: str) -> set[str]:
            rows = sync_connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            return {row[1] for row in rows}

        simulation_columns = columns("simulation_results")
        simulation_additions = {
            "visual_quality_image_1": "VARCHAR(12) NOT NULL DEFAULT 'pass'",
            "visual_quality_image_2": "VARCHAR(12) NOT NULL DEFAULT 'pass'",
            "visual_issues": "TEXT NOT NULL DEFAULT ''",
            "critical_visual_defect": "BOOLEAN NOT NULL DEFAULT 0",
        }
        for column_name, column_type in simulation_additions.items():
            if column_name not in simulation_columns:
                sync_connection.exec_driver_sql(
                    f"ALTER TABLE simulation_results ADD COLUMN {column_name} {column_type}"
                )

        report_columns = columns("experiment_reports")
        report_additions = {
            "image_1_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "image_2_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "control_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "challenger_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
        }
        for column_name, column_type in report_additions.items():
            if column_name not in report_columns:
                sync_connection.exec_driver_sql(
                    f"ALTER TABLE experiment_reports ADD COLUMN {column_name} {column_type}"
                )

    await connection.run_sync(migrate)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Synthetic AB Preflight</title>
  <style>
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f7f9; color: #17202a; }
    main { max-width: 920px; margin: 0 auto; padding: 32px 20px; }
    h1 { font-size: 28px; margin: 0 0 20px; }
    section { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
    label { display: block; font-weight: 650; margin-top: 12px; }
    input, textarea { width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px; border: 1px solid #c8d0d8; border-radius: 6px; font: inherit; }
    textarea { min-height: 88px; resize: vertical; }
    button { margin-top: 16px; padding: 10px 14px; border: 0; border-radius: 6px; background: #1769aa; color: white; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: wait; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    pre { white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 16px; border-radius: 8px; overflow: auto; }
    @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <h1>Synthetic AB Preflight</h1>
    <section>
      <label>Name <input id="name" value="Homepage CTA test" /></label>
      <label>Conversion goal <textarea id="goal">Increase clicks on the primary signup CTA.</textarea></label>
      <label>Target audience <textarea id="audience">Busy B2B SaaS buyers evaluating a new workflow tool.</textarea></label>
      <div class="grid">
        <label>Control image <input id="control" type="file" accept="image/*" /></label>
        <label>Challenger image <input id="challenger" type="file" accept="image/*" /></label>
      </div>
      <label>Personas <input id="personas" type="number" min="1" max="500" value="20" /></label>
      <button id="run">Run</button>
    </section>
    <section>
      <h2>Result</h2>
      <pre id="result">No run yet.</pre>
    </section>
  </main>
  <script>
    const result = document.getElementById("result");
    document.getElementById("run").addEventListener("click", async () => {
      const button = document.getElementById("run");
      button.disabled = true;
      result.textContent = "Running...";
      try {
        const created = await fetch("/experiments", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            name: document.getElementById("name").value,
            conversion_goal: document.getElementById("goal").value,
            target_audience: document.getElementById("audience").value
          })
        }).then(r => r.json());

        const form = new FormData();
        form.append("control", document.getElementById("control").files[0]);
        form.append("challenger", document.getElementById("challenger").files[0]);
        await fetch(`/experiments/${created.id}/upload`, { method: "POST", body: form });

        const report = await fetch(`/experiments/${created.id}/run`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ num_personas: Number(document.getElementById("personas").value), batch_size: 10 })
        }).then(r => r.json());
        result.textContent = JSON.stringify(report, null, 2);
      } catch (error) {
        result.textContent = String(error);
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
