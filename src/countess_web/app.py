"""The HTTP API and the page that uses it.

Every API request carries the session's token in a header, and the event socket sends it as its
first message. The page reads the token once, from the address the server prints
(``/?token=...``), and keeps it in the tab's own storage. A cookie would not do: browsers send a
localhost cookie to every port, so every local web server would receive the token. And because
the token travels in a header, no page from another site can make a request that carries it.
"""

from __future__ import annotations

import asyncio
import fnmatch
import pathlib
import secrets
from typing import Any, Optional

import fastapi
import fastapi.responses
import fastapi.staticfiles
import pydantic
import starlette.requests

from countess_web import VERSION
from countess_web.session import Session, SessionError

TOKEN_HEADER = "x-countess-token"
STATIC = pathlib.Path(__file__).parent / "static"
# How often the event socket looks for changes to send.
EVENT_INTERVAL = 0.25
# Seconds a new event socket has to send the token.
SOCKET_AUTH_TIMEOUT = 5.0


class NodeCreate(pydantic.BaseModel):
    position: tuple[float, float] = (0.5, 0.5)
    plugin: Optional[str] = None


class NodeUpdate(pydantic.BaseModel):
    name: Optional[str] = None
    position: Optional[tuple[float, float]] = None
    notes: Optional[str] = None


class PluginChoice(pydantic.BaseModel):
    plugin: str


class Edge(pydantic.BaseModel):
    parent: str
    child: str


class ParameterChange(pydantic.BaseModel):
    path: str
    value: Any = None
    action: Optional[str] = None
    index: Optional[int] = None
    paths: Optional[list[str]] = None


class ConfigPath(pydantic.BaseModel):
    path: Optional[str] = None


def create_app(session: Session, token: str) -> fastapi.FastAPI:  # pylint: disable=too-many-locals
    app = fastapi.FastAPI(title="CountESS", version=VERSION, docs_url=None, redoc_url=None)

    def valid(offered: Any) -> bool:
        return isinstance(offered, str) and secrets.compare_digest(offered.encode(), token.encode())

    def authorised(request: starlette.requests.HTTPConnection) -> bool:
        return valid(request.headers.get(TOKEN_HEADER, ""))

    @app.middleware("http")
    async def require_token(request: fastapi.Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path.startswith("/api/") and not authorised(request):
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
    def plugins() -> list[dict[str, Any]]:
        return sorted(
            (
                {
                    "key": key,
                    "name": cls.name,
                    "description": " ".join(cls.description.split()),
                    "numInputs": cls.num_inputs,
                    "numOutputs": cls.num_outputs,
                }
                for key, cls in session.plugin_classes().items()
            ),
            key=lambda p: str(p["name"]).lower(),
        )

    @app.get("/api/graph")
    def graph() -> dict[str, Any]:
        return session.describe_graph()

    @app.post("/api/config/new")
    def config_new() -> dict[str, Any]:
        session.new()
        return session.describe_graph()

    @app.post("/api/config/load")
    def config_load(body: ConfigPath) -> dict[str, Any]:
        if not body.path:
            raise SessionError("Choose a pipeline to load")
        session.load(body.path)
        return session.describe_graph()

    @app.post("/api/config/save")
    def config_save(body: ConfigPath) -> dict[str, Any]:
        return {"path": str(session.save(body.path))}

    @app.post("/api/graph/tidy")
    def tidy() -> dict[str, Any]:
        session.tidy()
        return session.describe_graph()

    @app.post("/api/nodes")
    def node_create(body: NodeCreate) -> dict[str, Any]:
        return session.describe_node(session.add_node(body.position, body.plugin))

    @app.patch("/api/nodes/{node_id}")
    def node_update(node_id: str, body: NodeUpdate) -> dict[str, Any]:
        session.update_node(node_id, name=body.name, position=body.position, notes=body.notes)
        return session.describe_node(session.node(node_id))

    @app.delete("/api/nodes/{node_id}")
    def node_delete(node_id: str) -> dict[str, Any]:
        session.delete_node(node_id)
        return {"deleted": node_id}

    @app.post("/api/nodes/{node_id}/plugin")
    def node_plugin(node_id: str, body: PluginChoice) -> dict[str, Any]:
        session.set_plugin(node_id, body.plugin)
        return session.describe_node(session.node(node_id))

    @app.post("/api/edges")
    def edge_create(body: Edge) -> dict[str, Any]:
        session.connect(body.parent, body.child)
        return body.model_dump()

    @app.delete("/api/edges")
    def edge_delete(parent: str, child: str) -> dict[str, Any]:
        session.disconnect(parent, child)
        return {"parent": parent, "child": child}

    @app.get("/api/nodes/{node_id}/parameters")
    def parameters(node_id: str) -> list[dict[str, Any]]:
        return session.describe_parameters(node_id)

    @app.post("/api/nodes/{node_id}/parameters")
    def parameter_change(node_id: str, body: ParameterChange) -> list[dict[str, Any]]:
        change = body.model_dump(exclude_none=True)
        if "value" not in body.model_fields_set:
            change.pop("value", None)
        else:
            change["value"] = body.value
        session.change_parameter(node_id, body.path, change)
        return session.describe_parameters(node_id)

    @app.get("/api/nodes/{node_id}/preview")
    def preview(
        node_id: str,
        offset: int = 0,
        limit: int = 100,
        sort: Optional[str] = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        return session.preview(node_id, offset, limit, sort, descending)

    # ---- runs ------------------------------------------------------------------------------------

    @app.get("/api/run")
    def run_state() -> Optional[dict[str, Any]]:
        return session.run.summary() if session.run else None

    @app.post("/api/run")
    def run_start() -> dict[str, Any]:
        return session.start_run().summary()

    @app.post("/api/run/stop")
    def run_stop() -> dict[str, Any]:
        session.stop_run()
        return {"stopping": True}

    # ---- files on the server ---------------------------------------------------------------------

    @app.get("/api/files")
    def files(path: Optional[str] = None, patterns: Optional[str] = None, hidden: bool = False) -> dict[str, Any]:
        return list_dir(pathlib.Path(path).expanduser() if path else session.browse_dir(), patterns, hidden)

    # ---- events ----------------------------------------------------------------------------------

    @app.websocket("/api/events")
    async def events(socket: fastapi.WebSocket) -> None:
        await socket.accept()
        try:
            hello = await asyncio.wait_for(socket.receive_json(), SOCKET_AUTH_TIMEOUT)
        except (asyncio.TimeoutError, ValueError, fastapi.WebSocketDisconnect):
            hello = None
        if not isinstance(hello, dict) or not valid(hello.get("token")):
            await socket.close(code=4401)
            return
        last_state: Optional[dict[str, Any]] = None
        last_run: Optional[dict[str, Any]] = None
        since = hello.get("since", 0)
        seq = since if isinstance(since, int) else 0
        try:
            while True:
                state = session.statuses()
                if state != last_state:
                    await socket.send_json({"type": "state", **state})
                    last_state = state
                run = session.run.summary() if session.run else None
                if run != last_run:
                    await socket.send_json({"type": "run", "run": run})
                    last_run = run
                logs = session.logs.since(seq)
                if logs:
                    await socket.send_json({"type": "logs", "records": logs})
                    seq = logs[-1]["seq"]
                await asyncio.sleep(EVENT_INTERVAL)
        except (fastapi.WebSocketDisconnect, RuntimeError):
            return

    if (STATIC / "assets").is_dir():
        app.mount("/assets", fastapi.staticfiles.StaticFiles(directory=STATIC / "assets"), name="assets")

    return app


def list_dir(directory: pathlib.Path, patterns: Optional[str], hidden: bool) -> dict[str, Any]:
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
        entries.append({"name": child.name, "path": str(child), "isDir": is_dir, "size": size})
    entries.sort(key=lambda e: (not e["isDir"], str(e["name"]).lower()))
    return {
        "path": str(directory),
        "parent": str(directory.parent) if directory.parent != directory else None,
        "entries": entries,
    }
