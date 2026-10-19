"""DuckDB's share of the machine: on a cluster, the job's allocation rather than the whole node.

DuckDB sizes itself from the node it runs on. Under a scheduler that is often far more than the
job was given, so the preview connection is held to the allocation SLURM reports.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Union

import duckdb
from countess.utils.duckdb import duckdb_escape_literal

logger = logging.getLogger(__name__)

# The fractions of the job's memory DuckDB may use for previews and for a full run, which can be
# going at the same time; the rest is for Python and the plugins themselves.
PREVIEW_MEMORY_FRACTION = 0.35
RUN_MEMORY_FRACTION = 0.4


def allocation() -> tuple[Optional[int], Optional[int]]:
    """The CPUs and memory (MB) the scheduler allocated this job, or None for each it did not state."""
    cpus = _int_env("SLURM_CPUS_PER_TASK") or _int_env("SLURM_CPUS_ON_NODE")
    memory = _int_env("SLURM_MEM_PER_NODE")
    per_cpu = _int_env("SLURM_MEM_PER_CPU")
    if memory is None and per_cpu is not None and cpus is not None:
        memory = per_cpu * cpus
    return cpus, memory


def settings(memory_fraction: float) -> dict[str, Union[str, bool, int, float, list[str]]]:
    """DuckDB settings holding a connection to the job's allocation (none outside a job)."""
    cpus, memory = allocation()
    config: dict[str, Union[str, bool, int, float, list[str]]] = {}
    if cpus is not None:
        config["threads"] = str(cpus)
    if memory is not None:
        config["memory_limit"] = f"{int(memory * memory_fraction)}MB"
    scratch = os.environ.get("TMPDIR")
    if scratch and os.path.isdir(scratch):
        config["temp_directory"] = os.path.join(scratch, "countess-duckdb")
    return config


def configure(ddbc: duckdb.DuckDBPyConnection, memory_fraction: float) -> None:
    config = settings(memory_fraction)
    for name, value in config.items():
        ddbc.sql(f"SET {name} = {duckdb_escape_literal(str(value))}")
    if "threads" in config or "memory_limit" in config:
        logger.info("DuckDB held to the job's allocation: %s", config)


def _int_env(name: str) -> Optional[int]:
    value = os.environ.get(name)
    try:
        return int(value) if value else None
    except ValueError:
        return None
