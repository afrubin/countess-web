"""``countess_web``: serve CountESS's browser interface for one user.

On a laptop it opens the browser. On a cluster, run it inside a job (an interactive session or a
batch job) and it prints how to reach it: the SSH tunnel to the compute node it is running on.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import pathlib
import secrets
import socket
import sys
import threading
import webbrowser
from typing import Optional

import uvicorn

from countess_web import VERSION
from countess_web.app import create_app
from countess_web.session import Session

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="countess_web", description="CountESS in a web browser")
    parser.add_argument("config", nargs="?", help="a pipeline .ini to open")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: this machine only)")
    parser.add_argument("--port", type=int, default=0, help="port to listen on (default: any free port)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a web browser")
    parser.add_argument("--preview-rows", type=int, default=100_000, help="rows each preview computes (default 100000)")
    parser.add_argument("--version", action="version", version=f"countess_web {VERSION}")
    return parser.parse_args(argv)


def free_port(host: str) -> int:
    with socket.socket() as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def connection_help(host: str, port: int, token: str) -> str:
    url = f"http://localhost:{port}/?token={token}"
    lines = ["", "CountESS is running. Open:", f"    {url}"]
    if "SLURM_JOB_ID" in os.environ:
        node = os.environ.get("SLURMD_NODENAME") or socket.gethostname()
        login = os.environ.get("SLURM_SUBMIT_HOST", "<login node>")
        target = "localhost" if host in ("127.0.0.1", "localhost") else node
        lines += [
            "",
            f"This is SLURM job {os.environ['SLURM_JOB_ID']} on {node}. From your own computer, first run:",
            f"    ssh -N -L {port}:{target}:{port} {getpass.getuser()}@{login}"
            if target != "localhost"
            else f"    ssh -N -L {port}:localhost:{port} -J {getpass.getuser()}@{login} {getpass.getuser()}@{node}",
            f"(If {login} is not the address you log in to, use that address instead.) Then open the address above.",
        ]
    lines += ["", "Anyone with this address can use your account's files through CountESS: keep it private.", ""]
    return "\n".join(lines)


def announce(help_text: str) -> None:
    """Shows the address, token included, to the user and no one else.

    In a terminal it is printed. In a batch job stderr goes to the job's output file, which other
    users can often read, so the address goes to a file only the user can read and the output
    file gets its path.
    """
    if "SLURM_JOB_ID" in os.environ and not sys.stderr.isatty():
        directory = pathlib.Path.home() / ".countess-web"
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / f"job-{os.environ['SLURM_JOB_ID']}.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(help_text)
        os.chmod(path, 0o600)
        message = f"CountESS is running; how to connect (with its private address) is in {path}"
        print(message, file=sys.stderr)  # pylint: disable=bad-builtin
    else:
        print(help_text, file=sys.stderr)  # pylint: disable=bad-builtin


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    session = Session(pathlib.Path.cwd(), preview_row_limit=args.preview_rows)
    logging.getLogger().addHandler(session.logs)
    if args.config:
        session.load(args.config)

    # A fixed token is for development (the front end's dev server sends it); otherwise each start makes one.
    token = os.environ.get("COUNTESS_WEB_TOKEN") or secrets.token_urlsafe(24)
    port = args.port or free_port(args.host)
    announce(connection_help(args.host, port, token))

    if not args.no_browser and "SLURM_JOB_ID" not in os.environ:
        url = f"http://localhost:{port}/?token={token}"
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    try:
        uvicorn.run(create_app(session, token), host=args.host, port=port, log_level="warning")
    finally:
        session.close()


if __name__ == "__main__":
    main()
