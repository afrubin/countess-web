// The API's types, named for use in the page. They are generated (src/api-schema.ts) from the
// server's OpenAPI schema, whose models (countess_web/models.py) follow CountESS's own classes;
// nothing here describes the API by hand. Regenerate with `npm run generate:api`.

import type { components, paths } from './api-schema'

type Schemas = components['schemas']

export type Graph = Schemas['Graph']
export type GraphNode = Schemas['Node']
export type NodePlugin = Schemas['NodePlugin']
export type PluginInfo = Schemas['PluginInfo']
export type Workflow = Schemas['Workflow']
export type Status = GraphNode['status']

export type Param = Schemas['Param']
export type ParamKind = Param['kind']
/** The parameter model of one kind: ParamOf<'array'> is ArrayParamModel. */
export type ParamOf<K extends ParamKind> = Extract<Param, { kind: K }>
export type ParameterChange = Schemas['ParameterChange']
export type FileType = Schemas['FileType']

export type Preview = Schemas['Preview']
export type Column = Schemas['Column']
export type RunSummary = Schemas['RunSummary']
export type RunOutput = Schemas['RunOutput']
export type DownloadLink = Schemas['DownloadLink']
export type FileListing = Schemas['FileListing']
export type FileEntry = Schemas['FileEntry']
export type LogRecord = Schemas['LogRecord']
export type ServerEvent = Schemas['ServerEvent']
export type StateEvent = Schemas['StateEvent']
export type EventHello = Schemas['EventHello']
export type NodeUpdate = Schemas['NodeUpdate']

/** The JSON body a route sends back, by path and method. */
export type ResponseOf<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends {
  responses: { 200: { content: { 'application/json': infer Body } } }
}
  ? Body
  : never

/** The page's own: what a file dialog is asked for. Not part of the API. */
export interface FileDialogOptions {
  title: string
  mode: 'open' | 'save' | 'multiple'
  fileTypes: FileType[]
  /** The file (or, to save, the name) to start from, if any. */
  initial: string | null
}
