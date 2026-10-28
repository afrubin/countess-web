"""Runs a pipeline as ``countess_cmd`` does, with DuckDB held to the job's allocation and its output
directory named from a start time the caller chose.

``PipelineGraph.run`` opens its own DuckDB connection with ``duckdb.connect()``, which sizes
itself to the whole node; on a cluster the scheduler then kills the run for using memory the job
was not given. This runs the pipeline with that connection made with the job's settings.

The caller passes the start time (``--started``) so that it can work out the run's output
directory, which may hold the date and time, exactly as the run fills it in. The pipeline is a
snapshot in a folder of its own, so the caller also passes the folder a relative output directory is
relative to (``--base-dir``): the pipeline's own.
"""

from __future__ import annotations

import argparse
import datetime
import functools
import logging
import sys

import duckdb
from countess.core import cmd

from countess_web import resources


def main() -> None:
    parser = argparse.ArgumentParser(prog="countess_web.runner")
    parser.add_argument("--started", type=datetime.datetime.fromisoformat, default=None)
    parser.add_argument("--base-dir", default=None)
    parser.add_argument("config")
    args = parser.parse_args()

    config = resources.settings(resources.RUN_MEMORY_FRACTION)
    if config:
        # This process exists only for the run, so replacing duckdb.connect reaches nothing else.
        duckdb.connect = functools.partial(duckdb.connect, config=config)  # type: ignore[assignment]
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    for graph in cmd.configure_graphs([args.config]):
        if args.base_dir:
            graph.base_dir = args.base_dir
        graph.run(started=args.started)


if __name__ == "__main__":
    main()
