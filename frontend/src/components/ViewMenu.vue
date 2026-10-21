<script setup lang="ts">
// The View menu: colour theme and text size, and themes added from files. All are this browser's
// display preferences, not part of the pipeline.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { COLOR_THEMES, TEXT_SIZES } from '../theme/presets'
import { contrastWarnings } from '../theme/contrast'
import { activeTheme, addThemeFile, removeUserTheme, view } from '../theme/theme'
import { themeFile } from '../theme/themeFile'

const open = ref(false)
const menu = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const errors = ref<string[]>([])
const warnings = ref<string[]>([])

function closeOnOutsideClick(event: MouseEvent): void {
  if (open.value && menu.value && event.target instanceof Node && !menu.value.contains(event.target)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', closeOnOutsideClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', closeOnOutsideClick)
})

async function loadThemeFile(event: Event): Promise<void> {
  const input = event.target instanceof HTMLInputElement ? event.target : null
  const file = input?.files?.[0]
  if (!input || !file) return
  input.value = ''
  const result = addThemeFile(await file.text())
  errors.value = result.ok ? [] : [`${file.name} is not a theme file:`, ...result.errors]
  warnings.value = result.ok ? contrastWarnings(result.theme) : []
}

/** Downloads the theme in use as a theme file: the starting point for one of your own. */
function saveThemeFile(): void {
  const theme = activeTheme()
  const url = URL.createObjectURL(new Blob([themeFile(theme)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${theme.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.countess-theme.json`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div ref="menu" class="view-menu" @keydown.esc="open = false">
    <button :aria-expanded="open" aria-haspopup="dialog" @click="open = !open">View</button>
    <div v-if="open" class="panel" role="dialog" aria-label="View">
      <fieldset>
        <legend>Theme</legend>
        <label>
          <input v-model="view.theme" type="radio" name="theme" value="system" />
          System <span class="hint">follows this computer's light or dark setting</span>
        </label>
        <label v-for="theme in COLOR_THEMES" :key="theme.id">
          <input v-model="view.theme" type="radio" name="theme" :value="theme.id" />
          {{ theme.label }}
        </label>
        <div v-for="theme in view.userThemes" :key="theme.id" class="user-theme">
          <label>
            <input v-model="view.theme" type="radio" name="theme" :value="theme.id" />
            {{ theme.label }} <span class="hint">from a file</span>
          </label>
          <button class="icon" :title="`Remove ${theme.label}`" @click="removeUserTheme(theme.id)">✕</button>
        </div>
        <div class="theme-files">
          <button @click="fileInput?.click()">Load a theme file…</button>
          <button @click="saveThemeFile">Save current theme as a file</button>
          <input ref="fileInput" type="file" accept=".json,application/json" hidden @change="loadThemeFile" />
        </div>
        <ul v-if="errors.length" class="errors" role="alert">
          <li v-for="error in errors" :key="error">{{ error }}</li>
        </ul>
        <ul v-if="warnings.length" class="warnings">
          <li>Loaded, but some colours are hard to tell apart:</li>
          <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
        </ul>
      </fieldset>
      <fieldset>
        <legend>Text size</legend>
        <label v-for="size in TEXT_SIZES" :key="size.id">
          <input v-model="view.textSize" type="radio" name="text-size" :value="size.id" />
          {{ size.label }} <span class="hint">{{ size.hint }}</span>
        </label>
      </fieldset>
    </div>
  </div>
</template>

<style scoped>
.view-menu {
  position: relative;
}
.panel {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  z-index: 50;
  min-width: 24em;
  max-width: 34em;
  padding: 0.6em 0.9em;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  box-shadow: 0 6px 18px var(--color-backdrop);
}
fieldset {
  border: none;
  margin: 0 0 0.5em;
  padding: 0;
}
legend {
  font-weight: 600;
  margin-bottom: 0.2em;
}
label {
  display: block;
  padding: 0.15em 0;
  cursor: pointer;
}
.user-theme {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.theme-files {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4em;
  margin-top: 0.4em;
}
.hint {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
.errors,
.warnings {
  margin: 0.4em 0 0;
  padding-left: 1.2em;
  font-size: var(--text-sm);
}
.errors {
  color: var(--color-bad);
}
.warnings {
  color: var(--color-working);
}
.errors li:first-child,
.warnings li:first-child {
  list-style: none;
  margin-left: -1.2em;
}
</style>
