<script setup lang="ts">
import { computed } from 'vue'
import { api } from '../api'
import { attempt, chooseFiles, refreshGraph, setGraph, store } from '../store'

const INI = [{ label: 'CountESS pipelines', patterns: ['*.ini'] }, { label: 'All files', patterns: ['*'] }]

function discardOk(): boolean {
  return !store.graph.modified || confirm('Discard the changes to this pipeline?')
}

async function newPipeline() {
  if (!discardOk()) return
  const graph = await attempt(api.newConfig)
  if (graph) setGraph(graph)
}

async function open() {
  if (!discardOk()) return
  const paths = await chooseFiles({ title: 'Open a pipeline', mode: 'open', fileTypes: INI, initial: store.graph.config ?? undefined })
  if (!paths) return
  const graph = await attempt(() => api.loadConfig(paths[0]))
  if (graph) {
    store.selectedId = null
    setGraph(graph)
  }
}

async function save(as: boolean) {
  let path = store.graph.config ?? undefined
  if (as || !path) {
    const paths = await chooseFiles({ title: 'Save the pipeline as', mode: 'save', fileTypes: INI, initial: path })
    if (!paths) return
    path = paths[0]
  }
  if ((await attempt(() => api.saveConfig(path))) !== undefined) await refreshGraph()
}

async function tidy() {
  const graph = await attempt(api.tidy)
  if (graph) setGraph(graph)
}

async function addNode() {
  const node = await attempt(() => api.addNode([0.5, 0.5]))
  if (node) {
    await refreshGraph()
    store.selectedId = node.id
  }
}

async function run() {
  await attempt(api.startRun)
}

async function stop() {
  await attempt(api.stopRun)
}

const title = computed(() => {
  const config = store.graph.config
  const name = config ? config.slice(config.lastIndexOf('/') + 1) : 'Untitled pipeline'
  return `${name}${store.graph.modified ? ' •' : ''}`
})

const workflowLabel = computed(() =>
  [store.graph.workflow.name, store.graph.workflow.version && `v${store.graph.workflow.version}`].filter(Boolean).join(' '),
)

const runLabel = computed(() => {
  const r = store.run
  if (!r) return ''
  if (r.running) return `Running since ${r.started.slice(11)}`
  return r.returncode === 0 ? `Run finished ${r.finished?.slice(11)}` : `Run failed (exit ${r.returncode})`
})
</script>

<template>
  <nav class="toolbar">
    <strong class="brand">CountESS</strong>
    <button @click="newPipeline">New</button>
    <button @click="open">Open…</button>
    <button @click="save(false)">Save</button>
    <button @click="save(true)">Save as…</button>
    <span class="sep" />
    <button :title="workflowLabel ? 'Change the workflow\'s name or version' : 'Name and version this workflow'" @click="store.showWorkflow = true">
      {{ workflowLabel || 'Workflow…' }}
    </button>
    <span class="sep" />
    <button @click="addNode">Add node</button>
    <button @click="tidy">Tidy</button>
    <span class="sep" />
    <button v-if="!store.run?.running" class="primary" :disabled="!store.graph.nodes.length" @click="run">Run</button>
    <button v-else class="danger" @click="stop">Stop run</button>
    <span class="run" :class="{ failed: store.run && !store.run.running && store.run.returncode !== 0 }">{{ runLabel }}</span>
    <button v-if="store.run && !store.run.running" @click="store.showOutputs = true">Outputs…</button>
    <span class="title" :title="store.graph.config ?? ''">{{ title }}</span>
    <span class="connection" :class="{ off: !store.connected }" :title="store.connected ? 'Connected' : 'Reconnecting…'">●</span>
  </nav>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.brand {
  margin-right: 8px;
}
.sep {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}
.run {
  font-size: 12px;
  color: var(--muted);
}
.run.failed {
  color: var(--bad);
}
.title {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 13px;
}
.connection {
  color: var(--ok);
}
.connection.off {
  color: var(--bad);
}
</style>
