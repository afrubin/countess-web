// The themes and text sizes the page offers. A new colour theme is one more ColorTheme here: the
// type-checker requires every token, and theme.test.ts checks its contrast.

import type { ColorTheme, TextSize, Typography } from './tokens'

export const LIGHT: ColorTheme = {
  id: 'light',
  label: 'Light',
  scheme: 'light',
  colors: {
    background: '#ffffff',
    surface: '#ffffff',
    'surface-alt': '#f4f5f7',
    text: '#1d2330',
    'text-muted': '#5d6778',
    border: '#d5d9e0',
    focus: '#cfe0ff',
    accent: '#2b65cc',
    'on-accent': '#ffffff',
    ok: '#2a8c52',
    working: '#b06f00',
    bad: '#b83232',
    'bad-surface': '#fbeaea',
    backdrop: 'rgb(0 0 0 / 0.35)',
    canvas: '#ffffff',
    'canvas-pattern': '#c9ced6',
    edge: '#8a93a3',
    'edge-active': '#2b65cc',
    handle: '#5d6778',
  },
}

export const DARK: ColorTheme = {
  id: 'dark',
  label: 'Dark',
  scheme: 'dark',
  colors: {
    background: '#14171e',
    surface: '#1b1f27',
    'surface-alt': '#232834',
    text: '#e6e9ef',
    'text-muted': '#a3adbd',
    border: '#3a4150',
    focus: '#2a3f66',
    accent: '#7aa5f2',
    'on-accent': '#0f1625',
    ok: '#4cc27f',
    working: '#e5a93a',
    bad: '#f07878',
    'bad-surface': '#3a2326',
    backdrop: 'rgb(0 0 0 / 0.55)',
    canvas: '#171b22',
    'canvas-pattern': '#353c4a',
    edge: '#7b8597',
    'edge-active': '#7aa5f2',
    handle: '#a3adbd',
  },
}

export const COLOR_THEMES: readonly ColorTheme[] = [LIGHT, DARK]

export const TEXT_SIZES: readonly TextSize[] = [
  { id: 'normal', label: 'Normal', basePx: 14, hint: 'for working at a desk' },
  { id: 'large', label: 'Large', basePx: 17, hint: 'easier to read' },
  { id: 'presentation', label: 'Presentation', basePx: 21, hint: 'for screenshots on slides, and projectors' },
]

export const TYPOGRAPHY: Typography = {
  ui: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  mono: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
}
