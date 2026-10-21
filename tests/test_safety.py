"""Who may use the API, and the inputs it refuses because a saved pipeline could not hold them."""

from __future__ import annotations

import pathlib
import time

import duckdb
import fastapi.testclient
import pytest
from countess.core.pipeline import PipelineNode
from countess.core.plugins import DuckdbInputPlugin

from conftest import TOKEN, add_plugin_node, load, preview_rows
from countess_web.app import TOKEN_HEADER, create_app
from countess_web.session import Session

# ---- the token ----------------------------------------------------------------------------------


def test_the_api_refuses_a_request_without_the_token(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    assert client.get("/api/graph").status_code == 401


def test_the_api_refuses_a_wrong_token(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    assert client.get("/api/graph", headers={TOKEN_HEADER: "not-the-token"}).status_code == 401


def test_the_api_accepts_the_token_in_its_header(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    assert client.get("/api/graph", headers={TOKEN_HEADER: TOKEN}).status_code == 200


def test_the_api_ignores_the_token_offered_as_a_cookie(session: Session) -> None:
    # Browsers send a localhost cookie to every local port, so a cookie must not carry the token.
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))
    client.cookies.set("countess_web_token", TOKEN)

    assert client.get("/api/graph").status_code == 401


def test_the_api_refuses_a_token_that_is_not_ascii(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    assert client.get("/api/graph", headers={TOKEN_HEADER: "tokén".encode()}).status_code == 401


def test_the_page_itself_needs_no_token(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    assert client.get("/").status_code != 401


def test_the_event_socket_closes_a_connection_that_sends_a_wrong_token(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    with client.websocket_connect("/api/events") as socket:
        socket.send_json({"token": "not-the-token"})
        with pytest.raises(fastapi.WebSocketDisconnect) as closed:
            socket.receive_json()

    assert closed.value.code == 4401


def test_the_event_socket_sends_the_pipelines_state_once_given_the_token(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    with client.websocket_connect("/api/events") as socket:
        socket.send_json({"token": TOKEN})
        first = socket.receive_json()

    assert first["type"] == "state"


# ---- values a saved pipeline could not hold -----------------------------------------------------


@pytest.mark.parametrize("raw", ["1e999", "-1e999"])
def test_a_number_too_large_to_save_is_refused_and_the_old_value_kept(
    client: fastapi.testclient.TestClient, raw: str
) -> None:
    node = add_plugin_node(client, "countess.plugins.fastq:LoadFastqPlugin")

    response = client.post(
        f"/api/nodes/{node}/parameters",
        content=f'{{"path": "min_avg_quality", "value": {raw}}}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    parameters = {p["path"]: p for p in client.get(f"/api/nodes/{node}/parameters").json()}
    assert parameters["min_avg_quality"]["value"] == 10


def test_typed_text_that_reads_as_infinity_leaves_the_value_unchanged(client: fastapi.testclient.TestClient) -> None:
    node = add_plugin_node(client, "countess.plugins.fastq:LoadFastqPlugin")

    response = client.post(f"/api/nodes/{node}/parameters", json={"path": "min_avg_quality", "value": "inf"})

    assert {p["path"]: p for p in response.json()}["min_avg_quality"]["value"] == 10


def test_an_integer_parameter_given_infinity_is_refused_not_a_server_error(
    client: fastapi.testclient.TestClient,
) -> None:
    node = add_plugin_node(client, "countess.plugins.variant:VariantConverter")

    response = client.post(
        f"/api/nodes/{node}/parameters",
        content='{"path": "offset", "value": 1e999}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


@pytest.mark.parametrize("name", ["two\nlines", "has ] bracket", "[bracket", "DEFAULT", "default", "   "])
def test_a_node_name_a_saved_pipeline_cannot_hold_is_refused(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path, name: str
) -> None:
    ids = load(client, workdir)

    response = client.patch(f"/api/nodes/{ids['Total']}", json={"name": name})

    assert response.status_code == 400


def test_a_position_outside_the_canvas_is_kept_on_it(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    node = client.patch(f"/api/nodes/{ids['Total']}", json={"position": [-0.25, 1.5]}).json()

    assert node["position"] == [0.0, 1.0]


def test_a_position_that_is_not_finite_is_refused(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    ids = load(client, workdir)

    response = client.patch(
        f"/api/nodes/{ids['Total']}", content='{"position": [1e999, 0.5]}', headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400


def test_a_file_list_takes_chosen_files_not_an_empty_row(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    response = client.post(f"/api/nodes/{ids['Load']}/parameters", json={"path": "files", "action": "add"})

    assert response.status_code == 400


# ---- previews -----------------------------------------------------------------------------------


def test_a_column_with_time_zones_is_previewed_as_text(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    (workdir / "times.csv").write_text("event,at\nstart,2024-01-02 03:04:05+02:00\n")
    node = add_plugin_node(client, "countess.plugins.csv:LoadCsvPlugin")
    client.post(
        f"/api/nodes/{node}/parameters",
        json={"path": "files", "action": "addFiles", "paths": [str(workdir / "times.csv")]},
    )

    rows = preview_rows(client, node)
    columns = client.get(f"/api/nodes/{node}/preview").json()["columns"]

    assert columns[1]["type"] == "TIMESTAMP WITH TIME ZONE"
    assert rows[0][0] == "start"
    assert isinstance(rows[0][1], str)


# ---- the preview thread and the graph's lifetime -------------------------------------------------

SLOW_NODE_SECONDS = 1.0


class SlowPlugin(DuckdbInputPlugin):
    """A node whose preview takes a second, outside any DuckDB query an interrupt could stop."""

    name = "Slow"
    version = "0"

    def execute(self, ddbc: duckdb.DuckDBPyConnection, source: None, row_limit: int | None = None):  # type: ignore[override]
        time.sleep(SLOW_NODE_SECONDS)
        return ddbc.sql("SELECT 1 AS one")


def test_a_change_made_during_a_preview_does_not_wait_for_the_rest_of_it(session: Session) -> None:
    with session.change():
        for n in range(4):
            session.graph.add_node(PipelineNode(name=f"slow {n}", plugin=SlowPlugin()))
    time.sleep(0.2)
    renamed = session.graph.nodes[3].uuid

    started = time.monotonic()
    session.update_node(renamed, name="renamed")
    elapsed = time.monotonic() - started

    # Stopping waits for the node running now; CountESS's own loop would also run the other dirty nodes.
    assert elapsed < 2 * SLOW_NODE_SECONDS


def test_loading_a_pipeline_closes_the_previous_pipelines_database(session: Session, workdir: pathlib.Path) -> None:
    previous = session.graph

    session.load(str(workdir / "pipeline.ini"))

    with pytest.raises(duckdb.ConnectionException):
        previous.ddbc.sql("SELECT 1")


def test_a_loaded_pipeline_has_each_list_parameter_once(session: Session, workdir: pathlib.Path) -> None:
    session.load(str(workdir / "pipeline.ini"))

    load_node = next(n for n in session.graph.nodes if n.name == "Load")

    # Applied before the preview thread starts, so the thread cannot apply it a second time.
    assert load_node.config == []
    assert len(load_node.plugin.columns) == 2


# ---- the workflow's name and version ------------------------------------------------------------


def test_the_workflow_name_and_version_are_saved_with_the_pipeline(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)

    graph = client.patch("/api/workflow", json={"name": "FWD test", "version": "1.2.0"}).json()
    client.post("/api/config/save", json={})

    assert graph["workflow"] == {"name": "FWD test", "version": "1.2.0"}
    assert "[_workflow]\nname = FWD test\nversion = 1.2.0" in (workdir / "pipeline.ini").read_text()


def test_a_version_that_is_not_semantic_is_refused(client: fastapi.testclient.TestClient) -> None:
    response = client.patch("/api/workflow", json={"name": "FWD test", "version": "1.2"})

    assert response.status_code == 400
    assert "semantic version" in response.json()["detail"]


def test_a_save_path_is_described_with_the_file_it_names_now(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    client.patch("/api/workflow", json={"name": "FWD test", "version": "1.2.0"})
    node = add_plugin_node(client, "countess.plugins.csv:SaveCsvPlugin")

    filename = {p["path"]: p for p in client.get(f"/api/nodes/{node}/parameters").json()}["filename"]

    assert filename["kind"] == "save-file"
    assert filename["value"] == "{date}_{workflow}_{version}_{node}.csv"
    assert filename["filled"].startswith(str(workdir))
    assert filename["filled"].endswith("_fwd-test_v1-2-0_csv-save.csv")
    assert "node" in [field["name"] for field in filename["fields"]]


def test_a_save_path_template_that_cannot_be_filled_says_why(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    node = add_plugin_node(client, "countess.plugins.csv:SaveCsvPlugin")

    described = client.post(f"/api/nodes/{node}/parameters", json={"path": "filename", "value": "{nope}.csv"}).json()

    filename = {p["path"]: p for p in described}["filename"]
    assert filename["filled"] is None
    assert "unknown field {nope}" in filename["templateError"]


def test_an_integer_a_browser_cannot_hold_exactly_is_previewed_as_text(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    (workdir / "big.csv").write_text("name,count\nsmall,9007199254740991\nbig,9007199254740993\n")
    node = add_plugin_node(client, "countess.plugins.csv:LoadCsvPlugin")
    client.post(
        f"/api/nodes/{node}/parameters",
        json={"path": "files", "action": "addFiles", "paths": [str(workdir / "big.csv")]},
    )

    rows = preview_rows(client, node)

    assert rows == [["big", "9007199254740993"], ["small", 9007199254740991]]
