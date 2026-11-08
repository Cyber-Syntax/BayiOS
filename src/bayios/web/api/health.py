from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from bayios.application.ports.health import HealthProbe
from bayios.web.deps import get_health_probe

router = APIRouter()


@router.get("/health")
def health(probe: Annotated[HealthProbe, Depends(get_health_probe)]) -> JSONResponse:
    report = probe.check()
    if not report.database_ok:
        migrations_status = "unknown"
    elif report.migrations_ok:
        migrations_status = "ok"
    else:
        migrations_status = "mismatch"

    body = {
        "status": "ok" if report.healthy else "unavailable",
        "database": "ok" if report.database_ok else "unreachable",
        "migrations": {
            "status": migrations_status,
            "current": list(report.current_revisions),
            "expected": list(report.expected_revisions),
        },
    }
    return JSONResponse(body, status_code=200 if report.healthy else 503)
