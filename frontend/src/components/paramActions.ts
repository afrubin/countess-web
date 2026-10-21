import { inject, type InjectionKey } from 'vue'
import type { FileType, ParameterChange } from '../types'

/** What a parameter widget can ask of the form that holds it. */
export interface ParamActions {
  change: (change: ParameterChange) => Promise<void>
  chooseFiles: (
    title: string,
    mode: 'open' | 'save' | 'multiple',
    fileTypes: FileType[],
    initial: string | null,
  ) => Promise<string[] | null>
}

export const paramActionsKey: InjectionKey<ParamActions> = Symbol('paramActions')

/** The actions of the form a parameter widget is in; a widget outside one is a programming error. */
export function useParamActions(): ParamActions {
  const actions = inject(paramActionsKey)
  if (!actions) throw new Error('A parameter widget must be inside a form that provides paramActionsKey')
  return actions
}
