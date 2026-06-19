import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.session import get_session
from app.llm.factory import get_llm_client
from app.models import (
    Experiment,
    ExperimentMode,
    ExperimentReport,
    ExperimentStatus,
    Persona,
    SimulationResult,
)
from app.schemas import (
    ExperimentCreate,
    ExperimentRead,
    ExperimentReportRead,
    GenerateVariantImageRequest,
    RunExperimentRequest,
    RunVariantGenerationRequest,
    SimulationResultRead,
)
from app.services.aggregator import Aggregator
from app.services.openclaw_variant_generator import OpenClawVariantGenerator
from app.services.persona_generator import PersonaGenerator
from app.services.prompt_renderer import PromptRenderer
from app.services.report_generator import ReportGenerator
from app.services.simulation_runner import SimulationRunner

router = APIRouter(prefix="/experiments", tags=["experiments"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ExperimentRead)
async def create_experiment(
    payload: ExperimentCreate,
    session: AsyncSession = Depends(get_session),
) -> Experiment:
    experiment = Experiment(
        name=payload.name,
        mode=payload.mode,
        conversion_goal=payload.conversion_goal,
        target_audience=payload.target_audience,
    )
    session.add(experiment)
    await session.commit()
    await session.refresh(experiment)
    logger.info(
        "Experiment created id=%s name=%r goal_chars=%s audience_chars=%s",
        experiment.id,
        experiment.name,
        len(experiment.conversion_goal or ""),
        len(experiment.target_audience or ""),
    )
    return experiment


@router.post("/{experiment_id}/upload", response_model=ExperimentRead)
async def upload_images(
    experiment_id: int,
    control: UploadFile = File(...),
    challenger: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
) -> Experiment:
    experiment = await _get_experiment(session, experiment_id)
    _validate_image(control)
    if challenger is not None:
        _validate_image(challenger)

    experiment_dir = get_settings().storage_dir / str(experiment.id)
    experiment_dir.mkdir(parents=True, exist_ok=True)
    control_path = _save_upload(
        control, experiment_dir / f"control{_suffix(control.filename)}"
    )
    experiment.control_image_path = str(control_path)
    challenger_path = None
    if challenger is not None:
        challenger_path = _save_upload(
            challenger, experiment_dir / f"challenger{_suffix(challenger.filename)}"
        )
        experiment.challenger_image_path = str(challenger_path)
    await session.commit()
    await session.refresh(experiment)
    logger.info(
        "Images uploaded experiment_id=%s control=%s challenger=%s",
        experiment.id,
        control_path,
        challenger_path,
    )
    return experiment


@router.post("/{experiment_id}/run", response_model=ExperimentReportRead)
async def run_experiment(
    experiment_id: int,
    payload: RunExperimentRequest,
    session: AsyncSession = Depends(get_session),
) -> ExperimentReportRead:
    experiment = await _get_experiment(session, experiment_id)
    if experiment.mode != ExperimentMode.ab_test:
        raise HTTPException(
            status_code=400, detail="Use /run-generation for variant generation experiments"
        )
    if not experiment.control_image_path or not experiment.challenger_image_path:
        raise HTTPException(
            status_code=400, detail="Both control and challenger images are required"
        )

    logger.info(
        "Run requested experiment_id=%s num_personas=%s batch_size=%s",
        experiment_id,
        payload.num_personas,
        payload.batch_size,
    )
    experiment.status = ExperimentStatus.running
    await session.execute(
        delete(SimulationResult).where(SimulationResult.experiment_id == experiment_id)
    )
    await session.execute(
        delete(ExperimentReport).where(ExperimentReport.experiment_id == experiment_id)
    )
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
        logger.info(
            "Personas ready experiment_id=%s count=%s", experiment_id, len(personas)
        )
        results = await SimulationRunner(llm_client, prompt_renderer).run(
            session=session,
            experiment=experiment,
            personas=personas,
            concurrency=payload.batch_size,
        )
        logger.info(
            "Simulations ready experiment_id=%s result_count=%s",
            experiment_id,
            len(results),
        )
        aggregation = Aggregator().aggregate(results)
        logger.info(
            "Aggregation ready experiment_id=%s winner=%s control=%s challenger=%s none=%s stable=%s unstable=%s",
            experiment_id,
            aggregation["winner"],
            aggregation["control_votes"],
            aggregation["challenger_votes"],
            aggregation["none_votes"],
            aggregation["stable_personas"],
            aggregation["unstable_personas"],
        )
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
        logger.info(
            "Run completed experiment_id=%s report_experiment_id=%s",
            experiment_id,
            report.experiment_id,
        )
        return _report_to_schema(report, results)
    except Exception:
        logger.exception("Run failed experiment_id=%s", experiment_id)
        experiment.status = ExperimentStatus.failed
        await session.commit()
        raise


@router.post("/{experiment_id}/run-generation")
async def run_variant_generation(
    experiment_id: int,
    payload: RunVariantGenerationRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    experiment = await _get_experiment(session, experiment_id)
    if experiment.mode != ExperimentMode.variant_generation:
        raise HTTPException(
            status_code=400, detail="Experiment mode must be variant_generation"
        )
    if not experiment.control_image_path:
        raise HTTPException(status_code=400, detail="Control image is required")

    logger.info(
        "Variant generation requested experiment_id=%s batch_size=%s",
        experiment_id,
        payload.batch_size,
    )
    experiment.status = ExperimentStatus.running
    await session.execute(
        delete(SimulationResult).where(SimulationResult.experiment_id == experiment_id)
    )
    await session.execute(
        delete(ExperimentReport).where(ExperimentReport.experiment_id == experiment_id)
    )
    await session.execute(delete(Persona).where(Persona.experiment_id == experiment_id))
    await session.commit()

    try:
        result = await OpenClawVariantGenerator().start(
            experiment=experiment,
            batch_size=payload.batch_size,
        )
        experiment.status = ExperimentStatus.completed
        await session.commit()
        logger.info(
            "Variant generation completed experiment_id=%s status=%s",
            experiment_id,
            result["status"],
        )
        return result
    except Exception:
        logger.exception("Variant generation failed experiment_id=%s", experiment_id)
        experiment.status = ExperimentStatus.failed
        await session.commit()
        raise


@router.post("/{experiment_id}/generate-variant-image")
async def generate_variant_image(
    experiment_id: int,
    payload: GenerateVariantImageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    experiment = await _get_experiment(session, experiment_id)
    if experiment.mode != ExperimentMode.variant_generation:
        raise HTTPException(
            status_code=400, detail="Experiment mode must be variant_generation"
        )
    if not experiment.control_image_path:
        raise HTTPException(status_code=400, detail="Control image is required")

    logger.info("Variant image requested experiment_id=%s", experiment_id)
    experiment.status = ExperimentStatus.running
    await session.commit()
    try:
        result = await OpenClawVariantGenerator().generate_variant_image(
            experiment=experiment,
            selected_hypothesis=payload.selected_hypothesis,
            generation_prompt=payload.generation_prompt,
        )
        experiment.challenger_image_path = result["challenger_image_path"]
        experiment.status = ExperimentStatus.completed
        await session.commit()
        logger.info(
            "Variant image completed experiment_id=%s challenger=%s",
            experiment_id,
            experiment.challenger_image_path,
        )
        return result
    except Exception:
        logger.exception("Variant image failed experiment_id=%s", experiment_id)
        experiment.status = ExperimentStatus.failed
        await session.commit()
        raise


@router.post("/{experiment_id}/approve-generated-variant", response_model=ExperimentRead)
async def approve_generated_variant(
    experiment_id: int,
    session: AsyncSession = Depends(get_session),
) -> Experiment:
    experiment = await _get_experiment(session, experiment_id)
    if not experiment.control_image_path or not experiment.challenger_image_path:
        raise HTTPException(
            status_code=400, detail="Control and generated challenger are required"
        )
    experiment.mode = ExperimentMode.ab_test
    experiment.status = ExperimentStatus.created
    experiment.completed_at = None
    await session.commit()
    await session.refresh(experiment)
    logger.info("Generated variant approved experiment_id=%s", experiment_id)
    return experiment


@router.get("/{experiment_id}/generated-variant")
async def get_generated_variant(
    experiment_id: int,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    experiment = await _get_experiment(session, experiment_id)
    if not experiment.challenger_image_path:
        raise HTTPException(status_code=404, detail="Generated variant not found")
    image_path = Path(experiment.challenger_image_path)
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Generated variant file not found")
    return FileResponse(image_path)


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
        .options(
            selectinload(Experiment.personas),
            selectinload(Experiment.simulation_results),
        )
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
        text_findings=json.loads(report.text_findings),
        visual_findings=json.loads(report.visual_findings),
        combined_conclusion=report.combined_conclusion,
        agent_results=[
            _simulation_result_to_schema(result) for result in results or []
        ],
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
