<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue'
import { api } from '../api'
import { attempt, chooseFiles, refreshGraph, store } from '../store'
import type { GraphNode, Param, ParameterChange } from '../types'
import ParamField from './ParamField.vue'
import PreviewTable from './PreviewTable.vue'
import { paramActionsKey } from './paramActions'

const props = defineProps<{ node: GraphNode }>()

const params = ref<Param[]>([])
const name = ref(props.node.name)
const notes = ref(props.node.notes)
const filter = ref('')

async function loadParams() {
  if (!props.node.plugin) {
    params.value = []
    return
  }
  const loaded = await attempt(() => api.parameters(props.node.id))
  if (loaded) params.value = loaded
}

watch(
  () => props.node.id,
  () => {
    name.value = props.node.name
    notes.value = props.node.notes
    filter.value = ''
    void loadParams()
  },
  { immediate: true },
)

// The server can rename a node (choosing its plugin names it, and names are kept unique), and
// another tab can change it; follow that unless the field is being edited.
const editing = ref<'name' | 'notes' | null>(null)
watch(
  () => props.node.name,
  (value) => {
    if (editing.value !== 'name') name.value = value
  },
)
watch(
  () => props.node.notes,
  (value) => {
    if (editing.value !== 'notes') notes.value = value
  },
)

// A finished recalculation can change a node's parameters: the column choices follow its input.
watch(
  () => [props.node.status, store.graph.version] as const,
  ([status]) => {
    if (status === 'RESULT' || status === 'ERROR') void loadParams()
  },
)

provide(paramActionsKey, {
  async change(change: ParameterChange) {
    const updated = await attempt(() => api.changeParameter(props.node.id, change))
    if (updated) params.value = updated
  },
  chooseFiles: (title, mode, fileTypes, initial) => chooseFiles({ title, mode, fileTypes, initial }),
})

async function rename() {
  editing.value = null
  if (name.value.trim() === props.node.name) return
  if ((await attempt(() => api.updateNode(props.node.id, { name: name.value }))) !== undefined) await refreshGraph()
  name.value = props.node.name
}

async function saveNotes() {
  editing.value = null
  if (notes.value === props.node.notes) return
  await attempt(() => api.updateNode(props.node.id, { notes: notes.value }))
  await refreshGraph()
}

async function remove() {
  if (!confirm(`Delete ${props.node.name}?`)) return
  if ((await attempt(() => api.deleteNode(props.node.id))) !== undefined) {
    store.selectedId = null
    await refreshGraph()
  }
}

const hasParents = computed(() => props.node.parents.length > 0)
const hasChildren = computed(() => store.graph.nodes.some((n) => n.parents.includes(props.node.id)))
const choices = computed(() =>
  store.plugins.filter(
    (p) =>
      (!hasParents.value || p.numInputs > 0) &&
      (!hasChildren.value || p.numOutputs > 0) &&
      (p.name + ' ' + p.description).toLowerCase().includes(filter.value.toLowerCase()),
  ),
)

async function choosePlugin(key: string) {
  if ((await attempt(() => api.setPlugin(props.node.id, key))) !== undefined) {
    await refreshGraph()
    await loadParams()
  }
}
</script>

<template>
  <div class="node-panel">
    <header>
      <input v-model="name" class="node-name" @focus="editing = 'name'" @change="rename" @blur="rename" />
      <button class="danger" title="Delete this node" @click="remove">Delete</button>
    </header>

    <template v-if="node.plugin">
      <p class="description">
        <strong>{{ node.plugin.name }} {{ node.plugin.version }}</strong> — {{ node.plugin.description }}
        <span v-if="node.plugin.additional"> {{ node.plugin.additional }}</span>
        <a v-if="node.plugin.link" :href="node.plugin.link" target="_blank" rel="noopener"> documentation</a>
      </p>
      <textarea v-model="notes" class="notes" rows="2" placeholder="Notes" @focus="editing = 'notes'" @blur="saveNotes" />
      <div class="params">
        <ParamField v-for="param in params" :key="param.path" :param="param" />
      </div>
    </template>

    <div v-else class="chooser">
      <input v-model="filter" placeholder="Find a plugin" />
      <ul>
        <li v-for="plugin in choices" :key="plugin.key">
          <button class="plugin" @click="choosePlugin(plugin.key)">
            <strong>{{ plugin.name }}</strong>
            <span>{{ plugin.description }}</span>
          </button>
        </li>
      </ul>
    </div>
  </div>
  <div v-if="node.plugin && node.plugin.showPreview" class="preview-pane">
    <PreviewTable :node="node" />
  </div>
</template>

<style scoped>
.node-panel {
  padding: 10px 14px;
  overflow: auto;
  flex: 1 1 55%;
  min-height: 0;
}
header {
  display: flex;
  gap: 8px;
}
.node-name {
  flex: 1;
  font-size: 18px;
  font-weight: 600;
}
.description {
  color: var(--muted);
  font-size: 13px;
}
.notes {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 8px;
}
.chooser ul {
  list-style: none;
  padding: 0;
}
.chooser input {
  width: 100%;
  box-sizing: border-box;
  margin: 8px 0;
}
.plugin {
  display: block;
  width: 100%;
  text-align: left;
  margin: 2px 0;
  padding: 6px 8px;
}
.plugin span {
  display: block;
  color: var(--muted);
  font-size: 12px;
}
.preview-pane {
  flex: 1 1 45%;
  min-height: 0;
  border-top: 1px solid var(--border);
}
</style>
