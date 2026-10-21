import { describe, expect, it } from 'vitest'
import { contrast, contrastWarnings, MARK_PAIRS, TEXT_PAIRS } from './contrast'
import { COLOR_THEMES, DARK, LIGHT, TEXT_SIZES } from './presets'
import { applyTheme } from './theme'
import { parseThemeFile, themeFile, USER_THEME_PREFIX } from './themeFile'
import { COLOR_TOKENS, type ColorTheme } from './tokens'

describe.each(COLOR_THEMES.map((theme): [string, ColorTheme] => [theme.label, theme]))('the %s theme', (_, theme) => {
  it.each(TEXT_PAIRS)('has text in %s readable on %s', (fore, back) => {
    expect(contrast(theme.colors[fore], theme.colors[back])).toBeGreaterThanOrEqual(4.5)
  })

  it.each(MARK_PAIRS)('has %s visible on %s', (fore, back) => {
    expect(contrast(theme.colors[fore], theme.colors[back])).toBeGreaterThanOrEqual(3)
  })
})

describe('applyTheme', () => {
  it('sets every colour token and the type scale', () => {
    const root = document.createElement('div')
    const size = TEXT_SIZES[2]
    if (!size) throw new Error('expected a presentation size')

    applyTheme(DARK, size, root)

    for (const token of COLOR_TOKENS) expect(root.style.getPropertyValue(`--color-${token}`)).toBe(DARK.colors[token])
    expect(root.style.getPropertyValue('--text-base')).toBe(`${size.basePx.toFixed(2)}px`)
    expect(root.style.fontSize).toBe(`${size.basePx}px`)
    expect(root.dataset.theme).toBe('dark')
  })
})

// ---- theme files --------------------------------------------------------------------------------

// jsdom has no CSS colour parser; this stands in for the browser's.
const isColor = (value: string): boolean => /^(#[0-9a-f]{6}|rgb\(.+\)|[a-z]+)$/i.test(value)

function file(overrides: Record<string, unknown> = {}, colors: Record<string, unknown> = LIGHT.colors): string {
  return JSON.stringify({ format: 'countess-web-theme', version: 1, label: 'Lab slides', scheme: 'light', colors, ...overrides })
}

describe('parseThemeFile', () => {
  it('reads a theme file as a user theme', () => {
    const result = parseThemeFile(file(), isColor)

    expect(result.ok && result.theme).toEqual({ id: `${USER_THEME_PREFIX}lab-slides`, label: 'Lab slides', scheme: 'light', colors: LIGHT.colors })
  })

  it('reads back the file a theme is saved as', () => {
    const result = parseThemeFile(themeFile(DARK), isColor)

    expect(result.ok && result.theme.colors).toEqual(DARK.colors)
  })

  it('names each colour token the file leaves out', () => {
    const rest = Object.fromEntries(Object.entries(LIGHT.colors).filter(([token]) => token !== 'text' && token !== 'edge'))

    const result = parseThemeFile(file({}, rest), isColor)

    expect(!result.ok && result.errors).toEqual(['"colors" has no "text"', '"colors" has no "edge"'])
  })

  it('refuses a colour token it does not know', () => {
    const result = parseThemeFile(file({}, { ...LIGHT.colors, sparkle: '#ffffff' }), isColor)

    expect(!result.ok && result.errors).toEqual(['"colors" has "sparkle", which is not a colour token'])
  })

  it('refuses a value that is not a colour', () => {
    const result = parseThemeFile(file({}, { ...LIGHT.colors, accent: 'not a colour!' }), isColor)

    expect(!result.ok && result.errors).toEqual(['"colors.accent" is not a CSS colour'])
  })

  it.each([
    [{ format: 'something-else' }, '"format" must be "countess-web-theme"'],
    [{ version: 2 }, '"version" must be 1'],
    [{ label: '  ' }, '"label" must be the theme\'s name'],
    [{ scheme: 'sepia' }, '"scheme" must be "light" or "dark"'],
  ])('refuses %j', (overrides, error) => {
    const result = parseThemeFile(file(overrides), isColor)

    expect(!result.ok && result.errors).toEqual([error])
  })

  it('refuses a file that is not JSON', () => {
    const result = parseThemeFile('{ not json', isColor)

    expect(!result.ok && result.errors[0]).toMatch(/^not JSON/)
  })
})

describe('contrastWarnings', () => {
  it('says which colours are too close', () => {
    const theme = { ...LIGHT, colors: { ...LIGHT.colors, 'text-muted': '#bbbbbb' } }

    expect(contrastWarnings(theme)).toEqual([
      'text-muted on surface is 1.92:1; WCAG asks for 4.5:1',
      'text-muted on surface-alt is 1.76:1; WCAG asks for 4.5:1',
    ])
  })

  it('has nothing to say about the built-in themes', () => {
    expect(COLOR_THEMES.flatMap(contrastWarnings)).toEqual([])
  })
})
