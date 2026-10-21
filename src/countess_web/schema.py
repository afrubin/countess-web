"""Writes the API's OpenAPI schema, which the browser's types are generated from.

    python -m countess_web.schema frontend/openapi.json

then, in frontend/, ``npm run generate:api``. tests/test_schema.py fails if the committed schema
is not what the server's routes and models describe.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from typing import Any

from countess_web.app import create_app
from countess_web.session import Session


def openapi() -> dict[str, Any]:
    session = Session(pathlib.Path(tempfile.gettempdir()))
    try:
        return create_app(session, "unused").openapi()
    finally:
        session.close()


def render() -> str:
    return json.dumps(openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m countess_web.schema OUTPUT.json")
    pathlib.Path(sys.argv[1]).write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
