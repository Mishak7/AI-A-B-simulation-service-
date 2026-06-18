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
      --bg: #f4f7f6;
      --panel: #ffffff;
      --text: #101820;
      --muted: #667085;
      --line: #d9e1df;
      --green: #12a154;
      --green-dark: #08783d;
      --blue: #2364aa;
      --yellow: #f2c94c;
      --red: #d92d20;
      --soft: #edf8f2;
      --shadow: 0 16px 44px rgba(16, 24, 32, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { max-width: 1240px; margin: 0 auto; padding: 28px 20px 40px; }
    header {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-end;
      margin-bottom: 22px;
    }
    h1 { font-size: 30px; font-weight: 650; line-height: 1.1; margin: 0 0 8px; letter-spacing: 0; }
    h2 { font-size: 18px; font-weight: 600; margin: 0 0 16px; letter-spacing: 0; }
    h3 { font-size: 15px; font-weight: 600; margin: 0 0 10px; letter-spacing: 0; }
    p { margin: 0; color: var(--muted); line-height: 1.45; }
    .badge {
      border: 1px solid #b7dfc9;
      background: #e9f8ef;
      color: var(--green-dark);
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 13px;
      font-weight: 550;
      white-space: nowrap;
    }
    .layout { display: grid; grid-template-columns: minmax(360px, 440px) 1fr; gap: 18px; align-items: start; }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .panel { padding: 20px; }
    label { display: block; font-size: 13px; font-weight: 560; margin: 14px 0 0; color: #26352f; }
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
      border-radius: 8px;
      background: #fbfdfc;
      cursor: pointer;
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
      color: #24352f;
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
      background: #edf8f2;
      box-shadow: 0 0 0 3px rgba(18, 161, 84, 0.1);
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
      border: 1px solid #c8d4d1;
      border-radius: 7px;
      background: #fbfdfc;
      color: var(--text);
      font: inherit;
      font-weight: 400;
      font-size: 14px;
      outline: none;
    }
    input:focus, textarea:focus { border-color: var(--green); box-shadow: 0 0 0 3px rgba(18, 161, 84, 0.13); }
    textarea { min-height: 92px; resize: vertical; }
    .row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .upload-row.single { grid-template-columns: 1fr; }
    body.variant-generation .challenger-upload { display: none; }
    .upload-row label {
      display: grid;
      grid-template-rows: 18px auto;
      align-items: start;
    }
    .upload {
      position: relative;
      overflow: hidden;
      min-height: 184px;
      margin-top: 7px;
      border: 1px dashed #abc6bd;
      border-radius: 8px;
      background: #f9fcfb;
    }
    .upload input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
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
    .upload-title { color: #24352f; font-weight: 600; }
    .upload img { width: 100%; height: 128px; object-fit: cover; border-bottom: 1px solid var(--line); display: none; }
    .upload.has-image img { display: block; }
    .upload.has-image .upload-content { min-height: 55px; padding: 10px 12px; text-align: left; }
    .actions { display: flex; align-items: center; gap: 12px; margin-top: 18px; }
    button {
      border: 0;
      border-radius: 7px;
      background: var(--green);
      color: white;
      padding: 12px 15px;
      min-width: 220px;
      min-height: 44px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
      white-space: normal;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    button:hover { background: var(--green-dark); }
    button:disabled { opacity: 0.62; cursor: wait; }
    .status { color: var(--muted); font-size: 13px; line-height: 1.35; }
    .result { min-height: 680px; overflow: hidden; }
    .result-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 20px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(90deg, #ffffff 0%, #f2fbf6 100%);
    }
    .winner {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e8f6ee;
      color: var(--green-dark);
      font-weight: 450;
      white-space: nowrap;
    }
    .empty {
      display: grid;
      place-items: center;
      min-height: 560px;
      padding: 28px;
      text-align: center;
      color: var(--muted);
    }
    .empty-inner { max-width: 460px; }
    .empty-visual {
      width: min(360px, 100%);
      height: 180px;
      margin: 0 auto 22px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(90deg, rgba(18, 161, 84, 0.2) 62%, transparent 62%),
        linear-gradient(90deg, rgba(35, 100, 170, 0.22) 38%, transparent 38%),
        #fff;
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
      background: #e3ece9;
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
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.78), transparent);
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
      border-radius: 8px;
      background: #fff;
    }
    .stage-dot {
      width: 10px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: #c8d4d1;
      justify-self: center;
    }
    .stage-label {
      color: #26352f;
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
      background: #fff;
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
    }
    .donut-center {
      width: 116px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: #fff;
      border: 1px solid var(--line);
    }
    .viz-summary { margin-bottom: 2px; }
    .viz-summary strong { font-weight: 600; }
    .bars { display: grid; gap: 12px; }
    .bar-row { display: grid; grid-template-columns: 120px 1fr 46px; gap: 10px; align-items: center; font-size: 13px; }
    .track { height: 12px; background: #edf1ef; border-radius: 999px; overflow: hidden; }
    .fill { height: 100%; border-radius: 999px; width: var(--w); }
    .fill.control { background: var(--green); }
    .fill.challenger { background: var(--blue); }
    .fill.none { background: var(--yellow); }
    .split { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .block {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fff;
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
      border-radius: 8px;
      background: #fbfdfc;
      cursor: pointer;
    }
    .hypothesis-option input { margin: 3px 0 0; width: auto; }
    .hypothesis-option strong,
    .hypothesis-option span,
    .hypothesis-option em { grid-column: 2; }
    .hypothesis-option strong { color: #26352f; font-size: 14px; }
    .hypothesis-option span { color: var(--muted); font-size: 13px; line-height: 1.4; }
    .hypothesis-option em { color: #2364aa; font-size: 12px; font-style: normal; }
    .generated-mockup {
      width: 100%;
      max-height: 520px;
      object-fit: contain;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f7faf9;
    }
    .mockup-approval {
      padding: 10px;
    }
    .mockup-approval .generated-mockup {
      max-height: none;
      min-height: 640px;
      height: min(76vh, 980px);
      object-fit: contain;
      object-position: top center;
    }
    ul { margin: 0; padding-left: 18px; color: #26352f; line-height: 1.5; }
    li + li { margin-top: 7px; }
    .agents {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      overflow: hidden;
    }
    th, td { padding: 10px 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; background: #f7faf9; }
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
    .pill.control { color: var(--green-dark); background: #e8f6ee; }
    .pill.challenger { color: #174d86; background: #e9f1fb; }
    .pill.none { color: #7a5a00; background: #fff6d7; }
    .pill.bad { color: #981b12; background: #fee4e2; }
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
      background: #eef7f2;
      color: var(--green-dark);
      border: 1px solid #b7dfc9;
    }
    .logs-head button:hover { background: #dff2e8; }
    .log-output {
      margin: 0;
      max-height: 320px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0f1713;
      color: #d7f4df;
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
        <h1>Синтетический A/B-тест интерфейса</h1>
        <p>Проверка гипотезы на наборе банковских персон до запуска реального эксперимента.</p>
      </div>
      <div class="badge">SimAB для продуктовых команд</div>
    </header>

    <div class="layout">
      <section class="panel">
        <h2>Настройка эксперимента</h2>
        <div class="mode-switch" role="radiogroup" aria-label="Режим эксперимента">
          <label class="mode-option">
            <input type="radio" name="experimentMode" value="ab_test" />
            <span class="mode-title">Проверить готовый A/B-тест</span>
            <span class="mode-copy">Есть контрольный и тестовый макет.</span>
          </label>
          <label class="mode-option">
            <input type="radio" name="experimentMode" value="variant_generation" />
            <span class="mode-title">Сгенерировать гипотезы и вариант</span>
            <span class="mode-copy">Есть только контрольный макет.</span>
          </label>
        </div>
        <div class="experiment-form" id="experimentForm">
          <label>Название
            <input id="name" value="Consumer Loan Calculator Default Values" />
          </label>
          <label>Цель эксперимента
            <textarea id="goal">Повысить вероятность перехода к следующему шагу оформления потребительского кредита («Продолжить») после просмотра кредитного калькулятора за счет более привлекательных значений суммы и срока кредита по умолчанию.</textarea>
            <span class="field-hint">Можно оставить пустым: OpenClaw сможет сформулировать гипотезы от контрольного макета.</span>
          </label>
          <label>Целевая аудитория
            <textarea id="audience">Российские розничные клиенты, рассматривающие оформление потребительского кредита онлайн. Пользователи находятся на этапе первичного изучения условий кредита и оценивают доступность ежемесячного платежа, размер кредита и срок погашения перед началом оформления заявки.</textarea>
            <span class="field-hint">Можно оставить пустым, если аудиторию нужно вывести из контекста интерфейса.</span>
          </label>
          <div class="row upload-row" id="uploadRow">
            <label>Контроль
              <div class="upload has-image" id="controlDrop">
                <img id="controlPreview" src="/static/consumer_loan_300k_5y.png" alt="" />
                <div class="upload-content">
                  <span class="upload-title" id="controlName">Контроль: 300 000 ₽, 5 лет</span>
                  <span>Можно заменить своим PNG или JPG</span>
                </div>
                <input id="control" type="file" accept="image/*" />
              </div>
            </label>
            <label class="challenger-upload">Тестовый вариант
              <div class="upload has-image" id="challengerDrop">
                <img id="challengerPreview" src="/static/consumer_loan_100k_3y.png" alt="" />
                <div class="upload-content">
                  <span class="upload-title" id="challengerName">Тест: 100 000 ₽, 3 года</span>
                  <span>Можно заменить своим PNG или JPG</span>
                </div>
                <input id="challenger" type="file" accept="image/*" />
              </div>
            </label>
          </div>
          <div class="row">
            <label>Количество персон
              <input id="personas" type="number" min="1" max="500" value="24" />
            </label>
            <label>Размер батча
              <input id="batch" type="number" min="1" max="50" value="10" />
            </label>
          </div>
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
            <p id="subtitle">После запуска здесь появятся голоса персон, причины выбора и рекомендации.</p>
          </div>
          <div class="winner" id="winner">Нет результата</div>
        </div>
        <div id="report" class="empty">
          <div class="empty-inner">
            <div class="empty-visual"></div>
            <h2>Готов пример для запуска</h2>
            <p>По умолчанию сравниваются значения кредитного калькулятора: контроль 300 000 ₽ на 5 лет и тест 100 000 ₽ на 3 года. Скриншоты можно заменить своими.</p>
          </div>
        </div>
      </section>
    </div>

    <section class="logs-panel">
      <div class="logs-head">
        <div>
          <h2>Журнал событий</h2>
          <p>Последние серверные события: генерация персон, решения и сборка отчета.</p>
        </div>
        <button id="refreshLogs" type="button">Обновить</button>
      </div>
      <pre id="logs" class="log-output">Лог пока пуст.</pre>
    </section>
  </main>
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
    let logPoller = null;
    let progressState = null;
    let sessionLogMarker = null;
    let lastGenerationResult = null;

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
          line.includes("OpenClaw variant generation")
        );
      });
    }

    function currentMode() {
      return document.querySelector('input[name="experimentMode"]:checked')?.value || null;
    }

    function isVariantGenerationMode() {
      return currentMode() === "variant_generation";
    }

    function syncModeUi() {
      const mode = currentMode();
      const hasMode = Boolean(mode);
      const generationMode = isVariantGenerationMode();
      document.getElementById("experimentForm").classList.toggle("is-visible", hasMode);
      document.body.classList.toggle("variant-generation", generationMode);
      document.getElementById("uploadRow").classList.toggle("single", generationMode);
      document.getElementById("run").textContent = generationMode
        ? "Сгенерировать гипотезы"
        : "Запустить симуляцию";
      if (!hasMode) {
        setStatus("Выберите режим эксперимента.");
        subtitleNode.textContent = "Выберите сценарий слева, чтобы открыть настройки запуска.";
      } else if (generationMode) {
        setStatus("Режим генерации: загрузите контрольный макет. Цель и аудиторию можно оставить пустыми.");
        subtitleNode.textContent = "OpenClaw подготовит top-гипотезы, затем выбранный вариант пройдет генерацию и critic-проверку.";
      } else {
        setStatus("Загружен пример: кредитный калькулятор с разными значениями суммы и срока по умолчанию.");
        subtitleNode.textContent = "После запуска здесь появятся голоса персон, причины выбора и рекомендации.";
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
              <h2>${generationMode ? "Готовим OpenClaw-запуск" : "Симуляция выполняется"}</h2>
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
              <div class="run-stage" data-stage="openclaw"><span class="stage-dot"></span><span class="stage-label">Заявка OpenClaw</span><span class="stage-count">ожидает</span></div>
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
        const openClawStarted = scoped.some(line => line.includes("Variant generation requested"));
        const openClawDone = scoped.some(line => line.includes("OpenClaw variant generation completed"));
        if (progressState.experimentId) setProgressStage("setup", "done", "готово");
        setProgressStage("openclaw", openClawDone ? "done" : openClawStarted ? "active" : "", openClawDone ? "готово" : openClawStarted ? "в процессе" : "ожидает");
        setProgressStage("report", openClawDone ? "done" : "", openClawDone ? "готово" : "ожидает");
        setProgressText(openClawDone ? "Гипотезы OpenClaw готовы." : "OpenClaw формирует top-гипотезы.");
        updateProgressPercent(openClawDone ? 100 : openClawStarted ? 72 : 35);
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
        setProgressStage("openclaw", "done", "готово");
        setProgressStage("report", "done", "готово");
        setProgressText("Гипотезы OpenClaw готовы.");
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
      winnerNode.textContent = "OpenClaw: выберите гипотезу";
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
          <p>${escapeHtml(result.message || "OpenClaw обработал контрольный макет.")}</p>
        </div>
        <div class="block">
          <h3>Top-3 гипотезы</h3>
          <div class="hypothesis-list">${hypothesisCards || "OpenClaw пока не вернул гипотезы."}</div>
          <button id="generateMockup" class="secondary" type="button" ${hypotheses.length ? "" : "disabled"}>Сгенерировать макет по выбранной гипотезе</button>
        </div>
      `;
      const generateButton = document.getElementById("generateMockup");
      if (generateButton) {
        generateButton.addEventListener("click", () => {
          const selected = document.querySelector('input[name="selectedHypothesis"]:checked');
          const selectedIndex = Number(selected ? selected.value : 0);
          generateMockupForHypothesis(result, hypotheses[selectedIndex] || hypotheses[0]);
        });
      }
    }

    async function generateMockupForHypothesis(result, selectedHypothesis) {
      console.log("[mockup] click");
      console.log("[mockup] result =", result);
      console.log("[mockup] experiment_id =", result.experiment_id);
      console.log("[mockup] id =", result.id);
      console.log("[mockup] selectedHypothesis =", selectedHypothesis);
      if (!selectedHypothesis) {
        setStatus("Выберите гипотезу.", true);
        return;
      }
      setStatus("Генерируем тестовый макет и запускаем critic-проверку...");
      winnerNode.textContent = "OpenClaw: генерируем макет";
      subtitleNode.textContent = "Mockup Generator создает вариант, Critic проверяет до 3 итераций.";
      try {
        const mockup = await fetch(`/experiments/${result.experiment_id}/generate-mockup`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            selected_hypothesis: selectedHypothesis,
            batch_size: Number(document.getElementById("batch").value)
          })
        }).then(parseResponse);
        renderMockupApproval(mockup);
        setStatus("Тестовый макет готов к согласованию.");
      } catch (error) {
        setStatus(error.message || String(error), true);
      }
    }

    function renderMockupApproval(result) {
      const agentResponse = result.agent_response || {};
      const mockup = agentResponse.mockup_generator || {};
      winnerNode.textContent = "Макет готов";
      subtitleNode.textContent = "Проверьте тестовый вариант и выберите дальнейшее действие.";
      reportNode.className = "report-body";
      reportNode.innerHTML = `
        <div class="block mockup-approval">
          <h2>${escapeHtml(mockup.variant_name || "Тестовый вариант")}</h2>
          ${result.challenger_image_data_url ? `<img class="generated-mockup" src="${result.challenger_image_data_url}" alt="Сгенерированный тестовый макет" />` : "<p>Превью недоступно.</p>"}
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
            batch_size: Number(document.getElementById("batch").value)
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
    document.getElementById("refreshLogs").addEventListener("click", refreshLogs);
    document.querySelectorAll('input[name="experimentMode"]').forEach(input => {
      input.addEventListener("change", syncModeUi);
    });
    syncModeUi();

    defaultFilesPromise = Promise.all([
      loadDefaultFile("/static/consumer_loan_300k_5y.png", "consumer_loan_300k_5y.png"),
      loadDefaultFile("/static/consumer_loan_100k_3y.png", "consumer_loan_100k_3y.png")
    ])
      .then(([controlFile, challengerFile]) => {
        defaultControlFile = controlFile;
        defaultChallengerFile = challengerFile;
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
      winnerNode.textContent = generationMode ? "OpenClaw..." : "Расчет...";
      subtitleNode.textContent = generationMode
        ? "Запускаем агентный анализ и подготовку top-гипотез."
        : "Создаем эксперимент и опрашиваем синтетические персоны.";
      setStatus(generationMode ? "Готовим OpenClaw-анализ..." : "Запускаем эксперимент...");
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
          setProgressStage("openclaw", "active", "в процессе");
          setProgressText("OpenClaw формирует top-гипотезы.");
          updateProgressPercent(35);
          setStatus("Формируем top-гипотезы в OpenClaw...");
          const result = await fetch(`/experiments/${created.id}/run-generation`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              batch_size: Number(document.getElementById("batch").value)
            })
          }).then(parseResponse);
          finishProgress();
          renderGenerationResult(result);
          setStatus("OpenClaw вернул гипотезы.");
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
            batch_size: Number(document.getElementById("batch").value)
          })
        }).then(parseResponse);
        finishProgress();
        renderReport(report);
        setStatus("Отчет готов.");
      } catch (error) {
        failProgress();
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
