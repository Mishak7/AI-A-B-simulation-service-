import importlib


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00"
    b"\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_mock_pipeline_end_to_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "SAB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setenv("SAB_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SAB_LOG_FILE", str(tmp_path / "simab.log"))
    monkeypatch.setenv("SAB_LLM_PROVIDER", "mock")

    main = importlib.import_module("app.main")

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        created = client.post(
            "/experiments",
            json={
                "name": "Smoke test",
                "conversion_goal": "Increase signup clicks",
                "target_audience": "B2B buyers",
            },
        )
        assert created.status_code == 200
        experiment_id = created.json()["id"]

        uploaded = client.post(
            f"/experiments/{experiment_id}/upload",
            files={
                "control": ("control.png", PNG_1X1, "image/png"),
                "challenger": ("challenger.png", PNG_1X1, "image/png"),
            },
        )
        assert uploaded.status_code == 200

        report = client.post(
            f"/experiments/{experiment_id}/run",
            json={"num_personas": 6, "batch_size": 3, "early_stopping": False},
        )
        assert report.status_code == 200
        payload = report.json()
        assert (
            payload["control_votes"]
            + payload["challenger_votes"]
            + payload["none_votes"]
            == payload["stable_personas"]
        )
        assert payload["stable_personas"] + payload["unstable_personas"] == 6
        assert 0.0 <= payload["unstable_rate"] <= 1.0
        assert payload["image_1_votes"] + payload["image_2_votes"] <= 12
        assert 0.0 <= payload["position_switch_rate"] <= 1.0
        assert 0.0 <= payload["positional_bias_score"] <= 1.0
        assert payload["winner"] in {"control", "challenger", "inconclusive"}
        assert payload["image_1_visual_fail_rate"] == 0.0
        assert payload["image_2_visual_fail_rate"] == 0.0
        assert payload["control_visual_fail_rate"] == 0.0
        assert payload["challenger_visual_fail_rate"] == 0.0
        assert payload["text_findings"]
        assert isinstance(payload["visual_findings"], list)
        assert payload["combined_conclusion"]
        assert len(payload["agent_results"]) == 12
        assert {
            "raw_verdict",
            "mapped_verdict",
            "visual_quality_image_1",
            "visual_quality_image_2",
            "critical_visual_defect",
            "normalized_rationale",
        }.issubset(payload["agent_results"][0])
        assert {result["presented_order"] for result in payload["agent_results"]} == {
            "control_first",
            "challenger_first",
        }
        assert "Синтетическая оценка не заменяет" in payload["limitations"]

        status = client.get(f"/experiments/{experiment_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "completed"

        rerun_report = client.post(
            f"/experiments/{experiment_id}/run",
            json={"num_personas": 3, "batch_size": 2, "early_stopping": False},
        )
        assert rerun_report.status_code == 200
        rerun_payload = rerun_report.json()
        assert (
            rerun_payload["control_votes"]
            + rerun_payload["challenger_votes"]
            + rerun_payload["none_votes"]
            == rerun_payload["stable_personas"]
        )
        assert (
            rerun_payload["stable_personas"] + rerun_payload["unstable_personas"] == 3
        )
        assert rerun_payload["combined_conclusion"]
        assert len(rerun_payload["agent_results"]) == 6

        logs = client.get("/logs?limit=50")
        assert logs.status_code == 200
        log_lines = "\n".join(logs.json()["lines"])
        assert "Run completed experiment_id=" in log_lines
        assert "Generated persona experiment_id=" in log_lines


def test_variant_generation_calls_openclaw_gateway(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "SAB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'generation.db'}"
    )
    monkeypatch.setenv("SAB_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SAB_LOG_FILE", str(tmp_path / "generation.log"))
    monkeypatch.setenv("SAB_LLM_PROVIDER", "mock")
    monkeypatch.setenv("SAB_OPENCLAW_BASE_URL", "http://openclaw-gateway:18789")
    from app.config import get_settings

    get_settings.cache_clear()

    async def fake_generate_hypotheses(self, payload):
        return {
            "agent": "openclaw_pipeline",
            "status": "hypotheses_ready",
            "hypotheses": [
                {
                    "title": "Test",
                    "rationale": "Because",
                    "hypothesis": "If X then Y",
                    "proposed_change": "Change CTA",
                }
            ],
            "variant_direction": {},
            "next_step": "user_selects_top_hypothesis",
        }

    async def fake_generate_mockup(self, experiment, selected_hypothesis, batch_size):
        challenger_path = tmp_path / "storage" / str(experiment.id) / "challenger.svg"
        challenger_path.parent.mkdir(parents=True, exist_ok=True)
        challenger_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        return {
            "experiment_id": experiment.id,
            "status": "mockup_ready",
            "message": "ready",
            "response_path": str(tmp_path / "response.json"),
            "challenger_image_path": str(challenger_path),
            "challenger_image_data_url": "data:image/svg+xml;base64,PHN2Zy8+",
            "runtime": "openclaw_gateway",
            "agent_response": {
                "mockup_generator": {"variant_name": "Variant"},
                "critic": {"final_decision": "accept", "score": 5},
                "critic_attempts": [{"attempt": 1}],
            },
        }

    from app.services.openclaw_variant_generator import OpenClawVariantGenerator

    monkeypatch.setattr(
        OpenClawVariantGenerator, "_generate_hypotheses", fake_generate_hypotheses
    )
    monkeypatch.setattr(
        OpenClawVariantGenerator, "generate_mockup", fake_generate_mockup
    )

    main = importlib.import_module("app.main")

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        created = client.post(
            "/experiments",
            json={
                "name": "Generate variant",
                "mode": "variant_generation",
                "conversion_goal": "",
                "target_audience": "",
            },
        )
        assert created.status_code == 200
        experiment_id = created.json()["id"]
        assert created.json()["mode"] == "variant_generation"

        uploaded = client.post(
            f"/experiments/{experiment_id}/upload",
            files={"control": ("control.png", PNG_1X1, "image/png")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["challenger_image_path"] is None

        result = client.post(
            f"/experiments/{experiment_id}/run-generation",
            json={"batch_size": 3},
        )
        assert result.status_code == 200
        payload = result.json()
        assert payload["status"] == "hypotheses_ready"
        assert payload["runtime"] == "openclaw_gateway"
        assert payload["agent_response"]["status"] == "hypotheses_ready"
        assert payload["agent_response"]["agent"] == "openclaw_pipeline"
        assert len(payload["agent_response"]["hypotheses"]) == 1
        from pathlib import Path

        assert Path(payload["request_path"]).exists()
        assert Path(payload["response_path"]).exists()

        mockup = client.post(
            f"/experiments/{experiment_id}/generate-mockup",
            json={
                "selected_hypothesis": payload["agent_response"]["hypotheses"][0],
                "batch_size": 3,
            },
        )
        assert mockup.status_code == 200
        assert mockup.json()["status"] == "mockup_ready"
        assert Path(mockup.json()["challenger_image_path"]).exists()

        ab_run = client.post(
            f"/experiments/{experiment_id}/run",
            json={"num_personas": 3, "batch_size": 2, "early_stopping": False},
        )
        assert ab_run.status_code == 400

        approved = client.post(f"/experiments/{experiment_id}/approve-generated-variant")
        assert approved.status_code == 200
        assert approved.json()["mode"] == "ab_test"
