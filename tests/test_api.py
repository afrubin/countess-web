"""The HTTP API, driven as the browser drives it, over a pipeline of CountESS's own plugins:
Load (counts.csv) -> Total (Group By variant, sum count) -> Save (totals.csv)."""

from __future__ import annotations

import pathlib
import time

import fastapi.testclient

from conftest import load, preview_rows, settled

# ---- pipelines ----------------------------------------------------------------------------------


def test_a_loaded_pipeline_is_described_with_its_edges(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    nodes = {n["name"]: n for n in client.get("/api/graph").json()["nodes"]}

    assert set(nodes) == {"Load", "Total", "Save"}
    assert nodes["Total"]["parents"] == [ids["Load"]]
    assert nodes["Total"]["plugin"]["name"] == "Group By"


def test_a_loaded_pipeline_previews_each_nodes_result(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    rows = preview_rows(client, ids["Total"])

    assert rows == [["alpha", 7], ["beta", 7], ["gamma", 1]]


def test_a_preview_is_sorted_by_its_first_column_unless_told_otherwise(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    rows = preview_rows(client, ids["Load"])

    # CountESS's GUI sorts by column 0, then by the others: alpha 3 before alpha 4.
    assert rows == [["alpha", 3], ["alpha", 4], ["beta", 2], ["beta", 5], ["gamma", 1]]


def test_a_preview_pages_in_the_nodes_sort_order(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    ids = load(client, workdir)
    client.patch(f"/api/nodes/{ids['Load']}", json={"sortColumn": 1, "sortDescending": True})

    rows = preview_rows(client, ids["Load"], offset=1, limit=2)

    assert rows == [["alpha", 4], ["alpha", 3]]


def test_a_nodes_preview_sort_is_saved_with_the_pipeline(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    client.patch(f"/api/nodes/{ids['Load']}", json={"sortColumn": 1, "sortDescending": True})
    client.post("/api/config/save", json={})

    assert "_sort = 1 1" in (workdir / "pipeline.ini").read_text().split("[Total]")[0]


def test_a_changed_parameter_recalculates_the_preview(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)
    settled(client)

    response = client.post(f"/api/nodes/{ids['Total']}/parameters", json={"path": "columns.1.sum", "value": False})
    assert response.status_code == 200, response.text
    client.post(f"/api/nodes/{ids['Total']}/parameters", json={"path": "columns.1.max", "value": True})

    assert preview_rows(client, ids["Total"]) == [["alpha", 4], ["beta", 5], ["gamma", 1]]


def test_a_parameter_is_described_by_the_path_its_ini_key_uses(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)
    settled(client)

    parameters = client.get(f"/api/nodes/{ids['Load']}/parameters").json()

    by_path = {p["path"]: p for p in parameters}
    assert (by_path["header"]["kind"], by_path["header"]["value"]) == ("boolean", True)
    first_column_name = by_path["columns"]["items"][0]["children"][0]
    assert (first_column_name["path"], first_column_name["value"]) == ("columns.0.name", "variant")


def test_a_parameter_that_does_not_exist_is_refused(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    response = client.post(f"/api/nodes/{ids['Total']}/parameters", json={"path": "columns.99.sum", "value": True})

    assert response.status_code == 400
    assert "no such parameter" in response.json()["detail"]


def test_a_row_can_be_added_to_and_deleted_from_a_list(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)
    path = f"/api/nodes/{ids['Save']}/parameters"

    added = client.post(path, json={"path": "sorting", "action": "add"}).json()
    client.post(path, json={"path": "sorting.1.order_by", "value": "count__sum"})
    deleted = client.post(path, json={"path": "sorting", "action": "delete", "index": 0}).json()

    assert len({p["path"]: p for p in added}["sorting"]["items"]) == 2
    [remaining] = {p["path"]: p for p in deleted}["sorting"]["items"]
    assert remaining["children"][0]["selected"] == "count__sum"


def test_a_new_node_with_a_plugin_joins_the_pipeline(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    node = client.post(
        "/api/nodes", json={"position": [0.5, 0.8], "plugin": "countess.plugins.expression:ExpressionPlugin"}
    ).json()
    response = client.post("/api/edges", json={"parent": ids["Load"], "child": node["id"]})
    client.post(f"/api/nodes/{node['id']}/parameters", json={"path": "code", "value": "double = count * 2"})
    client.patch(f"/api/nodes/{node['id']}", json={"sortColumn": 2})

    assert response.status_code == 200, response.text
    assert preview_rows(client, node["id"])[-1] == ["beta", 5, 10]


def test_an_edge_that_would_make_a_loop_is_refused(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    response = client.post("/api/edges", json={"parent": ids["Total"], "child": ids["Load"]})

    assert response.status_code == 400
    assert "loop" in response.json()["detail"]


def test_a_removed_edge_leaves_the_child_without_input(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    client.delete("/api/edges", params={"parent": ids["Load"], "child": ids["Total"]})

    nodes = {n["name"]: n for n in client.get("/api/graph").json()["nodes"]}
    assert nodes["Total"]["parents"] == []


def test_a_renamed_node_keeps_its_name_unique(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    ids = load(client, workdir)

    renamed = client.patch(f"/api/nodes/{ids['Total']}", json={"name": "Load"}).json()

    assert renamed["name"] != "Load"
    assert renamed["name"].startswith("Load")


def test_a_saved_pipeline_loads_back_with_its_changes(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)
    client.post(f"/api/nodes/{ids['Save']}/parameters", json={"path": "filename", "value": "other.csv"})

    client.post("/api/config/save", json={"path": str(workdir / "saved.ini")})
    reloaded = load_path(client, workdir / "saved.ini")

    save = client.get(f"/api/nodes/{reloaded['Save']}/parameters").json()
    assert {p["path"]: p for p in save}["filename"]["value"] == "other.csv"


def load_path(client: fastapi.testclient.TestClient, path: pathlib.Path) -> dict[str, str]:
    response = client.post("/api/config/load", json={"path": str(path)})
    assert response.status_code == 200, response.text
    return {n["name"]: n["id"] for n in response.json()["nodes"]}


def test_loading_a_file_that_is_not_there_is_refused(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    response = client.post("/api/config/load", json={"path": str(workdir / "missing.ini")})

    assert response.status_code == 400


# ---- runs ---------------------------------------------------------------------------------------


def test_a_run_writes_the_pipelines_output(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    load(client, workdir)
    client.patch("/api/workflow", json={"outputDir": "out", "metadataHeader": False})

    client.post("/api/run")
    deadline = time.monotonic() + 60
    while (run := client.get("/api/run").json())["running"] and time.monotonic() < deadline:
        time.sleep(0.1)

    assert run["returncode"] == 0
    assert (workdir / "out" / "totals.csv").read_text().splitlines() == [
        "variant,count__sum",
        "alpha,7",
        "beta,7",
        "gamma,1",
    ]


# ---- files --------------------------------------------------------------------------------------


def test_the_file_list_shows_directories_and_matching_files(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    (workdir / "sub").mkdir()
    (workdir / ".hidden.csv").write_text("x")

    listing = client.get("/api/files", params={"path": str(workdir), "patterns": "*.csv"}).json()

    assert [(e["name"], e["isDir"]) for e in listing["entries"]] == [("sub", True), ("counts.csv", False)]


def test_a_file_parameter_offers_its_extensions_as_globs_and_all_files(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)

    files = {p["path"]: p for p in client.get(f"/api/nodes/{ids['Load']}/parameters").json()}["files"]

    assert files["fileTypes"][0] == {"label": "CSV", "patterns": ["*.csv", "*.csv.gz", "*.csv.bz2"]}
    assert files["fileTypes"][-1] == {"label": "All files", "patterns": ["*"]}
