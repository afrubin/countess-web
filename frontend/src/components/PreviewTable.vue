<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, ApiError, followDownload } from '../api'
import { attempt, refreshGraph, store } from '../store'
import type { GraphNode, Preview, SavedPreview } from '../types'

// A node's preview is sorted as CountESS's GUI sorts it: by the node's own column number and
// direction (saved with the pipeline), then by its other columns.
const props = defineProps<{ node: GraphNode }>()
const PAGE = 100

const preview = ref<Preview | null>(null)
const offset = ref(0)
const failed = ref<string | null>(null)
const saving = ref(false)
// The last preview saved, and its one-time download link until that is used.
const saved = ref<{ path: string; url: string | null } | null>(null)

async function load(): Promise<void> {
  if (props.node.status !== 'RESULT') return
  try {
    failed.value = null
    preview.value = await api.preview(props.node.id, offset.value, PAGE)
  } catch (exc) {
    failed.value = exc instanceof Error ? exc.message : String(exc)
  }
}

// The graph's version moves with every change, which catches a recalculation that finished
// between two status updates and so never showed as anything but RESULT.
watch(
  () => [props.node.id, props.node.status, store.graph.version] as const,
  ([, status], previous) => {
    if (previous && previous[0] !== props.node.id) {
      offset.value = 0
      preview.value = null
      saved.value = null
    }
    if (status === 'RESULT') void load()
  },
  { immediate: true },
)

/** Sorts by column number ``index``: a second click on the same column reverses it. */
async function sortBy(index: number): Promise<void> {
  const sortDescending = index === props.node.sortColumn ? !props.node.sortDescending : false
  offset.value = 0
  if ((await attempt(() => api.updateNode(props.node.id, { sortColumn: index, sortDescending }))) !== undefined) {
    await refreshGraph()
    await load()
  }
}

function page(step: number): void {
  offset.value = Math.max(0, offset.value + step * PAGE)
  void load()
}

/** Save Preview CSV, as CountESS's GUI does: to <output directory>/<node-name>_preview.csv on the
 * server, asking before replacing a file already there. */
async function savePreview(): Promise<void> {
  saving.value = true
  saved.value = null
  try {
    failed.value = null
    let result: SavedPreview
    try {
      result = await api.savePreview(props.node.id, false)
    } catch (exc) {
      if (!(exc instanceof ApiError && exc.status === 409)) throw exc
      if (!confirm(`${exc.message}. Replace it?`)) return
      result = await api.savePreview(props.node.id, true)
    }
    saved.value = { path: result.path, url: result.url }
  } catch (exc) {
    failed.value = exc instanceof Error ? exc.message : String(exc)
  } finally {
    saving.value = false
  }
}

function downloadSaved(): void {
  if (!saved.value?.url) return
  followDownload(saved.value.url)
  saved.value.url = null
}

/** A cell as the preview model sends it: null, true or false, a number, text, or a list or object. */
function show(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}
</script>

<template>
  <section class="preview">
    <div v-if="node.status === 'ERROR' && node.message" class="message error">
      <pre>{{ node.message }}</pre>
    </div>
    <div v-else-if="node.status === 'ERROR'" class="message">This node produced no table to preview.</div>
    <div v-else-if="node.status !== 'RESULT'" class="message">Calculating…</div>
    <div v-else-if="failed" class="message error">{{ failed }}</div>
    <template v-else-if="preview">
      <div class="bar">
        <span>{{ preview.total.toLocaleString() }} rows</span>
        <button
          class="download"
          :disabled="saving"
          title="Save these rows on the server as <node-name>_preview.csv in the output directory, in the order shown. A preview holds at most the preview's row limit; Run writes every row."
          @click="savePreview"
        >
          {{ saving ? 'Saving…' : 'Save Preview CSV' }}
        </button>
        <span class="pager">
          <button :disabled="offset === 0" @click="page(-1)">‹</button>
          {{ preview.total ? offset + 1 : 0 }}–{{ Math.min(offset + PAGE, preview.total) }}
          <button :disabled="offset + PAGE >= preview.total" @click="page(1)">›</button>
        </span>
      </div>
      <div v-if="saved" class="saved" role="status">
        <span class="saved-path" :title="saved.path">Saved {{ saved.path }}</span>
        <button v-if="saved.url" @click="downloadSaved">Download</button>
        <button class="dismiss" aria-label="Dismiss" @click="saved = null">×</button>
      </div>
      <div class="scroller">
        <table>
          <thead>
            <tr>
              <th v-for="(column, index) in preview.columns" :key="column.name" @click="sortBy(index)">
                {{ column.name }}
                <span v-if="index === node.sortColumn">{{ node.sortDescending ? '▼' : '▲' }}</span>
                <div class="type">{{ column.type }}</div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, r) in preview.rows" :key="r">
              <td v-for="(value, c) in row" :key="c" :class="{ number: typeof value === 'number', null: value === null }">
                {{ show(value) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.preview {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
.message {
  padding: 12px;
  color: var(--color-text-muted);
}
.message.error pre {
  color: var(--color-bad);
  white-space: pre-wrap;
  font-size: var(--text-sm);
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}
.download {
  margin-left: 12px;
  margin-right: auto;
  font-size: var(--text-sm);
  padding: 1px 8px;
}
.saved {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 8px 4px;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}
.saved-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
}
.saved button {
  font-size: var(--text-sm);
  padding: 1px 8px;
}
.dismiss {
  margin-left: auto;
}
.scroller {
  overflow: auto;
  flex: 1;
}
table {
  border-collapse: collapse;
  font-size: var(--text-sm);
  font-family: var(--font-mono);
}
th {
  position: sticky;
  top: 0;
  background: var(--color-surface-alt);
  cursor: pointer;
  text-align: left;
  padding: 4px 8px;
  white-space: nowrap;
}
.type {
  font-weight: normal;
  color: var(--color-text-muted);
  font-size: var(--text-2xs);
}
td {
  padding: 2px 8px;
  border-top: 1px solid var(--color-border);
  white-space: nowrap;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
}
td.number {
  text-align: right;
}
td.null {
  color: var(--color-text-muted);
}
</style>
