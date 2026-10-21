"""The HTTP API and the page that uses it.

Every API request carries the session's token in a header, and the event socket sends it as its
first message. The page reads the token once, from the address the server prints
(``/?token=...``), and keeps it in the tab's own storage. A cookie would not do: browsers send a
localhost cookie to every port, so every local web server would receive the token. And because
the token travels in a header, no page from another site can make a request that carries it.

Every route declares its response model (countess_web.models), so the OpenAPI schema the browser's
types are generated from describes exactly what the routes send.
"""

from __future__ import annotations

import asyncio
import dataclasses
import fnmatch
import os
import pathlib
import secrets
import threading
import time
from typing import Any, Optional

import fastapi
import fastapi.openapi.utils
import fastapi.responses
import fastapi.staticfiles
import pydantic
import starlette.background
import starlette.requests

from countess_web import VERSION
from countess_web import models
from countess_web.session import Session, SessionError

TOKEN_HEADER = "x-countess-token"
STATIC = pathlib.Path(__file__).parent / "static"
# How often the event socket looks for changes to send.
EVENT_INTERVAL = 0.25
# Seconds a new event socket has to send the token.
SOCKET_AUTH_TIMEOUT = 5.0
# Seconds a download link works for; each works once.
DOWNLOAD_LINK_SECONDS = 60.0
DOWNLOAD_PREFIX = "/api/download/"


@dataclasses.dataclass(frozen=True)
class Download:
    file: pathlib.Path
    filename: str
    expires: float
    # A file made for this download (a preview's CSV), removed once sent or expired.
    temporary: bool


class Downloads:
    """One-time links to files.

    A browser saves a download by following a link, which carries no request header, so the API
    hands out a link instead: valid once, for a minute, to one file the session chose.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.links: dict[str, Download] = {}

    def issue(self, file: pathlib.Path, filename: str, temporary: bool = False) -> str:
        key = secrets.token_urlsafe(24)
        with self.lock:
            self._expire()
            self.links[key] = Download(file, filename, time.monotonic() + DOWNLOAD_LINK_SECONDS, temporary)
        return f"{DOWNLOAD_PREFIX.lstrip('/')}{key}"

    def take(self, key: str) -> Optional[Download]:
        with self.lock:
            self._expire()
            return self.links.pop(key, None)

    def _expire(self) -> None:
        now = time.monotonic()
        for key, download in list(self.links.items()):
            if download.expires < now:
                del self.links[key]
                if download.temporary:
                    remove(download.file)


def remove(file: pathlib.Path) -> None:
    try:
        os.remove(file)
    except FileNotFoundError:
        pass


def create_app(session: Session, token: str) -> fastapi.FastAPI:  # pylint: disable=too-many-locals,too-many-statements
    app = fastapi.FastAPI(title="CountESS", version=VERSION, docs_url=None, redoc_url=None)
    downloads = Downloads()

    def valid(offered: Any) -> bool:
        return isinstance(offered, str) and secrets.compare_digest(offered.encode(), token.encode())

    def authorised(request: starlette.requests.HTTPConnection) -> bool:
        return valid(request.headers.get(TOKEN_HEADER, ""))

    @app.middleware("http")
    async def require_token(request: fastapi.Request, call_next):  # type: ignore[no-untyped-def]
        # A download link is its own authority: the API issued it, to a holder of the token.
        protected = request.url.path.startswith("/api/") and not request.url.path.startswith(DOWNLOAD_PREFIX)
        if protected and not authorised(request):
            return fastapi.responses.JSONResponse({"detail": "Not authorised"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(SessionError)
    async def session_error(_request: fastapi.Request, exc: SessionError) -> fastapi.responses.JSONResponse:
        return fastapi.responses.JSONResponse({"detail": str(exc)}, status_code=400)

    # ---- the page --------------------------------------------------------------------------------

    # The page holds no data; everything it shows comes through the API, which needs the token.
    @app.get("/", include_in_schema=False)
    def index() -> Any:
        page = STATIC / "index.html"
        if not page.is_file():
            return fastapi.responses.PlainTextResponse(
                "The browser interface has not been built: run `npm run build` in countess-web/frontend.",
                status_code=503,
            )
        return fastapi.responses.FileResponse(page)

    # ---- the pipeline ----------------------------------------------------------------------------

    @app.get("/api/plugins")
    def plugins() -> list[models.PluginInfo]:
        return sorted(
            (
                models.PluginInfo(
                    key=key,
                    name=cls.name,
                    description=" ".join(cls.description.split()),
                    numInputs=cls.num_inputs,
                    numOutputs=cls.num_outputs,
                )
                for key, cls in session.plugin_classes().items()
            ),
            key=lambda p: p.name.lower(),
        )

    @app.get("/api/graph")
    def graph() -> models.Graph:
        return session.describe_graph()

    @app.post("/api/config/new")
    def config_new() -> models.Graph:
        session.new()
        return session.describe_graph()

    @app.post("/api/config/load")
    def config_load(body: models.ConfigPath) -> models.Graph:
        if not body.path:
            raise SessionError("Choose a pipeline to load")
        session.load(body.path)
        return session.describe_graph()

    @app.post("/api/config/save")
    def config_save(body: models.ConfigPath) -> models.SavedConfig:
        return models.SavedConfig(path=str(session.save(body.path)))

    @app.patch("/api/workflow")
    def workflow(body: models.WorkflowUpdate) -> models.Graph:
        session.set_workflow(body.name, body.version)
        return session.describe_graph()

    @app.post("/api/graph/tidy")
    def tidy() -> models.Graph:
        session.tidy()
        return session.describe_graph()

    @app.post("/api/nodes")
    def node_create(body: models.NodeCreate) -> models.Node:
        return session.describe_node(session.add_node(body.position, body.plugin))

    @app.patch("/api/nodes/{node_id}")
    def node_update(node_id: str, body: models.NodeUpdate) -> models.Node:
        session.update_node(
            node_id,
            name=body.name,
            position=body.position,
            notes=body.notes,
            sort_column=body.sortColumn,
            sort_descending=body.sortDescending,
        )
        return session.describe_node(session.node(node_id))

    @app.delete("/api/nodes/{node_id}")
    def node_delete(node_id: str) -> models.Deleted:
        session.delete_node(node_id)
        return models.Deleted(deleted=node_id)

    @app.post("/api/nodes/{node_id}/plugin")
    def node_plugin(node_id: str, body: models.PluginChoice) -> models.Node:
        session.set_plugin(node_id, body.plugin)
        return session.describe_node(session.node(node_id))

    @app.post("/api/edges")
    def edge_create(body: models.Edge) -> models.Edge:
        session.connect(body.parent, body.child)
        return body

    @app.delete("/api/edges")
    def edge_delete(parent: str, child: str) -> models.Edge:
        session.disconnect(parent, child)
        return models.Edge(parent=parent, child=child)

    @app.get("/api/nodes/{node_id}/parameters")
    def parameters(node_id: str) -> list[models.Param]:
        return session.describe_parameters(node_id)

    @app.post("/api/nodes/{node_id}/parameters")
    def parameter_change(node_id: str, body: models.ParameterChange) -> list[models.Param]:
        session.change_parameter(node_id, body)
        return session.describe_parameters(node_id)

    @app.get("/api/nodes/{node_id}/preview")
    def preview(node_id: str, offset: int = 0, limit: int = 100) -> models.Preview:
        return session.preview(node_id, offset, limit)

    # ---- runs ------------------------------------------------------------------------------------

    @app.get("/api/run")
    def run_state() -> Optional[models.RunSummary]:
        return session.run.summary() if session.run else None

    @app.post("/api/run")
    def run_start() -> models.RunSummary:
        return session.start_run().summary()

    @app.post("/api/run/stop")
    def run_stop() -> models.Stopping:
        session.stop_run()
        return models.Stopping(stopping=True)

    # ---- downloads -------------------------------------------------------------------------------

    @app.get("/api/run/outputs")
    def run_outputs() -> list[models.RunOutput]:
        return session.run_outputs()

    @app.post("/api/run/outputs/{index}/download")
    def run_output_download(index: int) -> models.DownloadLink:
        file = session.run_output_file(index)
        return models.DownloadLink(url=downloads.issue(file, file.name))

    @app.post("/api/run/log/download")
    def run_log_download() -> models.DownloadLink:
        file, filename = session.run_log()
        return models.DownloadLink(url=downloads.issue(file, filename))

    @app.post("/api/nodes/{node_id}/preview/download")
    def preview_download(node_id: str) -> models.DownloadLink:
        file, filename, rows = session.export_preview(node_id)
        return models.DownloadLink(url=downloads.issue(file, filename, temporary=True), rows=rows)

    @app.get(DOWNLOAD_PREFIX + "{key}", include_in_schema=False)
    def download(key: str) -> Any:
        found = downloads.take(key)
        if found is None:
            return fastapi.responses.PlainTextResponse(
                "This download link has expired or was already used.", status_code=404
            )
        if not found.file.is_file():
            return fastapi.responses.PlainTextResponse(f"{found.filename} is no longer there.", status_code=404)
        background = starlette.background.BackgroundTask(remove, found.file) if found.temporary else None
        return fastapi.responses.FileResponse(found.file, filename=found.filename, background=background)

    # ---- files on the server ---------------------------------------------------------------------

    @app.get("/api/files")
    def files(path: Optional[str] = None, patterns: Optional[str] = None, hidden: bool = False) -> models.FileListing:
        return list_dir(pathlib.Path(path).expanduser() if path else session.browse_dir(), patterns, hidden)

    # ---- events ----------------------------------------------------------------------------------

    @app.websocket("/api/events")
    async def events(socket: fastapi.WebSocket) -> None:
        await socket.accept()
        try:
            hello = models.EventHello.model_validate(await asyncio.wait_for(socket.receive_json(), SOCKET_AUTH_TIMEOUT))
        except (asyncio.TimeoutError, ValueError, pydantic.ValidationError, fastapi.WebSocketDisconnect):
            hello = None
        if hello is None or not valid(hello.token):
            await socket.close(code=4401)
            return
        last_state: Optional[models.StateEvent] = None
        last_run: Optional[models.RunSummary] = None
        seq = hello.since
        try:
            while True:
                state = session.statuses()
                if state != last_state:
                    await socket.send_json(state.model_dump(mode="json"))
                    last_state = state
                run = session.run.summary() if session.run else None
                if run != last_run or last_state is None:
                    await socket.send_json(models.RunEvent(type="run", run=run).model_dump(mode="json"))
                    last_run = run
                logs = session.logs.since(seq)
                if logs:
                    await socket.send_json(models.LogsEvent(type="logs", records=logs).model_dump(mode="json"))
                    seq = logs[-1].seq
                await asyncio.sleep(EVENT_INTERVAL)
        except (fastapi.WebSocketDisconnect, RuntimeError):
            return

    if (STATIC / "assets").is_dir():
        app.mount("/assets", fastapi.staticfiles.StaticFiles(directory=STATIC / "assets"), name="assets")

    app.openapi = lambda: openapi_schema(app)  # type: ignore[method-assign]
    return app


def openapi_schema(app: fastapi.FastAPI) -> dict[str, Any]:
    """The app's OpenAPI schema, with models.EXTRA_SCHEMAS added; the browser's types are
    generated from it."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = fastapi.openapi.utils.get_openapi(title=app.title, version=app.version, routes=app.routes)
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    adapter = pydantic.TypeAdapter(dict[str, Any])
    for name, model in models.EXTRA_SCHEMAS.items():
        definition = pydantic.TypeAdapter(model).json_schema(ref_template="#/components/schemas/{model}")
        for sub_name, sub_schema in definition.pop("$defs", {}).items():
            components.setdefault(sub_name, sub_schema)
        components[name] = adapter.validate_python(definition)
    app.openapi_schema = schema
    return schema


def list_dir(directory: pathlib.Path, patterns: Optional[str], hidden: bool) -> models.FileListing:
    """A directory's subdirectories and the files matching any of ``patterns`` (comma-separated globs)."""
    directory = directory.resolve()
    if not directory.is_dir():
        raise SessionError(f"{directory} is not a directory")
    globs = [p.strip() for p in (patterns or "*").split(",") if p.strip()] or ["*"]
    entries = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise SessionError(f"No permission to read {directory}") from exc
    for child in children:
        if not hidden and child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
            if not is_dir and not any(fnmatch.fnmatch(child.name, g) for g in globs):
                continue
            size = None if is_dir else child.stat().st_size
        except OSError:
            continue
        entries.append(models.FileEntry(name=child.name, path=str(child), isDir=is_dir, size=size))
    entries.sort(key=lambda e: (not e.isDir, e.name.lower()))
    return models.FileListing(
        path=str(directory),
        parent=str(directory.parent) if directory.parent != directory else None,
        entries=entries,
    )
