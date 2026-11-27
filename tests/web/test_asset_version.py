from __future__ import annotations

import re

from fastapi.testclient import TestClient

from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web import templating
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork

_ASSET_URL = re.compile(r"/static/css/app\.css\?v=([^\"]+)")


def _asset_version_in(html: str) -> str:
    match = _ASSET_URL.search(html)
    assert match is not None, "app.css link missing from rendered page"
    return match.group(1)


def test_page_asset_version_tracks_static_changes(tmp_path, monkeypatch) -> None:
    """The ?v= URL is computed per request, not frozen when the module imports.

    A phone keeps the stylesheet of a previously seen ?v= URL; if the version
    never changes after a CSS edit, layout fixes never reach the device.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "app.css").write_text("/* first version */", encoding="utf-8")
    monkeypatch.setattr(templating, "STATIC_DIR", static_dir)

    fake_uow = FakeUnitOfWork()
    app = create_app(
        ApplicationSettings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
        )
    )
    app.dependency_overrides[get_unit_of_work] = lambda: fake_uow
    client = TestClient(app)

    first = _asset_version_in(client.get("/offers/new").text)
    (static_dir / "app.css").write_text("/* second, longer version */", encoding="utf-8")
    second = _asset_version_in(client.get("/offers/new").text)

    assert first != second
