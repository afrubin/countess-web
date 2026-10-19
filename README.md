# countess-web

A web browser interface for [CountESS](https://github.com/CountESS-Project/CountESS). The pipeline is built,
previewed and run on the machine where the data is, whether that is a laptop or a compute node on a cluster, and it is
controlled from a browser anywhere the user can reach that machine.

It is a prototype. It edits and runs the same `.ini` pipelines as CountESS's desktop GUI, with every installed CountESS
plugin, but it has not had the desktop GUI's years of use.

## Using it

```shell
pip install countess-web
countess_web my_pipeline.ini
```

`countess_web` starts a server for one user and prints the address to open, which ends in `?token=…`. On a laptop it
opens the browser itself. The token is what keeps other users of the machine out (see [Security](#security)).

In the browser:

- **The graph** (left) is the pipeline. Double-click empty space, or press **Add node**, to add a node; drag from a
  node's right edge to another's left edge to connect them; click a connection to remove it; drag nodes to arrange
  them, or press **Tidy**.
- **The node panel** (right) configures the selected node: choose its plugin, set its parameters, and see a preview of
  its output that updates as the parameters change. Click a column heading to sort the preview.
- **Run** runs the whole pipeline, writing its outputs, in a separate process: editing the pipeline while it runs does
  not change the run, and closing the browser does not stop it. The run's output appears in the log at the bottom.
- **Open**, **Save** and **Save as** read and write pipeline `.ini` files, and **Choose…** picks input files, all
  through a browser of the *server's* files: on a cluster, the data and the pipeline are where the job runs, not on
  the computer showing the page.

## On an HPC cluster

Run `countess_web` inside a job, so the previews and runs use the job's allocation rather than a shared login node:

```shell
srun --cpus-per-task=8 --mem=32G --time=4:00:00 --pty countess_web my_pipeline.ini
```

or submit [`hpc/countess_web.sbatch`](hpc/countess_web.sbatch) with `sbatch` and read the address from its output file.

Inside a SLURM job, `countess_web` holds DuckDB to the job's CPUs and memory (`SLURM_CPUS_PER_TASK`,
`SLURM_MEM_PER_NODE`), puts DuckDB's spill files under `$TMPDIR`, and prints the SSH command that tunnels from your own
computer to the compute node:

```text
This is SLURM job 123456 on node042. From your own computer, first run:
    ssh -N -L 40123:localhost:40123 -J you@login.hpc.example.edu you@node042
then open the address above.
```

Sites that run [Open OnDemand](https://openondemand.org) can wrap `countess_web` as an interactive app, so that users
start it from the portal and reach it through the portal's proxy without an SSH tunnel; the site's login then guards it
in place of the token. That needs a small site-specific app definition, which is not included yet.

## Security

The server acts as the user who started it: it reads and writes the files that user can, and runs the pipelines it is
given. Anyone who can use the page can do the same.

- It listens on `127.0.0.1` only, unless `--host` says otherwise; on a cluster the SSH tunnel reaches it there.
- Every API request needs the token printed at start, sent in a request header, and the event stream needs it as its
  first message. The page takes the token out of the address bar and keeps it in the tab's own storage.
- The token is never a cookie. Browsers send a `localhost` cookie to every port, so every web server on the machine
  (or reached through another tunnel) would receive it. And because it travels in a header, a page from another site
  cannot make a request that carries it, and two CountESS servers do not interfere with each other.
- In a batch job, where the job's output file may be readable by others, the address goes to
  `~/.countess-web/job-<id>.txt`, readable only by you, and the output file says where.
- A new token is made at every start. Keep the address private: anyone with it, who can reach the port, can use your
  account's files.

## How it works

CountESS keeps the pipeline engine (`countess.core`) separate from its Tk interface (`countess.gui`), and plugins
declare their parameters without any interface code. countess-web replaces only the interface:

- **`countess_web.session`** holds one `PipelineGraph`. Every change stops CountESS's preview thread, makes the change
  and restarts it, as the desktop GUI does, so the preview thread never sees a half-made change.
- **`countess_web.params`** turns a plugin's parameters into JSON the page draws as a form, and applies the page's
  changes back. A parameter is addressed by the key the `.ini` file uses for it (`steps.0.output`), so new plugins and
  parameter types need no interface code unless they introduce a new kind of parameter.
- **`countess_web.app`** is the HTTP API (FastAPI), plus a WebSocket that pushes node status, run status and log
  records to the page.
- **`frontend/`** is the page: Vue 3 and TypeScript, with [Vue Flow](https://vueflow.dev) for the graph. It is built
  into `src/countess_web/static`, and a wheel carries the built page, so installing on a cluster needs no Node.js.
- **Runs** are CountESS's command-line run on a snapshot of the pipeline, in a child process
  (`countess_web.runner`), with DuckDB held to the job's allocation.
- **The preview loop** is CountESS's own with one difference: it stops between nodes when a change arrives. CountESS's
  loop interrupts only the node running and then computes every other dirty node, so a change would wait for the whole
  preview.

### Known limits

- One server serves one user and one pipeline at a time.
- Previews and a full run can go at the same time, so each takes part of the job's memory (35% and 40%).
- Two things are worked around here and would be better fixed in CountESS: the preview loop not stopping when asked,
  and `PipelineGraph.run` opening its own DuckDB connection with no way to pass its settings.
- No Open OnDemand app definition yet, and no submission of runs as their own batch jobs. The page uses relative
  addresses so it can be served under a proxy's path prefix, but this has not been tried behind Open OnDemand.

## Development

```shell
pip install -e ".[dev]"
pytest

cd frontend
npm ci
npm test
npm run build      # type-checks, then builds into ../src/countess_web/static
```

For working on the page with hot reload, run the server with a fixed token and Vite's dev server alongside it, then
open `http://localhost:5173/?token=dev`:

```shell
COUNTESS_WEB_TOKEN=dev countess_web my_pipeline.ini --port 8642 --no-browser
cd frontend && COUNTESS_WEB_PORT=8642 npm run dev
```

Front-end dependencies are installed with a release-age cutoff (`npm install --before <date a week ago>`), so a
just-published, possibly compromised release is never resolved; `package-lock.json` records what was installed.
