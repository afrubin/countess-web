"""Browser tests: a real countess_web server and the built page, driven in headless Chromium.

Each test gets its own server, on a free port, over a copy of tests/data, so tests share no state.
They need the page built (``npm run build`` in frontend/) and Playwright's browser installed
(``python -m playwright install chromium``); run them with ``pytest -m e2e``.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator

import playwright.sync_api
import pytest

from countess_web.app import STATIC

DATA = pathlib.Path(__file__).parent.parent / "data"
TOKEN = "e2e-token"
START_SECONDS = 30


@dataclasses.dataclass(frozen=True)
class Server:
    url: str
    workdir: pathlib.Path

    @property
    def address(self) -> str:
        """The address the server prints for the user to open."""
        return f"{self.url}/?token={TOKEN}"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_serving(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        assert process.poll() is None, f"countess_web exited with status {process.returncode}"
        try:
            urllib.request.urlopen(f"{url}/api/graph", timeout=1)  # noqa: S310 - a local URL
        except urllib.error.HTTPError as exc:
            if exc.code == 401:  # serving, and refusing a request without the token
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError(f"countess_web did not start serving within {START_SECONDS}s")


@pytest.fixture
def server(tmp_path: pathlib.Path) -> Iterator[Server]:
    assert (STATIC / "index.html").is_file(), "the page is not built: run `npm run build` in frontend/"
    workdir = tmp_path / "work"
    workdir.mkdir()
    for name in ("counts.csv", "pipeline.ini"):
        shutil.copy(DATA / name, workdir / name)
    port = free_port()
    log = (tmp_path / "server.log").open("w")
    process = subprocess.Popen(  # noqa: S603 - our own command
        [sys.executable, "-m", "countess_web.cli", "pipeline.ini", "--port", str(port), "--no-browser"],
        cwd=workdir,
        env=os.environ | {"COUNTESS_WEB_TOKEN": TOKEN},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        wait_until_serving(url, process)
        yield Server(url, workdir)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise AssertionError("countess_web did not stop within 10s of being asked to") from None
        finally:
            log.close()


@pytest.fixture
def app(page: playwright.sync_api.Page, server: Server) -> Iterator[playwright.sync_api.Page]:
    """The page, opened at the address the server prints, with the pipeline drawn. An uncaught error
    in the page's scripts fails the test."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(server.address)
    page.wait_for_selector(".pipeline-node")
    yield page
    assert errors == []


def node(page: playwright.sync_api.Page, name: str) -> playwright.sync_api.Locator:
    return page.locator(".pipeline-node", has_text=name)


def preview_rows(page: playwright.sync_api.Page) -> list[list[str]]:
    page.wait_for_selector(".preview table")
    return [row.locator("td").all_inner_texts() for row in page.locator(".preview tbody tr").all()]
