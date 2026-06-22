from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.experiments import router as experiments_router
from app.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.services.logging_config import configure_logging

from app import models as _models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
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
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(experiments_router)


@app.get("/logs")
async def read_logs(
    limit: int = Query(default=180, ge=1, le=1000)
) -> dict[str, object]:
    log_file = get_settings().log_file
    if not log_file.exists():
        return {"path": str(log_file), "lines": []}
    with log_file.open("r", encoding="utf-8", errors="replace") as file:
        lines = file.readlines()
    return {
        "path": str(log_file),
        "lines": [line.rstrip("\n") for line in lines[-limit:]],
    }


async def _run_sqlite_migrations(connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    def migrate(sync_connection) -> None:
        def columns(table_name: str) -> set[str]:
            rows = sync_connection.exec_driver_sql(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
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

        persona_columns = columns("personas")
        persona_additions = {
            "financial_literacy": "VARCHAR(128) NOT NULL DEFAULT ''",
            "digital_literacy": "VARCHAR(128) NOT NULL DEFAULT ''",
            "trust_in_online_banking": "VARCHAR(128) NOT NULL DEFAULT ''",
            "fraud_anxiety": "VARCHAR(128) NOT NULL DEFAULT ''",
            "fee_sensitivity": "VARCHAR(128) NOT NULL DEFAULT ''",
            "privacy_sensitivity": "VARCHAR(128) NOT NULL DEFAULT ''",
            "banking_channel_preference": "VARCHAR(255) NOT NULL DEFAULT ''",
            "decision_style": "VARCHAR(255) NOT NULL DEFAULT ''",
            "region_type": "VARCHAR(128) NOT NULL DEFAULT ''",
            "income_stability": "VARCHAR(128) NOT NULL DEFAULT ''",
            "cohort": "VARCHAR(64) NOT NULL DEFAULT 'Целевой пользователь'",
            "cohort_motivation": "TEXT NOT NULL DEFAULT 'Быстро решить конкретную задачу'",
            "information_discovery_style": "TEXT NOT NULL DEFAULT 'Ищет нужную кнопку, форму, цену, вход или конкретную услугу'",
            "typical_behavior": "TEXT NOT NULL DEFAULT 'Быстро скроллит до целевого блока, кликает по очевидным CTA, мало изучает второстепенные разделы'",
            "funnel_exit_risk": "TEXT NOT NULL DEFAULT 'Нет понятного следующего шага, слишком много лишней информации, длинный путь до действия'",
        }
        for column_name, column_type in persona_additions.items():
            if column_name not in persona_columns:
                sync_connection.exec_driver_sql(
                    f"ALTER TABLE personas ADD COLUMN {column_name} {column_type}"
                )

        experiment_columns = columns("experiments")
        experiment_additions = {
            "mode": "VARCHAR(32) NOT NULL DEFAULT 'ab_test'",
        }
        for column_name, column_type in experiment_additions.items():
            if column_name not in experiment_columns:
                sync_connection.exec_driver_sql(
                    f"ALTER TABLE experiments ADD COLUMN {column_name} {column_type}"
                )

        report_columns = columns("experiment_reports")
        report_additions = {
            "image_1_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "image_2_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "control_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "challenger_visual_fail_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "image_1_votes": "INTEGER NOT NULL DEFAULT 0",
            "image_2_votes": "INTEGER NOT NULL DEFAULT 0",
            "position_switch_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "positional_bias_score": "FLOAT NOT NULL DEFAULT 0.0",
            "stable_personas": "INTEGER NOT NULL DEFAULT 0",
            "unstable_personas": "INTEGER NOT NULL DEFAULT 0",
            "unstable_rate": "FLOAT NOT NULL DEFAULT 0.0",
            "text_findings": "TEXT NOT NULL DEFAULT '[]'",
            "visual_findings": "TEXT NOT NULL DEFAULT '[]'",
            "combined_conclusion": "TEXT NOT NULL DEFAULT ''",
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
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SimAB | Синтетический A/B-тест</title>
  <style>
    :root {
      --bg: #031923;
      --panel: #082d37;
      --panel-soft: #0b3942;
      --panel-deep: #05242e;
      --text: #e3fff7;
      --muted: #8fbab6;
      --line: rgba(111, 244, 202, 0.18);
      --green: #53e89b;
      --green-dark: #22bd7b;
      --blue: #45bce9;
      --yellow: #ffc76b;
      --red: #ff6f79;
      --soft: rgba(83, 232, 155, 0.09);
      --shadow: 0 22px 70px rgba(0, 8, 13, 0.46), inset 0 1px 0 rgba(198, 255, 235, 0.08);
    }

    * { box-sizing: border-box; }
    html { background: #031923; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 12% -8%, rgba(31, 119, 151, 0.42), transparent 34%),
        radial-gradient(circle at 88% 4%, rgba(34, 189, 123, 0.16), transparent 28%),
        linear-gradient(145deg, #031923 0%, #052731 52%, #03171f 100%);
      background-attachment: fixed;
      color: var(--text);
      font-family: "Manrope", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    main { max-width: 1240px; margin: 0 auto; padding: 28px 20px 40px; }
    header {
      position: relative;
      overflow: hidden;
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: center;
      min-height: 142px;
      margin-bottom: 22px;
      padding: 30px 34px;
      border: 1px solid rgba(111, 244, 202, 0.2);
      border-radius: 20px;
      background:
        radial-gradient(circle at 82% 28%, rgba(83, 232, 155, 0.2), transparent 28%),
        linear-gradient(120deg, rgba(10, 56, 68, 0.96), rgba(4, 36, 46, 0.98));
      box-shadow: var(--shadow);
    }
    header::after {
      content: "";
      position: absolute;
      width: 260px;
      aspect-ratio: 1;
      right: -80px;
      top: -150px;
      border-radius: 50%;
      border: 1px solid rgba(112, 255, 207, 0.22);
      box-shadow: inset 0 0 70px rgba(69, 188, 233, 0.12);
      pointer-events: none;
    }
    h1 { max-width: 760px; font-size: clamp(28px, 4vw, 46px); font-weight: 680; line-height: 1.08; margin: 0; letter-spacing: -0.025em; }
    h2 { font-size: 18px; font-weight: 600; margin: 0 0 16px; letter-spacing: 0; }
    h3 { font-size: 15px; font-weight: 600; margin: 0 0 10px; letter-spacing: 0; }
    p { margin: 0; color: var(--muted); line-height: 1.45; }
    .badge {
      border: 1px solid rgba(83, 232, 155, 0.34);
      background: linear-gradient(135deg, rgba(83, 232, 155, 0.17), rgba(17, 84, 91, 0.5));
      color: #8fffc5;
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 13px;
      font-weight: 550;
      white-space: nowrap;
      box-shadow: inset 0 1px 0 rgba(210, 255, 240, 0.16), 0 10px 28px rgba(0, 0, 0, 0.22);
    }
    .layout { display: grid; grid-template-columns: minmax(360px, 440px) 1fr; gap: 18px; align-items: start; }
    section {
      position: relative;
      background: linear-gradient(145deg, rgba(12, 57, 67, 0.96), rgba(5, 36, 46, 0.98));
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }
    section::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(150, 255, 218, 0.42), transparent);
      pointer-events: none;
    }
    .panel { padding: 20px; }
    label { display: block; font-size: 13px; font-weight: 560; margin: 14px 0 0; color: #c8eee7; }
    .mode-switch {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .mode-option {
      display: block;
      margin: 0;
      min-height: 92px;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 11px;
      background: linear-gradient(145deg, rgba(13, 60, 69, 0.9), rgba(6, 39, 48, 0.94));
      cursor: pointer;
      box-shadow: inset 0 1px 0 rgba(201, 255, 238, 0.05);
      min-width: 0;
      min-height: 64px;
      display: grid;
      place-items: center;
      text-align: center;
    }
    .mode-option.is-active {
      border-color: var(--green);
      background: linear-gradient(145deg, rgba(83, 232, 155, 0.2), rgba(7, 55, 57, 0.94));
      box-shadow: 0 0 0 3px rgba(83, 232, 155, 0.09), inset 0 1px 0 rgba(215, 255, 241, 0.14);
    }
    .mode-option input {
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      opacity: 0;
      pointer-events: none;
    }
    .mode-title {
      display: block;
      margin-bottom: 6px;
      color: #d9f9f2;
      font-size: 13px;
      font-weight: 650;
      overflow-wrap: anywhere;
    }
    .mode-copy {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      font-weight: 400;
      overflow-wrap: anywhere;
    }
    .experiment-form {
      display: none;
    }
    .experiment-form.is-visible {
      display: block;
    }
    .mode-option:has(input:checked) {
      border-color: var(--green);
      background: linear-gradient(145deg, rgba(83, 232, 155, 0.18), rgba(7, 55, 57, 0.92));
      box-shadow: 0 0 0 3px rgba(83, 232, 155, 0.1), inset 0 1px 0 rgba(215, 255, 241, 0.12);
    }
    .field-hint {
      display: none;
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 400;
      line-height: 1.35;
    }
    body.variant-generation .field-hint { display: block; }
    input, textarea {
      width: 100%;
      margin-top: 7px;
      padding: 11px 12px;
      border: 1px solid rgba(143, 219, 205, 0.22);
      border-radius: 10px;
      background: linear-gradient(180deg, rgba(3, 28, 36, 0.9), rgba(7, 42, 50, 0.92));
      color: var(--text);
      font: inherit;
      font-weight: 400;
      font-size: 14px;
      outline: none;
    }
    input::placeholder, textarea::placeholder { color: #668f8d; }
    input:focus, textarea:focus { border-color: var(--green); box-shadow: 0 0 0 3px rgba(83, 232, 155, 0.12), inset 0 1px 0 rgba(196, 255, 235, 0.08); }
    textarea { min-height: 92px; resize: vertical; }
    .row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .upload-row.single { grid-template-columns: 1fr; }
    body.variant-generation .challenger-upload { display: none; }
    .upload-field {
      display: grid;
      grid-template-rows: 18px auto auto;
      gap: 7px;
      align-items: start;
      color: #c8eee7;
      font-size: 13px;
      font-weight: 560;
    }
    .upload {
      position: relative;
      overflow: hidden;
      min-height: 184px;
      margin-top: 0;
      border: 1px dashed rgba(117, 232, 198, 0.34);
      border-radius: 12px;
      background: linear-gradient(145deg, rgba(8, 48, 57, 0.78), rgba(4, 31, 40, 0.9));
    }
    .upload input { display: none; }
    .upload-content {
      min-height: 184px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 8px;
      padding: 16px;
      text-align: center;
      color: var(--muted);
    }
    .upload-title { color: #d6f7f0; font-weight: 600; }
    .image-preview {
      display: block;
      width: 100%;
      min-width: 0;
      min-height: 0;
      padding: 0;
      border-radius: 11px 11px 0 0;
      overflow: hidden;
      background: transparent;
      box-shadow: none;
    }
    .image-preview:hover { transform: none; filter: brightness(1.06); box-shadow: none; }
    .upload img { width: 100%; height: 128px; object-fit: cover; border-bottom: 1px solid var(--line); display: none; }
    .upload.has-image img { display: block; }
    .upload.has-image .upload-content { min-height: 55px; padding: 10px 12px; text-align: left; }
    .upload-button {
      display: block;
      margin: 0;
      padding: 9px 12px;
      border: 1px solid rgba(83, 232, 155, 0.24);
      border-radius: 9px;
      background: rgba(83, 232, 155, 0.09);
      color: #9fffc9;
      text-align: center;
      cursor: pointer;
    }
    .upload-button:hover { background: rgba(83, 232, 155, 0.15); }
    .image-lightbox {
      width: min(94vw, 1400px);
      max-height: 92vh;
      padding: 46px 12px 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #031923;
      box-shadow: 0 30px 90px rgba(0, 0, 0, 0.72);
    }
    .image-lightbox::backdrop { background: rgba(0, 10, 15, 0.88); backdrop-filter: blur(8px); }
    .image-lightbox img { display: block; max-width: 100%; max-height: calc(92vh - 60px); margin: auto; object-fit: contain; border-radius: 10px; }
    .lightbox-close { position: absolute; top: 10px; right: 12px; min-width: 0; min-height: 30px; padding: 5px 10px; }
    .actions { display: flex; align-items: center; gap: 12px; margin-top: 18px; }
    button {
      border: 0;
      border-radius: 10px;
      background: linear-gradient(135deg, #63f2aa 0%, #2fc884 58%, #19a96e 100%);
      color: #03251d;
      padding: 12px 15px;
      min-width: 220px;
      min-height: 44px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
      white-space: normal;
      line-height: 1.2;
      overflow-wrap: anywhere;
      box-shadow: inset 0 1px 0 rgba(232, 255, 246, 0.62), 0 12px 30px rgba(20, 194, 121, 0.22);
      transition: transform 0.18s ease, filter 0.18s ease, box-shadow 0.18s ease;
    }
    button:hover { filter: brightness(1.08); transform: translateY(-1px); box-shadow: inset 0 1px 0 rgba(232, 255, 246, 0.72), 0 15px 36px rgba(20, 194, 121, 0.3); }
    button:disabled { opacity: 0.62; cursor: wait; }
    .status { color: var(--muted); font-size: 13px; line-height: 1.35; }
    .result { min-height: 680px; overflow: hidden; }
    .result-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 20px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(105deg, rgba(8, 43, 54, 0.98), rgba(11, 64, 65, 0.92));
    }
    .winner {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(83, 232, 155, 0.13);
      color: #8fffc5;
      border: 1px solid rgba(83, 232, 155, 0.25);
      font-weight: 450;
      white-space: nowrap;
    }
    .winner[hidden], .winner:empty { display: none; }
    .empty {
      display: grid;
      place-items: center;
      min-height: 560px;
      padding: 28px;
      text-align: center;
      color: var(--muted);
    }
    .empty-inner { width: min(460px, 100%); max-width: 460px; }
    .empty-visual {
      width: min(360px, 100%);
      height: 180px;
      margin: 0 auto 22px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(90deg, rgba(83, 232, 155, 0.25) 62%, transparent 62%),
        linear-gradient(90deg, rgba(69, 188, 233, 0.25) 38%, transparent 38%),
        linear-gradient(145deg, #0a3943, #05252f);
      background-size: 100% 42px, 100% 42px, auto;
      background-position: 0 30px, 0 92px, 0 0;
      background-repeat: no-repeat;
      position: relative;
    }
    .empty-visual::after {
      content: "";
      position: absolute;
      left: 22px;
      right: 22px;
      bottom: 28px;
      height: 18px;
      background: linear-gradient(90deg, var(--green) 54%, var(--blue) 54% 82%, var(--yellow) 82%);
      border-radius: 999px;
    }
    .running-report {
      place-items: stretch;
      align-content: start;
      text-align: left;
      color: var(--text);
    }
    .run-progress {
      display: grid;
      gap: 18px;
      width: 100%;
      max-width: 760px;
      margin: 0 auto;
    }
    .run-progress-top {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
    }
    .run-progress-copy {
      display: grid;
      gap: 6px;
    }
    .run-progress-copy h2 {
      margin: 0;
    }
    .run-progress-copy p,
    .run-progress-eta,
    .stage-count {
      color: var(--muted);
      font-size: 13px;
    }
    .run-progress-percent {
      min-width: 72px;
      text-align: right;
      font-size: 28px;
      line-height: 1;
      font-weight: 650;
      color: var(--green-dark);
    }
    .run-progress-track {
      position: relative;
      height: 8px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(1, 22, 29, 0.75);
    }
    .run-progress-fill {
      height: 100%;
      width: var(--progress-width, 2%);
      border-radius: inherit;
      background: linear-gradient(90deg, var(--green), var(--blue));
      transition: width 0.35s ease;
    }
    .run-progress-track::after {
      content: "";
      position: absolute;
      top: 0;
      bottom: 0;
      width: 96px;
      border-radius: inherit;
      background: linear-gradient(90deg, transparent, rgba(202, 255, 237, 0.52), transparent);
      animation: progress-sweep 1.35s ease-in-out infinite;
    }
    @keyframes progress-sweep {
      from { transform: translateX(-110px); }
      to { transform: translateX(760px); }
    }
    .run-progress.done .run-progress-track::after,
    .run-progress.failed .run-progress-track::after {
      display: none;
    }
    .run-stages {
      display: grid;
      gap: 10px;
    }
    .run-stage {
      display: grid;
      grid-template-columns: 20px 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: linear-gradient(145deg, rgba(10, 52, 61, 0.92), rgba(5, 34, 43, 0.95));
    }
    .stage-dot {
      width: 10px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: #527875;
      justify-self: center;
    }
    .stage-label {
      color: #c9eee7;
      font-size: 13px;
      font-weight: 560;
    }
    .run-stage.active .stage-dot {
      background: var(--green);
      box-shadow: 0 0 0 5px rgba(18, 161, 84, 0.12);
    }
    .run-stage.done .stage-dot {
      background: var(--blue);
    }
    .run-stage.failed .stage-dot {
      background: var(--red);
    }
    .run-stage.failed .stage-label,
    .run-stage.failed .stage-count {
      color: var(--red);
      font-weight: 600;
    }
    .report-body { padding: 20px; display: grid; gap: 18px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: linear-gradient(145deg, rgba(12, 57, 66, 0.86), rgba(5, 34, 43, 0.92));
      min-height: 92px;
    }
    .metric-value { font-size: 26px; font-weight: 650; margin-top: 4px; }
    .metric-label { color: var(--muted); font-size: 12px; font-weight: 560; }
    .viz { display: grid; grid-template-columns: 220px 1fr; gap: 18px; align-items: center; }
    .donut {
      width: 190px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: conic-gradient(var(--green) 0deg, var(--green) var(--control-deg), var(--blue) var(--control-deg), var(--blue) var(--challenger-deg), var(--yellow) var(--challenger-deg) 360deg);
      display: grid;
      place-items: center;
      margin: 0 auto;
      box-shadow: inset 0 0 30px rgba(2, 20, 27, 0.3), 0 16px 42px rgba(0, 8, 13, 0.34);
    }
    .donut-center {
      width: 116px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: var(--panel-deep);
      border: 1px solid var(--line);
    }
    .viz-summary { margin-bottom: 2px; }
    .viz-summary strong { font-weight: 600; }
    .bars { display: grid; gap: 12px; }
    .bar-row { display: grid; grid-template-columns: 120px 1fr 46px; gap: 10px; align-items: center; font-size: 13px; }
    .track { height: 12px; background: rgba(1, 20, 27, 0.76); border: 1px solid rgba(139, 224, 207, 0.1); border-radius: 999px; overflow: hidden; }
    .fill { height: 100%; border-radius: 999px; width: var(--w); }
    .fill.control { background: var(--green); }
    .fill.challenger { background: var(--blue); }
    .fill.none { background: var(--yellow); }
    .split { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .block {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: linear-gradient(145deg, rgba(12, 57, 66, 0.82), rgba(5, 34, 43, 0.9));
    }
    .hypothesis-list { display: grid; gap: 10px; margin-bottom: 14px; }
    .hypothesis-option {
      display: grid;
      grid-template-columns: 18px 1fr;
      gap: 8px 10px;
      align-items: start;
      margin: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: linear-gradient(145deg, rgba(11, 54, 63, 0.86), rgba(5, 35, 44, 0.94));
      cursor: pointer;
    }
    .hypothesis-option input { margin: 3px 0 0; width: auto; }
    .hypothesis-option strong,
    .hypothesis-option span,
    .hypothesis-option em { grid-column: 2; }
    .hypothesis-option strong { color: #d3f5ee; font-size: 14px; }
    .hypothesis-option span { color: var(--muted); font-size: 13px; line-height: 1.4; }
    .hypothesis-option em { color: #72d8ff; font-size: 12px; font-style: normal; }
    .generated-variant {
      width: 100%;
      max-height: 520px;
      object-fit: contain;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #041f29;
    }
    .variant-approval {
      padding: 10px;
    }
    .variant-approval .generated-variant {
      max-height: none;
      min-height: 640px;
      height: min(76vh, 980px);
      object-fit: contain;
      object-position: top center;
    }
    ul { margin: 0; padding-left: 18px; color: #c9eee7; line-height: 1.5; }
    li + li { margin-top: 7px; }
    .agents {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      overflow: hidden;
    }
    th, td { padding: 10px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; background: rgba(3, 29, 37, 0.72); }
    tr:last-child td { border-bottom: 0; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      font-weight: 600;
      font-size: 12px;
      white-space: nowrap;
    }
    .pill.control { color: #8fffc5; background: rgba(83, 232, 155, 0.14); }
    .pill.challenger { color: #86ddff; background: rgba(69, 188, 233, 0.15); }
    .pill.none { color: #ffd893; background: rgba(255, 199, 107, 0.14); }
    .pill.bad { color: #ff9da5; background: rgba(255, 111, 121, 0.14); }
    .error { color: var(--red); font-weight: 600; }
    .logs-panel {
      margin-top: 18px;
      padding: 18px;
      display: grid;
      gap: 12px;
    }
    .logs-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }
    .logs-head button {
      min-width: 0;
      min-height: 36px;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 560;
      background: rgba(83, 232, 155, 0.1);
      color: #8fffc5;
      border: 1px solid rgba(83, 232, 155, 0.26);
      box-shadow: inset 0 1px 0 rgba(210, 255, 240, 0.08);
    }
    .logs-head button:hover { background: rgba(83, 232, 155, 0.17); }
    .log-output {
      margin: 0;
      max-height: 320px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #02141b;
      color: #bcebdc;
      padding: 12px;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      white-space: pre-wrap;
    }
    @media (max-width: 980px) {
      .layout, .viz, .split { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      header { align-items: flex-start; flex-direction: column; }
    }
    @media (max-width: 640px) {
      main { padding: 18px 12px 28px; }
      .mode-switch { grid-template-columns: 1fr; }
      .row, .metrics { grid-template-columns: 1fr; }
      .actions { align-items: stretch; flex-direction: column; }
      button { width: 100%; }
      .result-header { flex-direction: column; }
      .agents { display: block; overflow-x: auto; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>SimAB: проверка продуктовых гипотез</h1>
      </div>
    </header>

    <div class="layout">
      <section class="panel">
        <h2>Настройка эксперимента</h2>
        <div class="mode-switch" aria-label="Режим эксперимента">
          <button class="mode-option" type="button" data-mode="ab_test">
            <span class="mode-title">A/B тестирование</span>
          </button>
          <button class="mode-option" type="button" data-mode="variant_generation">
            <span class="mode-title">Продуктовая команда</span>
          </button>
        </div>
        <div class="experiment-form" id="experimentForm">
          <label>Название
            <input id="name" value="Демо" />
          </label>
          <label>Цель эксперимента
            <textarea id="goal">Если в кредитном калькуляторе по умолчанию показать более привлекательные сумму и срок кредита, то больше пользователей нажмут «Продолжить».</textarea>
            <span class="field-hint">Можно оставить пустым: команда LLM-агентов сформулирует гипотезы по контрольному макету.</span>
          </label>
          <label>Целевая аудитория
            <textarea id="audience">Российские розничные клиенты, которые онлайн изучают условия потребительского кредита и оценивают платёж, сумму и срок перед оформлением заявки.</textarea>
            <span class="field-hint">Можно оставить пустым, если аудиторию нужно вывести из контекста интерфейса.</span>
          </label>
          <div class="row upload-row" id="uploadRow">
            <div class="upload-field">Контроль
              <div class="upload has-image" id="controlDrop">
                <button class="image-preview" type="button" data-preview="controlPreview" aria-label="Открыть контрольное изображение">
                  <img id="controlPreview" src="/static/consumer_loan_300k_5y.png" alt="Контрольный макет" />
                </button>
                <div class="upload-content">
                  <span class="upload-title" id="controlName">Контроль: 300 000 ₽, 5 лет</span>
                </div>
              </div>
              <label class="upload-button" for="control">Загрузить другое изображение</label>
              <input id="control" type="file" accept="image/*" hidden />
            </div>
            <div class="upload-field challenger-upload">Тестовый вариант
              <div class="upload has-image" id="challengerDrop">
                <button class="image-preview" type="button" data-preview="challengerPreview" aria-label="Открыть тестовое изображение">
                  <img id="challengerPreview" src="/static/consumer_loan_100k_3y.png" alt="Тестовый макет" />
                </button>
                <div class="upload-content">
                  <span class="upload-title" id="challengerName">Тест: 100 000 ₽, 3 года</span>
                </div>
              </div>
              <label class="upload-button" for="challenger">Загрузить другое изображение</label>
              <input id="challenger" type="file" accept="image/*" hidden />
            </div>
          </div>
          <label>Количество персон
            <input id="personas" type="number" min="1" max="500" value="24" />
          </label>
          <div class="actions">
            <button id="run">Запустить симуляцию</button>
            <div class="status" id="status">Выберите режим эксперимента.</div>
          </div>
        </div>
      </section>

      <section class="result">
        <div class="result-header">
          <div>
            <h2>Отчет по эксперименту</h2>
            <p id="subtitle">Выберите сценарий слева, чтобы открыть настройки запуска.</p>
          </div>
          <div class="winner" id="winner" hidden></div>
        </div>
        <div id="report" class="empty">
          <div class="empty-inner">
            <div class="empty-visual"></div>
          </div>
        </div>
      </section>
    </div>

    <section class="logs-panel">
      <div class="logs-head">
        <div>
          <h2>Журнал событий</h2>
        </div>
        <button id="refreshLogs" type="button">Обновить</button>
      </div>
      <pre id="logs" class="log-output">Лог пока пуст.</pre>
    </section>
  </main>
  <dialog class="image-lightbox" id="imageLightbox">
    <button class="lightbox-close" id="closeLightbox" type="button">Закрыть</button>
    <img id="lightboxImage" alt="Увеличенный макет" />
  </dialog>
  <script>
    const reportNode = document.getElementById("report");
    const statusNode = document.getElementById("status");
    const winnerNode = document.getElementById("winner");
    const subtitleNode = document.getElementById("subtitle");
    const logsNode = document.getElementById("logs");
    let defaultControlFile = null;
    let defaultChallengerFile = null;
    let selectedControlFile = null;
    let selectedChallengerFile = null;
    let defaultFilesPromise = null;
    const demoFiles = {};
    let logPoller = null;
    let progressState = null;
    let sessionLogMarker = null;
    let lastGenerationResult = null;
    let activeMode = "ab_test";

    const modePresets = {
      ab_test: {
        name: "Демо",
        goal: "Если в кредитном калькуляторе по умолчанию показать более привлекательные сумму и срок кредита, то больше пользователей нажмут «Продолжить».",
        audience: "Российские розничные клиенты, которые онлайн изучают условия потребительского кредита и оценивают платёж, сумму и срок перед оформлением заявки.",
        controlSrc: "/static/consumer_loan_300k_5y.png",
        controlName: "Контроль: 300 000 ₽, 5 лет",
        challengerSrc: "/static/consumer_loan_100k_3y.png",
        challengerName: "Тест: 100 000 ₽, 3 года"
      },
      variant_generation: {
        name: "Демо",
        goal: "Если поменять приз с машины на квартиру, то мы увеличим конверсию в перевод зарплаты.",
        audience: "",
        controlSrc: "/static/product_team_salary_car.png",
        controlName: "Контроль: розыгрыш автомобиля",
        challengerSrc: null,
        challengerName: ""
      }
    };

    const labels = {
      control: "Базовый вариант",
      challenger: "Тестовый вариант",
      none: "Нет выбора",
      inconclusive: "Нет явного победителя",
      low: "низкая",
      medium: "средняя",
      high: "высокая",
      pass: "без критичных проблем",
      minor_issues: "есть замечания",
      fail: "критичная проблема"
    };

    function setupPreview(inputId, boxId, imageId, nameId) {
      const input = document.getElementById(inputId);
      const box = document.getElementById(boxId);
      const image = document.getElementById(imageId);
      const name = document.getElementById(nameId);
      input.addEventListener("change", () => {
        const file = input.files[0];
        if (!file) return;
        if (inputId === "control") {
          selectedControlFile = file;
        } else {
          selectedChallengerFile = file;
        }
        image.src = URL.createObjectURL(file);
        name.textContent = file.name;
        box.classList.add("has-image");
      });
    }

    async function loadDefaultFile(url, filename) {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Не удалось загрузить пример ${filename}`);
      }
      const blob = await response.blob();
      return new File([blob], filename, { type: blob.type || "image/png" });
    }

    function setStatus(text, isError = false) {
      statusNode.textContent = text;
      statusNode.className = isError ? "status error" : "status";
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function parseResponse(response) {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Запрос завершился с ошибкой");
      }
      return payload;
    }

    function percent(value, total) {
      if (!total) return 0;
      return Math.round((value / total) * 100);
    }

    function renderList(items, emptyText) {
      if (!items || items.length === 0) return `<p>${emptyText}</p>`;
      return `<ul>${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
    }

    function renderConclusionText(value, emptyText) {
      const text = String(value || "").trim();
      return text ? `<p>${escapeHtml(text)}</p>` : `<p>${emptyText}</p>`;
    }

    async function logSnapshot() {
      const payload = await fetch("/logs?limit=1000").then(parseResponse).catch(() => ({lines: []}));
      return payload.lines || [];
    }

    function linesAfterMarker(lines, marker) {
      if (!Array.isArray(lines) || marker === null) return [];
      let markerIndex = -1;
      for (let index = lines.length - 1; index >= 0; index -= 1) {
        if (lines[index] === marker) {
          markerIndex = index;
          break;
        }
      }
      return markerIndex >= 0 ? lines.slice(markerIndex + 1) : lines;
    }

    function currentSessionLines(lines) {
      if (!Array.isArray(lines)) return [];
      if (sessionLogMarker === null) return [];
      const recentLines = linesAfterMarker(lines, sessionLogMarker);
      if (!progressState || !progressState.experimentId) return recentLines;
      const experimentNeedle = `experiment_id=${progressState.experimentId}`;
      return recentLines.filter(line => {
        return (
          line.includes(experimentNeedle) ||
          line.includes("Selecting LLM client provider=") ||
          line.includes("Using RealLLMClient") ||
          line.includes("Using MockLLMClient") ||
          line.includes("Initialized RealLLMClient") ||
          line.includes("Calling real LLM") ||
          line.includes("Calling real VLM") ||
          line.includes("LLM request failed") ||
          line.includes("LLM pipeline step")
        );
      });
    }

    function currentMode() {
      return activeMode;
    }

    function isVariantGenerationMode() {
      return currentMode() === "variant_generation";
    }

    function applyModePreset(mode) {
      const preset = modePresets[mode];
      if (!preset) return;
      document.getElementById("name").value = preset.name;
      document.getElementById("goal").value = preset.goal;
      document.getElementById("audience").value = preset.audience;
      document.getElementById("controlPreview").src = preset.controlSrc;
      document.getElementById("controlName").textContent = preset.controlName;
      defaultControlFile = demoFiles[mode]?.control || null;
      selectedControlFile = null;
      document.getElementById("control").value = "";
      if (preset.challengerSrc) {
        document.getElementById("challengerPreview").src = preset.challengerSrc;
        document.getElementById("challengerName").textContent = preset.challengerName;
      }
      defaultChallengerFile = demoFiles[mode]?.challenger || null;
      selectedChallengerFile = null;
      document.getElementById("challenger").value = "";
    }

    function syncModeUi() {
      const mode = currentMode();
      const hasMode = Boolean(mode);
      const generationMode = isVariantGenerationMode();
      document.getElementById("experimentForm").classList.toggle("is-visible", hasMode);
      document.querySelectorAll("[data-mode]").forEach(button => {
        const isActive = button.dataset.mode === mode;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      document.body.classList.toggle("variant-generation", generationMode);
      document.getElementById("uploadRow").classList.toggle("single", generationMode);
      document.getElementById("run").textContent = generationMode
        ? "Сгенерировать гипотезы"
        : "Запустить симуляцию";
      if (!hasMode) {
        setStatus("Выберите режим эксперимента.");
        subtitleNode.textContent = "Выберите сценарий слева, чтобы открыть настройки запуска.";
      } else if (generationMode) {
        applyModePreset(mode);
        setStatus("Режим генерации: загрузите контрольный макет. Цель и аудиторию можно оставить пустыми.");
        subtitleNode.textContent = "Команда LLM-агентов подготовит top-гипотезы, затем image-модель применит выбранное изменение к контролю.";
      } else {
        applyModePreset(mode);
        setStatus("Настройки A/B-тестирования готовы к запуску.");
        subtitleNode.textContent = "Настройте эксперимент и запустите симуляцию.";
      }
    }

    function renderRunningProgress(totalPersonas, baselineMarker, mode = "ab_test") {
      const generationMode = mode === "variant_generation";
      progressState = {
        baselineMarker,
        experimentId: null,
        startedAt: Date.now(),
        totalPersonas,
        totalDecisions: generationMode ? 0 : totalPersonas * 2,
        mode,
        percent: 0,
        active: true
      };
      reportNode.className = "empty running-report";
      reportNode.innerHTML = `
        <div class="run-progress" id="runProgress">
          <div class="run-progress-top">
            <div class="run-progress-copy">
              <h2>${generationMode ? "Готовим агентный запуск" : "Симуляция выполняется"}</h2>
              <p id="progressStageText">${generationMode ? "Создаем эксперимент и фиксируем заявку для агентной системы." : "Создаем эксперимент и готовим изображения."}</p>
              <div class="run-progress-eta" id="progressEta">Оцениваем время</div>
            </div>
            <div class="run-progress-percent" id="progressPercent">0%</div>
          </div>
          <div class="run-progress-track" aria-hidden="true">
            <div class="run-progress-fill"></div>
          </div>
          <div class="run-stages">
            <div class="run-stage active" data-stage="setup"><span class="stage-dot"></span><span class="stage-label">Создание эксперимента</span><span class="stage-count">в процессе</span></div>
            <div class="run-stage" data-stage="upload"><span class="stage-dot"></span><span class="stage-label">Загрузка изображений</span><span class="stage-count">ожидает</span></div>
            ${generationMode ? `
              <div class="run-stage" data-stage="agents"><span class="stage-dot"></span><span class="stage-label">Анализ LLM-агентов</span><span class="stage-count">ожидает</span></div>
              <div class="run-stage" data-stage="report"><span class="stage-dot"></span><span class="stage-label">Готовность к следующему шагу</span><span class="stage-count">ожидает</span></div>
            ` : `
              <div class="run-stage" data-stage="personas"><span class="stage-dot"></span><span class="stage-label">Генерация персон</span><span class="stage-count">0 / ${totalPersonas}</span></div>
              <div class="run-stage" data-stage="visual"><span class="stage-dot"></span><span class="stage-label">Проверка визуала</span><span class="stage-count">ожидает</span></div>
              <div class="run-stage" data-stage="simulation"><span class="stage-dot"></span><span class="stage-label">Голосование персон</span><span class="stage-count">0 / ${totalPersonas * 2}</span></div>
              <div class="run-stage" data-stage="report"><span class="stage-dot"></span><span class="stage-label">Сборка отчета</span><span class="stage-count">ожидает</span></div>
            `}
          </div>
        </div>
      `;
      updateProgressPercent(2);
    }

    function setProgressStage(stageName, state, countText) {
      const stage = reportNode.querySelector(`[data-stage="${stageName}"]`);
      if (!stage) return;
      stage.className = `run-stage ${state || ""}`.trim();
      if (countText !== undefined) {
        stage.querySelector(".stage-count").textContent = countText;
      }
    }

    function setProgressText(text) {
      const node = document.getElementById("progressStageText");
      if (node) node.textContent = text;
    }

    function updateProgressPercent(percent) {
      if (!progressState) return;
      const safePercent = Math.max(progressState.percent || 0, Math.min(100, Math.round(percent)));
      progressState.percent = safePercent;
      const progress = document.getElementById("runProgress");
      const fill = reportNode.querySelector(".run-progress-fill");
      const percentNode = document.getElementById("progressPercent");
      const etaNode = document.getElementById("progressEta");
      if (fill) fill.style.setProperty("--progress-width", `${Math.max(2, safePercent)}%`);
      if (percentNode) percentNode.textContent = `${safePercent}%`;
      if (!etaNode) return;
      if (safePercent >= 100) {
        etaNode.textContent = "Готово";
        if (progress) progress.classList.add("done");
        return;
      }
      if (safePercent < 8) {
        etaNode.textContent = "Оцениваем время";
        return;
      }
      const elapsedSeconds = Math.max(1, Math.round((Date.now() - progressState.startedAt) / 1000));
      const remainingSeconds = Math.max(1, Math.round((elapsedSeconds * (100 - safePercent)) / safePercent));
      etaNode.textContent = `Осталось: ~${formatDuration(remainingSeconds)}`;
    }

    function formatDuration(seconds) {
      if (seconds < 60) return `${seconds} с`;
      const minutes = Math.floor(seconds / 60);
      const rest = seconds % 60;
      return rest ? `${minutes} мин ${rest} с` : `${minutes} мин`;
    }

    function updateProgressFromLogs(lines) {
      if (!progressState || !progressState.active) return;
      const recentLines = linesAfterMarker(lines, progressState.baselineMarker);
      const scoped = progressState.experimentId
        ? recentLines.filter(line => line.includes(`experiment_id=${progressState.experimentId}`))
        : recentLines;
      if (progressState.mode === "variant_generation") {
        const agentPipelineStarted = scoped.some(line => line.includes("Variant generation requested"));
        const agentPipelineDone = scoped.some(line => line.includes("Variant generation completed"));
        if (progressState.experimentId) setProgressStage("setup", "done", "готово");
        setProgressStage("agents", agentPipelineDone ? "done" : agentPipelineStarted ? "active" : "", agentPipelineDone ? "готово" : agentPipelineStarted ? "в процессе" : "ожидает");
        setProgressStage("report", agentPipelineDone ? "done" : "", agentPipelineDone ? "готово" : "ожидает");
        setProgressText(agentPipelineDone ? "Гипотезы команды агентов готовы." : "LLM-агенты формируют top-гипотезы.");
        updateProgressPercent(agentPipelineDone ? 100 : agentPipelineStarted ? 72 : 35);
        return;
      }
      const generatedPersonas = Math.min(
        progressState.totalPersonas,
        scoped.filter(line => line.includes("Generated persona experiment_id=")).length
      );
      const decisions = Math.min(
        progressState.totalDecisions,
        scoped.filter(line => line.includes("Persona decision experiment_id=")).length
      );
      const visualDone = scoped.some(line => line.includes("Visual QA experiment_id=")) || decisions > 0;
      const reportStarted = scoped.some(line => line.includes("Report generation started experiment_id="));
      const reportDone = scoped.some(line => line.includes("Report generation finished experiment_id="));
      const runDone = scoped.some(line => line.includes("Run completed experiment_id="));

      if (progressState.experimentId) setProgressStage("setup", "done", "готово");
      setProgressStage(
        "personas",
        generatedPersonas >= progressState.totalPersonas ? "done" : generatedPersonas > 0 ? "active" : "",
        `${generatedPersonas} / ${progressState.totalPersonas}`
      );
      setProgressStage("visual", visualDone ? "done" : generatedPersonas ? "active" : "", visualDone ? "готово" : "ожидает");
      setProgressStage(
        "simulation",
        decisions >= progressState.totalDecisions ? "done" : decisions > 0 ? "active" : "",
        `${decisions} / ${progressState.totalDecisions}`
      );
      setProgressStage(
        "report",
        runDone || reportDone ? "done" : reportStarted ? "active" : "",
        runDone || reportDone ? "готово" : reportStarted ? "в процессе" : "ожидает"
      );

      const personaProgress = progressState.totalPersonas ? generatedPersonas / progressState.totalPersonas : 0;
      const decisionProgress = progressState.totalDecisions ? decisions / progressState.totalDecisions : 0;
      let percent = 15 + personaProgress * 25 + (visualDone ? 10 : 0) + decisionProgress * 40;
      if (reportStarted) percent = Math.max(percent, 92);
      if (reportDone || runDone) percent = 100;
      updateProgressPercent(percent);

      if (reportStarted) setProgressText("Собираем выводы и рекомендации.");
      else if (decisions > 0) setProgressText("Персоны сравнивают варианты в двух порядках.");
      else if (visualDone) setProgressText("Готовим парные сравнения для персон.");
      else if (generatedPersonas > 0) setProgressText("Генерируем синтетические персоны.");
    }

    function finishProgress() {
      if (!progressState) return;
      progressState.active = false;
      setProgressStage("setup", "done", "готово");
      setProgressStage("upload", "done", "готово");
      if (progressState.mode === "variant_generation") {
        setProgressStage("agents", "done", "готово");
        setProgressStage("report", "done", "готово");
        setProgressText("Гипотезы команды агентов готовы.");
        updateProgressPercent(100);
        return;
      }
      setProgressStage("personas", "done", `${progressState.totalPersonas} / ${progressState.totalPersonas}`);
      setProgressStage("visual", "done", "готово");
      setProgressStage("simulation", "done", `${progressState.totalDecisions} / ${progressState.totalDecisions}`);
      setProgressStage("report", "done", "готово");
      setProgressText("Отчет готов.");
      updateProgressPercent(100);
    }

    function failProgress() {
      if (!progressState) return;
      progressState.active = false;
      const progress = document.getElementById("runProgress");
      const etaNode = document.getElementById("progressEta");
      if (progress) progress.classList.add("failed");
      if (etaNode) etaNode.textContent = "Остановлено из-за ошибки";
      const activeStage = reportNode.querySelector(".run-stage.active") || reportNode.querySelector(".run-stage:not(.done)");
      if (activeStage) {
        activeStage.className = "run-stage failed";
        activeStage.querySelector(".stage-count").textContent = "ошибка";
      }
    }

    async function refreshLogs() {
      try {
        const payload = await fetch("/logs?limit=1000").then(parseResponse);
        const visibleLines = currentSessionLines(payload.lines || []);
        logsNode.textContent = visibleLines.length
          ? visibleLines.join("\\n")
          : "Лог пока пуст.";
        updateProgressFromLogs(payload.lines || []);
      } catch (error) {
        logsNode.textContent = `Не удалось загрузить журнал: ${error.message || String(error)}`;
      }
    }

    function startLogPolling() {
      refreshLogs();
      if (logPoller) clearInterval(logPoller);
      logPoller = setInterval(refreshLogs, 1800);
    }

    function stopLogPolling() {
      if (!logPoller) return;
      clearInterval(logPoller);
      logPoller = null;
      refreshLogs();
    }

    function renderReport(report) {
      const stableTotal = report.control_votes + report.challenger_votes + report.none_votes;
      const personaTotal = (report.stable_personas || 0) + (report.unstable_personas || 0);
      const controlPct = percent(report.control_votes, stableTotal);
      const challengerPct = percent(report.challenger_votes, stableTotal);
      const nonePct = percent(report.none_votes, stableTotal);
      const unstablePct = Math.round((report.unstable_rate || 0) * 100);
      const controlDeg = stableTotal ? (report.control_votes / stableTotal) * 360 : 0;
      const challengerDeg = stableTotal ? controlDeg + (report.challenger_votes / stableTotal) * 360 : 0;
      const confidence = Math.round((report.confidence_score || 0) * 100);
      const winnerLabel = labels[report.winner] || report.winner;

      winnerNode.hidden = false;
      winnerNode.textContent = `Победитель: ${winnerLabel}`;
      subtitleNode.textContent = `${personaTotal} персон: результат считается только по стабильным`;

      const personaPairs = new Map();
      for (const agent of report.agent_results || []) {
        if (!personaPairs.has(agent.persona_id)) {
          personaPairs.set(agent.persona_id, []);
        }
        personaPairs.get(agent.persona_id).push(agent);
      }
      const stablePersonaRows = Array.from(personaPairs.entries())
        .map(([personaId, results]) => {
          if (results.length < 2) return null;
          const firstChoice = results[0].mapped_verdict;
          const isStable = results.every(result => result.mapped_verdict === firstChoice);
          if (!isStable) return null;
          const hasVisualDefect = results.some(result => result.critical_visual_defect);
          const confidenceValues = [...new Set(results.map(result => result.confidence))];
          return {
            personaId,
            choice: firstChoice,
            confidence: confidenceValues.length === 1 ? confidenceValues[0] : "mixed",
            hasVisualDefect,
            rationale: results[0].normalized_rationale || results[0].rationale
          };
        })
        .filter(Boolean);

      const agentRows = stablePersonaRows.slice(0, 8).map((persona, index) => {
        const mapped = persona.choice;
        const mappedClass = mapped === "control" ? "control" : mapped === "challenger" ? "challenger" : "none";
        const visualState = persona.hasVisualDefect ? `<span class="pill bad">визуальный дефект</span>` : "без критичных проблем";
        const confidenceLabel = persona.confidence === "mixed" ? "смешанная" : labels[persona.confidence] || persona.confidence;
        return `
          <tr>
            <td>${index + 1}</td>
            <td>${persona.personaId}</td>
            <td><span class="pill ${mappedClass}">${labels[mapped] || mapped}</span></td>
            <td>${confidenceLabel}</td>
            <td>${visualState}</td>
            <td>${escapeHtml(persona.rationale)}</td>
          </tr>
        `;
      }).join("");

      reportNode.className = "report-body";
      reportNode.innerHTML = `
        <div class="metrics">
          <div class="metric"><div class="metric-label">Всего персон</div><div class="metric-value">${personaTotal}</div></div>
          <div class="metric"><div class="metric-label">Базовый вариант</div><div class="metric-value">${report.control_votes}</div></div>
          <div class="metric"><div class="metric-label">Тестовый вариант</div><div class="metric-value">${report.challenger_votes}</div></div>
          <div class="metric"><div class="metric-label">Нестабильные</div><div class="metric-value">${unstablePct}%</div></div>
        </div>

        <div class="block viz" style="--control-deg:${controlDeg}deg; --challenger-deg:${challengerDeg}deg;">
          <div class="donut"><div class="donut-center"></div></div>
          <div class="bars">
            <p class="viz-summary">Победитель: <strong>${winnerLabel}</strong></p>
            <div class="bar-row"><strong>Базовый</strong><div class="track"><div class="fill control" style="--w:${controlPct}%"></div></div><span>${controlPct}%</span></div>
            <div class="bar-row"><strong>Тестовый</strong><div class="track"><div class="fill challenger" style="--w:${challengerPct}%"></div></div><span>${challengerPct}%</span></div>
            <div class="bar-row"><strong>Нет выбора</strong><div class="track"><div class="fill none" style="--w:${nonePct}%"></div></div><span>${nonePct}%</span></div>
            <p class="viz-summary">Исключено нестабильных персон: <strong>${report.unstable_personas || 0} из ${personaTotal}</strong></p>
          </div>
        </div>

        <div class="split">
          <div class="block">
            <h3>Выводы по тексту</h3>
            ${renderList(report.text_findings, "Отдельных выводов по содержанию нет.")}
          </div>
          <div class="block">
            <h3>Выводы по визуалу</h3>
            ${renderList(report.visual_findings, "Отдельных выводов по визуалу нет.")}
          </div>
        </div>

        <div class="block">
          <h3>Совместный вывод</h3>
          ${renderConclusionText(report.combined_conclusion, "Совместный вывод не сформирован.")}
        </div>

        <div class="split">
          <div class="block">
            <h3>Рекомендации</h3>
            ${renderList(report.recommendations, "Рекомендации не сформированы.")}
          </div>
          <div class="block">
            <h3>Визуальное качество</h3>
            <ul>
              <li>Базовый вариант: ${Math.round((report.control_visual_fail_rate || 0) * 100)}% критичных проблем</li>
              <li>Тестовый вариант: ${Math.round((report.challenger_visual_fail_rate || 0) * 100)}% критичных проблем</li>
              <li>${escapeHtml(report.limitations)}</li>
            </ul>
          </div>
        </div>

        <div class="block">
          <h3>Голоса стабильных персон</h3>
          <table class="agents">
            <thead>
              <tr><th>#</th><th>Persona ID</th><th>Выбор</th><th>Уверенность</th><th>QA</th><th>Причина</th></tr>
            </thead>
            <tbody>${agentRows || `<tr><td colspan="6">Нет стабильных персон для отображения.</td></tr>`}</tbody>
          </table>
        </div>
      `;
    }

    function renderGenerationResult(result) {
      lastGenerationResult = result;
      const agentResponse = result.agent_response || {};
      const hypotheses = agentResponse.hypotheses || [];
      winnerNode.hidden = false;
      winnerNode.textContent = "Выберите гипотезу";
      subtitleNode.textContent = "Агенты сформировали top-3 гипотезы. Выберите одну для генерации тестового макета.";
      const hypothesisCards = hypotheses.slice(0, 3).map((item, index) => `
        <label class="hypothesis-option">
          <input type="radio" name="selectedHypothesis" value="${index}" ${index === 0 ? "checked" : ""} />
          <strong>${escapeHtml(item.title || `Гипотеза ${index + 1}`)}</strong>
          <span>${escapeHtml(item.hypothesis || item.rationale || "")}</span>
          ${item.proposed_change ? `<em>${escapeHtml(item.proposed_change)}</em>` : ""}
        </label>
      `).join("");
      reportNode.className = "report-body";
      reportNode.innerHTML = `
        <div class="block">
          <h2>Выбор гипотезы</h2>
          <p>${escapeHtml(result.message || "LLM-агенты обработали контрольный макет.")}</p>
        </div>
        <div class="block">
          <h3>Top-3 гипотезы</h3>
          <div class="hypothesis-list">${hypothesisCards || "LLM-агенты пока не вернули гипотезы."}</div>
          <button id="generateVariantImage" class="secondary" type="button" ${hypotheses.length ? "" : "disabled"}>Сгенерировать тестовый вариант</button>
        </div>
      `;
      const generateButton = document.getElementById("generateVariantImage");
      if (generateButton) {
        generateButton.addEventListener("click", () => {
          const selected = document.querySelector('input[name="selectedHypothesis"]:checked');
          const selectedIndex = Number(selected ? selected.value : 0);
          generateImageForHypothesis(result, hypotheses[selectedIndex] || hypotheses[0]);
        });
      }
    }

    async function generateImageForHypothesis(result, selectedHypothesis) {
      if (!selectedHypothesis) {
        setStatus("Выберите гипотезу.", true);
        return;
      }
      setStatus("Генерируем тестовый вариант по контрольному макету...");
      winnerNode.hidden = false;
      winnerNode.textContent = "Генерируем вариант";
      subtitleNode.textContent = "Модель генерации изображений применяет только выбранную гипотезу.";
      try {
        const variant = await fetch(`/experiments/${result.experiment_id}/generate-variant-image`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            selected_hypothesis: selectedHypothesis,
            generation_prompt: selectedHypothesis.generation_prompt || null
          })
        }).then(parseResponse);
        renderVariantApproval(variant);
        setStatus("Тестовый макет готов к согласованию.");
      } catch (error) {
        setStatus(error.message || String(error), true);
      }
    }

    function renderVariantApproval(result) {
      const agentResponse = result.agent_response || {};
      winnerNode.hidden = false;
      winnerNode.textContent = "Макет готов";
      subtitleNode.textContent = "Проверьте тестовый вариант и выберите дальнейшее действие.";
      reportNode.className = "report-body";
      reportNode.innerHTML = `
        <div class="block variant-approval">
          <h2>${escapeHtml(agentResponse.selected_hypothesis_title || "Тестовый вариант")}</h2>
          ${result.challenger_image_url ? `<img class="generated-variant" src="${result.challenger_image_url}" alt="Сгенерированный тестовый вариант" />` : "<p>Превью недоступно.</p>"}
        </div>
        <div class="block actions">
          <button id="sendGeneratedToAb" type="button">Отправить на A/B-тест</button>
          <button id="rejectGeneratedVariant" class="secondary" type="button">Отказаться</button>
        </div>
      `;
      document.getElementById("sendGeneratedToAb").addEventListener("click", () => runApprovedGeneratedAb(result.experiment_id));
      document.getElementById("rejectGeneratedVariant").addEventListener("click", () => rejectGeneratedVariant());
    }

    function rejectGeneratedVariant() {
      setStatus("Сгенерированный макет отклонен.");
      winnerNode.hidden = false;
      winnerNode.textContent = "Макет отклонен";
      subtitleNode.textContent = "Можно выбрать другую гипотезу или изменить входные данные.";
      if (lastGenerationResult) {
        renderGenerationResult(lastGenerationResult);
      }
    }

    async function runApprovedGeneratedAb(experimentId) {
      const totalPersonas = Number(document.getElementById("personas").value);
      const baselineLines = await logSnapshot();
      const baselineMarker = baselineLines.length ? baselineLines[baselineLines.length - 1] : "";
      sessionLogMarker = baselineMarker;
      logsNode.textContent = "Лог пока пуст.";
      renderRunningProgress(totalPersonas, baselineMarker, "ab_test");
      progressState.experimentId = experimentId;
      setProgressStage("setup", "done", "готово");
      setProgressStage("upload", "done", "готово");
      setProgressStage("personas", "active", `0 / ${totalPersonas}`);
      setProgressText("Запускаем synthetic A/B для согласованного макета.");
      updateProgressPercent(15);
      startLogPolling();
      setStatus("Отправляем сгенерированный вариант в synthetic A/B...");
      winnerNode.hidden = false;
      winnerNode.textContent = "Synthetic A/B...";
      subtitleNode.textContent = "Запускаем стандартный блок оценки готового теста.";
      try {
        await fetch(`/experiments/${experimentId}/approve-generated-variant`, {
          method: "POST"
        }).then(parseResponse);
        const report = await fetch(`/experiments/${experimentId}/run`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            num_personas: totalPersonas,
            batch_size: 10
          })
        }).then(parseResponse);
        finishProgress();
        renderReport(report);
        setStatus("A/B-отчет готов.");
      } catch (error) {
        failProgress();
        setStatus(error.message || String(error), true);
      } finally {
        stopLogPolling();
      }
    }

    setupPreview("control", "controlDrop", "controlPreview", "controlName");
    setupPreview("challenger", "challengerDrop", "challengerPreview", "challengerName");
    const lightbox = document.getElementById("imageLightbox");
    const lightboxImage = document.getElementById("lightboxImage");
    document.querySelectorAll(".image-preview").forEach(button => {
      button.addEventListener("click", () => {
        const preview = document.getElementById(button.dataset.preview);
        lightboxImage.src = preview.src;
        lightboxImage.alt = preview.alt;
        lightbox.showModal();
      });
    });
    document.getElementById("closeLightbox").addEventListener("click", () => lightbox.close());
    lightbox.addEventListener("click", event => {
      if (event.target === lightbox) lightbox.close();
    });
    document.getElementById("refreshLogs").addEventListener("click", refreshLogs);
    document.querySelectorAll("[data-mode]").forEach(button => {
      button.addEventListener("click", () => {
        activeMode = button.dataset.mode;
        syncModeUi();
      });
    });
    syncModeUi();

    defaultFilesPromise = Promise.all([
      loadDefaultFile("/static/consumer_loan_300k_5y.png", "consumer_loan_300k_5y.png"),
      loadDefaultFile("/static/consumer_loan_100k_3y.png", "consumer_loan_100k_3y.png"),
      loadDefaultFile("/static/product_team_salary_car.png", "product_team_salary_car.png")
    ])
      .then(([controlFile, challengerFile, productTeamControlFile]) => {
        demoFiles.ab_test = {control: controlFile, challenger: challengerFile};
        demoFiles.variant_generation = {control: productTeamControlFile, challenger: null};
        if (currentMode()) applyModePreset(currentMode());
      })
      .catch(error => setStatus(error.message || String(error), true));

    document.getElementById("run").addEventListener("click", async () => {
      const button = document.getElementById("run");
      button.disabled = true;
      const mode = currentMode();
      if (!mode) {
        setStatus("Сначала выберите режим эксперимента.", true);
        button.disabled = false;
        return;
      }
      const generationMode = mode === "variant_generation";
      const totalPersonas = Number(document.getElementById("personas").value);
      const baselineLines = await logSnapshot();
      const baselineMarker = baselineLines.length ? baselineLines[baselineLines.length - 1] : "";
      sessionLogMarker = baselineMarker;
      logsNode.textContent = "Лог пока пуст.";
      renderRunningProgress(totalPersonas, baselineMarker, mode);
      startLogPolling();
      winnerNode.hidden = false;
      winnerNode.textContent = generationMode ? "LLM-агенты..." : "Расчет...";
      subtitleNode.textContent = generationMode
        ? "Запускаем агентный анализ и подготовку top-гипотез."
        : "Создаем эксперимент и опрашиваем синтетические персоны.";
      setStatus(generationMode ? "Готовим агентный анализ..." : "Запускаем эксперимент...");
      try {
        if (defaultFilesPromise) {
          await defaultFilesPromise;
        }
        const controlFile = selectedControlFile || defaultControlFile || document.getElementById("control").files[0];
        const challengerFile = selectedChallengerFile || defaultChallengerFile || document.getElementById("challenger").files[0];
        if (!controlFile) {
          throw new Error("Загрузите контрольный скриншот.");
        }
        if (!generationMode && !challengerFile) {
          throw new Error("Загрузите оба скриншота: базовый и тестовый варианты.");
        }

        const created = await fetch("/experiments", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            name: document.getElementById("name").value,
            mode,
            conversion_goal: document.getElementById("goal").value,
            target_audience: document.getElementById("audience").value
          })
        }).then(parseResponse);
        progressState.experimentId = created.id;
        setProgressStage("setup", "done", "готово");
        setProgressStage("upload", "active", "в процессе");
        setProgressText("Загружаем изображения и готовим запуск.");
        updateProgressPercent(8);

        setStatus(generationMode ? "Загружаем контрольный макет..." : "Загружаем изображения...");
        const form = new FormData();
        form.append("control", controlFile);
        if (!generationMode) {
          form.append("challenger", challengerFile);
        }
        await fetch(`/experiments/${created.id}/upload`, { method: "POST", body: form }).then(parseResponse);
        setProgressStage("upload", "done", "готово");
        if (generationMode) {
          setProgressStage("agents", "active", "в процессе");
          setProgressText("LLM-агенты формируют top-гипотезы.");
          updateProgressPercent(35);
          setStatus("Формируем top-гипотезы командой LLM-агентов...");
          const result = await fetch(`/experiments/${created.id}/run-generation`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              batch_size: 10
            })
          }).then(parseResponse);
          finishProgress();
          renderGenerationResult(result);
          setStatus("Команда LLM-агентов вернула гипотезы.");
          return;
        }
        setProgressStage("personas", "active", `0 / ${totalPersonas}`);
        setProgressText("Генерируем синтетические персоны.");
        updateProgressPercent(15);

        setStatus("Персоны голосуют за варианты...");
        const report = await fetch(`/experiments/${created.id}/run`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            num_personas: totalPersonas,
            batch_size: 10
          })
        }).then(parseResponse);
        finishProgress();
        renderReport(report);
        setStatus("Отчет готов.");
      } catch (error) {
        failProgress();
        winnerNode.hidden = false;
        winnerNode.textContent = "Ошибка";
        subtitleNode.textContent = "Проверьте параметры эксперимента и файлы.";
        reportNode.className = "empty";
        reportNode.innerHTML = `<div class="empty-inner"><div class="empty-visual"></div><h2>Не удалось выполнить запуск</h2><p class="error">${escapeHtml(error.message || String(error))}</p></div>`;
        setStatus(error.message || String(error), true);
      } finally {
        stopLogPolling();
        button.disabled = false;
      }
    });
    refreshLogs();
  </script>
</body>
</html>
"""
