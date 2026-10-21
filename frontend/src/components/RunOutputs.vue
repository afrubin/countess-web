<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, followDownload } from '../api'
import { store } from '../store'
import type { RunOutput } from '../types'

const outputs = ref<RunOutput[] | null>(null)
const failed = ref<string | null>(null)

onMounted(async () => {
  try {
    outputs.value = await api.runOutputs()
  } catch (exc) {
    failed.value = exc instanceof Error ? exc.message : String(exc)
  }
})

async function downloadLog() {
  try {
    failed.value = null
    followDownload((await api.runLogLink()).url)
  } catch (exc) {
    failed.value = exc instanceof Error ? exc.message : String(exc)
  }
}

async function download(output: RunOutput) {
  try {
    failed.value = null
    followDownload((await api.runOutputLink(output.index)).url)
  } catch (exc) {
    failed.value = exc instanceof Error ? exc.message : String(exc)
  }
}

function size(bytes: number | null): string {
  if (bytes === null) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(unit ? 1 : 0)} ${units[unit]}`
}
</script>

<template>
  <div class="backdrop" @click.self="store.showOutputs = false">
    <div class="dialog" role="dialog" aria-label="Run outputs">
      <h2>Files the last run wrote</h2>
      <p class="where">They are on the server; downloading copies one to this computer.</p>
      <p v-if="failed" class="failed">{{ failed }}</p>
      <p v-else-if="outputs && !outputs.length" class="empty">This pipeline has no node that writes a file.</p>
      <table v-if="outputs && outputs.length">
        <tbody>
          <tr v-for="output in outputs" :key="output.index" :class="{ missing: !output.written }">
            <td>
              <div class="name">{{ output.name || output.node }}</div>
              <div v-if="output.error" class="path failed">{{ output.error }}</div>
              <div v-else class="path" :title="output.file">{{ output.node }} · {{ output.file }}</div>
            </td>
            <td class="size">{{ output.written ? size(output.size) : 'not written by this run' }}</td>
            <td>
              <button :disabled="!output.written" @click="download(output)">Download</button>
            </td>
          </tr>
        </tbody>
      </table>
      <footer>
        <button @click="downloadLog">Download run log</button>
        <button @click="store.showOutputs = false">Close</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: var(--color-backdrop);
  display: grid;
  place-items: center;
  z-index: 100;
}
.dialog {
  background: var(--color-surface);
  border-radius: 8px;
  width: min(760px, 92vw);
  max-height: 80vh;
  overflow: auto;
  padding: 14px 16px;
}
h2 {
  margin: 0 0 4px;
  font-size: var(--text-lg);
}
.where,
.empty,
.size,
.path {
  color: var(--color-text-muted);
}
.where {
  margin: 0 0 10px;
  font-size: var(--text-md);
}
table {
  width: 100%;
  border-collapse: collapse;
}
td {
  padding: 6px 4px;
  border-top: 1px solid var(--color-border);
  vertical-align: middle;
}
.name {
  font-family: var(--font-mono);
}
.path {
  font-size: var(--text-sm);
  max-width: 480px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.size {
  white-space: nowrap;
  font-size: var(--text-sm);
  text-align: right;
}
.missing .name {
  color: var(--color-text-muted);
}
.failed {
  color: var(--color-bad);
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}
</style>
