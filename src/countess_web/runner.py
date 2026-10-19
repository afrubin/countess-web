"""Runs a pipeline as ``countess_cmd`` does, with DuckDB held to the job's allocation.

``PipelineGraph.run`` opens its own DuckDB connection with ``duckdb.connect()``, which sizes
itself to the whole node; on a cluster the scheduler then kills the run for using memory the job
was not given. This runs the same command with that connection made with the job's settings.
"""

from __future__ import annotations

import functools
import logging
import sys

import duckdb
from countess.core import cmd

from countess_web import resources


def main() -> None:
    config = resources.settings(resources.RUN_MEMORY_FRACTION)
    if config:
        # This process exists only for the run, so replacing duckdb.connect reaches nothing else.
        duckdb.connect = functools.partial(duckdb.connect, config=config)  # type: ignore[assignment]
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    cmd.run(sys.argv[1:])


if __name__ == "__main__":
    main()
