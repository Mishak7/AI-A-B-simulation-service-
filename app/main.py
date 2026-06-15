from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

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
app.mount("/static", StaticFiles(directory="app/static"), name="static")
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
      white-space: nowrap;
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
    @media (max-width: 980px) {
      .layout, .viz, .split { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      header { align-items: flex-start; flex-direction: column; }
    }
    @media (max-width: 640px) {
      main { padding: 18px 12px 28px; }
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
        <label>Название
          <input id="name" value="Меню кредитов Сбера: влияние входа в ГигаЧат" />
        </label>
        <label>Цель эксперимента
          <textarea id="goal">Повысить CTR по основному CTA «Оформить кредит онлайн» на экране меню кредитов, то есть увеличить долю пользователей, которые после просмотра меню переходят к началу онлайн-оформления кредита.</textarea>
        </label>
        <label>Целевая аудитория
          <textarea id="audience">Российские розничные пользователи банковских сервисов, которые открыли раздел кредитов Сбера на десктопе. Аудитория включает действующих и потенциальных клиентов Сбера с разным уровнем финансовой грамотности, цифровой грамотности, доверия к онлайн-банкингу и готовности взять кредит. Часть пользователей активно ищет кредит, рефинансирование, рассрочку или информацию по условиям, а часть просто изучает варианты и пытается понять, подходит ли им продукт.</textarea>
        </label>
        <div class="row">
          <label>Базовый вариант без ГигаЧата
            <div class="upload has-image" id="controlDrop">
              <img id="controlPreview" src="/static/sber_credits_without_gigachat.png" alt="" />
              <div class="upload-content">
                <span class="upload-title" id="controlName">Базовый вариант: без ГигаЧата</span>
                <span>Можно заменить своим PNG или JPG</span>
              </div>
              <input id="control" type="file" accept="image/*" />
            </div>
          </label>
          <label>Тестовый вариант с ГигаЧатом
            <div class="upload has-image" id="challengerDrop">
              <img id="challengerPreview" src="/static/sber_credits_with_gigachat.png" alt="" />
              <div class="upload-content">
                <span class="upload-title" id="challengerName">Тестовый вариант: с ГигаЧатом</span>
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
          <div class="status" id="status">Загружен пример: меню кредитов Сбера без ГигаЧата против версии с ГигаЧатом.</div>
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
            <p>По умолчанию сравниваются меню кредитов Сбера без ГигаЧата и тестовый вариант с входом в ГигаЧат. Скриншоты можно заменить своими.</p>
          </div>
        </div>
      </section>
    </div>
  </main>
  <script>
    const reportNode = document.getElementById("report");
    const statusNode = document.getElementById("status");
    const winnerNode = document.getElementById("winner");
    const subtitleNode = document.getElementById("subtitle");
    let defaultControlFile = null;
    let defaultChallengerFile = null;
    let selectedControlFile = null;
    let selectedChallengerFile = null;
    let defaultFilesPromise = null;

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

    function renderReport(report) {
      const total = report.control_votes + report.challenger_votes + report.none_votes;
      const controlPct = percent(report.control_votes, total);
      const challengerPct = percent(report.challenger_votes, total);
      const nonePct = percent(report.none_votes, total);
      const controlDeg = total ? (report.control_votes / total) * 360 : 0;
      const challengerDeg = total ? controlDeg + (report.challenger_votes / total) * 360 : 0;
      const confidence = Math.round((report.confidence_score || 0) * 100);
      const winnerLabel = labels[report.winner] || report.winner;

      winnerNode.textContent = `Победитель: ${winnerLabel}`;
      subtitleNode.textContent = `${total} персон оценили два варианта интерфейса`;

      const agentRows = (report.agent_results || []).slice(0, 8).map((agent, index) => {
        const mapped = agent.mapped_verdict;
        const mappedClass = mapped === "control" ? "control" : mapped === "challenger" ? "challenger" : "none";
        const visualBad = agent.critical_visual_defect ? `<span class="pill bad">визуальный дефект</span>` : "";
        return `
          <tr>
            <td>${index + 1}</td>
            <td><span class="pill ${mappedClass}">${labels[mapped] || mapped}</span></td>
            <td>${labels[agent.confidence] || agent.confidence}</td>
            <td>${visualBad || labels[agent.visual_quality_image_1] || agent.visual_quality_image_1}</td>
            <td>${escapeHtml(agent.normalized_rationale || agent.rationale)}</td>
          </tr>
        `;
      }).join("");

      reportNode.className = "report-body";
      reportNode.innerHTML = `
        <div class="metrics">
          <div class="metric"><div class="metric-label">Всего голосов</div><div class="metric-value">${total}</div></div>
          <div class="metric"><div class="metric-label">Базовый вариант</div><div class="metric-value">${report.control_votes}</div></div>
          <div class="metric"><div class="metric-label">Тестовый вариант</div><div class="metric-value">${report.challenger_votes}</div></div>
          <div class="metric"><div class="metric-label">Уверенность</div><div class="metric-value">${confidence}%</div></div>
        </div>

        <div class="block viz" style="--control-deg:${controlDeg}deg; --challenger-deg:${challengerDeg}deg;">
          <div class="donut"><div class="donut-center"></div></div>
          <div class="bars">
            <p class="viz-summary">Победитель: <strong>${winnerLabel}</strong></p>
            <div class="bar-row"><strong>Базовый</strong><div class="track"><div class="fill control" style="--w:${controlPct}%"></div></div><span>${controlPct}%</span></div>
            <div class="bar-row"><strong>Тестовый</strong><div class="track"><div class="fill challenger" style="--w:${challengerPct}%"></div></div><span>${challengerPct}%</span></div>
            <div class="bar-row"><strong>Нет выбора</strong><div class="track"><div class="fill none" style="--w:${nonePct}%"></div></div><span>${nonePct}%</span></div>
          </div>
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

        <div class="split">
          <div class="block">
            <h3>Почему выбирали базовый вариант</h3>
            ${renderList(report.top_control_reasons, "Нет устойчивых причин в пользу базового варианта.")}
          </div>
          <div class="block">
            <h3>Почему выбирали тестовый вариант</h3>
            ${renderList(report.top_challenger_reasons, "Нет устойчивых причин в пользу тестового варианта.")}
          </div>
        </div>

        <div class="block">
          <h3>Голоса отдельных персон</h3>
          <table class="agents">
            <thead>
              <tr><th>#</th><th>Выбор</th><th>Уверенность</th><th>QA</th><th>Причина</th></tr>
            </thead>
            <tbody>${agentRows || `<tr><td colspan="5">Нет данных по персонам.</td></tr>`}</tbody>
          </table>
        </div>
      `;
    }

    setupPreview("control", "controlDrop", "controlPreview", "controlName");
    setupPreview("challenger", "challengerDrop", "challengerPreview", "challengerName");

    defaultFilesPromise = Promise.all([
      loadDefaultFile("/static/sber_credits_without_gigachat.png", "sber_credits_without_gigachat.png"),
      loadDefaultFile("/static/sber_credits_with_gigachat.png", "sber_credits_with_gigachat.png")
    ])
      .then(([controlFile, challengerFile]) => {
        defaultControlFile = controlFile;
        defaultChallengerFile = challengerFile;
      })
      .catch(error => setStatus(error.message || String(error), true));

    document.getElementById("run").addEventListener("click", async () => {
      const button = document.getElementById("run");
      button.disabled = true;
      winnerNode.textContent = "Расчет...";
      subtitleNode.textContent = "Создаем эксперимент и опрашиваем синтетические персоны.";
      reportNode.className = "empty";
      reportNode.innerHTML = `<div class="empty-inner"><div class="empty-visual"></div><h2>Симуляция выполняется</h2><p>Генерируем персоны, сравниваем два варианта и собираем отчет.</p></div>`;
      setStatus("Запускаем эксперимент...");
      try {
        if (defaultFilesPromise) {
          await defaultFilesPromise;
        }
        const controlFile = selectedControlFile || defaultControlFile || document.getElementById("control").files[0];
        const challengerFile = selectedChallengerFile || defaultChallengerFile || document.getElementById("challenger").files[0];
        if (!controlFile || !challengerFile) {
          throw new Error("Загрузите оба скриншота: базовый и тестовый варианты.");
        }

        const created = await fetch("/experiments", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            name: document.getElementById("name").value,
            conversion_goal: document.getElementById("goal").value,
            target_audience: document.getElementById("audience").value
          })
        }).then(parseResponse);

        setStatus("Загружаем изображения...");
        const form = new FormData();
        form.append("control", controlFile);
        form.append("challenger", challengerFile);
        await fetch(`/experiments/${created.id}/upload`, { method: "POST", body: form }).then(parseResponse);

        setStatus("Персоны голосуют за варианты...");
        const report = await fetch(`/experiments/${created.id}/run`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            num_personas: Number(document.getElementById("personas").value),
            batch_size: Number(document.getElementById("batch").value)
          })
        }).then(parseResponse);
        renderReport(report);
        setStatus("Отчет готов.");
      } catch (error) {
        winnerNode.textContent = "Ошибка";
        subtitleNode.textContent = "Проверьте параметры эксперимента и файлы.";
        reportNode.className = "empty";
        reportNode.innerHTML = `<div class="empty-inner"><div class="empty-visual"></div><h2>Не удалось запустить симуляцию</h2><p class="error">${escapeHtml(error.message || String(error))}</p></div>`;
        setStatus(error.message || String(error), true);
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
