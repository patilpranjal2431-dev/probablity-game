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


def test_menu_homepage_guest_session_and_background_asset(client: TestClient) -> None:
    home_res = client.get("/")
    assert home_res.status_code == 200
    assert "login-form" not in home_res.text
    assert "register-form" not in home_res.text
    assert "Live Table Lobby" in home_res.text
    assert "Order Book Market Making" in home_res.text
    assert "Quant &amp; Convergence Lab" in home_res.text

    css_res = client.get("/static/styles.css")
    assert css_res.status_code == 200
    bg_path = (
        "/assets/aistudio/the-dice-roll-chance-outcome-excitement-unpredictable-"
        "future-ideal-for-game-development-probability-destiny-themes-photo_319ba2b7.jpeg"
    )
    assert bg_path in css_res.text

    img_res = client.get(bg_path)
    assert img_res.status_code == 200
    assert img_res.headers["content-type"].startswith("image/jpeg")

    guest_res = client.post("/api/auth/guest")
    assert guest_res.status_code == 200
    assert guest_res.json()["balance"] == 1000
    assert client.get("/profile").status_code == 200
    assert client.get("/orderbook").status_code == 200

