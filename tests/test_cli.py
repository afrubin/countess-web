"""Where the address, with its token, is shown."""

from __future__ import annotations

import pathlib
import stat

import pytest

from countess_web import cli


def test_outside_a_batch_job_the_address_is_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)

    cli.announce(cli.connection_help("127.0.0.1", 40123, "secret-token"))

    assert "http://localhost:40123/?token=secret-token" in capsys.readouterr().err


def test_in_a_batch_job_the_address_goes_to_a_file_only_the_user_can_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "4242")
    monkeypatch.setenv("HOME", str(tmp_path))

    cli.announce(cli.connection_help("127.0.0.1", 40123, "secret-token"))

    printed = capsys.readouterr().err
    written = tmp_path / ".countess-web" / "job-4242.txt"
    assert "secret-token" not in printed
    assert str(written) in printed
    assert "?token=secret-token" in written.read_text()
    assert stat.S_IMODE(written.stat().st_mode) == 0o600
