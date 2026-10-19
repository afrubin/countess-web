<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import type { GraphNode } from '../types'

defineProps<{ data: GraphNode; selected: boolean }>()

// CountESS marks a node that made no table as ERROR; with no message that is a node, such as
// CSV Save, that has no preview to show, not a failure.
function noPreview(node: GraphNode): boolean {
  return node.status === 'ERROR' && !node.message
}

function statusClass(node: GraphNode): string {
  return noPreview(node) ? 'no-preview' : node.status.toLowerCase()
}

function statusTitle(node: GraphNode): string {
  return noPreview(node) ? 'No preview: this node writes output when the pipeline runs' : node.status
}
</script>

<template>
  <div class="pipeline-node" :class="[statusClass(data), { selected }]" :title="data.message || statusTitle(data)">
    <Handle
      v-if="!data.plugin || data.plugin.numInputs > 0"
      type="target"
      :position="Position.Left"
    />
    <div class="name">{{ data.name }}</div>
    <div class="plugin">{{ data.plugin ? data.plugin.name : 'choose a plugin' }}</div>
    <Handle
      v-if="!data.plugin || data.plugin.numOutputs > 0"
      type="source"
      :position="Position.Right"
    />
  </div>
</template>

<style scoped>
.pipeline-node {
  min-width: 120px;
  max-width: 180px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 2px solid var(--border);
  border-left-width: 6px;
  background: var(--surface);
  font-size: 13px;
}
.pipeline-node.selected {
  box-shadow: 0 0 0 3px var(--focus);
}
.name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plugin {
  font-size: 11px;
  color: var(--muted);
}
.dirty,
.working {
  border-left-color: var(--working);
}
.result {
  border-left-color: var(--ok);
}
.error {
  border-left-color: var(--bad);
}
.no-preview {
  border-left-color: var(--muted);
}
</style>
