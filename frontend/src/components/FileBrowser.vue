<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import type { FileDialogOptions, FileListing } from '../types'

const props = defineProps<{ options: FileDialogOptions }>()
const emit = defineEmits<{ done: [paths: string[] | null] }>()

const listing = ref<FileListing | null>(null)
const failed = ref<string | null>(null)
const typeIndex = ref(0)
const chosen = ref<Set<string>>(new Set())
const saveName = ref('')
const typedPath = ref('')

const patterns = computed(() => props.options.fileTypes[typeIndex.value]?.patterns ?? ['*'])

function dirOf(path: string): string {
  const cut = path.lastIndexOf('/')
  return cut > 0 ? path.slice(0, cut) : '/'
}

async function open(path: string | null) {
  try {
    failed.value = null
    listing.value = await api.files(path, patterns.value)
    typedPath.value = listing.value.path
    chosen.value = new Set()
  } catch (exc) {
    failed.value = exc instanceof Error ? exc.message : String(exc)
  }
}

onMounted(() => {
  const initial = props.options.initial
  if (initial && props.options.mode === 'save') saveName.value = initial.slice(initial.lastIndexOf('/') + 1)
  void open(initial ? dirOf(initial) : null)
})

function click(path: string, isDir: boolean) {
  if (isDir) {
    void open(path)
    return
  }
  if (props.options.mode === 'multiple') {
    const next = new Set(chosen.value)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    chosen.value = next
  } else if (props.options.mode === 'save') {
    saveName.value = path.slice(path.lastIndexOf('/') + 1)
  } else {
    chosen.value = new Set([path])
  }
}

function accept() {
  if (props.options.mode === 'save') {
    if (!listing.value || !saveName.value.trim()) return
    emit('done', [`${listing.value.path.replace(/\/$/, '')}/${saveName.value.trim()}`])
  } else if (chosen.value.size) {
    emit('done', [...chosen.value])
  }
}

const canAccept = computed(() => (props.options.mode === 'save' ? !!saveName.value.trim() : chosen.value.size > 0))

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
  <div class="backdrop" @click.self="emit('done', null)">
    <div class="dialog" role="dialog" :aria-label="options.title">
      <h2>{{ options.title }}</h2>
      <form class="location" @submit.prevent="open(typedPath)">
        <button type="button" :disabled="!listing?.parent" title="Up" @click="open(listing?.parent ?? null)">↑</button>
        <input v-model="typedPath" aria-label="Folder" />
        <select v-if="options.fileTypes.length" v-model.number="typeIndex" @change="open(listing?.path ?? null)">
          <option v-for="(type, i) in options.fileTypes" :key="type.label" :value="i">{{ type.label }}</option>
        </select>
      </form>
      <p v-if="failed" class="failed">{{ failed }}</p>
      <ul v-if="listing" class="entries">
        <li
          v-for="entry in listing.entries"
          :key="entry.path"
          :class="{ dir: entry.isDir, chosen: chosen.has(entry.path) }"
          @click="click(entry.path, entry.isDir)"
          @dblclick="!entry.isDir && options.mode !== 'multiple' ? accept() : undefined"
        >
          <span>{{ entry.isDir ? '📁' : '📄' }} {{ entry.name }}</span>
          <span class="size">{{ size(entry.size) }}</span>
        </li>
        <li v-if="!listing.entries.length" class="empty">No matching files</li>
      </ul>
      <label v-if="options.mode === 'save'" class="save-name">
        File name <input v-model="saveName" />
      </label>
      <footer>
        <span v-if="options.mode === 'multiple'">{{ chosen.size }} chosen</span>
        <button @click="emit('done', null)">Cancel</button>
        <button class="primary" :disabled="!canAccept" @click="accept">
          {{ options.mode === 'save' ? 'Save' : 'Choose' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgb(0 0 0 / 0.35);
  display: grid;
  place-items: center;
  z-index: 100;
}
.dialog {
  background: var(--surface);
  border-radius: 8px;
  width: min(720px, 92vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  gap: 8px;
}
h2 {
  margin: 0;
  font-size: 16px;
}
.location {
  display: flex;
  gap: 6px;
}
.location input {
  flex: 1;
  font-family: var(--mono);
}
.entries {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 6px;
  min-height: 200px;
}
.entries li {
  display: flex;
  justify-content: space-between;
  padding: 4px 8px;
  cursor: pointer;
}
.entries li:hover {
  background: var(--surface-2);
}
.entries li.chosen {
  background: var(--focus);
}
.size,
.empty {
  color: var(--muted);
}
.failed {
  color: var(--bad);
}
.save-name {
  display: flex;
  gap: 8px;
  align-items: center;
}
.save-name input {
  flex: 1;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  align-items: center;
}
footer span {
  margin-right: auto;
  color: var(--muted);
}
</style>
