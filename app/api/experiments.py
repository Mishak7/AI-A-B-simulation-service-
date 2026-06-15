import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.session import get_session
from app.llm.factory import get_llm_client
from app.models import Experiment, ExperimentReport, ExperimentStatus, Persona, SimulationResult
from app.schemas import (
    ExperimentCreate,
    ExperimentRead,
    ExperimentReportRead,
    RunExperimentRequest,
    SimulationResultRead,
)
from app.services.aggregator import Aggregator
from app.services.persona_generator import PersonaGenerator
from app.services.prompt_renderer import PromptRenderer
from app.services.report_generator import ReportGenerator
from app.services.simulation_runner import SimulationRunner

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentRead)
async def create_experiment(
    payload: ExperimentCreate,
    session: AsyncSession = Depends(get_session),
) -> Experiment:
    experiment = Experiment(
        name=payload.name,
        conversion_goal=payload.conversion_goal,
        target_audience=payload.target_audience,
    )
    session.add(experiment)
    await session.commit()
    await session.refresh(experiment)
    return experiment


@router.post("/{experiment_id}/upload", response_model=ExperimentRead)
async def upload_images(
    experiment_id: int,
    control: UploadFile = File(...),
    challenger: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> Experiment:
    experiment = await _get_experiment(session, experiment_id)
    _validate_image(control)
    _validate_image(challenger)

    experiment_dir = get_settings().storage_dir / str(experiment.id)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    control_path = _save_upload(control, experiment_dir / f"control{_suffix(control.filename)}")
    challenger_path = _save_upload(challenger, experiment_dir / f"challenger{_suffix(challenger.filename)}")

    experiment.control_image_path = str(control_path)
    experiment.challenger_image_path = str(challenger_path)
    await session.commit()
    await session.refresh(experiment)
    return experiment


@router.post("/{experiment_id}/run", response_model=ExperimentReportRead)
async def run_experiment(
    experiment_id: int,
    payload: RunExperimentRequest,
    session: AsyncSession = Depends(get_session),
) -> ExperimentReportRead:
    experiment = await _get_experiment(session, experiment_id)
    if not experiment.conversion_goal:
        raise HTTPException(status_code=400, detail="conversion_goal is required")
    if not experiment.control_image_path or not experiment.challenger_image_path:
        raise HTTPException(status_code=400, detail="Both control and challenger images are required")

    experiment.status = ExperimentStatus.running
    await session.execute(delete(SimulationResult).where(SimulationResult.experiment_id == experiment_id))
    await session.execute(delete(ExperimentReport).where(ExperimentReport.experiment_id == experiment_id))
    await session.execute(delete(Persona).where(Persona.experiment_id == experiment_id))
    await session.commit()

    llm_client = get_llm_client()
    prompt_renderer = PromptRenderer()
    try:
        personas = await PersonaGenerator(llm_client, prompt_renderer).generate(
            session=session,
            experiment=experiment,
            num_personas=payload.num_personas,
            batch_size=min(payload.batch_size, 10),
        )
        results = await SimulationRunner(llm_client, prompt_renderer).run(
            session=session,
            experiment=experiment,
            personas=personas,
            concurrency=payload.batch_size,
        )
        aggregation = Aggregator().aggregate(results)
        report = await ReportGenerator(llm_client, prompt_renderer).generate(
            session=session,
            experiment=experiment,
            results=results,
            aggregation=aggregation,
        )
        experiment.status = ExperimentStatus.completed
        experiment.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(report)
        return _report_to_schema(report, results)
    except Exception:
        experiment.status = ExperimentStatus.failed
        await session.commit()
        raise


@router.get("/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(
    experiment_id: int,
    session: AsyncSession = Depends(get_session),
) -> Experiment:
    return await _get_experiment(session, experiment_id)


@router.get("/{experiment_id}/report", response_model=ExperimentReportRead)
async def get_report(
    experiment_id: int,
    session: AsyncSession = Depends(get_session),
) -> ExperimentReportRead:
    result = await session.execute(
        select(ExperimentReport).where(ExperimentReport.experiment_id == experiment_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    results_query = await session.execute(
        select(SimulationResult)
        .where(SimulationResult.experiment_id == experiment_id)
        .order_by(SimulationResult.id)
    )
    return _report_to_schema(report, list(results_query.scalars().all()))


async def _get_experiment(session: AsyncSession, experiment_id: int) -> Experiment:
    result = await session.execute(
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.personas), selectinload(Experiment.simulation_results))
    )
    experiment = result.scalar_one_or_none()
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


def _validate_image(file: UploadFile) -> None:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"{file.filename} is not an image")


def _save_upload(file: UploadFile, destination: Path) -> Path:
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return destination


def _suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix else ".png"


def _report_to_schema(
    report: ExperimentReport,
    results: list[SimulationResult] | None = None,
) -> ExperimentReportRead:
    return ExperimentReportRead(
        experiment_id=report.experiment_id,
        control_votes=report.control_votes,
        challenger_votes=report.challenger_votes,
        none_votes=report.none_votes,
        winner=report.winner,
        confidence_score=report.confidence_score,
        image_1_visual_fail_rate=report.image_1_visual_fail_rate,
        image_2_visual_fail_rate=report.image_2_visual_fail_rate,
        control_visual_fail_rate=report.control_visual_fail_rate,
        challenger_visual_fail_rate=report.challenger_visual_fail_rate,
        image_1_votes=report.image_1_votes,
        image_2_votes=report.image_2_votes,
        position_switch_rate=report.position_switch_rate,
        positional_bias_score=report.positional_bias_score,
        stable_personas=report.stable_personas,
        unstable_personas=report.unstable_personas,
        unstable_rate=report.unstable_rate,
        top_control_reasons=json.loads(report.top_control_reasons),
        top_challenger_reasons=json.loads(report.top_challenger_reasons),
        top_none_reasons=json.loads(report.top_none_reasons),
        recommendations=json.loads(report.recommendations),
        limitations=report.limitations,
        agent_results=[_simulation_result_to_schema(result) for result in results or []],
    )


def _simulation_result_to_schema(result: SimulationResult) -> SimulationResultRead:
    from app.services.report_generator import ReportGenerator

    return SimulationResultRead(
        id=result.id,
        experiment_id=result.experiment_id,
        persona_id=result.persona_id,
        presented_order=result.presented_order.value,
        raw_verdict=result.raw_verdict.value,
        mapped_verdict=result.mapped_verdict.value,
        confidence=result.confidence.value,
        visual_quality_image_1=result.visual_quality_image_1.value,
        visual_quality_image_2=result.visual_quality_image_2.value,
        visual_issues=result.visual_issues,
        critical_visual_defect=result.critical_visual_defect,
        rationale=result.rationale,
        normalized_rationale=ReportGenerator._normalize_rationale(result),
    )
