"""The API's parameter models against CountESS's own parameter classes: each class described as
the model of its family, with its value as CountESS holds it, and every installed plugin's
parameters fitting the models."""

from __future__ import annotations

import decimal
import math

import pydantic
import pytest
from countess.core.parameters import (
    ArrayParam,
    BooleanParam,
    ChoiceParam,
    ColumnChoiceParam,
    ColumnOrIntegerParam,
    ColumnOrStringParam,
    DataTypeChoiceParam,
    DecimalParam,
    DictChoiceParam,
    FileArrayParam,
    FileParam,
    FileSaveParam,
    FloatParam,
    FramedMultiParam,
    IntegerParam,
    MultiChoiceParam,
    MultiParam,
    OutputFileParam,
    PerColumnArrayParam,
    StringCharacterSetParam,
    StringParam,
    TabularMultiParam,
    TextParam,
)
from countess.core.plugins import BasePlugin, get_plugin_classes

from countess_web import models, params

PARAMS = pydantic.TypeAdapter(list[models.Param])


def described(param: object) -> dict:
    return params.describe(param, "p").model_dump()  # type: ignore[arg-type]


# ---- values as CountESS holds them --------------------------------------------------------------


def test_a_boolean_never_set_is_none_not_false() -> None:
    assert described(BooleanParam("Index"))["value"] is None


def test_a_boolean_set_false_is_false() -> None:
    param = BooleanParam("Index")
    param.value = False

    assert described(param)["value"] is False


def test_a_string_never_set_is_none() -> None:
    assert described(StringParam("Name"))["value"] is None


def test_a_text_is_its_own_kind() -> None:
    assert described(TextParam("Code", "x = 1"))["kind"] == "text"


def test_an_integer_set_empty_is_none() -> None:
    param = IntegerParam("Max", 10)
    param.value = ""

    assert (described(param)["kind"], described(param)["value"]) == ("integer", None)


def test_a_float_that_is_not_a_number_is_sent_as_none() -> None:
    # DataTypeChoiceParam gives FLOAT columns a NaN default; JSON has no NaN.
    assert described(FloatParam("Weight", math.nan))["value"] is None


def test_a_decimal_is_sent_as_its_exact_text() -> None:
    assert described(DecimalParam("Threshold", decimal.Decimal("0.10")))["value"] == "0.10"


def test_a_character_set_string_names_its_characters() -> None:
    param = StringCharacterSetParam("Sequence", "ACGT", character_set={"A", "C", "G", "T"})

    assert described(param)["characterSet"] == ["A", "C", "G", "T"]


def test_a_dict_choice_offers_its_keys_and_labels_and_selects_a_key() -> None:
    param = DictChoiceParam("Operation", "g_to_c", choices={"normalize": "Normalise", "g_to_c": "g. → c."})

    out = described(param)

    assert out["options"] == [{"value": "normalize", "label": "Normalise"}, {"value": "g_to_c", "label": "g. → c."}]
    assert out["selected"] == "g_to_c"


def test_a_choice_keeps_a_value_its_choices_no_longer_hold() -> None:
    param = ColumnChoiceParam("Column", "gone")
    param.set_choices(["hgvs", "count"])
    param.value = "gone"

    out = described(param)

    assert out["selected"] == "gone"
    assert [o["value"] for o in out["options"]] == ["hgvs", "count"]


def test_a_data_type_choice_is_a_choice() -> None:
    assert [o["value"] for o in described(DataTypeChoiceParam("Type"))["options"]] == [
        "STRING",
        "FLOAT",
        "INTEGER",
        "BOOLEAN",
    ]


def test_a_column_or_string_set_to_a_column_names_the_column_without_its_prefix() -> None:
    param = ColumnOrStringParam("Reference")
    param.set_column_choices({"genome": False, "count": True})
    param.value = ColumnOrStringParam.PREFIX + "genome"

    out = described(param)

    assert (out["kind"], out["value"], out["column"]) == ("column-or-value", None, "genome")
    assert out["columns"] == ["genome", "count"]


def test_a_column_or_string_set_to_a_value_has_no_column() -> None:
    param = ColumnOrStringParam("Reference")
    param.value = "NM_000099.1"

    out = described(param)

    assert (out["value"], out["column"], out["valueType"]) == ("NM_000099.1", None, "string")


def test_a_column_or_integer_takes_integers_and_offers_numeric_columns() -> None:
    param = ColumnOrIntegerParam("Offset", 3)
    param.set_column_choices({"name": False, "position": True})

    out = described(param)

    assert (out["valueType"], out["value"], out["columns"]) == ("integer", 3, ["position"])


def test_a_multichoice_lists_its_values_in_the_order_of_its_choices() -> None:
    param = MultiChoiceParam("Group By", choices=["a", "b", "c"])
    param.set_values({"c", "a"})

    assert described(param)["values"] == ["a", "c"]


def test_a_file_to_read_and_a_file_to_write_are_different_kinds() -> None:
    assert described(FileParam("FASTA"))["kind"] == "file"
    assert described(FileSaveParam("Filename", "out.csv"))["kind"] == "save-file"


def test_a_save_path_is_resolved_against_the_pipelines_folder() -> None:
    out = described(FileSaveParam("Filename", "out.csv", base_dir="/data"))

    assert (out["absolute"], out["inOutputDir"]) == ("/data/out.csv", False)


def test_a_relative_output_file_is_in_each_runs_output_directory() -> None:
    out = described(OutputFileParam("Filename", "results.csv", base_dir="/data"))

    assert (out["absolute"], out["inOutputDir"]) == (None, True)


def test_an_absolute_output_file_is_where_it_says() -> None:
    out = described(OutputFileParam("Filename", "/elsewhere/results.csv", base_dir="/data"))

    assert (out["absolute"], out["inOutputDir"]) == ("/elsewhere/results.csv", False)


@pytest.mark.parametrize(
    "group,layout",
    [(MultiParam("G"), "plain"), (TabularMultiParam("G"), "table"), (FramedMultiParam("G"), "frame")],
)
def test_a_groups_layout_is_countess_hint_for_it(group: MultiParam, layout: str) -> None:
    assert described(group)["layout"] == layout


def test_a_per_column_array_has_a_row_per_column_that_cannot_be_added_or_removed() -> None:
    param = PerColumnArrayParam("Columns", BooleanParam("Index"))
    param.set_column_choices({"variant": False, "count": True})

    out = described(param)

    assert out["perColumn"] is True
    assert [item["label"] for item in out["items"]] == ["variant", "count"]
    assert (out["canAdd"], out["canDelete"]) == (False, False)


def test_an_array_respects_its_minimum_and_maximum_size() -> None:
    param = ArrayParam("Order By", StringParam("Column"), min_size=1, max_size=2)
    param.add_row()

    out = described(param)

    assert (out["minSize"], out["maxSize"], out["canAdd"], out["canDelete"]) == (1, 2, False, True)


def test_a_file_array_is_added_to_by_choosing_files() -> None:
    assert described(FileArrayParam("Files", FileParam("File")))["files"] is True


# ---- every installed plugin ---------------------------------------------------------------------


@pytest.mark.parametrize("cls", sorted(get_plugin_classes(), key=lambda c: c.__name__), ids=lambda c: c.__name__)
def test_every_installed_plugins_parameters_fit_the_models(cls: type[BasePlugin]) -> None:
    plugin = cls()

    out = params.describe_plugin(plugin)

    assert PARAMS.validate_json(PARAMS.dump_json(out)) == out
    assert [p.path for p in out] == list(plugin.params)


# ---- changes ------------------------------------------------------------------------------------


class Plugin(BasePlugin):
    name = "Test"
    version = "0"

    reference = ColumnOrStringParam("Reference")
    operation = DictChoiceParam("Operation", choices={"normalize": "Normalise", "g_to_c": "g. → c."})
    group_by = MultiChoiceParam("Group By", choices=["a", "b"])
    index = BooleanParam("Index")


def plugin_with_columns() -> Plugin:
    plugin = Plugin()
    plugin.reference.set_column_choices({"genome": False})
    return plugin


def test_a_column_is_chosen_by_name() -> None:
    plugin = plugin_with_columns()

    params.set_column(plugin, "reference", "genome")

    assert plugin.reference.get_column_name() == "genome"


def test_a_column_the_input_lacks_is_refused() -> None:
    with pytest.raises(params.ParameterError, match="no column 'gone'"):
        params.set_column(plugin_with_columns(), "reference", "gone")


def test_a_value_spelt_as_a_column_reference_is_refused() -> None:
    with pytest.raises(params.ParameterError, match="choose a column with 'column'"):
        params.set_value(plugin_with_columns(), "reference", ColumnOrStringParam.PREFIX + "genome")


def test_a_dict_choice_is_set_by_its_key() -> None:
    plugin = Plugin()

    params.set_value(plugin, "operation", "g_to_c")

    assert plugin.operation.get_choice() == "g_to_c"


def test_a_dict_choice_refuses_a_label() -> None:
    with pytest.raises(params.ParameterError, match="no option"):
        params.set_value(Plugin(), "operation", "Normalise")


def test_a_multichoice_refuses_a_value_that_is_not_a_choice() -> None:
    plugin = Plugin()

    with pytest.raises(params.ParameterError, match="no choice 'c'"):
        params.set_value(plugin, "group_by", ["a", "c"])
    assert plugin.group_by.choices == ["a", "b"]


def test_a_boolean_takes_only_true_or_false() -> None:
    with pytest.raises(params.ParameterError, match="true or false"):
        params.set_value(Plugin(), "index", "yes")
