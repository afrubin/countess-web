import type { InjectionKey } from 'vue'
import type { FileType, ParameterChange } from '../types'

/** What a parameter widget can ask of the form that holds it. */
export interface ParamActions {
  change: (change: ParameterChange) => Promise<void>
  chooseFiles: (title: string, mode: 'open' | 'save' | 'multiple', fileTypes: FileType[], initial?: string) => Promise<string[] | null>
}

export const paramActionsKey: InjectionKey<ParamActions> = Symbol('paramActions')
