<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import type { GraphNode, Preview } from '../types'

const props = defineProps<{ node: GraphNode }>()
const PAGE = 100

const preview = ref<Preview | null>(null)
const offset = ref(0)
const sort = ref<string | null>(null)
const descending = ref(false)
const failed = ref<string | null>(null)

async function load() {
  if (props.node.status !== 'RESULT') return
  try {
    failed.value = null
    preview.value = await api.preview(props.node.id, offset.value, PAGE, sort.value, descending.value)
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
      sort.value = null
      preview.value = null
    }
    if (status === 'RESULT') void load()
  },
  { immediate: true },
)

function sortBy(column: string) {
  if (sort.value === column) descending.value = !descending.value
  else {
    sort.value = column
    descending.value = false
  }
  offset.value = 0
  void load()
}

function page(step: number) {
  offset.value = Math.max(0, offset.value + step * PAGE)
  void load()
}

function show(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
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
        <span class="pager">
          <button :disabled="offset === 0" @click="page(-1)">‹</button>
          {{ preview.total ? offset + 1 : 0 }}–{{ Math.min(offset + PAGE, preview.total) }}
          <button :disabled="offset + PAGE >= preview.total" @click="page(1)">›</button>
        </span>
      </div>
      <div class="scroller">
        <table>
          <thead>
            <tr>
              <th v-for="column in preview.columns" :key="column.name" @click="sortBy(column.name)">
                {{ column.name }}
                <span v-if="sort === column.name">{{ descending ? '▼' : '▲' }}</span>
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
  color: var(--muted);
}
.message.error pre {
  color: var(--bad);
  white-space: pre-wrap;
  font-size: 12px;
}
.bar {
  display: flex;
  justify-content: space-between;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--muted);
}
.scroller {
  overflow: auto;
  flex: 1;
}
table {
  border-collapse: collapse;
  font-size: 12px;
  font-family: var(--mono);
}
th {
  position: sticky;
  top: 0;
  background: var(--surface-2);
  cursor: pointer;
  text-align: left;
  padding: 4px 8px;
  white-space: nowrap;
}
.type {
  font-weight: normal;
  color: var(--muted);
  font-size: 10px;
}
td {
  padding: 2px 8px;
  border-top: 1px solid var(--border);
  white-space: nowrap;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
}
td.number {
  text-align: right;
}
td.null {
  color: var(--muted);
}
</style>
