"""Downloading a run's output files and a node's preview, through one-time links."""

from __future__ import annotations

import os
import pathlib
import re
import time

import fastapi.testclient
import pytest

from conftest import TOKEN, load, settled
from countess_web import app as app_module
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


def anonymous(client: fastapi.testclient.TestClient) -> fastapi.testclient.TestClient:
    """A client of the same server without the token, as a browser following a download link is."""
    return fastapi.testclient.TestClient(client.app)


# ---- run outputs --------------------------------------------------------------------------------


def test_a_run_lists_the_file_its_save_node_wrote(client: fastapi.testclient.TestClient, workdir: pathlib.Path) -> None:
    load(client, workdir)
    finished_run(client)

    [output] = client.get("/api/run/outputs").json()

    assert output["node"] == "Save"
    assert output["file"] == str(workdir / "totals.csv")
    assert output["written"] is True


def test_a_run_output_downloads_through_its_link(
    client: fastapi.testclient.TestClient, session: Session, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    finished_run(client)

    link = client.post("/api/run/outputs/0/download").json()["url"]
    response = anonymous(client).get(f"/{link}")

    assert response.status_code == 200
    assert response.text.splitlines() == ["variant,count__sum", "alpha,7", "beta,7", "gamma,1"]
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
    stale = workdir / "totals.csv"
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


def test_a_preview_downloads_as_csv_in_its_sort_order(
    client: fastapi.testclient.TestClient, session: Session, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)

    made = client.post(
        f"/api/nodes/{node_id(client, 'Load')}/preview/download", json={"sort": "count", "descending": True}
    )
    response = anonymous(client).get(f"/{made.json()['url']}")

    assert made.json()["rows"] == 5
    assert response.text.splitlines() == ["variant,count", "beta,5", "alpha,4", "alpha,3", "beta,2", "gamma,1"]
    assert re.search(r'filename="\d{4}-\d{2}-\d{2}_load-preview\.csv"', response.headers["content-disposition"])


def test_a_downloaded_preview_leaves_no_file_behind(
    client: fastapi.testclient.TestClient, session: Session, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)

    link = client.post(f"/api/nodes/{node_id(client, 'Load')}/preview/download", json={}).json()["url"]
    anonymous(client).get(f"/{link}")

    assert list(session.state_dir.glob("preview-*.csv")) == []


def test_an_expired_preview_link_finds_nothing_and_leaves_no_file_behind(
    client: fastapi.testclient.TestClient,
    session: Session,
    workdir: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load(client, workdir)
    settled(client)
    monkeypatch.setattr(app_module, "DOWNLOAD_LINK_SECONDS", -1.0)

    link = client.post(f"/api/nodes/{node_id(client, 'Load')}/preview/download", json={}).json()["url"]
    response = anonymous(client).get(f"/{link}")

    assert response.status_code == 404
    assert list(session.state_dir.glob("preview-*.csv")) == []


def test_a_node_without_a_preview_has_nothing_to_download(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    settled(client)

    response = client.post(f"/api/nodes/{node_id(client, 'Save')}/preview/download", json={})

    assert response.status_code == 400


# ---- names from the workflow ----------------------------------------------------------------------


def name_workflow(client: fastapi.testclient.TestClient) -> None:
    response = client.patch("/api/workflow", json={"name": "FWD test", "version": "1.2.0"})
    assert response.status_code == 200, response.text


def test_a_preview_download_is_named_from_the_date_workflow_and_node(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    name_workflow(client)
    settled(client)

    link = client.post(f"/api/nodes/{node_id(client, 'Total')}/preview/download", json={}).json()["url"]
    disposition = anonymous(client).get(f"/{link}").headers["content-disposition"]

    assert re.search(r'filename="\d{4}-\d{2}-\d{2}_fwd-test_v1-2-0_total-preview\.csv"', disposition)


def test_a_run_log_downloads_whole_with_a_name_from_the_workflow(
    client: fastapi.testclient.TestClient, workdir: pathlib.Path
) -> None:
    load(client, workdir)
    name_workflow(client)
    finished_run(client)

    link = client.post("/api/run/log/download").json()["url"]
    response = anonymous(client).get(f"/{link}")

    assert re.search(
        r'filename="\d{4}-\d{2}-\d{2}_fwd-test_v1-2-0_run-log\.txt"', response.headers["content-disposition"]
    )
    assert "Finished" in response.text


def test_a_run_writes_and_offers_a_csv_named_by_the_default_template(
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
    assert written.parent == workdir
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_fwd-test_v1-2-0_save-totals\.csv", written.name)
    assert outputs["Save Totals"]["written"] is True
