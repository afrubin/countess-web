<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
import { setGraph, store } from '../store'

const name = ref(store.graph.workflow.name ?? '')
const version = ref(store.graph.workflow.version ?? '')
const outputDir = ref(store.graph.workflow.outputDir)
const metadataHeader = ref(store.graph.workflow.metadataHeader)
const failed = ref<string | null>(null)
const nameInput = ref<HTMLInputElement | null>(null)

onMounted(() => nameInput.value?.focus())

async function save() {
  try {
    failed.value = null
    setGraph(
      await api.setWorkflow({
        name: name.value,
        version: version.value,
        outputDir: outputDir.value,
        metadataHeader: metadataHeader.value,
      }),
    )
    store.showWorkflow = false
  } catch (exc) {
    failed.value = exc instanceof ApiError || exc instanceof Error ? exc.message : String(exc)
  }
}
</script>

<template>
  <div class="backdrop" @click.self="store.showWorkflow = false">
    <form class="dialog" role="dialog" aria-label="Workflow" @submit.prevent="save" @keydown.esc="store.showWorkflow = false">
      <h2>Workflow</h2>
      <label>Name <input ref="nameInput" v-model="name" placeholder="FWD saturation" /></label>
      <label>Version <input v-model="version" placeholder="1.0.0" /></label>
      <label>Output directory <input v-model="outputDir" spellcheck="false" placeholder="{date}_{time}_{workflow}_{version}" /></label>
      <label class="check"><input v-model="metadataHeader" type="checkbox" /> Start CSV files with a metadata header (<code>#</code> lines)</label>
      <p class="hint">
        A short name, and a <a href="https://semver.org" target="_blank" rel="noopener">semantic version</a> such as
        1.0.0. Each run writes its files into the output directory, which may use the fields
        <code>{date}</code>, <code>{time}</code>, <code>{workflow}</code> and <code>{version}</code>; a relative one is
        beside the pipeline file. A CSV Save writes <code>results.csv</code> there unless told otherwise, and
        <em>Save Preview CSV</em> writes there too. The metadata header says what wrote a file; a CSV Save can
        override this setting.
      </p>
      <p v-if="failed" class="failed" role="alert">{{ failed }}</p>
      <footer>
        <button type="button" @click="store.showWorkflow = false">Cancel</button>
        <button type="submit" class="primary">Save</button>
      </footer>
    </form>
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
  width: min(520px, 92vw);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
h2 {
  margin: 0;
  font-size: var(--text-lg);
}
label {
  display: grid;
  grid-template-columns: 120px 1fr;
  align-items: center;
  gap: 8px;
}
.check {
  display: flex;
  gap: 8px;
}
.hint {
  color: var(--color-text-muted);
  font-size: var(--text-md);
  margin: 0;
}
.failed {
  color: var(--color-bad);
  margin: 0;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
