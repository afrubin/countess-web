export type Status = 'DIRTY' | 'WORKING' | 'RESULT' | 'ERROR'

export interface PluginInfo {
  key: string
  name: string
  description: string
  numInputs: number
  numOutputs: number
}

export interface NodePlugin extends PluginInfo {
  version: string
  additional: string
  link: string | null
  showPreview: boolean
}

export interface GraphNode {
  id: string
  name: string
  position: [number, number]
  notes: string
  status: Status
  message: string
  parents: string[]
  plugin: NodePlugin | null
}

export interface Graph {
  version: number
  config: string | null
  modified: boolean
  nodes: GraphNode[]
}

export interface FileType {
  label: string
  patterns: string[]
}

interface ParamBase {
  path: string
  label: string
  hide: boolean
  readOnly: boolean
}

export type ScalarParam = ParamBase &
  (
    | { kind: 'boolean'; value: boolean }
    | { kind: 'string'; value: string | null }
    | { kind: 'integer'; value: number | null }
    | { kind: 'number'; value: number | string | null }
    | { kind: 'text'; value: string }
    | { kind: 'choice'; value: string | null; choices: string[] }
    | { kind: 'combo'; value: string | number | null; choices: string[] }
    | { kind: 'multichoice'; value: string[]; choices: string[] }
    | { kind: 'file'; value: string; absolute: string; mode: 'open' | 'save'; fileTypes: FileType[] }
  )

export type GroupParam = ParamBase & { kind: 'group'; framed: boolean; children: Param[] }

export type ArrayParam = ParamBase & {
  kind: 'array'
  layout: 'table' | 'frames' | 'list'
  columns: string[]
  rowLabels: boolean
  rows: Param[]
  canAdd: boolean
  canDelete: boolean
  addFiles: boolean
  fileTypes: FileType[]
  itemLabel: string
}

export type Param = ScalarParam | GroupParam | ArrayParam

export interface ParameterChange {
  path: string
  value?: unknown
  action?: 'add' | 'delete' | 'addFiles'
  index?: number
  paths?: string[]
}

export interface Column {
  name: string
  type: string
}

export interface Preview {
  status: Status
  message: string
  columns: Column[]
  rows: unknown[][]
  total: number
}

export interface RunSummary {
  id: string
  config: string
  started: string
  finished: string | null
  returncode: number | null
  running: boolean
}

export interface RunOutput {
  index: number
  node: string
  parameter: string
  file: string
  name: string
  size: number | null
  written: boolean
}

export interface DownloadLink {
  url: string
  rows?: number
}

export interface LogRecord {
  seq: number
  time: string
  level: string
  source: string
  message: string
}

export interface FileEntry {
  name: string
  path: string
  isDir: boolean
  size: number | null
}

export interface FileListing {
  path: string
  parent: string | null
  entries: FileEntry[]
}

export interface FileDialogOptions {
  title: string
  mode: 'open' | 'save' | 'multiple'
  fileTypes: FileType[]
  initial?: string
}
