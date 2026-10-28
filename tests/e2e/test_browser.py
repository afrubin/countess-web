"""What a user does in the browser, end to end, over tests/data's pipeline of CountESS's own plugins:
Load (counts.csv) -> Total (Group By variant, sum count) -> Save (totals.csv)."""

from __future__ import annotations

import json
import pathlib
import re

import playwright.sync_api
import pytest
from playwright.sync_api import expect

from .conftest import Server, node, preview_rows

pytestmark = pytest.mark.e2e

Page = playwright.sync_api.Page


# ---- the token ----------------------------------------------------------------------------------


def test_the_token_leaves_the_address_bar_and_is_no_cookie(app: Page) -> None:
    assert not re.search("token", app.url)
    assert app.context.cookies() == []


def test_a_reloaded_page_stays_connected(app: Page) -> None:
    app.reload()

    expect(app.locator(".pipeline-node").first).to_be_visible()


def test_a_page_opened_without_the_token_says_so(browser: playwright.sync_api.Browser, server: Server) -> None:
    page = browser.new_context().new_page()

    page.goto(server.url)

    expect(page.locator(".unauthorised h2")).to_have_text("Not connected")


# ---- configuring and previewing -----------------------------------------------------------------


def test_a_node_previews_its_result(app: Page) -> None:
    node(app, "Total").click()

    assert preview_rows(app) == [["alpha", "7"], ["beta", "7"], ["gamma", "1"]]


def test_changing_a_parameter_recalculates_the_preview(app: Page) -> None:
    node(app, "Total").click()
    preview_rows(app)
    count_row = app.locator(".array-table tbody tr", has=app.locator("th", has_text=re.compile("^count$")))

    count_row.locator("input[type=checkbox]").nth(5).uncheck()  # Sum
    count_row.locator("input[type=checkbox]").nth(4).check()  # Max

    expect(app.locator(".preview th").nth(1)).to_contain_text("count__max")
    assert preview_rows(app) == [["alpha", "4"], ["beta", "5"], ["gamma", "1"]]


def test_clicking_a_column_heading_sorts_the_preview_and_marks_the_pipeline_changed(app: Page) -> None:
    node(app, "Load").click()
    preview_rows(app)

    app.locator(".preview th", has_text="count").click()
    expect(app.locator(".preview th", has_text="count")).to_contain_text("▲")
    app.locator(".preview th", has_text="count").click()
    expect(app.locator(".preview th", has_text="count")).to_contain_text("▼")

    assert [row[1] for row in preview_rows(app)] == ["5", "4", "3", "2", "1"]
    expect(app.locator(".title")).to_contain_text("•")


# ---- building a pipeline ------------------------------------------------------------------------


def test_a_pipeline_built_in_the_browser_saves_as_a_countess_config(app: Page, server: Server) -> None:
    app.on("dialog", lambda dialog: dialog.accept())
    app.get_by_role("button", name="New").click()
    expect(app.locator(".hint")).to_be_visible()

    app.get_by_role("button", name="Add node").click()
    app.locator(".chooser .plugin", has_text="CSV Load").click()
    app.get_by_role("button", name="Add files…").click()
    app.locator(".dialog .entries li", has_text="counts.csv").click()
    app.get_by_role("button", name="Choose", exact=True).click()
    expect(app.locator(".preview .bar")).to_contain_text("5 rows")

    app.locator(".vue-flow__pane").dblclick(position={"x": 420, "y": 160})
    app.locator(".chooser .plugin", has_text="Group By").click()
    expect(app.locator(".node-name")).to_have_value("Group By")

    source = node(app, "CSV Load").locator(".vue-flow__handle.source").bounding_box()
    target = node(app, "Group By").locator(".vue-flow__handle.target").bounding_box()
    assert source is not None and target is not None
    app.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    app.mouse.down()
    app.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2, steps=10)
    app.mouse.up()
    expect(app.locator(".vue-flow__edge")).to_have_count(1)

    app.get_by_role("button", name="Save as…").click()
    app.locator(".dialog .save-name input").fill("built.ini")
    app.locator(".dialog").get_by_role("button", name="Save", exact=True).click()
    expect(app.locator(".title")).to_contain_text("built.ini")

    saved = (server.workdir / "built.ini").read_text()
    assert "[CSV Load]" in saved
    assert "_parent.0 = CSV Load" in saved.split("[Group By]")[1]


def test_a_connection_can_be_removed(app: Page) -> None:
    app.locator(".vue-flow__edge").first.click(force=True)
    app.get_by_role("button", name="Remove connection").click()

    expect(app.locator(".vue-flow__edge")).to_have_count(1)


# ---- runs and downloads -------------------------------------------------------------------------


def run_pipeline(page: Page) -> None:
    page.get_by_role("button", name="Run", exact=True).click()
    expect(page.locator(".run")).to_contain_text("Run finished", timeout=60_000)


def test_a_run_writes_its_outputs_on_the_server_and_offers_them_for_download(
    app: Page, server: Server, tmp_path: pathlib.Path
) -> None:
    run_pipeline(app)
    app.get_by_role("button", name="Outputs…").click()
    expect(app.locator(".dialog .name")).to_have_text(["totals.csv"])

    with app.expect_download() as download:
        app.locator(".dialog").get_by_role("button", name="Download", exact=True).click()
    saved = tmp_path / download.value.suggested_filename
    download.value.save_as(saved)

    [written] = server.workdir.glob("*/totals.csv")
    assert saved.read_bytes() == written.read_bytes()


def data_lines(path: pathlib.Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if not line.startswith("#")]


def test_save_preview_csv_writes_the_order_shown_and_asks_before_replacing(
    app: Page, server: Server, tmp_path: pathlib.Path
) -> None:
    node(app, "Load").click()
    preview_rows(app)
    app.locator(".preview th", has_text="count").click()
    expect(app.locator(".preview th", has_text="count")).to_contain_text("▲")

    app.get_by_role("button", name="Save Preview CSV").click()
    expect(app.locator(".preview .saved")).to_contain_text("load_preview.csv")
    with app.expect_download() as download:
        app.locator(".preview .saved").get_by_role("button", name="Download").click()
    saved = tmp_path / download.value.suggested_filename
    download.value.save_as(saved)

    assert download.value.suggested_filename == "load_preview.csv"
    assert [line.split(",")[1] for line in data_lines(saved)[1:]] == ["1", "2", "3", "4", "5"]
    [on_server] = server.workdir.glob("*/load_preview.csv")
    assert on_server.read_bytes() == saved.read_bytes()

    asked: list[str] = []
    app.once("dialog", lambda dialog: (asked.append(dialog.message), dialog.dismiss()))
    on_server.write_text("mine")
    app.get_by_role("button", name="Save Preview CSV").click()
    expect(app.get_by_role("button", name="Save Preview CSV")).to_be_enabled()

    assert "load_preview.csv is already there" in asked[0]
    assert on_server.read_text() == "mine"


# ---- the workflow ---------------------------------------------------------------------------------


def test_a_version_that_is_not_semantic_is_refused_in_the_dialog(app: Page) -> None:
    app.get_by_role("button", name="Workflow…").click()
    app.get_by_label("Version").fill("1.2")
    app.locator(".dialog").get_by_role("button", name="Save", exact=True).click()

    expect(app.locator(".dialog .failed")).to_contain_text("not a semantic version")


def test_a_named_workflows_run_writes_into_its_output_directory(app: Page, server: Server) -> None:
    app.get_by_role("button", name="Workflow…").click()
    app.get_by_label("Name").fill("E2E test")
    app.get_by_label("Version").fill("2.0.1")
    app.get_by_label("Output directory").fill("out/{workflow}_{version}")
    app.locator(".dialog").get_by_role("button", name="Save", exact=True).click()
    expect(app.locator(".toolbar")).to_contain_text("E2E test v2.0.1")

    node(app, "Save").click()
    expect(app.locator(".save-where")).to_have_text("in each run's output directory")

    run_pipeline(app)
    app.get_by_role("button", name="Outputs…").click()
    expect(app.locator(".dialog .name")).to_have_text(["totals.csv"])
    with app.expect_download() as download:
        app.get_by_role("button", name="Download run log").click()

    assert download.value.suggested_filename == "run-log.txt"
    assert (server.workdir / "out" / "e2e-test_v2-0-1" / "totals.csv").read_text().startswith("# CountESS ")


# ---- themes and text size -----------------------------------------------------------------------


def computed(page: Page, prop: str) -> str:
    return page.evaluate(f"getComputedStyle(document.body).{prop}")


def choose_view(page: Page, setting: str, value: str) -> None:
    page.get_by_role("button", name="View").click()
    page.locator(f".view-menu input[name={setting}][value={value}]").check()
    page.get_by_role("button", name="View").click()


def test_the_dark_theme_and_presentation_size_apply_and_are_remembered(app: Page) -> None:
    choose_view(app, "theme", "dark")
    choose_view(app, "text-size", "presentation")

    assert computed(app, "backgroundColor") == "rgb(20, 23, 30)"
    assert computed(app, "fontSize") == "21px"
    app.reload()
    app.wait_for_selector(".pipeline-node")
    assert (computed(app, "backgroundColor"), computed(app, "fontSize")) == ("rgb(20, 23, 30)", "21px")


def test_a_theme_saved_as_a_file_can_be_edited_and_loaded_back(app: Page, tmp_path: pathlib.Path) -> None:
    choose_view(app, "theme", "light")
    app.get_by_role("button", name="View").click()
    with app.expect_download() as download:
        app.get_by_role("button", name="Save current theme as a file").click()
    theme = json.loads(pathlib.Path(download.value.path()).read_text())
    theme["label"] = "Lab slides"
    theme["colors"]["background"] = "#fdf6e3"
    edited = tmp_path / "lab-slides.json"
    edited.write_text(json.dumps(theme))

    app.locator(".view-menu input[type=file]").set_input_files(edited)

    expect(app.locator(".view-menu .user-theme")).to_contain_text("Lab slides")
    assert computed(app, "backgroundColor") == "rgb(253, 246, 227)"


def test_a_theme_file_with_a_colour_missing_is_refused_with_its_reason(app: Page, tmp_path: pathlib.Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(
        json.dumps({"format": "countess-web-theme", "version": 1, "label": "Broken", "scheme": "light", "colors": {}})
    )
    app.get_by_role("button", name="View").click()

    app.locator(".view-menu input[type=file]").set_input_files(broken)

    expect(app.locator(".view-menu .errors")).to_contain_text('"colors" has no "background"')
    expect(app.locator(".view-menu .user-theme")).to_have_count(0)
