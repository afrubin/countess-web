"""Plugin parameters as JSON for the browser, and changes from the browser applied back.

A parameter is addressed by its path: the dotted key CountESS uses for it in a pipeline's .ini
(``reference.fasta``, ``steps.0.output``), so the browser and a saved pipeline name a parameter the
same way.
"""

from __future__ import annotations

import decimal
import math
import os
from collections.abc import Sequence
from typing import Any, Literal, Optional, Union

from countess.core.parameters import (
    ArrayParam,
    BaseParam,
    BooleanParam,
    ChoiceParam,
    ColumnOrIntegerParam,
    ColumnOrStringParam,
    DecimalParam,
    DictChoiceParam,
    FileArrayParam,
    FileBaseParam,
    FileSaveParam,
    FloatParam,
    FramedMultiParam,
    IntegerParam,
    MultiChoiceParam,
    MultiParam,
    OutputFileParam,
    PerColumnArrayParam,
    ScalarParam,
    StringCharacterSetParam,
    StringParam,
    TabularMultiParam,
    TextParam,
)
from countess.core.plugins import BasePlugin
from countess.core.workflow import RunContext, WorkflowError

from countess_web import models


class ParameterError(ValueError):
    """A change the browser asked for that the parameter cannot take."""


def describe_plugin(plugin: BasePlugin) -> list[models.Param]:
    """A plugin's parameters."""
    return [describe(param, key) for key, param in plugin.params.items()]


def describe(param: BaseParam, path: str) -> models.Param:  # pylint: disable=too-many-return-statements
    """One parameter, and those inside it, as the model of its CountESS class family.

    The order of the checks is CountESS's class hierarchy, most specific first: a TextParam is a
    StringParam, a FileSaveParam a FileBaseParam, a ColumnOrIntegerParam a ColumnOrStringParam, and
    a ColumnOrStringParam a ChoiceParam.
    """
    common = {"path": path, "label": param.label, "hide": bool(param.hide), "readOnly": bool(param.read_only)}

    if isinstance(param, ArrayParam):
        return describe_array(param, path, common)
    if isinstance(param, MultiParam):
        if isinstance(param, TabularMultiParam):
            layout: Literal["plain", "table", "frame"] = "table"
        elif isinstance(param, FramedMultiParam):
            layout = "frame"
        else:
            layout = "plain"
        children = [describe(p, f"{path}.{k}") for k, p in param.params.items()]
        return models.GroupParamModel(kind="group", layout=layout, children=children, **common)
    if isinstance(param, BooleanParam):
        return models.BooleanParamModel(kind="boolean", value=param.value, **common)
    if isinstance(param, MultiChoiceParam):
        chosen = param.get_values()
        return models.MultiChoiceParamModel(
            kind="multichoice", values=[c for c in param.choices if c in chosen], choices=list(param.choices), **common
        )
    if isinstance(param, FileSaveParam):
        return describe_save_path(param, common)
    if isinstance(param, FileBaseParam):
        return models.FileParamModel(
            kind="file",
            value=param.value,
            absolute=param.get_file_path() if param.value else None,
            fileTypes=file_types(param.file_types),
            **common,
        )
    if isinstance(param, ColumnOrStringParam):
        column = param.get_column_name()
        prefix = len(ColumnOrStringParam.PREFIX)
        return models.ColumnOrValueParamModel(
            kind="column-or-value",
            valueType="integer" if isinstance(param, ColumnOrIntegerParam) else "string",
            value=None if column is not None else param.value,
            column=column,
            columns=[c[prefix:] for c in param.get_values()],
            **common,
        )
    if isinstance(param, DictChoiceParam):
        return models.ChoiceParamModel(
            kind="choice",
            selected=param.get_choice() or None,
            options=[models.ChoiceOption(value=key, label=label) for key, label in param.choices.items()],
            **common,
        )
    if isinstance(param, ChoiceParam):
        return models.ChoiceParamModel(
            kind="choice",
            selected=param.value if param.value is not None else None,
            options=[models.ChoiceOption(value=c, label=c) for c in param.get_values()],
            **common,
        )
    if isinstance(param, TextParam):
        return models.TextParamModel(kind="text", value=param.value, **common)
    if isinstance(param, StringParam):
        character_set = sorted(param.character_set) if isinstance(param, StringCharacterSetParam) else None
        return models.StringParamModel(kind="string", value=param.value, characterSet=character_set, **common)
    if isinstance(param, IntegerParam):
        return models.IntegerParamModel(kind="integer", value=param.value, **common)
    if isinstance(param, FloatParam):
        return models.FloatParamModel(kind="float", value=finite_or_none(param.value), **common)
    if isinstance(param, DecimalParam):
        return models.DecimalParamModel(
            kind="decimal", value=str(param.value) if param.value is not None else None, **common
        )
    raise TypeError(f"{path}: countess-web has no model for {type(param).__name__}")


def finite_or_none(value: Optional[float]) -> Optional[float]:
    # A FloatParam defaults to NaN in places (DataTypeChoiceParam's FLOAT); JSON has no NaN.
    return value if value is not None and math.isfinite(value) else None


def describe_save_path(param: FileSaveParam, common: dict[str, Any]) -> models.SaveFileParamModel:
    """A file to write. A relative OutputFileParam (CSV Save's filename) is in each run's output
    directory, so it has no one absolute path; any other is resolved against the pipeline's folder."""
    in_output_dir = isinstance(param, OutputFileParam) and not os.path.isabs(os.path.expanduser(param.value or ""))
    return models.SaveFileParamModel(
        kind="save-file",
        value=param.value,
        absolute=param.get_file_path() if param.value and not in_output_dir else None,
        inOutputDir=in_output_dir,
        fileTypes=file_types(param.file_types),
        **common,
    )


def describe_array(param: ArrayParam, path: str, common: dict[str, Any]) -> models.ArrayParamModel:
    size = len(param.params)
    editable = not param.read_only
    return models.ArrayParamModel(
        kind="array",
        items=[describe(p, f"{path}.{n}") for n, p in enumerate(param.params)],
        # The template is not itself saved; its path names where a new row will be.
        template=describe(param.param, f"{path}.{size}"),
        minSize=param.min_size,
        maxSize=param.max_size,
        perColumn=isinstance(param, PerColumnArrayParam),
        files=isinstance(param, FileArrayParam),
        fileTypes=file_types(param.file_types) if isinstance(param, FileArrayParam) else [],
        canAdd=editable and (param.max_size is None or size < param.max_size),
        canDelete=editable and size > param.min_size,
        **common,
    )


def file_types(types: Sequence[tuple[str, Union[str, list[str]]]]) -> list[models.FileType]:
    """A parameter's file types with glob patterns, and "All files" last.

    Plugins write them for Tk's file dialogs, which take either a glob (``*.fa``) or a bare
    extension (``.csv``); a bare extension becomes the glob it means.
    """
    described = []
    for label, patterns in types:
        globs = [patterns] if isinstance(patterns, str) else list(patterns)
        described.append(models.FileType(label=label, patterns=[f"*{g}" if g.startswith(".") else g for g in globs]))
    if not any(t.patterns == ["*"] for t in described):
        described.append(models.FileType(label="All files", patterns=["*"]))
    return described


def output_files(plugin: BasePlugin, context: RunContext) -> list[tuple[str, str, str]]:
    """The files a plugin is set to write in ``context``: (parameter path, absolute file, error). A
    relative OutputFileParam is in the run's output directory; if the workflow's output directory
    template cannot be filled, it gives no file and the reason."""
    found = []

    def walk(param: BaseParam, path: str) -> None:
        if isinstance(param, FileSaveParam) and param.value:
            try:
                if isinstance(param, OutputFileParam):
                    found.append((path, param.get_output_path(context.output_dir()), ""))
                else:
                    found.append((path, param.get_file_path(), ""))
            except WorkflowError as exc:
                found.append((path, "", str(exc)))
        elif isinstance(param, ArrayParam):
            for n, row in enumerate(param.params):
                walk(row, f"{path}.{n}")
        elif isinstance(param, MultiParam):
            for key, child in param.params.items():
                walk(child, f"{path}.{key}")

    for key, param in plugin.params.items():
        walk(param, key)
    return found


def resolve(plugin: BasePlugin, path: str) -> BaseParam:
    """The parameter at ``path``.

    Raises:
        ParameterError: If no parameter has that path.
    """
    first, *rest = path.split(".")
    try:
        param: BaseParam = plugin.params[first]
        for part in rest:
            if isinstance(param, ArrayParam):
                param = param.params[int(part)]
            elif isinstance(param, MultiParam):
                param = param.params[part]
            else:
                raise KeyError(part)
    except (KeyError, IndexError, ValueError) as exc:
        raise ParameterError(f"{path}: no such parameter") from exc
    return param


def set_value(plugin: BasePlugin, path: str, value: Any) -> None:
    """Sets the parameter at ``path`` as its widget would.

    Raises:
        ParameterError: If there is no such parameter, it is read-only or not a single value, or
            the value is the wrong type for it.
    """
    param = resolve(plugin, path)
    if param.read_only:
        raise ParameterError(f"{path} is read-only")
    if isinstance(param, BooleanParam):
        if not isinstance(value, bool):
            raise ParameterError(f"{path} takes true or false")
        param.value = value
    elif isinstance(param, MultiChoiceParam):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ParameterError(f"{path} takes a list of choices")
        # MultiChoiceParam.set_value would add an unknown value to the choices; refuse it instead.
        unknown = [v for v in value if v not in param.choices]
        if unknown:
            raise ParameterError(f"{path} has no choice {', '.join(map(repr, unknown))}")
        param.set_values(value)
    elif isinstance(param, ColumnOrStringParam) and isinstance(value, str) and value.startswith(param.PREFIX):
        # A value spelt like a column reference would be read as one; columns are chosen by name.
        raise ParameterError(f"{path}: choose a column with 'column', not a value starting {param.PREFIX!r}")
    elif isinstance(param, DictChoiceParam) and value not in param.choices:
        raise ParameterError(f"{path} has no option {value!r}")
    elif isinstance(param, ScalarParam):
        if value is not None and not isinstance(value, (str, int, float)):
            raise ParameterError(f"{path} takes a single value")
        previous = param.value
        try:
            param.value = value
        except (ValueError, TypeError, OverflowError) as exc:
            param.value = previous
            raise ParameterError(f"{path}: {exc}") from exc
        # A saved pipeline cannot hold a non-finite number (it writes inf, which does not read back).
        cleaned = param.value
        if isinstance(cleaned, (float, decimal.Decimal)) and not math.isfinite(cleaned):
            param.value = previous
            raise ParameterError(f"{path} takes a finite number")
    else:
        raise ParameterError(f"{path} is not a single value")


def set_column(plugin: BasePlugin, path: str, column: str) -> None:
    """Sets a column-or-value parameter to take each row's value from ``column``.

    Raises:
        ParameterError: If the parameter takes no column, or the input has no such column.
    """
    param = resolve(plugin, path)
    if not isinstance(param, ColumnOrStringParam):
        raise ParameterError(f"{path} does not take a column")
    if param.read_only:
        raise ParameterError(f"{path} is read-only")
    reference = param.PREFIX + column
    if reference not in param.get_values():
        raise ParameterError(f"{path}: the input has no column {column!r}")
    param.value = reference


def add_row(plugin: BasePlugin, path: str) -> None:
    array = _array(plugin, path)
    if isinstance(array, FileArrayParam):
        raise ParameterError(f"{path} takes files: add them by choosing files")
    if array.max_size is not None and len(array.params) >= array.max_size:
        raise ParameterError(f"{path} holds at most {array.max_size}")
    array.add_row()


def add_files(plugin: BasePlugin, path: str, filenames: Sequence[str]) -> None:
    array = _array(plugin, path)
    if not isinstance(array, FileArrayParam):
        raise ParameterError(f"{path} is not a list of files")
    array.add_files(list(filenames))


def delete_row(plugin: BasePlugin, path: str, index: int) -> None:
    array = _array(plugin, path)
    if len(array.params) <= array.min_size:
        raise ParameterError(f"{path} needs at least {array.min_size}")
    if not 0 <= index < len(array.params):
        raise ParameterError(f"{path} has no row {index}")
    array.del_row(index)


def _array(plugin: BasePlugin, path: str) -> ArrayParam:
    param = resolve(plugin, path)
    if not isinstance(param, ArrayParam):
        raise ParameterError(f"{path} is not a list")
    if param.read_only:
        raise ParameterError(f"{path} is read-only")
    return param
