import type { paths } from './api-schema'
import type { NodeUpdate, ParameterChange, ResponseOf, WorkflowUpdate } from './types'
import { forgetToken, token } from './token'

export class ApiError extends Error {
  /** The response's HTTP status, if there was a response. */
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
  }
}

/** Raised when the server refuses the token: the page needs the address with the current one. */
export class NotAuthorisedError extends ApiError {}

/** Saves the file behind a one-time download link: the browser streams it to disk. */
export function followDownload(url: string): void {
  const link = document.createElement('a')
  link.href = url
  link.download = ''
  document.body.append(link)
  link.click()
  link.remove()
}

type Method = 'get' | 'post' | 'patch' | 'delete'

/**
 * Calls a route of the API. ``route`` is the path as the schema names it (``/api/nodes/{node_id}``);
 * ``url`` is the same path with its parameters filled in. The body sent back is typed from the
 * schema, so a route's response cannot be read as some other shape.
 */
async function call<P extends keyof paths, M extends Method & keyof paths[P]>(
  method: M,
  _route: P,
  url: string,
  body?: unknown,
): Promise<ResponseOf<P, M>> {
  // Relative, so the page also works behind a proxy that serves it under a path prefix.
  const headers: Record<string, string> = { 'x-countess-token': token() }
  const init: RequestInit = { method: method.toUpperCase(), credentials: 'omit', headers }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  const response = await fetch(url.replace(/^\//, ''), init)
  if (response.status === 401) {
    forgetToken()
    throw new NotAuthorisedError('This page is not authorised: open CountESS with the address it printed.')
  }
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return (await response.json()) as ResponseOf<P, M>
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const json: unknown = await response.json()
    if (typeof json === 'object' && json !== null && 'detail' in json) {
      const detail = json.detail
      return typeof detail === 'string' ? detail : JSON.stringify(detail)
    }
  } catch {
    // the error body was not JSON; report the status line
  }
  return `${response.status} ${response.statusText}`
}

const query = (params: Record<string, string | number | boolean | undefined | null>): string =>
  new URLSearchParams(
    Object.entries(params).flatMap(([k, v]) => (v === undefined || v === null ? [] : [[k, String(v)]])),
  ).toString()

const id = encodeURIComponent

export const api = {
  plugins: () => call('get', '/api/plugins', '/api/plugins'),
  graph: () => call('get', '/api/graph', '/api/graph'),
  newConfig: () => call('post', '/api/config/new', '/api/config/new'),
  loadConfig: (path: string) => call('post', '/api/config/load', '/api/config/load', { path }),
  saveConfig: (path?: string) => call('post', '/api/config/save', '/api/config/save', { path }),
  tidy: () => call('post', '/api/graph/tidy', '/api/graph/tidy'),
  setWorkflow: (workflow: WorkflowUpdate) => call('patch', '/api/workflow', '/api/workflow', workflow),

  addNode: (position: [number, number], plugin?: string) =>
    call('post', '/api/nodes', '/api/nodes', { position, plugin }),
  updateNode: (nodeId: string, changes: NodeUpdate) =>
    call('patch', '/api/nodes/{node_id}', `/api/nodes/${id(nodeId)}`, changes),
  deleteNode: (nodeId: string) => call('delete', '/api/nodes/{node_id}', `/api/nodes/${id(nodeId)}`),
  setPlugin: (nodeId: string, plugin: string) =>
    call('post', '/api/nodes/{node_id}/plugin', `/api/nodes/${id(nodeId)}/plugin`, { plugin }),

  connect: (parent: string, child: string) => call('post', '/api/edges', '/api/edges', { parent, child }),
  disconnect: (parent: string, child: string) =>
    call('delete', '/api/edges', `/api/edges?${query({ parent, child })}`),

  parameters: (nodeId: string) =>
    call('get', '/api/nodes/{node_id}/parameters', `/api/nodes/${id(nodeId)}/parameters`),
  changeParameter: (nodeId: string, change: ParameterChange) =>
    call('post', '/api/nodes/{node_id}/parameters', `/api/nodes/${id(nodeId)}/parameters`, change),
  preview: (nodeId: string, offset: number, limit: number) =>
    call('get', '/api/nodes/{node_id}/preview', `/api/nodes/${id(nodeId)}/preview?${query({ offset, limit })}`),

  run: () => call('get', '/api/run', '/api/run'),
  startRun: () => call('post', '/api/run', '/api/run'),
  stopRun: () => call('post', '/api/run/stop', '/api/run/stop'),
  runOutputs: () => call('get', '/api/run/outputs', '/api/run/outputs'),
  runOutputLink: (index: number) =>
    call('post', '/api/run/outputs/{index}/download', `/api/run/outputs/${index}/download`),
  runLogLink: () => call('post', '/api/run/log/download', '/api/run/log/download'),
  savePreview: (nodeId: string, overwrite: boolean) =>
    call('post', '/api/nodes/{node_id}/preview/save', `/api/nodes/${id(nodeId)}/preview/save`, { overwrite }),

  files: (path: string | null, patterns: string[]) =>
    call('get', '/api/files', `/api/files?${query({ path, patterns: patterns.join(',') })}`),
}
