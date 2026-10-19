<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { api } from './api'
import { attempt, connectEvents, refreshGraph, selectedNode, store } from './store'
import AppToolbar from './components/AppToolbar.vue'
import FileBrowser from './components/FileBrowser.vue'
import GraphView from './components/GraphView.vue'
import LogPanel from './components/LogPanel.vue'
import NodePanel from './components/NodePanel.vue'
import RunOutputs from './components/RunOutputs.vue'
import WorkflowDialog from './components/WorkflowDialog.vue'

const node = computed(selectedNode)

onMounted(async () => {
  const plugins = await attempt(api.plugins)
  if (plugins) store.plugins = plugins
  store.run = (await attempt(api.run)) ?? null
  await refreshGraph()
  connectEvents()
})
</script>

<template>
  <div class="app">
    <AppToolbar />
    <div v-if="store.error" class="error-banner" role="alert">
      {{ store.error }}
      <button class="icon" title="Dismiss" @click="store.error = null">✕</button>
    </div>
    <div v-if="!store.authorised" class="unauthorised">
      <h2>Not connected</h2>
      <p>Open CountESS with the address it printed when it started; it ends <code>?token=…</code>.</p>
      <p>If the server was restarted, it printed a new address.</p>
    </div>
    <main v-else>
      <section class="graph"><GraphView /></section>
      <section class="detail">
        <NodePanel v-if="node" :key="node.id" :node="node" />
        <div v-else class="placeholder">
          <p>Select a node to configure it and preview its output.</p>
          <p>Drag from a node's right edge to another node's left edge to connect them.</p>
        </div>
      </section>
    </main>
    <LogPanel />
    <RunOutputs v-if="store.showOutputs" />
    <WorkflowDialog v-if="store.showWorkflow" />
    <FileBrowser v-if="store.fileDialog" :options="store.fileDialog.options" @done="store.fileDialog.resolve" />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
main {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(320px, 2fr) minmax(380px, 3fr);
  min-height: 0;
}
.graph {
  border-right: 1px solid var(--border);
  min-height: 0;
}
.detail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}
.unauthorised {
  padding: 40px;
  max-width: 640px;
}
.placeholder {
  padding: 24px;
  color: var(--muted);
}
.error-banner {
  background: var(--bad-bg);
  color: var(--bad);
  padding: 6px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
@media (max-width: 900px) {
  main {
    grid-template-columns: 1fr;
    grid-template-rows: 40% 60%;
  }
  .graph {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
}
</style>
