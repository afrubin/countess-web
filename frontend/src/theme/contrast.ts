// WCAG 2.2 contrast between theme colours: which pairs must be readable, and how readable they are.

import type { ColorTheme, ColorToken } from './tokens'

/** Text on a background needs 4.5:1 (WCAG AA for normal text). */
export const TEXT_PAIRS: readonly [ColorToken, ColorToken][] = [
  ['text', 'background'],
  ['text', 'surface'],
  ['text', 'surface-alt'],
  ['text', 'focus'],
  ['text-muted', 'surface'],
  ['text-muted', 'surface-alt'],
  ['on-accent', 'accent'],
  ['accent', 'surface'],
  ['bad', 'surface'],
  ['bad', 'bad-surface'],
]

/** A graphical mark against what it sits on needs 3:1 (WCAG non-text contrast). */
export const MARK_PAIRS: readonly [ColorToken, ColorToken][] = [
  ['ok', 'surface'],
  ['working', 'surface'],
  ['bad', 'surface'],
  ['edge', 'canvas'],
  ['edge-active', 'canvas'],
  ['handle', 'surface'],
]

/** The relative luminance of a #rrggbb colour, or null for any other way of writing a colour. */
export function luminance(color: string): number | null {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color)
  if (!match) return null
  const [r, g, b] = match.slice(1).map((part) => {
    const channel = parseInt(part, 16) / 255
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** The contrast ratio of two #rrggbb colours, or null if either is written another way. */
export function contrast(a: string, b: string): number | null {
  const [la, lb] = [luminance(a), luminance(b)]
  if (la === null || lb === null) return null
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/** Each pair of a theme's colours below the contrast WCAG asks for, said in words. Pairs whose
 * colours are not written as #rrggbb are not checked. */
export function contrastWarnings(theme: ColorTheme): string[] {
  const check = (pairs: readonly [ColorToken, ColorToken][], needed: number) =>
    pairs.flatMap(([fore, back]) => {
      const ratio = contrast(theme.colors[fore], theme.colors[back])
      return ratio !== null && ratio < needed
        ? [`${fore} on ${back} is ${ratio.toFixed(2)}:1; WCAG asks for ${needed}:1`]
        : []
    })
  return [...check(TEXT_PAIRS, 4.5), ...check(MARK_PAIRS, 3)]
}
