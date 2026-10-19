"""One user's pipeline: the CountESS graph being edited, its preview thread, and full runs.

Every change to the graph goes through ``Session.change()``, which stops CountESS's preview
thread, makes the change, and starts the thread again. That is how CountESS's own GUI does it,
and it means the thread never sees a half-made change.
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
import datetime
import decimal
import functools
import itertools
import logging
import math
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import uuid as uuid_mod
from collections.abc import Iterator
from typing import Any, Optional

import duckdb
from countess.core.config import read_config, write_config
from countess.core.parameters import set_file_base_dirs
from countess.core.pipeline import PipelineGraph, PipelineNode, PipelineNodeStatus
from countess.core.plugins import BasePlugin
from countess.core.workflow import RunContext, WorkflowError, WorkflowInfo, default_filename
from countess.utils.duckdb import duckdb_escape_identifier

from countess_web import params
from countess_web import resources

logger = logging.getLogger(__name__)

# Rows a preview may ask for at once.
MAX_PREVIEW_ROWS = 1000

# Column types whose Python values need a library CountESS does not install (pytz); previewed as text.
TEXT_PREVIEW_TYPES = ("TIMESTAMP WITH TIME ZONE", "TIME WITH TIME ZONE")


class SessionError(ValueError):
    """A request the pipeline cannot carry out; its message is shown to the user."""


def plugin_key(cls: type) -> str:
    return f"{cls.__module__}:{cls.__name__}"


@dataclasses.dataclass
class RunState:
    """A full run of the saved pipeline, in its own process."""

    id: str
    config: str
    started: str
    started_at: float
    # The workflow as it was when the run started, and the time its output names are made from.
    context: RunContext
    process: subprocess.Popen
    lines: collections.deque
    # Every line the run printed; ``lines`` keeps only the latest.
    log_file: pathlib.Path
    # The files the pipeline's save nodes were set to write when the run started.
    outputs: list[dict[str, str]] = dataclasses.field(default_factory=list)
    finished: Optional[str] = None
    returncode: Optional[int] = None

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "config": self.config,
            "started": self.started,
            "finished": self.finished,
            "returncode": self.returncode,
            "running": self.returncode is None,
        }


class LogBuffer(logging.Handler):
    """The most recent log records, numbered so the browser can ask for those it has not seen."""

    def __init__(self, size: int = 2000) -> None:
        super().__init__(level=logging.INFO)
        self.records: collections.deque = collections.deque(maxlen=size)
        self.counter = itertools.count(1)
        self.lock_ = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        self.add(record.levelname, record.name, record.getMessage())

    def add(self, level: str, source: str, message: str) -> None:
        with self.lock_:
            self.records.append(
                {
                    "seq": next(self.counter),
                    "time": datetime.datetime.now().isoformat(timespec="seconds"),
                    "level": level,
                    "source": source,
                    "message": message,
                }
            )

    def since(self, seq: int) -> list[dict[str, Any]]:
        with self.lock_:
            return [r for r in self.records if r["seq"] > seq]


class Session:
    def __init__(self, start_dir: pathlib.Path, preview_row_limit: int = 100_000) -> None:
        self.lock = threading.RLock()
        self.start_dir = start_dir.resolve()
        self.preview_row_limit = preview_row_limit
        self.config_path: Optional[pathlib.Path] = None
        self.modified = False
        self.version = 0
        self.run: Optional[RunState] = None
        self.logs = LogBuffer()
        self.state_dir = pathlib.Path(tempfile.mkdtemp(prefix="countess-web-"))
        self.graph = self._new_graph(PipelineGraph())

    # ---- the graph as a whole -------------------------------------------------------------------

    def _new_graph(self, graph: PipelineGraph) -> PipelineGraph:
        graph.preview_row_limit = self.preview_row_limit
        resources.configure(graph.ddbc, resources.PREVIEW_MEMORY_FRACTION)
        # Each node's settings from the file are applied here, before the preview thread starts:
        # applied from two threads at once, a list parameter can gain a duplicate row.
        for node in graph.nodes:
            if node.plugin:
                node.load_config()
        # Shadows the method start_thread runs, for one that stops when asked (see preview_thread).
        graph._thread_target = functools.partial(preview_thread, graph)  # pylint: disable=protected-access
        return graph

    def _replace_graph(self, graph: PipelineGraph) -> None:
        old = self.graph
        old.stop_thread()
        self.graph = self._new_graph(graph)
        self.version += 1
        self.graph.start_thread()
        # The old graph is never collected (its connection holds a function bound to it), so close
        # the connection to free its preview tables.
        old.ddbc.close()

    def new(self) -> None:
        with self.lock:
            self._replace_graph(PipelineGraph())
            self.config_path = None
            self.modified = False

    def load(self, path: str) -> None:
        config = self._existing_file(path)
        with self.lock:
            try:
                graph = read_config([str(config)])
            except Exception as exc:  # pylint: disable=broad-exception-caught
                raise SessionError(f"Could not read {config}: {exc}") from exc
            self._replace_graph(graph)
            self.config_path = config
            self.modified = False
            logger.info("Loaded %s", config)

    def save(self, path: Optional[str] = None) -> pathlib.Path:
        with self.lock:
            target = pathlib.Path(path).expanduser().resolve() if path else self.config_path
            if target is None:
                raise SessionError("Choose a file to save the pipeline to")
            if not target.parent.is_dir():
                raise SessionError(f"{target.parent} is not a directory")
            for node in self.graph.nodes:
                if node.plugin:
                    node.load_config()
            write_config(self.graph, str(target))
            self.config_path = target
            self.modified = False
            self.version += 1
            logger.info("Saved %s", target)
            return target

    def set_workflow(self, name: Optional[str], version: Optional[str]) -> None:
        """Sets the workflow's name and version; an empty string unsets one.

        Raises:
            SessionError: If the name or version cannot be used.
        """
        try:
            workflow = WorkflowInfo.from_strings(name, version)
        except WorkflowError as exc:
            raise SessionError(str(exc)) from exc
        with self.change(recalculate=False):
            self.graph.workflow = workflow

    def tidy(self) -> None:
        with self.change(recalculate=False):
            if self.graph.nodes:
                self.graph.tidy()

    @contextlib.contextmanager
    def change(self, recalculate: bool = True) -> Iterator[None]:
        """Holds the session while the graph is changed, with the preview thread stopped."""
        with self.lock:
            if recalculate:
                self.graph.stop_thread()
                # A node the stop interrupted is left WORKING, which the preview thread never revisits.
                for node in self.graph.nodes:
                    if node.status == PipelineNodeStatus.WORKING:
                        node.mark_dirty()
            try:
                yield
            finally:
                self.version += 1
                self.modified = True
                if recalculate:
                    self.graph.start_thread()

    # ---- nodes and edges -------------------------------------------------------------------------

    def node(self, node_id: str) -> PipelineNode:
        for node in self.graph.nodes:
            if node.uuid == node_id:
                return node
        raise SessionError(f"No node {node_id}")

    def plugin_classes(self) -> dict[str, type[BasePlugin]]:
        return {plugin_key(cls): cls for cls in self.graph.plugin_classes}

    def add_node(self, position: tuple[float, float], plugin: Optional[str] = None) -> PipelineNode:
        with self.change():
            node = PipelineNode(name="NEW", position=valid_position(position))
            if plugin:
                self._set_plugin(node, plugin)
            self.graph.add_node(node)
            return node

    def set_plugin(self, node_id: str, plugin: str) -> None:
        with self.change():
            node = self.node(node_id)
            if node.plugin is not None:
                raise SessionError(f"{node.name} already has a plugin")
            self._set_plugin(node, plugin)
            self.graph.reset_node_name(node)
            node.mark_dirty()

    def _set_plugin(self, node: PipelineNode, plugin: str) -> None:
        try:
            cls = self.plugin_classes()[plugin]
        except KeyError as exc:
            raise SessionError(f"No plugin {plugin}") from exc
        node.plugin = cls()
        # A default save path (CSV Save's, say) then means a file beside the pipeline, as it would
        # for a node read from the pipeline's file.
        set_file_base_dirs(node.plugin.params.values(), str(self.browse_dir()))
        if node.name == "NEW":
            node.name = node.plugin.name

    def update_node(
        self,
        node_id: str,
        name: Optional[str] = None,
        position: Optional[tuple[float, float]] = None,
        notes: Optional[str] = None,
    ) -> None:
        # A rename changes how a node's children name their sources (a Join's inputs), so it recalculates.
        with self.change(recalculate=name is not None):
            node = self.node(node_id)
            if name is not None:
                node.name = valid_name(name)
                self.graph.reset_node_name(node)
                node.mark_dirty()
            if position is not None:
                node.position = valid_position(position)
            if notes is not None:
                node.notes = notes or None

    def delete_node(self, node_id: str) -> None:
        with self.change():
            self.graph.del_node(self.node(node_id))

    def connect(self, parent_id: str, child_id: str) -> None:
        with self.change():
            parent, child = self.node(parent_id), self.node(child_id)
            if parent is child or child.is_ancestor_of(parent):
                raise SessionError(f"Connecting {parent.name} to {child.name} would make a loop")
            if child.plugin is not None and not child.plugin.num_inputs:
                raise SessionError(f"{child.name} takes no input")
            if parent.plugin is not None and not parent.plugin.num_outputs:
                raise SessionError(f"{parent.name} has no output")
            child.add_parent(parent)

    def disconnect(self, parent_id: str, child_id: str) -> None:
        with self.change():
            self.node(child_id).del_parent(self.node(parent_id))

    # ---- parameters ------------------------------------------------------------------------------

    def plugin_of(self, node: PipelineNode) -> BasePlugin:
        if node.plugin is None:
            raise SessionError(f"{node.name} has no plugin yet")
        node.load_config()
        return node.plugin

    def change_parameter(self, node_id: str, path: str, change: dict[str, Any]) -> None:
        with self.change():
            node = self.node(node_id)
            plugin = self.plugin_of(node)
            try:
                if "value" in change:
                    params.set_value(plugin, path, change["value"])
                elif change.get("action") == "add":
                    params.add_row(plugin, path)
                elif change.get("action") == "addFiles":
                    params.add_files(plugin, path, change.get("paths") or [])
                elif change.get("action") == "delete":
                    params.delete_row(plugin, path, int(change.get("index", -1)))
                else:
                    raise SessionError(f"Unknown change to {path}")
            except params.ParameterError as exc:
                raise SessionError(str(exc)) from exc
            node.mark_dirty()

    # ---- what the browser shows ------------------------------------------------------------------

    def describe_graph(self) -> dict[str, Any]:
        with self.lock:
            return {
                "version": self.version,
                "workflow": {"name": self.graph.workflow.name, "version": self.graph.workflow.version},
                "config": str(self.config_path) if self.config_path else None,
                "modified": self.modified,
                "nodes": [self.describe_node(node) for node in self.graph.nodes],
            }

    @staticmethod
    def describe_node(node: PipelineNode) -> dict[str, Any]:
        plugin = node.plugin
        return {
            "id": node.uuid,
            "name": node.name,
            "position": list(node.position),
            "notes": node.notes or "",
            "status": node.status.name,
            "message": node.message or "",
            "parents": sorted(p.uuid for p in node.parent_nodes),
            "plugin": (
                {
                    "key": plugin_key(type(plugin)),
                    "name": plugin.name,
                    "version": plugin.version,
                    "description": " ".join(plugin.description.split()),
                    "additional": " ".join(plugin.additional.split()),
                    "link": plugin.link,
                    "numInputs": plugin.num_inputs,
                    "numOutputs": plugin.num_outputs,
                    "showPreview": plugin.show_preview,
                }
                if plugin
                else None
            ),
        }

    def statuses(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "modified": self.modified,
            "nodes": {n.uuid: {"status": n.status.name, "message": n.message or ""} for n in list(self.graph.nodes)},
        }

    def describe_parameters(self, node_id: str) -> list[dict[str, Any]]:
        with self.lock:
            node = self.node(node_id)
            context = RunContext(self.graph.workflow, node.name, datetime.datetime.now())
            return params.describe_plugin(self.plugin_of(node), context)

    def preview(
        self, node_id: str, offset: int, limit: int, sort: Optional[str] = None, descending: bool = False
    ) -> dict[str, Any]:
        node = self.node(node_id)
        if node.status != PipelineNodeStatus.RESULT:
            return {"status": node.status.name, "message": node.message or "", "columns": [], "rows": [], "total": 0}
        try:
            cursor = self.graph.ddbc.cursor()
        except duckdb.ConnectionException:
            # A load or New closed this graph's connection after the node was looked up.
            return {"status": "WORKING", "message": "", "columns": [], "rows": [], "total": 0}
        try:
            table = cursor.table(node.table_name)
            columns = [{"name": c, "type": str(t)} for c, t in zip(table.columns, table.dtypes)]
            if sort is not None and sort not in table.columns:
                raise SessionError(f"No column {sort}")
            shown = table.project(
                ", ".join(
                    f"CAST({duckdb_escape_identifier(c['name'])} AS VARCHAR) AS {duckdb_escape_identifier(c['name'])}"
                    if c["type"] in TEXT_PREVIEW_TYPES
                    else duckdb_escape_identifier(c["name"])
                    for c in columns
                )
            )
            if sort is not None:
                shown = shown.order(f"{duckdb_escape_identifier(sort)} {'DESC' if descending else 'ASC'} NULLS LAST")
            [(total,)] = cursor.table(node.table_name).count("*").fetchall()
            rows = shown.limit(max(0, min(limit, MAX_PREVIEW_ROWS)), max(0, offset)).fetchall()
        except (duckdb.CatalogException, duckdb.ConnectionException):
            # The preview thread replaced the table, or a load closed the connection, mid-read.
            return {"status": "WORKING", "message": "", "columns": [], "rows": [], "total": 0}
        finally:
            cursor.close()
        return {
            "status": "RESULT",
            "message": "",
            "columns": columns,
            "rows": [[cell(v) for v in row] for row in rows],
            "total": total,
        }

    # ---- full runs -------------------------------------------------------------------------------

    def start_run(self) -> RunState:
        with self.lock:
            if self.run and self.run.returncode is None:
                raise SessionError("A run is already going")
            run_id = uuid_mod.uuid4().hex[:12]
            # The run reads a snapshot, so editing the pipeline while it runs changes nothing it does.
            snapshot = self.state_dir / f"run-{run_id}.ini"
            for node in self.graph.nodes:
                if node.plugin:
                    node.load_config()
            # Whole seconds: the run is told this start, and fills its file names from it as these are.
            started = datetime.datetime.now().replace(microsecond=0)
            outputs = [
                {"node": node.name, "parameter": path, "file": file, "error": error}
                for node in self.graph.nodes
                if node.plugin
                for path, file, error in params.output_files(
                    node.plugin, RunContext(self.graph.workflow, node.name, started)
                )
            ]
            started_at = started.timestamp()
            write_config(self.graph, str(snapshot))
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, "-m", "countess_web.runner", "--started", started.isoformat(), str(snapshot)],
                cwd=str(self.config_path.parent if self.config_path else self.start_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ | {"PYTHONUNBUFFERED": "1"},
            )
            self.run = RunState(
                id=run_id,
                config=str(self.config_path or snapshot),
                started=started.isoformat(),
                started_at=started_at,
                context=RunContext(self.graph.workflow, "run", started),
                process=process,
                lines=collections.deque(maxlen=5000),
                log_file=self.state_dir / f"run-{run_id}.log",
                outputs=outputs,
            )
            threading.Thread(target=self._follow_run, args=(self.run,), daemon=True).start()
            self.logs.add("INFO", "run", f"Run {run_id} started")
            return self.run

    def _follow_run(self, run: RunState) -> None:
        assert run.process.stdout is not None
        with open(run.log_file, "w", encoding="utf-8") as log:
            for line in run.process.stdout:
                log.write(line)
                log.flush()
                line = line.rstrip()
                run.lines.append(line)
                self.logs.add("INFO", "run", line)
        run.returncode = run.process.wait()
        run.finished = datetime.datetime.now().isoformat(timespec="seconds")
        outcome = "finished" if run.returncode == 0 else f"failed (exit status {run.returncode})"
        self.logs.add("INFO" if run.returncode == 0 else "ERROR", "run", f"Run {run.id} {outcome}")

    def run_outputs(self) -> list[dict[str, Any]]:
        """The last run's output files: each save node's file, and whether this run wrote it."""
        if not self.run:
            return []
        described: list[dict[str, Any]] = []
        for index, output in enumerate(self.run.outputs):
            file = pathlib.Path(output["file"]) if output["file"] else None
            try:
                stat = file.stat() if file else None
            except OSError:
                stat = None
            described.append(
                output
                | {
                    "index": index,
                    "name": file.name if file else "",
                    "size": stat.st_size if stat else None,
                    # A file older than the run is left from before it, not this run's output.
                    "written": stat is not None and stat.st_mtime >= self.run.started_at - 1,
                }
            )
        return described

    def run_output_file(self, index: int) -> pathlib.Path:
        """The file the last run wrote for its ``index``th output.

        Raises:
            SessionError: If the run is still going, or did not write that output.
        """
        if not self.run:
            raise SessionError("Nothing has been run")
        if self.run.returncode is None:
            raise SessionError("The run is still going")
        outputs = self.run_outputs()
        if not 0 <= index < len(outputs) or not outputs[index]["written"]:
            raise SessionError("The run did not write that file")
        return pathlib.Path(outputs[index]["file"])

    def run_log(self) -> tuple[pathlib.Path, str]:
        """The last run's whole log, and a name for it.

        Raises:
            SessionError: If nothing has been run.
        """
        if not self.run:
            raise SessionError("Nothing has been run")
        return self.run.log_file, default_filename(self.run.context, "log", "txt")

    def export_preview(self, node_id: str, sort: Optional[str], descending: bool) -> tuple[pathlib.Path, str, int]:
        """Writes a node's whole preview table to a CSV file: the file, a name for it, and its rows.

        Raises:
            SessionError: If the node has no preview table, or ``sort`` is not one of its columns.
        """
        node = self.node(node_id)
        if node.status != PipelineNodeStatus.RESULT:
            raise SessionError(f"{node.name} has no preview to download")
        target = self.state_dir / f"preview-{uuid_mod.uuid4().hex}.csv"
        try:
            cursor = self.graph.ddbc.cursor()
            try:
                table = cursor.table(node.table_name)
                if sort is not None:
                    if sort not in table.columns:
                        raise SessionError(f"No column {sort}")
                    table = table.order(
                        f"{duckdb_escape_identifier(sort)} {'DESC' if descending else 'ASC'} NULLS LAST"
                    )
                [(rows,)] = cursor.table(node.table_name).count("*").fetchall()
                table.write_csv(str(target), header=True)
            finally:
                cursor.close()
        except (duckdb.CatalogException, duckdb.ConnectionException) as exc:
            raise SessionError(f"{node.name}'s preview changed; try again once it has finished") from exc
        name = default_filename(RunContext(self.graph.workflow, node.name, datetime.datetime.now()), "preview", "csv")
        return target, name, rows

    def stop_run(self) -> None:
        with self.lock:
            if not self.run or self.run.returncode is not None:
                raise SessionError("No run is going")
            self.run.process.terminate()

    def close(self) -> None:
        self.graph.stop_thread()
        if self.run and self.run.returncode is None:
            self.run.process.terminate()

    # ---- files -----------------------------------------------------------------------------------

    def _existing_file(self, path: str) -> pathlib.Path:
        file = pathlib.Path(path).expanduser().resolve()
        if not file.is_file():
            raise SessionError(f"{file} is not a file")
        return file

    def browse_dir(self) -> pathlib.Path:
        return self.config_path.parent if self.config_path else self.start_dir


def cell(value: Any) -> Any:
    """A table value as JSON."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.time, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [cell(v) for v in value]
    if isinstance(value, dict):
        return {str(k): cell(v) for k, v in value.items()}
    return str(value)


def preview_thread(graph: PipelineGraph) -> None:
    """CountESS's preview loop (PipelineGraph._thread_target), stopping between nodes when asked.

    CountESS's own loop interrupts only the node running when it is stopped and goes on to every
    other dirty node, so a change made while a preview runs waits for the whole preview.
    """
    graph.thread_cursor = graph.ddbc.cursor()
    graph.thread_cursor.sql("set enable_progress_bar=true")
    graph.thread_cursor.sql("set enable_progress_bar_print=false")
    graph.set_contexts(datetime.datetime.now())
    try:
        for node in graph.traverse_nodes():
            if graph.thread_stop:
                break
            if node.status == PipelineNodeStatus.DIRTY:
                node.run(graph.thread_cursor, graph.preview_row_limit)
    except duckdb.InterruptException:
        pass
    finally:
        graph.thread_cursor.close()


def valid_name(name: str) -> str:
    """A node name a saved pipeline can hold: it is an .ini section name.

    Raises:
        SessionError: If the name is empty, has a line break or a square bracket, or is DEFAULT.
    """
    name = name.strip()
    if not name:
        raise SessionError("A node needs a name")
    if any(c in name for c in "[]") or any(not c.isprintable() for c in name):
        raise SessionError("A node name cannot hold square brackets, line breaks or control characters")
    if name.upper() == "DEFAULT":
        raise SessionError("DEFAULT is reserved; choose another name")
    return name


def valid_position(position: tuple[float, float]) -> tuple[float, float]:
    """A node position a saved pipeline can hold: both coordinates finite, within 0 to 1.

    Raises:
        SessionError: If a coordinate is not a finite number.
    """
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in position):
        raise SessionError("A node position must be two finite numbers")
    x, y = position
    return (min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0))
