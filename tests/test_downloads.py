"""A run's output files and a node's saved preview, on the server and downloaded through one-time links."""

from __future__ import annotations

import os
import pathlib
import re
import time

import fastapi.testclient

from conftest import TOKEN, load, settled
from countess_web.app import create_app
from countess_web.session import Session

RUN_SECONDS = 60


def finished_run(client: fastapi.testclient.TestClient) -> dict:
    client.post("/api/run")
    deadline = time.monotonic() + RUN_SECONDS
    while (run := client.get("/api/run").json())["running"]:
        assert time.monotonic() < deadline, "the run did not finish"
        time.sleep(0.1)
    assert run["returncode"] == 0
    return run


def data_lines(text: str) -> list[str]:
    """A CSV file's lines without its metadata header."""
    return [line for line in text.splitlines() if not line.startswith("#")]


def anonymous(client: fastapi.testclient.TestClient) -> fastapi.testclient.TestClient:
    """A client of the same server without the token, as a browser following a download link is."""
    return fastapi.testclient.TestClient(client.app)


# ---- run outputs --------------------------------------------------------------------------------


def test_a_run_lists_the_file_its_save_node_wrote(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    load(client, workdir)
    finished_run(client)

    [output] = client.get("/api/run/outputs").json()

    # in the run's own output directory, by default {date}_{time} for an unnamed workflow
    written = pathlib.Path(output["file"])
    assert output["node"] == "Save"
    assert (written.parent.parent, written.name) == (workdir, "totals.csv")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", written.parent.name)
    assert output["written"] is True


def test_a_run_output_downloads_through_its_link(
    client: fastapi.testclient.TestClient, session: Session, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    finished_run(client)

    link = client.post("/api/run/outputs/0/download").json()["url"]
    response = anonymous(client).get(f"/{link}")

    assert response.status_code == 200
    assert response.text.startswith("# CountESS ")
    assert data_lines(response.text) == ["variant,count__sum", "alpha,7", "beta,7", "gamma,1"]
    assert 'filename="totals.csv"' in response.headers["content-disposition"]


def test_a_download_link_works_once(
    client: fastapi.testclient.TestClient, session: Session, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    finished_run(client)
    link = client.post("/api/run/outputs/0/download").json()["url"]
    anonymous(client).get(f"/{link}")

    assert anonymous(client).get(f"/{link}").status_code == 404


def test_a_made_up_download_link_finds_nothing(session: Session) -> None:
    assert fastapi.testclient.TestClient(create_app(session, TOKEN)).get("/api/download/made-up").status_code == 404


def test_asking_for_a_download_link_needs_the_token(session: Session) -> None:
    client = fastapi.testclient.TestClient(create_app(session, TOKEN))

    assert client.post("/api/run/outputs/0/download").status_code == 401


def test_a_file_left_from_before_the_run_is_not_offered(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    client.patch("/api/workflow", json={"outputDir": "out"})
    stale = workdir / "out" / "totals.csv"
    stale.parent.mkdir()
    stale.write_text("old")
    os.utime(stale, (time.time() - 3600, time.time() - 3600))
    # Break the run so that it writes nothing: the Load node reads a file that is not there.
    (workdir / "counts.csv").unlink()
    client.post("/api/run")
    while client.get("/api/run").json()["running"]:
        time.sleep(0.1)

    [output] = client.get("/api/run/outputs").json()
    response = client.post("/api/run/outputs/0/download")

    assert output["written"] is False
    assert response.status_code == 400


def test_an_output_that_does_not_exist_is_refused(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    load(client, workdir)
    finished_run(client)

    assert client.post("/api/run/outputs/7/download").status_code == 400


# ---- previews -----------------------------------------------------------------------------------


def node_id(client: fastapi.testclient.TestClient, name: str) -> str:
    return next(n["id"] for n in client.get("/api/graph").json()["nodes"] if n["name"] == name)


def save_preview(client: fastapi.testclient.TestClient, name: str, overwrite: bool = False) -> fastapi.Response:
    return client.post(f"/api/nodes/{node_id(client, name)}/preview/save", json={"overwrite": overwrite})


def test_a_preview_is_saved_in_the_output_directory_in_its_sort_order(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)

    client.patch(f"/api/nodes/{node_id(client, 'Load')}", json={"sortColumn": 1, "sortDescending": True})
    saved = save_preview(client, "Load").json()

    path = pathlib.Path(saved["path"])
    assert (path.parent.parent, path.name) == (workdir, "load_preview.csv")
    assert data_lines(path.read_text()) == ["variant,count", "beta,5", "alpha,4", "alpha,3", "beta,2", "gamma,1"]
    assert "# preview: the 5 rows the node's preview held" in path.read_text()


def test_a_saved_preview_downloads_through_its_link_under_its_own_name(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)

    saved = save_preview(client, "Total").json()
    response = anonymous(client).get(f"/{saved['url']}")

    assert response.text == pathlib.Path(saved["path"]).read_text()
    assert 'filename="total_preview.csv"' in response.headers["content-disposition"]


def test_a_preview_is_not_saved_over_one_already_there_unless_asked(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)
    path = pathlib.Path(save_preview(client, "Load").json()["path"])
    path.write_text("mine")

    refused = save_preview(client, "Load")
    assert refused.status_code == 409
    assert "load_preview.csv is already there" in refused.json()["detail"]
    assert path.read_text() == "mine"

    assert save_preview(client, "Load", overwrite=True).status_code == 200
    assert path.read_text() != "mine"


def test_a_node_without_a_preview_has_nothing_to_save(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)

    assert save_preview(client, "Save").status_code == 400


def test_the_metadata_header_can_be_turned_off_for_the_workflow(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    client.patch("/api/workflow", json={"metadataHeader": False})
    settled(client)

    path = pathlib.Path(save_preview(client, "Load").json()["path"])

    assert path.read_text().startswith("variant,count\n")


# ---- names from the workflow ----------------------------------------------------------------------


def name_workflow(client: fastapi.testclient.TestClient) -> None:
    response = client.patch("/api/workflow", json={"name": "FWD test", "version": "1.2.0"})
    assert response.status_code == 200, response.text


def test_a_run_log_downloads_whole_as_run_log_txt(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    load(client, workdir)
    finished_run(client)

    link = client.post("/api/run/log/download").json()["url"]
    response = anonymous(client).get(f"/{link}")

    assert 'filename="run-log.txt"' in response.headers["content-disposition"]
    assert "Finished" in response.text


def test_a_named_workflows_run_writes_into_a_directory_named_from_it(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    ids = load(client, workdir)
    name_workflow(client)
    save = client.post("/api/nodes", json={"position": [0.9, 0.9], "plugin": "countess.plugins.csv:SaveCsvPlugin"})
    save_id = save.json()["id"]
    client.patch(f"/api/nodes/{save_id}", json={"name": "Save Totals"})
    client.post("/api/edges", json={"parent": ids["Total"], "child": save_id})
    finished_run(client)

    outputs = {o["node"]: o for o in client.get("/api/run/outputs").json()}

    written = pathlib.Path(outputs["Save Totals"]["file"])
    assert written.name == "results.csv"
    assert written.parent.parent == workdir
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_fwd-test_v1-2-0", written.parent.name)
    assert outputs["Save Totals"]["written"] is True
    assert outputs["Save"]["file"] == str(written.parent / "totals.csv")


def test_a_run_whose_output_directory_cannot_be_named_says_why(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    client.patch("/api/workflow", json={"outputDir": "{workflow}"})
    client.post("/api/run")
    while client.get("/api/run").json()["running"]:
        time.sleep(0.1)

    [output] = client.get("/api/run/outputs").json()

    assert (output["file"], output["written"]) == ("", False)
    assert "gives no directory" in output["error"]
