"""The committed OpenAPI schema, which the browser's types are generated from, is the server's."""

from __future__ import annotations

import pathlib

from countess_web import schema

COMMITTED = pathlib.Path(__file__).parent.parent / "frontend" / "openapi.json"


def test_the_committed_schema_is_the_servers() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == schema.render(), (
        "frontend/openapi.json is out of date: run `python -m countess_web.schema frontend/openapi.json`, "
        "then `npm run generate:api` in frontend/"
    )
