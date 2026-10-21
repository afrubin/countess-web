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
- **Run** runs the whole pipeline in a separate process: editing the pipeline while it runs does not change the run,
  and closing the browser does not stop it. The run's output appears in the log at the bottom.
- **Workflow** (the button showing the workflow's name, once it has one) sets a short name and a semantic version
  for the pipeline, saved with it. Output file names are made from them: a new CSV Save writes
  `{date}_{workflow}_{version}_{node}.csv` beside the pipeline file, such as
  `2026-10-19_fwd-saturation_v1-2-0_save-results.csv`, so that runs on different days or of different versions do
  not overwrite each other. A save node's filename can use the fields `{date}`, `{time}`, `{workflow}`, `{version}`
  and `{node}` in any arrangement; the page shows the file it names now. Downloads follow the same pattern:
  `…_total-preview.csv` for a preview, `…_run-log.txt` for a run's log.
- **Where results go:** a run writes its files on the server, wherever each save node (CSV Save, say) is set to
  write. **Outputs…** lists the files the last run wrote, with a button to download each to the computer showing the
  page; **Download CSV** above a preview downloads that preview, in the order shown. A preview holds at most
  `--preview-rows` rows (100,000 unless set); a run writes every row. On a cluster, large results are better copied
  with `scp`, `rsync` or Globus than through the browser.
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
- A download is a link the API issues to a holder of the token: it works once, for a minute, and only for a file the
  last run wrote or a preview just exported, never an arbitrary path.
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

## Requirements

countess-web needs a CountESS with workflow names and versions (its `countess.core.workflow` module), which is
not in a CountESS release yet; until it is, install CountESS from the branch that adds it.

## Development

```shell
pip install -e ".[dev]"
pytest                       # the server's tests

cd frontend
npm ci
npm test
npm run lint
npm run build      # checks the generated API types, type-checks, then builds into ../src/countess_web/static
```

The browser tests drive the built page in headless Chromium, each against a fresh server over `tests/data`: the
token, previews, parameter changes, building and saving a pipeline, runs, downloads and the workflow dialog. They are
left out of a plain `pytest`; to run them:

```shell
pip install -e ".[dev,e2e]"
python -m playwright install chromium
(cd frontend && npm run build)
pytest -m e2e
```

GitHub Actions (`.github/workflows/ci.yml`) runs the server's tests, the front end's lint, unit tests, type-check
and build, and the browser tests, keeping a Playwright trace of any that fail. It installs CountESS from the git
ref in `COUNTESS_REF`, since countess-web needs CountESS's workflow names and versions, which no release has yet.

### The API's types

The browser's types are generated from the server, not written twice. `countess_web/models.py` declares every shape
the API sends and accepts, each parameter kind following one family of CountESS's parameter classes with its value
typed as CountESS holds it. FastAPI publishes those models as an OpenAPI schema, committed as
`frontend/openapi.json`, and `openapi-typescript` turns that into `frontend/src/api-schema.ts`, which
`frontend/src/types.ts` names for use. After changing a model or a route:

```shell
python -m countess_web.schema frontend/openapi.json
cd frontend && npm run generate:api
```

Neither file can fall behind unnoticed: `tests/test_schema.py` fails if `openapi.json` is not the server's schema, and
`npm run build` (through `npm run check:api`) fails if `api-schema.ts` is not what `openapi.json` generates. A model
change that the page does not follow then fails the page's type-check.

`npm run lint` runs ESLint with typescript-eslint's strict, type-checked rules; the compiler runs with `strict`,
`noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`.

For working on the page with hot reload, run the server with a fixed token and Vite's dev server alongside it, then
open `http://localhost:5173/?token=dev`:

```shell
COUNTESS_WEB_TOKEN=dev countess_web my_pipeline.ini --port 8642 --no-browser
cd frontend && COUNTESS_WEB_PORT=8642 npm run dev
```

Front-end dependencies are installed with a release-age cutoff (`npm install --before <date a week ago>`), so a
just-published, possibly compromised release is never resolved; `package-lock.json` records what was installed.
