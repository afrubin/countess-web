import type {
  FileListing,
  Graph,
  GraphNode,
  Param,
  ParameterChange,
  DownloadLink,
  PluginInfo,
  Preview,
  RunOutput,
  RunSummary,
} from './types'
import { forgetToken, token } from './token'

export class ApiError extends Error {}

/** Saves the file behind a one-time download link: the browser streams it to disk. */
export function followDownload(url: string) {
  const link = document.createElement('a')
  link.href = url
  link.download = ''
  document.body.append(link)
  link.click()
  link.remove()
}

/** Raised when the server refuses the token: the page needs the address with the current one. */
export class NotAuthorisedError extends ApiError {}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  // Relative, so the page also works behind a proxy that serves it under a path prefix.
  const response = await fetch(url.replace(/^\//, ''), {
    method,
    credentials: 'omit',
    headers: {
      'x-countess-token': token(),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 401) {
    forgetToken()
    throw new NotAuthorisedError('This page is not authorised: open CountESS with the address it printed.')
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const json = await response.json()
      if (typeof json.detail === 'string') detail = json.detail
      else if (json.detail) detail = JSON.stringify(json.detail)
    } catch {
      // the error body was not JSON; keep the status line
    }
    throw new ApiError(detail)
  }
  return (await response.json()) as T
}

const q = (params: Record<string, string | number | boolean | undefined | null>) =>
  new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => [k, String(v)]),
  ).toString()

export const api = {
  plugins: () => request<PluginInfo[]>('GET', '/api/plugins'),
  graph: () => request<Graph>('GET', '/api/graph'),
  newConfig: () => request<Graph>('POST', '/api/config/new'),
  loadConfig: (path: string) => request<Graph>('POST', '/api/config/load', { path }),
  saveConfig: (path?: string) => request<{ path: string }>('POST', '/api/config/save', { path }),
  tidy: () => request<Graph>('POST', '/api/graph/tidy'),
  setWorkflow: (name: string, version: string) => request<Graph>('PATCH', '/api/workflow', { name, version }),

  addNode: (position: [number, number], plugin?: string) =>
    request<GraphNode>('POST', '/api/nodes', { position, plugin }),
  updateNode: (id: string, changes: { name?: string; position?: [number, number]; notes?: string }) =>
    request<GraphNode>('PATCH', `/api/nodes/${id}`, changes),
  deleteNode: (id: string) => request<unknown>('DELETE', `/api/nodes/${id}`),
  setPlugin: (id: string, plugin: string) => request<GraphNode>('POST', `/api/nodes/${id}/plugin`, { plugin }),

  connect: (parent: string, child: string) => request<unknown>('POST', '/api/edges', { parent, child }),
  disconnect: (parent: string, child: string) => request<unknown>('DELETE', `/api/edges?${q({ parent, child })}`),

  parameters: (id: string) => request<Param[]>('GET', `/api/nodes/${id}/parameters`),
  changeParameter: (id: string, change: ParameterChange) =>
    request<Param[]>('POST', `/api/nodes/${id}/parameters`, change),
  preview: (id: string, offset: number, limit: number, sort: string | null, descending: boolean) =>
    request<Preview>('GET', `/api/nodes/${id}/preview?${q({ offset, limit, sort, descending })}`),

  run: () => request<RunSummary | null>('GET', '/api/run'),
  startRun: () => request<RunSummary>('POST', '/api/run'),
  stopRun: () => request<unknown>('POST', '/api/run/stop'),
  runOutputs: () => request<RunOutput[]>('GET', '/api/run/outputs'),
  runOutputLink: (index: number) => request<DownloadLink>('POST', `/api/run/outputs/${index}/download`),
  runLogLink: () => request<DownloadLink>('POST', '/api/run/log/download'),
  previewLink: (id: string, sort: string | null, descending: boolean) =>
    request<DownloadLink>('POST', `/api/nodes/${id}/preview/download`, { sort, descending }),

  files: (path: string | null, patterns: string[]) =>
    request<FileListing>('GET', `/api/files?${q({ path, patterns: patterns.join(',') })}`),
}
