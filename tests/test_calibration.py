"""Unit and integration tests for the server-authoritative Calibration & Brier Score game."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_SESSION_COOKIE_NAME
from app.games.rng import SeededRNG
from app.quant.calibration import (
    compute_brier_score,
    generate_calibration_prompt,
    summarize_calibration_history,
)


def _register_and_get_cookie(client: TestClient, username: str) -> str:
    client.cookies.clear()
    res = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert res.status_code == 201
    cookie = res.cookies.get(DEFAULT_SESSION_COOKIE_NAME)
    assert cookie is not None
    client.cookies.clear()
    return cookie


def test_brier_score_and_prompt_generation_math() -> None:
    assert compute_brier_score(0.80, True) == pytest.approx(0.04)
    assert compute_brier_score(0.80, False) == pytest.approx(0.64)
    assert compute_brier_score(0.50, False) == pytest.approx(0.25)

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        compute_brier_score(1.2, True)

    rng = SeededRNG(123)
    seen_categories: set[str] = set()
    for _ in range(40):
        prompt = generate_calibration_prompt(rng)
        seen_categories.add(prompt.category)
        assert 0.0 <= prompt.true_probability <= 1.0
        assert isinstance(prompt.actual_outcome, bool)
        assert len(prompt.question_text) > 15
        assert len(prompt.explanation) > 10

    assert len(seen_categories) == 5

    mean_brier, mean_abs_err, points, bins = summarize_calibration_history(
        [
            (1, "dice_sum_at_least", 0.70, 0.58, True, 0.09),
            (2, "birthday_collision", 0.50, 0.507, False, 0.25),
        ]
    )
    assert mean_brier == pytest.approx(0.17)
    assert mean_abs_err == pytest.approx((0.12 + 0.007) / 2, abs=1e-4)
    assert points[0].cumulative_mean_brier == pytest.approx(0.09)
    assert points[1].cumulative_mean_brier == pytest.approx(0.17)
    assert len(bins) == 2


def test_calibration_api_auth_privacy_and_brier_history(client: TestClient) -> None:
    # Unauthenticated access rejected
    assert client.post("/api/calibration/prompts").status_code == 401
    assert client.get("/api/calibration/history").status_code == 401
    assert client.get("/calibration", follow_redirects=False).status_code == 302

    c1 = _register_and_get_cookie(client, "cal_user1")
    c2 = _register_and_get_cookie(client, "cal_user2")

    # Authenticated page renders
    page_res = client.get("/calibration", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert page_res.status_code == 200
    assert "Probability Calibration" in page_res.text

    # Prompt never leaks hidden actual_outcome or true_probability;
    # re-request returns same pending ID.
    p1 = client.post("/api/calibration/prompts", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert p1.status_code == 201
    p1_data = p1.json()
    assert "actual_outcome" not in p1_data
    assert "true_probability" not in p1_data

    p1_again = client.post("/api/calibration/prompts", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert p1_again.json()["id"] == p1_data["id"]

    # Another user cannot answer User 1's prompt
    forbidden = client.post(
        f"/api/calibration/prompts/{p1_data['id']}/guess",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c2},
        json={"estimated_prob": 0.5},
    )
    assert forbidden.status_code == 403

    # Out-of-bounds guess rejected
    invalid = client.post(
        f"/api/calibration/prompts/{p1_data['id']}/guess",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"estimated_prob": 1.5},
    )
    assert invalid.status_code == 422

    # Valid guess scores Brier error and blocks duplicate submissions
    g1 = client.post(
        f"/api/calibration/prompts/{p1_data['id']}/guess",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"estimated_prob": 0.65},
    )
    assert g1.status_code == 200
    r1 = g1.json()
    expected_brier_1 = (0.65 - (1.0 if r1["actual_outcome"] else 0.0)) ** 2
    assert r1["brier_score"] == pytest.approx(expected_brier_1, abs=1e-5)

    dup = client.post(
        f"/api/calibration/prompts/{p1_data['id']}/guess",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"estimated_prob": 0.65},
    )
    assert dup.status_code == 409

    # Play a second round and verify cumulative Brier time-series in /history
    p2 = client.post("/api/calibration/prompts", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert p2.status_code == 201
    p2_id = p2.json()["id"]
    assert p2_id != p1_data["id"]
    g2 = client.post(
        f"/api/calibration/prompts/{p2_id}/guess",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"estimated_prob": 0.30},
    )
    assert g2.status_code == 200
    r2 = g2.json()

    hist = client.get("/api/calibration/history", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert hist.status_code == 200
    h = hist.json()
    assert h["pending_prompt"] is None
    assert h["rounds_answered"] == 2
    expected_mean = (r1["brier_score"] + r2["brier_score"]) / 2.0
    assert h["mean_brier_score"] == pytest.approx(expected_mean, abs=1e-3)
    assert [pt["round_number"] for pt in h["points"]] == [1, 2]
    assert h["points"][1]["cumulative_mean_brier"] == pytest.approx(expected_mean, abs=1e-3)
    assert sum(b["count"] for b in h["bins"]) == 2
