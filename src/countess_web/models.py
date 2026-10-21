"""The shapes of everything the API sends and accepts.

The parameter models follow CountESS's parameter classes (countess.core.parameters), one kind per
class family, with each value typed as CountESS holds it: a BooleanParam is True, False or None (an
unset one, which CountESS reads as false); a StringParam's value is None until one is set; a
DecimalParam's is a Decimal, sent as its exact text. The browser's types are generated from these
models (see frontend/README), so this module is the one description of the API.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

import pydantic

# ---- parameters ---------------------------------------------------------------------------------


class Model(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")


class FileType(Model):
    """One entry of a file parameter's ``file_types``, its patterns as globs."""

    label: str
    patterns: list[str]


class FilenameField(Model):
    """A field a save path template can use (countess.core.workflow.FILENAME_FIELDS)."""

    name: str
    description: str


class ParamBase(Model):
    """What every BaseParam has. ``path`` is the parameter's key in a pipeline's .ini file."""

    path: str
    label: str
    hide: bool
    readOnly: bool


class BooleanParamModel(ParamBase):
    """BooleanParam. None is a parameter never set, which CountESS reads (and the GUI shows) as false."""

    kind: Literal["boolean"]
    value: Optional[bool]


class StringParamModel(ParamBase):
    """StringParam (ColumnLabelParam, StringCharacterSetParam). ``characterSet``, when set, is every
    character the value may hold; CountESS uppercases a lowercase letter it allows only in upper case,
    and drops any other character."""

    kind: Literal["string"]
    value: Optional[str]
    characterSet: Optional[list[str]] = None


class TextParamModel(ParamBase):
    """TextParam: a long, multi-line string."""

    kind: Literal["text"]
    value: Optional[str]


class IntegerParamModel(ParamBase):
    """IntegerParam. None is an empty value."""

    kind: Literal["integer"]
    value: Optional[int]


class FloatParamModel(ParamBase):
    """FloatParam. None is an empty value."""

    kind: Literal["float"]
    value: Optional[float]


class DecimalParamModel(ParamBase):
    """DecimalParam, its value as exact decimal text."""

    kind: Literal["decimal"]
    value: Optional[str]


class ChoiceOption(Model):
    """``value`` is what is sent to choose it and what a pipeline saves; ``label`` is what is shown.
    They differ only for a DictChoiceParam."""

    value: str
    label: str


class ChoiceParamModel(ParamBase):
    """ChoiceParam and its family (column choices, data types), and DictChoiceParam. ``selected`` is
    the value chosen, which may be one no longer among the options (a column that has gone)."""

    kind: Literal["choice"]
    selected: Optional[str]
    options: list[ChoiceOption]


class ColumnOrValueParamModel(ParamBase):
    """ColumnOrStringParam and ColumnOrIntegerParam: either a value typed in, or a column of the input
    to take each row's value from. Exactly one of ``value`` and ``column`` is set, or neither."""

    kind: Literal["column-or-value"]
    valueType: Literal["string", "integer"]
    value: Union[str, int, None]
    column: Optional[str]
    columns: list[str]


class MultiChoiceParamModel(ParamBase):
    """MultiChoiceParam (MultiColumnChoiceParam): any number of ``choices``, in their order."""

    kind: Literal["multichoice"]
    values: list[str]
    choices: list[str]


class FileParamModel(ParamBase):
    """FileParam: a file to read. ``absolute`` is it resolved against the pipeline's folder."""

    kind: Literal["file"]
    value: Optional[str]
    absolute: Optional[str]
    fileTypes: list[FileType]


class SaveFileParamModel(ParamBase):
    """FileSaveParam: a file to write, possibly a template naming it from the run. ``filled`` is the
    file it names for a run starting now, or ``templateError`` why it names none."""

    kind: Literal["save-file"]
    value: Optional[str]
    filled: Optional[str]
    templateError: Optional[str]
    fields: list[FilenameField]
    fileTypes: list[FileType]


class GroupParamModel(ParamBase):
    """MultiParam. ``layout`` is CountESS's hint for drawing it: TabularMultiParam is a table row,
    FramedMultiParam a frame of its own."""

    kind: Literal["group"]
    layout: Literal["plain", "table", "frame"]
    children: list[Param]


class ArrayParamModel(ParamBase):
    """ArrayParam: rows copied from ``template``. A PerColumnArrayParam has a row per input column,
    each labelled with it, and none can be added or removed; a FileArrayParam's rows are files,
    added by choosing them."""

    kind: Literal["array"]
    items: list[Param]
    template: Param
    minSize: int
    maxSize: Optional[int]
    perColumn: bool
    files: bool
    fileTypes: list[FileType]
    canAdd: bool
    canDelete: bool


Param = Annotated[
    Union[
        BooleanParamModel,
        StringParamModel,
        TextParamModel,
        IntegerParamModel,
        FloatParamModel,
        DecimalParamModel,
        ChoiceParamModel,
        ColumnOrValueParamModel,
        MultiChoiceParamModel,
        FileParamModel,
        SaveFileParamModel,
        GroupParamModel,
        ArrayParamModel,
    ],
    pydantic.Field(discriminator="kind"),
]

GroupParamModel.model_rebuild()
ArrayParamModel.model_rebuild()


class ParameterChange(Model):
    """A change to the parameter at ``path``: a new ``value``, or for a column-or-value parameter a
    ``column`` to take it from; or adding a row to a list, adding files to a file list, or deleting
    row ``index``."""

    path: str
    value: Union[bool, int, float, str, list[str], None] = None
    column: Optional[str] = None
    action: Optional[Literal["add", "addFiles", "delete"]] = None
    index: Optional[int] = None
    paths: Optional[list[str]] = None


# ---- plugins, nodes and the graph ---------------------------------------------------------------

Status = Literal["DIRTY", "WORKING", "RESULT", "ERROR"]  # countess.core.pipeline.PipelineNodeStatus


class PluginInfo(Model):
    """A plugin class from the countess_plugins entry points, by ``module:Class``."""

    key: str
    name: str
    description: str
    numInputs: int
    numOutputs: int


class NodePlugin(PluginInfo):
    """A node's plugin (BasePlugin): its class's attributes."""

    version: str
    additional: str
    link: Optional[str]
    showPreview: bool


class Node(Model):
    """A PipelineNode. ``position`` is CountESS's (across, down), each from 0 to 1. ``message`` is the
    traceback of a failed preview, empty for a node that made no table without failing (a CSV Save,
    say). ``sortColumn`` and ``sortDescending`` are the preview's sort, which a pipeline saves."""

    id: str
    name: str
    position: tuple[float, float]
    notes: str
    status: Status
    message: str
    parents: list[str]
    sortColumn: int
    sortDescending: bool
    plugin: Optional[NodePlugin]


class Workflow(Model):
    """countess.core.workflow.WorkflowInfo: a short name and a semantic version, either unset."""

    name: Optional[str]
    version: Optional[str]


class Graph(Model):
    version: int
    workflow: Workflow
    config: Optional[str]
    modified: bool
    nodes: list[Node]


class NodeCreate(Model):
    position: tuple[float, float] = (0.5, 0.5)
    plugin: Optional[str] = None


class NodeUpdate(Model):
    name: Optional[str] = None
    position: Optional[tuple[float, float]] = None
    notes: Optional[str] = None
    sortColumn: Optional[int] = None
    sortDescending: Optional[bool] = None


class PluginChoice(Model):
    plugin: str


class Edge(Model):
    parent: str
    child: str


class WorkflowUpdate(Model):
    """An empty string unsets the name or version."""

    name: Optional[str] = None
    version: Optional[str] = None


class ConfigPath(Model):
    path: Optional[str] = None


class SavedConfig(Model):
    path: str


class Deleted(Model):
    deleted: str


# ---- previews -----------------------------------------------------------------------------------


class Column(Model):
    """A column of a node's table: its name, and its DuckDB type as DuckDB writes it."""

    name: str
    type: str


class Preview(Model):
    """Rows ``offset`` on of a node's preview table. Each cell is its DuckDB value as JSON: a number,
    text, true or false, null, or a list or object for a nested type. Sent as exact text: a DECIMAL,
    an integer a browser cannot hold exactly (beyond 2**53, as a BIGINT or HUGEINT can be), a time
    with a time zone, an infinite or not-a-number float, and other values JSON lacks."""

    status: Status
    message: str
    columns: list[Column]
    rows: list[list[Any]]
    total: int


class PreviewDownload(Model):
    sort: Optional[str] = None
    descending: bool = False


class DownloadLink(Model):
    """A link that downloads one file, once, within a minute. ``rows`` is a preview's row count."""

    url: str
    rows: Optional[int] = None


# ---- runs ---------------------------------------------------------------------------------------


class RunSummary(Model):
    id: str
    config: str
    started: str
    finished: Optional[str]
    returncode: Optional[int]
    running: bool


class RunOutput(Model):
    """A file a save node was set to write when the run started; ``written`` if this run wrote it.
    ``error`` is why its template named no file."""

    index: int
    node: str
    parameter: str
    file: str
    name: str
    size: Optional[int]
    written: bool
    error: str


class Stopping(Model):
    stopping: bool


# ---- files on the server ------------------------------------------------------------------------


class FileEntry(Model):
    name: str
    path: str
    isDir: bool
    size: Optional[int]


class FileListing(Model):
    path: str
    parent: Optional[str]
    entries: list[FileEntry]


# ---- the event socket ---------------------------------------------------------------------------


class NodeState(Model):
    status: Status
    message: str


class StateEvent(Model):
    """Sent when any node's status, or the graph's version or modified flag, changes. A new
    ``version`` means the graph itself changed and should be fetched again."""

    type: Literal["state"]
    version: int
    modified: bool
    nodes: dict[str, NodeState]


class RunEvent(Model):
    type: Literal["run"]
    run: Optional[RunSummary]


class LogRecord(Model):
    seq: int
    time: str
    level: str
    source: str
    message: str


class LogsEvent(Model):
    type: Literal["logs"]
    records: list[LogRecord]


class EventHello(Model):
    """The first message the browser sends on the event socket."""

    token: str
    since: int = 0


ServerEvent = Annotated[Union[StateEvent, RunEvent, LogsEvent], pydantic.Field(discriminator="type")]

# Named in the published schema so the browser's types name them too: the event socket's messages,
# which OpenAPI (describing HTTP routes) would otherwise leave out, and the parameter union, which
# it would only inline.
EXTRA_SCHEMAS: dict[str, Any] = {"EventHello": EventHello, "ServerEvent": ServerEvent, "Param": Param}
