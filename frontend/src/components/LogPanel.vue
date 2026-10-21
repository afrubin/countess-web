<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { store } from '../store'

const open = ref(false)
const scroller = ref<HTMLElement | null>(null)

watch(
  () => store.logs.length,
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  },
)

watch(
  () => store.run?.running,
  (running) => {
    if (running) open.value = true
  },
)
</script>

<template>
  <section class="log-panel" :class="{ open }">
    <button class="toggle" @click="open = !open">{{ open ? '▾' : '▸' }} Log ({{ store.logs.length }})</button>
    <div v-if="open" ref="scroller" class="lines">
      <div v-for="record in store.logs" :key="record.seq" :class="record.level.toLowerCase()">
        <span class="time">{{ record.time.slice(11) }}</span>
        <span class="source">{{ record.source }}</span>
        {{ record.message }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.log-panel {
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-alt);
}
.toggle {
  border: none;
  background: none;
  padding: 4px 10px;
}
.lines {
  height: 180px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  padding: 0 10px 6px;
}
.time,
.source {
  color: var(--color-text-muted);
  margin-right: 8px;
}
.warning {
  color: var(--color-working);
}
.error {
  color: var(--color-bad);
}
</style>
