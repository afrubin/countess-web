import { reactive } from 'vue'
import { api, ApiError, NotAuthorisedError } from './api'
import { token } from './token'
import type { FileDialogOptions, Graph, LogRecord, PluginInfo, RunSummary, Status } from './types'

const MAX_LOGS = 1000

interface FileDialog {
  options: FileDialogOptions
  resolve: (paths: string[] | null) => void
}

export const store = reactive({
  graph: { version: -1, workflow: { name: null, version: null }, config: null, modified: false, nodes: [] } as Graph,
  plugins: [] as PluginInfo[],
  selectedId: null as string | null,
  logs: [] as LogRecord[],
  run: null as RunSummary | null,
  error: null as string | null,
  connected: false,
  authorised: true,
  fileDialog: null as FileDialog | null,
  showOutputs: false,
  showWorkflow: false,
})

export function selectedNode() {
  return store.graph.nodes.find((n) => n.id === store.selectedId) ?? null
}

/** Runs an API call, reporting a failure in the error banner rather than throwing. */
export async function attempt<T>(action: () => Promise<T>): Promise<T | undefined> {
  try {
    store.error = null
    return await action()
  } catch (exc) {
    if (exc instanceof NotAuthorisedError) store.authorised = false
    store.error = exc instanceof ApiError || exc instanceof Error ? exc.message : String(exc)
    return undefined
  }
}

export async function refreshGraph() {
  const graph = await attempt(api.graph)
  if (graph) setGraph(graph)
}

export function setGraph(graph: Graph) {
  store.graph = graph
  if (store.selectedId && !graph.nodes.some((n) => n.id === store.selectedId)) store.selectedId = null
}

export function chooseFiles(options: FileDialogOptions): Promise<string[] | null> {
  return new Promise((resolve) => {
    store.fileDialog = {
      options,
      resolve: (paths) => {
        store.fileDialog = null
        resolve(paths)
      },
    }
  })
}

interface StateEvent {
  type: 'state'
  version: number
  modified: boolean
  nodes: Record<string, { status: Status; message: string }>
}
type ServerEvent =
  | StateEvent
  | { type: 'run'; run: RunSummary | null }
  | { type: 'logs'; records: LogRecord[] }

/** Follows the server's events, reconnecting when the connection drops. */
export function connectEvents() {
  const url = new URL('api/events', location.href)
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const since = store.logs.length ? store.logs[store.logs.length - 1].seq : 0
  const socket = new WebSocket(url)
  socket.onopen = () => {
    socket.send(JSON.stringify({ token: token(), since }))
    store.connected = true
  }
  socket.onclose = (event) => {
    store.connected = false
    if (event.code === 4401) {
      store.authorised = false
      return
    }
    setTimeout(connectEvents, 2000)
  }
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data) as ServerEvent
    if (event.type === 'state') applyState(event)
    else if (event.type === 'run') store.run = event.run
    else if (event.type === 'logs') {
      store.logs.push(...event.records)
      if (store.logs.length > MAX_LOGS) store.logs.splice(0, store.logs.length - MAX_LOGS)
    }
  }
}

function applyState(event: StateEvent) {
  if (event.version !== store.graph.version) {
    void refreshGraph()
    return
  }
  store.graph.modified = event.modified
  for (const node of store.graph.nodes) {
    const state = event.nodes[node.id]
    if (state) {
      node.status = state.status
      node.message = state.message
    }
  }
}
