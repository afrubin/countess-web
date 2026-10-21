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
  min-width: 8.5rem;
  max-width: 13rem;
  padding: 0.4em 0.7em;
  border-radius: 6px;
  border: 2px solid var(--color-border);
  border-left-width: 6px;
  background: var(--color-surface);
  font-size: var(--text-md);
}
.pipeline-node.selected {
  box-shadow: 0 0 0 3px var(--color-focus);
}
.name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plugin {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
.dirty,
.working {
  border-left-color: var(--color-working);
}
.result {
  border-left-color: var(--color-ok);
}
.error {
  border-left-color: var(--color-bad);
}
.no-preview {
  border-left-color: var(--color-text-muted);
}
</style>
