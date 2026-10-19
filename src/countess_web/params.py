"""Plugin parameters as JSON for the browser, and changes from the browser applied back.

A parameter is addressed by its path: the dotted key CountESS uses for it in a pipeline's .ini
(``reference.fasta``, ``steps.0.output``), so the browser and a saved pipeline name a parameter the
same way.
"""

from __future__ import annotations

import decimal
import math
from collections.abc import Sequence
from typing import Any, Union

from countess.core.parameters import (
    ArrayParam,
    BaseParam,
    BooleanParam,
    ChoiceParam,
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
    PerColumnArrayParam,
    ScalarParam,
    TabularMultiParam,
    TextParam,
)
from countess.core.plugins import BasePlugin

JsonValue = Union[None, bool, int, float, str, list, dict]


class ParameterError(ValueError):
    """A change the browser asked for that the parameter cannot take."""


def describe_plugin(plugin: BasePlugin) -> list[dict[str, Any]]:
    return [describe(param, key) for key, param in plugin.params.items()]


def describe(param: BaseParam, path: str) -> dict[str, Any]:  # pylint: disable=too-many-return-statements
    """One parameter (and those inside it) as JSON. ``kind`` says which widget draws it."""
    common = {"path": path, "label": param.label, "hide": bool(param.hide), "readOnly": bool(param.read_only)}

    if isinstance(param, ArrayParam):
        return common | describe_array(param, path)
    if isinstance(param, MultiParam):
        return common | {
            "kind": "group",
            "framed": isinstance(param, FramedMultiParam),
            "children": [describe(p, f"{path}.{k}") for k, p in param.params.items()],
        }
    if isinstance(param, BooleanParam):
        return common | {"kind": "boolean", "value": bool(param.value)}
    if isinstance(param, MultiChoiceParam):
        return common | {"kind": "multichoice", "choices": list(param.choices), "value": list(param.get_values())}
    if isinstance(param, FileBaseParam):
        return common | {
            "kind": "file",
            "mode": "save" if isinstance(param, FileSaveParam) else "open",
            "value": param.value or "",
            "absolute": param.get_file_path() if param.value else "",
            "fileTypes": file_types(param.file_types),
        }
    if isinstance(param, ColumnOrStringParam):
        return common | {"kind": "combo", "choices": list(param.get_values()), "value": json_value(param.value)}
    if isinstance(param, (ChoiceParam, DictChoiceParam)):
        return common | {"kind": "choice", "choices": list(param.get_values()), "value": json_value(param.value)}
    if isinstance(param, TextParam):
        return common | {"kind": "text", "value": param.value or ""}
    if isinstance(param, IntegerParam):
        return common | {"kind": "integer", "value": json_value(param.value)}
    if isinstance(param, (FloatParam, DecimalParam)):
        return common | {"kind": "number", "value": json_value(param.value)}
    if isinstance(param, ScalarParam):
        return common | {"kind": "string", "value": json_value(param.value)}
    raise TypeError(f"{path}: no description for {type(param).__name__}")


def describe_array(param: ArrayParam, path: str) -> dict[str, Any]:
    template = param.param
    if isinstance(template, TabularMultiParam):
        layout = "table"
    elif isinstance(template, MultiParam):
        layout = "frames"
    else:
        layout = "list"
    size = len(param.params)
    editable = not param.read_only
    return {
        "kind": "array",
        "layout": layout,
        "columns": [p.label for p in template.params.values()] if isinstance(template, MultiParam) else [],
        "rowLabels": isinstance(param, PerColumnArrayParam),
        "rows": [describe(p, f"{path}.{n}") for n, p in enumerate(param.params)],
        "canAdd": editable and (param.max_size is None or size < param.max_size),
        "canDelete": editable and size > param.min_size,
        "addFiles": isinstance(param, FileArrayParam),
        "fileTypes": file_types(param.file_types) if isinstance(param, FileArrayParam) else [],
        "itemLabel": template.label,
    }


def file_types(types: Sequence[tuple[str, Union[str, list[str]]]]) -> list[dict[str, Any]]:
    """A parameter's file types with glob patterns, and "All files" last.

    Plugins write them for Tk's file dialogs, which take either a glob (``*.fa``) or a bare
    extension (``.csv``); a bare extension becomes the glob it means.
    """
    described = []
    for label, patterns in types:
        globs = [patterns] if isinstance(patterns, str) else list(patterns)
        described.append({"label": label, "patterns": [f"*{g}" if g.startswith(".") else g for g in globs]})
    if not any(t["patterns"] == ["*"] for t in described):
        described.append({"label": "All files", "patterns": ["*"]})
    return described


def json_value(value: Any) -> JsonValue:
    if isinstance(value, decimal.Decimal):
        return str(value)
    return value


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
        param.set_values(value)
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
