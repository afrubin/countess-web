<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { VueFlow, useVueFlow, type Connection, type EdgeMouseEvent, type NodeDragEvent, type NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import PipelineNode from './PipelineNode.vue'
import { api } from '../api'
import { attempt, refreshGraph, store } from '../store'
import { activeTextSize, activeTheme, view } from '../theme/theme'

// CountESS keeps node positions as fractions of the canvas; the graph is drawn on this area.
// It grows with the text size, as the nodes do, so that larger nodes keep the same gaps.
const BASE_WIDTH = 950
const BASE_HEIGHT = 480
const NORMAL_TEXT_PX = 14
const scale = computed(() => activeTextSize().basePx / NORMAL_TEXT_PX)
const width = computed(() => BASE_WIDTH * scale.value)
const height = computed(() => BASE_HEIGHT * scale.value)

const { screenToFlowCoordinate, fitView } = useVueFlow()

// A new text size changes every node's size and place: fit the graph to the view again.
watch(
  () => view.textSize,
  async () => {
    await nextTick()
    await fitView()
  },
)
const selectedEdge = ref<{ parent: string; child: string } | null>(null)

const nodes = computed(() =>
  store.graph.nodes.map((n) => ({
    id: n.id,
    type: 'countess',
    position: { x: n.position[0] * width.value, y: n.position[1] * height.value },
    data: n,
    selected: n.id === store.selectedId,
  })),
)

const edges = computed(() =>
  store.graph.nodes.flatMap((child) =>
    child.parents.map((parent) => ({
      id: `${parent}->${child.id}`,
      source: parent,
      target: child.id,
      animated: child.status === 'WORKING',
      selected: selectedEdge.value !== null && selectedEdge.value.parent === parent && selectedEdge.value.child === child.id,
    })),
  ),
)

function toFraction(x: number, y: number): [number, number] {
  return [Math.max(0, Math.min(1, x / width.value)), Math.max(0, Math.min(1, y / height.value))]
}

async function onDragStop(event: NodeDragEvent) {
  for (const node of event.nodes) {
    await attempt(() => api.updateNode(node.id, { position: toFraction(node.position.x, node.position.y) }))
  }
}

async function onConnect(connection: Connection) {
  if (await attempt(() => api.connect(connection.source, connection.target)) !== undefined) await refreshGraph()
}

function onNodeClick(event: NodeMouseEvent) {
  selectedEdge.value = null
  store.selectedId = event.node.id
}

function onEdgeClick(event: EdgeMouseEvent) {
  selectedEdge.value = { parent: event.edge.source, child: event.edge.target }
}

async function disconnect() {
  const edge = selectedEdge.value
  if (!edge) return
  selectedEdge.value = null
  if (await attempt(() => api.disconnect(edge.parent, edge.child)) !== undefined) await refreshGraph()
}

async function onPaneClick(event: MouseEvent) {
  selectedEdge.value = null
  if (event.detail < 2) return
  const point = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  const node = await attempt(() => api.addNode(toFraction(point.x, point.y)))
  if (node) {
    await refreshGraph()
    store.selectedId = node.id
  }
}
</script>

<template>
  <div class="graph-view">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :delete-key-code="null"
      :zoom-on-double-click="false"
      fit-view-on-init
      @node-drag-stop="onDragStop"
      @connect="onConnect"
      @node-click="onNodeClick"
      @edge-click="onEdgeClick"
      @pane-click="onPaneClick"
    >
      <template #node-countess="props">
        <PipelineNode :data="props.data" :selected="props.data.id === store.selectedId" />
      </template>
      <!-- An SVG attribute, which a CSS variable cannot fill: the theme's colour itself. -->
      <Background :color="activeTheme().colors['canvas-pattern']" />
      <Controls :show-interactive="false" />
    </VueFlow>
    <div v-if="selectedEdge" class="edge-actions">
      <button @click="disconnect">Remove connection</button>
    </div>
    <div v-if="!store.graph.nodes.length" class="hint">Double-click to add a node, or open a pipeline.</div>
  </div>
</template>

<style scoped>
.graph-view {
  position: relative;
  height: 100%;
}
.edge-actions {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
}
.hint {
  position: absolute;
  top: 45%;
  width: 100%;
  text-align: center;
  color: var(--color-text-muted);
  pointer-events: none;
}
</style>
