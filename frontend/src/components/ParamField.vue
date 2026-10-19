<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import type { Param, ScalarParam } from '../types'
import { paramActionsKey } from './paramActions'

const props = withDefaults(defineProps<{ param: Param; bare?: boolean }>(), { bare: false })
const actions = inject(paramActionsKey)!

// Typed text is kept locally while the field has focus, so an update from the server (a preview
// finishing, say) does not overwrite what is being typed.
const local = ref<string>('')
const focused = ref(false)

function display(param: Param): string {
  if (param.kind === 'array' || param.kind === 'group' || param.kind === 'multichoice' || param.kind === 'boolean') {
    return ''
  }
  return param.value === null || param.value === undefined ? '' : String(param.value)
}

watch(
  () => props.param,
  (param) => {
    if (!focused.value) local.value = display(param)
  },
  { immediate: true },
)

const fileName = computed(() => (props.param.kind === 'file' ? props.param.value : ''))

async function commit(value: unknown) {
  await actions.change({ path: props.param.path, value })
}

async function commitText() {
  focused.value = false
  const param = props.param as ScalarParam
  if (local.value === display(param)) return
  if (param.kind === 'integer' || param.kind === 'number') {
    await commit(local.value === '' ? null : Number(local.value))
  } else {
    await commit(local.value)
  }
}

async function toggleChoice(choice: string, on: boolean) {
  if (props.param.kind !== 'multichoice') return
  const values = new Set(props.param.value)
  if (on) values.add(choice)
  else values.delete(choice)
  await commit(props.param.choices.filter((c) => values.has(c)))
}

const baseName = (path: string) => path.slice(path.lastIndexOf('/') + 1)
const dirName = (path: string) => path.slice(0, Math.max(path.lastIndexOf('/'), 0))

async function browse() {
  if (props.param.kind !== 'file') return
  const paths = await actions.chooseFiles(props.param.label, props.param.mode, props.param.fileTypes, props.param.absolute)
  if (!paths || !paths.length) return
  const chosen = paths[0]
  // Saving to another folder under the name the template gave keeps the template: the file is
  // then named afresh by each run, not fixed to today's name.
  const template = baseName(props.param.value)
  if (props.param.mode === 'save' && template.includes('{') && baseName(chosen) === baseName(props.param.absolute)) {
    await commit(`${dirName(chosen)}/${template}`)
  } else {
    await commit(chosen)
  }
}

async function addRow() {
  if (props.param.kind !== 'array') return
  if (props.param.addFiles) {
    const paths = await actions.chooseFiles(`Add ${props.param.itemLabel}`, 'multiple', props.param.fileTypes)
    if (paths && paths.length) await actions.change({ path: props.param.path, action: 'addFiles', paths })
  } else {
    await actions.change({ path: props.param.path, action: 'add' })
  }
}

async function deleteRow(index: number) {
  await actions.change({ path: props.param.path, action: 'delete', index })
}

const rowCells = (row: Param): Param[] => (row.kind === 'group' ? row.children : [row])
</script>

<template>
  <div v-if="!param.hide" class="param" :class="[`kind-${param.kind}`, { bare }]">
    <!-- groups and lists of parameters -->
    <fieldset v-if="param.kind === 'group'" :class="{ framed: param.framed }">
      <legend v-if="param.framed && !bare">{{ param.label }}</legend>
      <ParamField v-for="child in param.children" :key="child.path" :param="child" />
    </fieldset>

    <fieldset v-else-if="param.kind === 'array'" class="array">
      <legend v-if="!bare">{{ param.label }}</legend>
      <table v-if="param.layout === 'table'" class="array-table">
        <thead>
          <tr>
            <th v-if="param.rowLabels"></th>
            <th v-for="column in param.columns" :key="column">{{ column }}</th>
            <th v-if="param.canDelete"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in param.rows" :key="row.path">
            <th v-if="param.rowLabels" class="row-label">{{ row.label }}</th>
            <td v-for="cellParam in rowCells(row)" :key="cellParam.path">
              <ParamField :param="cellParam" bare />
            </td>
            <td v-if="param.canDelete">
              <button class="icon" title="Remove" @click="deleteRow(index)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <template v-else>
        <div v-for="(row, index) in param.rows" :key="row.path" class="array-row" :class="param.layout">
          <ParamField :param="row" :bare="param.layout === 'list'" />
          <button v-if="param.canDelete" class="icon" title="Remove" @click="deleteRow(index)">✕</button>
        </div>
      </template>
      <button v-if="param.canAdd" class="add" @click="addRow">
        {{ param.addFiles ? 'Add files…' : `Add ${param.itemLabel}` }}
      </button>
    </fieldset>

    <!-- single values -->
    <label v-else class="scalar">
      <span v-if="!bare" class="label">{{ param.label }}</span>

      <input
        v-if="param.kind === 'boolean'"
        type="checkbox"
        :checked="param.value"
        :disabled="param.readOnly"
        @change="commit(($event.target as HTMLInputElement).checked)"
      />

      <select
        v-else-if="param.kind === 'choice'"
        :value="param.value ?? ''"
        :disabled="param.readOnly"
        @change="commit(($event.target as HTMLSelectElement).value)"
      >
        <option v-if="param.value !== null && !param.choices.includes(String(param.value))" :value="param.value">
          {{ param.value }} (not available)
        </option>
        <option v-for="choice in param.choices" :key="choice" :value="choice">{{ choice }}</option>
      </select>

      <template v-else-if="param.kind === 'combo'">
        <input
          v-model="local"
          :list="`choices-${param.path}`"
          :disabled="param.readOnly"
          placeholder="a value, or a column"
          @focus="focused = true"
          @change="commitText"
          @blur="commitText"
        />
        <datalist :id="`choices-${param.path}`">
          <option v-for="choice in param.choices" :key="choice" :value="choice" />
        </datalist>
      </template>

      <span v-else-if="param.kind === 'multichoice'" class="multichoice">
        <label v-for="choice in param.choices" :key="choice">
          <input
            type="checkbox"
            :checked="param.value.includes(choice)"
            :disabled="param.readOnly"
            @change="toggleChoice(choice, ($event.target as HTMLInputElement).checked)"
          />
          {{ choice }}
        </label>
      </span>

      <span v-else-if="param.kind === 'file' && param.mode === 'save'" class="save-path">
        <span class="file">
          <input
            v-model="local"
            :disabled="param.readOnly"
            spellcheck="false"
            @focus="focused = true"
            @change="commitText"
            @blur="commitText"
          />
          <button :disabled="param.readOnly" @click.prevent="browse">Choose…</button>
        </span>
        <span v-if="param.templateError" class="template-error">{{ param.templateError }}</span>
        <span v-else-if="param.absolute" class="template-result" :title="param.absolute">
          → {{ baseName(param.absolute) }} <span class="template-dir">in {{ dirName(param.absolute) }}</span>
        </span>
        <span v-if="param.fields?.length" class="template-fields">
          Fields: <code v-for="field in param.fields" :key="field">{{ '{' + field + '}' }}</code>
        </span>
      </span>

      <span v-else-if="param.kind === 'file'" class="file">
        <span class="file-name" :title="param.absolute">{{ fileName || '(none)' }}</span>
        <button :disabled="param.readOnly" @click.prevent="browse">Choose…</button>
      </span>

      <textarea
        v-else-if="param.kind === 'text'"
        v-model="local"
        rows="6"
        :disabled="param.readOnly"
        @focus="focused = true"
        @blur="commitText"
      />

      <input
        v-else
        v-model="local"
        :type="param.kind === 'integer' || param.kind === 'number' ? 'number' : 'text'"
        :step="param.kind === 'integer' ? 1 : 'any'"
        :disabled="param.readOnly"
        @focus="focused = true"
        @change="commitText"
        @blur="commitText"
      />
    </label>
  </div>
</template>

<style scoped>
.param {
  margin: 4px 0;
}
.scalar {
  display: grid;
  grid-template-columns: minmax(120px, 34%) 1fr;
  gap: 8px;
  align-items: center;
}
.bare .scalar {
  grid-template-columns: 1fr;
}
.label {
  color: var(--muted);
}
fieldset {
  border: none;
  margin: 0;
  padding: 0;
}
fieldset.framed,
fieldset.array {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  margin: 6px 0;
}
legend {
  font-weight: 600;
  padding: 0 4px;
}
.array-table {
  width: 100%;
  border-collapse: collapse;
}
.array-table th {
  text-align: left;
  font-weight: 500;
  color: var(--muted);
  font-size: 12px;
}
.array-table td,
.array-table th {
  padding: 2px 4px;
  vertical-align: middle;
}
.row-label {
  white-space: nowrap;
}
.array-row {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.array-row > :first-child {
  flex: 1;
}
.multichoice {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}
.file {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.save-path {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.save-path input {
  flex: 1;
  font-family: var(--mono);
}
.template-result,
.template-fields {
  color: var(--muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.template-dir {
  opacity: 0.75;
}
.template-fields code {
  margin-left: 4px;
}
.template-error {
  color: var(--bad);
  font-size: 12px;
}
.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
}
.add {
  margin-top: 4px;
}
input[type='text'],
input[type='number'],
select,
textarea {
  width: 100%;
  box-sizing: border-box;
}
textarea {
  font-family: var(--mono);
}
</style>
