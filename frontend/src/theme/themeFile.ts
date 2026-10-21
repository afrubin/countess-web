// A colour theme as a file: how a user adds a theme of their own. The file is JSON, with a value for
// every colour token:
//
//   {
//     "format": "countess-web-theme",
//     "version": 1,
//     "label": "Lab slides",
//     "scheme": "light",
//     "colors": { "background": "#ffffff", "surface": "#ffffff", ... }
//   }
//
// Any CSS colour is accepted (#rrggbb, rgb(), hsl(), oklch(), a name). The easiest start is the View
// menu's "Save current theme as a file", which writes the theme in use in this format.

import { COLOR_TOKENS, type ColorTheme, type ColorToken } from './tokens'

export const THEME_FILE_FORMAT = 'countess-web-theme'
export const THEME_FILE_VERSION = 1

/** User themes' ids start with this, so that none can take a built-in theme's place. */
export const USER_THEME_PREFIX = 'user:'

export type ThemeFileResult = { ok: true; theme: ColorTheme } | { ok: false; errors: string[] }

/** Whether a string is a colour CSS understands; the browser's own parser where there is one. */
export function isCssColor(value: string): boolean {
  if (typeof CSS !== 'undefined' && typeof CSS.supports === 'function') return CSS.supports('color', value)
  return /^(#[0-9a-f]{3,8}|(rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\(.+\)|[a-z]+)$/i.test(value.trim())
}

const slug = (text: string): string =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')

/** Reads a theme file, or says everything that is wrong with it. */
export function parseThemeFile(text: string, isColor: (value: string) => boolean = isCssColor): ThemeFileResult {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch (exc) {
    return { ok: false, errors: [`not JSON: ${exc instanceof Error ? exc.message : String(exc)}`] }
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return { ok: false, errors: ['a theme file is a JSON object'] }
  }
  const file = data as Record<string, unknown>
  const errors: string[] = []

  if (file.format !== THEME_FILE_FORMAT) errors.push(`"format" must be "${THEME_FILE_FORMAT}"`)
  if (file.version !== THEME_FILE_VERSION) errors.push(`"version" must be ${THEME_FILE_VERSION}`)
  const label = typeof file.label === 'string' ? file.label.trim() : ''
  if (!label) errors.push('"label" must be the theme\'s name')
  else if (!slug(label)) errors.push('"label" needs at least one letter or digit')
  if (file.scheme !== 'light' && file.scheme !== 'dark') errors.push('"scheme" must be "light" or "dark"')

  const colors: Partial<Record<ColorToken, string>> = {}
  if (typeof file.colors !== 'object' || file.colors === null || Array.isArray(file.colors)) {
    errors.push('"colors" must be an object with a colour for every token')
  } else {
    const given = file.colors as Record<string, unknown>
    const known = new Set<string>(COLOR_TOKENS)
    for (const token of COLOR_TOKENS) {
      const value = given[token]
      if (value === undefined) errors.push(`"colors" has no "${token}"`)
      else if (typeof value !== 'string' || !isColor(value)) errors.push(`"colors.${token}" is not a CSS colour`)
      else colors[token] = value.trim()
    }
    for (const token of Object.keys(given)) {
      if (!known.has(token)) errors.push(`"colors" has "${token}", which is not a colour token`)
    }
  }

  if (errors.length) return { ok: false, errors }
  return {
    ok: true,
    theme: {
      id: USER_THEME_PREFIX + slug(label),
      label,
      scheme: file.scheme as ColorTheme['scheme'],
      colors: colors as Record<ColorToken, string>,
    },
  }
}

/** A theme written as a theme file. */
export function themeFile(theme: ColorTheme): string {
  const colors = Object.fromEntries(COLOR_TOKENS.map((token) => [token, theme.colors[token]]))
  const file = { format: THEME_FILE_FORMAT, version: THEME_FILE_VERSION, label: theme.label, scheme: theme.scheme, colors }
  return JSON.stringify(file, null, 2) + '\n'
}
