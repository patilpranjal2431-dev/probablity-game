"""Tests for documentation routes and Phase 9 repository docs."""

from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_docs_pages_and_openapi_routes(client: TestClient) -> None:
    docs_res = client.get("/docs")
    assert docs_res.status_code == 200
    assert "Algorithms in Plain Language" in docs_res.text
    assert "Dynamic Programming" in docs_res.text
    assert "Adverse Selection" in docs_res.text

    algo_res = client.get("/algorithms")
    assert algo_res.status_code == 200
    assert "Brier Score" in algo_res.text

    openapi_res = client.get("/api/docs")
    assert openapi_res.status_code == 200
    assert "SwaggerUIBundle" in openapi_res.text


def test_required_project_documentation_files_exist() -> None:
    required = [
        "README.md",
        "SECURITY.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "docs/index.html",
        "docs/algorithms.md",
        "docs/assets/architecture.svg",
        "docs/assets/quant_lab.svg",
        "docs/assets/bankroll.svg",
        "docs/assets/orderbook.svg",
    ]
    for rel_path in required:
        file_path = ROOT_DIR / rel_path
        assert file_path.is_file(), f"Missing documentation artifact: {rel_path}"
        assert file_path.stat().st_size > 100, f"Documentation file unexpectedly empty: {rel_path}"

    readme_text = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
    expected_headings = (
        "## What It Shows",
        "## Architecture Diagram",
        "## How to Run",
        "## The Maths Used",
        "## Limitations",
    )
    for heading in expected_headings:
        assert heading in readme_text
