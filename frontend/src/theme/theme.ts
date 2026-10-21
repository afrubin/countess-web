// The viewer's choice of colour theme and text size, and the themes they have added from files:
// applied to the page as CSS custom properties, and remembered in this browser. These are display
// preferences, not part of a pipeline.

import { reactive, watch } from 'vue'
import { COLOR_THEMES, DARK, LIGHT, TEXT_SIZES, TYPOGRAPHY } from './presets'
import { parseThemeFile, themeFile, type ThemeFileResult } from './themeFile'
import { COLOR_TOKENS, TEXT_STEPS, cssColor, cssText, type ColorTheme, type TextSize, type TextStep } from './tokens'

const THEME_KEY = 'countess-web.theme'
const SIZE_KEY = 'countess-web.text-size'
const USER_THEMES_KEY = 'countess-web.user-themes'

// The fallback size: 'normal', the first entry of TEXT_SIZES.
const DEFAULT_SIZE = TEXT_SIZES[0] ?? { id: 'normal', label: 'Normal', basePx: 14, hint: '' }

export const view = reactive({
  /** A colour theme's id, or 'system' to follow the operating system's light or dark setting. */
  theme: readSetting(THEME_KEY) ?? 'system',
  textSize: readSetting(SIZE_KEY) ?? DEFAULT_SIZE.id,
  systemDark: false,
  /** Themes added from files, kept as the files they came from. */
  userThemes: readUserThemes(),
})

/** Every theme on offer: the built-in ones, then those added from files. */
export function allThemes(): ColorTheme[] {
  return [...COLOR_THEMES, ...view.userThemes]
}

/** The colour theme in effect: the chosen one, or the system's. */
export function activeTheme(): ColorTheme {
  if (view.theme === 'system') return view.systemDark ? DARK : LIGHT
  return allThemes().find((t) => t.id === view.theme) ?? LIGHT
}

export function activeTextSize(): TextSize {
  return TEXT_SIZES.find((s) => s.id === view.textSize) ?? DEFAULT_SIZE
}

/** Adds the theme a file describes (replacing one of the same name) and switches to it. */
export function addThemeFile(text: string): ThemeFileResult {
  const result = parseThemeFile(text)
  if (result.ok) {
    view.userThemes = [...view.userThemes.filter((t) => t.id !== result.theme.id), result.theme]
    view.theme = result.theme.id
  }
  return result
}

export function removeUserTheme(id: string): void {
  view.userThemes = view.userThemes.filter((t) => t.id !== id)
  if (view.theme === id) view.theme = 'system'
}

/** Writes the theme and text size to the page's custom properties. */
export function applyTheme(theme: ColorTheme, size: TextSize, root: HTMLElement = document.documentElement): void {
  for (const token of COLOR_TOKENS) root.style.setProperty(cssColor(token), theme.colors[token])
  for (const [step, scale] of Object.entries(TEXT_STEPS) as [TextStep, number][]) {
    root.style.setProperty(cssText(step), `${(size.basePx * scale).toFixed(2)}px`)
  }
  root.style.setProperty('--font-ui', TYPOGRAPHY.ui)
  root.style.setProperty('--font-mono', TYPOGRAPHY.mono)
  root.style.fontSize = `${size.basePx}px`
  root.style.colorScheme = theme.scheme
  root.dataset.theme = theme.id
  root.dataset.textSize = size.id
}

/** Applies the remembered choice now, and again whenever it, or the system's setting, changes. */
export function startTheming(): void {
  const query = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null
  view.systemDark = query?.matches ?? false
  query?.addEventListener('change', (event) => {
    view.systemDark = event.matches
  })
  watch(
    () => [view.theme, view.textSize, view.systemDark, view.userThemes] as const,
    () => {
      applyTheme(activeTheme(), activeTextSize())
      writeSetting(THEME_KEY, view.theme)
      writeSetting(SIZE_KEY, view.textSize)
      writeSetting(USER_THEMES_KEY, JSON.stringify(view.userThemes.map(themeFile)))
    },
    { immediate: true },
  )
}

/** The added themes as remembered: each re-read as the file it was, and dropped if no longer valid. */
function readUserThemes(): ColorTheme[] {
  const stored = readSetting(USER_THEMES_KEY)
  if (stored === null) return []
  try {
    const files: unknown = JSON.parse(stored)
    if (!Array.isArray(files)) return []
    return files.flatMap((file) => {
      if (typeof file !== 'string') return []
      const result = parseThemeFile(file)
      return result.ok ? [result.theme] : []
    })
  } catch {
    return []
  }
}

// Storage can be unavailable (a private window, blocked site data); the page then simply does not
// remember the choice.
function readSetting(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeSetting(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // not remembered; the choice still applies to this page
  }
}
