"""Integration tests for /api/quant/* endpoints and /lab page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_exact_quant_endpoints(client: TestClient) -> None:
    dice_res = client.get("/api/quant/exact/dice-sum?num_dice=2&num_sides=6")
    assert dice_res.status_code == 200
    dice_data = dice_res.json()
    assert dice_data["total_outcomes"] == 36
    sum_7 = next(item for item in dice_data["outcomes"] if item["total"] == 7)
    assert sum_7["count"] == 6
    assert sum_7["probability"] == pytest.approx(1 / 6)

    poker_res = client.get("/api/quant/exact/poker")
    assert poker_res.status_code == 200
    poker_data = poker_res.json()
    assert poker_data["total_hands"] == 2_598_960
    assert sum(item["count"] for item in poker_data["hands"]) == 2_598_960

    hyper_res = client.get("/api/quant/exact/hypergeometric?N=52&K=4&n=5&k=1")
    assert hyper_res.status_code == 200
    hyper_data = hyper_res.json()
    assert hyper_data["at_least"] == pytest.approx(1.0 - hyper_data["distribution"]["0"])

    bday_res = client.get("/api/quant/exact/birthday?num_people=23&num_days=365")
    assert bday_res.status_code == 200
    assert bday_res.json()["collision_probability"] == pytest.approx(0.5072972343)


def test_convergence_endpoint_and_validation(client: TestClient) -> None:
    res = client.post(
        "/api/quant/convergence",
        json={
            "problem": "birthday_23",
            "sample_sizes": [50, 200, 1000],
            "seed": 42,
            "trials_per_run": 200,
            "num_experiments": 100,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["exact_probability"] == pytest.approx(0.5072972343)
    assert len(data["points"]) == 3
    assert 0.85 <= data["coverage"]["empirical_coverage"] <= 1.0

    bad_problem = client.post("/api/quant/convergence", json={"problem": "unknown"})
    assert bad_problem.status_code == 422

    bad_n = client.post(
        "/api/quant/convergence",
        json={"problem": "birthday_23", "sample_sizes": [10, 999_999]},
    )
    assert bad_n.status_code == 422


def test_lab_html_page_serves_successfully(client: TestClient) -> None:
    res = client.get("/lab")
    assert res.status_code == 200
    assert "Log-Log Scale" in res.text
    assert "2,598,960" in res.text
