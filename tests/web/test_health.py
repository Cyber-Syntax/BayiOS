from __future__ import annotations

from fastapi.testclient import TestClient

from bayios.application.ports.health import HealthReport
from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_health_probe


class _FakeProbe:
    def __init__(self, report: HealthReport) -> None:
        self._report = report

    def check(self) -> HealthReport:
        return self._report


def _client(report: HealthReport) -> TestClient:
    settings = ApplicationSettings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
    )
    app = create_app(settings)
    app.dependency_overrides[get_health_probe] = lambda: _FakeProbe(report)
    return TestClient(app)


def test_health_reports_build_metadata(monkeypatch) -> None:
    monkeypatch.setenv("BAYIOS_BUILD_SHA", "abc1234")
    monkeypatch.setenv("BAYIOS_BUILD_TIME", "2026-11-25T20:00:00Z")

    report = HealthReport(
        database_ok=True,
        migrations_ok=True,
        current_revisions=("0021",),
        expected_revisions=("0021",),
    )
    response = _client(report).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["build"] == {
        "sha": "abc1234",
        "built_at": "2026-11-25T20:00:00Z",
    }


def test_health_mismatch_is_unavailable_and_keeps_build_metadata(monkeypatch) -> None:
    monkeypatch.setenv("BAYIOS_BUILD_SHA", "old9999")
    monkeypatch.setenv("BAYIOS_BUILD_TIME", "2026-11-24T20:00:00Z")

    report = HealthReport(
        database_ok=True,
        migrations_ok=False,
        current_revisions=("0019",),
        expected_revisions=("0021",),
    )
    response = _client(report).get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["migrations"]["status"] == "mismatch"
    assert body["build"]["sha"] == "old9999"
