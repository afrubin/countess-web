// The design tokens every stylesheet draws from. A colour theme gives a value for every colour
// token, and a text size the size the type scale is built on; the page's CSS uses only the custom
// properties these become (--color-<token>, --text-<step>), never a colour or font size of its own.

/** The colour roles of the interface. */
export const COLOR_TOKENS = [
  'background', // the page behind everything
  'surface', // panels, inputs, dialogs
  'surface-alt', // the toolbar, the log, table headings
  'text',
  'text-muted', // labels, hints, secondary text
  'border',
  'focus', // a selection or highlight behind text
  'accent', // the main action, links, focus rings
  'on-accent', // text on an accent background
  'ok', // a node with a result
  'working', // a node being calculated, warnings
  'bad', // a failed node, errors
  'bad-surface', // the background of an error message
  'backdrop', // behind a dialog
  'canvas', // the graph's background
  'canvas-pattern', // the graph background's dots
  'edge', // a connection between nodes
  'edge-active', // a selected connection, or one being drawn
  'handle', // a node's connection point
] as const

export type ColorToken = (typeof COLOR_TOKENS)[number]

/** A complete colour theme: the type-checker refuses one that leaves a token out. */
export interface ColorTheme {
  id: string
  label: string
  /** Which native controls (scrollbars, date pickers) the browser should draw to match. */
  scheme: 'light' | 'dark'
  colors: Record<ColorToken, string>
}

/** The steps of the type scale, as multiples of the base size. */
export const TEXT_STEPS = {
  '2xs': 0.72,
  xs: 0.79,
  sm: 0.86,
  md: 0.93,
  base: 1,
  lg: 1.15,
  xl: 1.3,
} as const

export type TextStep = keyof typeof TEXT_STEPS

/** A text size: the size, in CSS pixels, the type scale and the spacing around text are built on. */
export interface TextSize {
  id: string
  label: string
  basePx: number
  /** What it is for, shown beside its name. */
  hint: string
}

export interface Typography {
  ui: string
  mono: string
}

export const cssColor = (token: ColorToken): string => `--color-${token}`
export const cssText = (step: TextStep): string => `--text-${step}`
