import { reactive } from 'vue'
import { api, ApiError, NotAuthorisedError } from './api'
import { token } from './token'
import type { EventHello, FileDialogOptions, Graph, LogRecord, PluginInfo, RunSummary, ServerEvent, StateEvent } from './types'

const MAX_LOGS = 1000

interface FileDialog {
  options: FileDialogOptions
  resolve: (paths: string[] | null) => void
}

interface State {
  graph: Graph
  plugins: PluginInfo[]
  selectedId: string | null
  logs: LogRecord[]
  run: RunSummary | null
  error: string | null
  connected: boolean
  authorised: boolean
  fileDialog: FileDialog | null
  showOutputs: boolean
  showWorkflow: boolean
}

const initial: State = {
  // Version -1 is no graph yet: the first state event fetches the real one.
  graph: { version: -1, workflow: { name: null, version: null }, config: null, modified: false, nodes: [] },
  plugins: [],
  selectedId: null,
  logs: [],
  run: null,
  error: null,
  connected: false,
  authorised: true,
  fileDialog: null,
  showOutputs: false,
  showWorkflow: false,
}

export const store = reactive<State>(initial)

export function selectedNode(): Graph['nodes'][number] | null {
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

export async function refreshGraph(): Promise<void> {
  const graph = await attempt(api.graph)
  if (graph) setGraph(graph)
}

export function setGraph(graph: Graph): void {
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

const EVENT_TYPES: ReadonlySet<string> = new Set<ServerEvent['type']>(['state', 'run', 'logs'])

/**
 * An event-socket message as the event it is. The page is served by the server whose events it
 * reads, so their shapes are the generated types; this checks only that the message is an event
 * at all, of a type the page knows, and ignores anything else.
 */
function parseEvent(data: unknown): ServerEvent | null {
  if (typeof data !== 'string') return null
  const parsed: unknown = JSON.parse(data)
  if (typeof parsed !== 'object' || parsed === null || !('type' in parsed)) return null
  return typeof parsed.type === 'string' && EVENT_TYPES.has(parsed.type) ? (parsed as ServerEvent) : null
}

/** Follows the server's events, reconnecting when the connection drops. */
export function connectEvents(): void {
  const url = new URL('api/events', location.href)
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const hello: EventHello = { token: token(), since: store.logs.at(-1)?.seq ?? 0 }
  const socket = new WebSocket(url)
  socket.onopen = () => {
    socket.send(JSON.stringify(hello))
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
  socket.onmessage = (message: MessageEvent<unknown>) => {
    const event = parseEvent(message.data)
    if (event === null) return
    switch (event.type) {
      case 'state':
        applyState(event)
        break
      case 'run':
        store.run = event.run
        break
      case 'logs':
        store.logs.push(...event.records)
        if (store.logs.length > MAX_LOGS) store.logs.splice(0, store.logs.length - MAX_LOGS)
        break
    }
  }
}

function applyState(event: StateEvent): void {
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
