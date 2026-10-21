"""Fixtures for driving the API as the browser does, over a pipeline of CountESS's own plugins:
Load (counts.csv) -> Total (Group By variant, sum count) -> Save (totals.csv)."""

from __future__ import annotations

import pathlib
import shutil
import time
from collections.abc import Iterator
from typing import Any

import fastapi.testclient
import pytest

from countess_web.app import TOKEN_HEADER, create_app
from countess_web.session import Session

DATA = pathlib.Path(__file__).parent / "data"
TOKEN = "test-token"
SETTLE_SECONDS = 30


@pytest.fixture
def workdir(tmp_path: pathlib.Path) -> pathlib.Path:
    for name in ("counts.csv", "pipeline.ini"):
        shutil.copy(DATA / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def session(workdir: pathlib.Path) -> Iterator[Session]:
    session = Session(workdir)
    yield session
    session.close()


@pytest.fixture
def client(session: Session) -> fastapi.testclient.TestClient:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))
    client.headers[TOKEN_HEADER] = TOKEN
    return client


def load(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> dict[str, str]:
    """Loads the test pipeline; the node ids by name."""
    response = client.post("/api/config/load", json={"path": str(workdir / "pipeline.ini")})
    assert response.status_code == 200, response.text
    return {n["name"]: n["id"] for n in response.json()["nodes"]}


def settled(client: fastapi.testclient.TestClient) -> dict[str, Any]:
    """The graph once the preview thread has finished with every node."""
    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline:
        graph = client.get("/api/graph").json()
        if all(n["status"] not in ("DIRTY", "WORKING") for n in graph["nodes"]):
            return graph
        time.sleep(0.05)
    raise AssertionError(f"the preview did not settle in {SETTLE_SECONDS}s")


def preview_rows(
    client: fastapi.testclient.TestClient, node_id: str, offset: int = 0, limit: int = 100
) -> list[list[Any]]:
    settled(client)
    response = client.get(f"/api/nodes/{node_id}/preview", params={"offset": offset, "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()["rows"]


def add_plugin_node(client: fastapi.testclient.TestClient, plugin: str) -> str:
    response = client.post("/api/nodes", json={"position": [0.5, 0.5], "plugin": plugin})
    assert response.status_code == 200, response.text
    return response.json()["id"]
