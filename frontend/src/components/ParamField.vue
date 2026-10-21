<script setup lang="ts">
// Draws one plugin parameter, by kind; each kind is a family of CountESS parameter classes (see
// countess_web/models.py for which), and its value is typed as CountESS holds it.
import { computed, ref, watch } from 'vue'
import type { Param, ParamOf } from '../types'
import { useParamActions } from './paramActions'

const props = withDefaults(defineProps<{ param: Param; bare?: boolean }>(), { bare: false })
const actions = useParamActions()

// The text being typed is kept locally while the field has focus, so an update from the server (a
// preview finishing, say) does not overwrite it. v-model on a type="number" input stores a number.
const local = ref<string | number>('')
const focused = ref(false)

/** The text a typed-in value is shown as, for the kinds with one. */
function text(param: Param): string {
  switch (param.kind) {
    case 'string':
    case 'text':
    case 'decimal':
    case 'file':
    case 'save-file':
      return param.value ?? ''
    case 'integer':
    case 'float':
      return param.value === null ? '' : String(param.value)
    case 'column-or-value':
      return param.value === null ? '' : String(param.value)
    default:
      return ''
  }
}

watch(
  () => props.param,
  (param) => {
    if (!focused.value) local.value = text(param)
  },
  { immediate: true },
)

async function commit(value: boolean | number | string | string[] | null): Promise<void> {
  await actions.change({ path: props.param.path, value })
}

/** Sends what was typed, as the value its kind takes. */
async function commitText(): Promise<void> {
  focused.value = false
  const param = props.param
  const typed = String(local.value).trim()
  if (String(local.value) === text(param)) return
  switch (param.kind) {
    case 'integer':
    case 'float':
      await commit(typed === '' ? null : Number(typed))
      return
    case 'column-or-value':
      await commit(param.valueType === 'integer' ? (typed === '' ? null : Number(typed)) : String(local.value))
      return
    default:
      await commit(String(local.value))
  }
}

// ---- choices -------------------------------------------------------------------------------------

const missingSelection = computed(() => {
  const param = props.param
  if (param.kind !== 'choice' || param.selected === null) return null
  const selected = param.selected
  return param.options.some((o) => o.value === selected) ? null : selected
})

async function toggleChoice(param: ParamOf<'multichoice'>, choice: string, on: boolean): Promise<void> {
  const values = new Set(param.values)
  if (on) values.add(choice)
  else values.delete(choice)
  await commit(param.choices.filter((c) => values.has(c)))
}

// The column-or-value select: '' is "a value typed in", anything else a column's name.
const VALUE = ''

async function chooseSource(param: ParamOf<'column-or-value'>, source: string): Promise<void> {
  if (source === VALUE) {
    await commit(param.valueType === 'integer' ? 0 : '')
  } else {
    await actions.change({ path: param.path, column: source })
  }
}

// ---- files ---------------------------------------------------------------------------------------

const baseName = (path: string): string => path.slice(path.lastIndexOf('/') + 1)
const dirName = (path: string): string => path.slice(0, Math.max(path.lastIndexOf('/'), 0))

async function chooseFile(param: ParamOf<'file'>): Promise<void> {
  const [chosen] = (await actions.chooseFiles(param.label, 'open', param.fileTypes, param.absolute)) ?? []
  if (chosen !== undefined) await commit(chosen)
}

async function chooseSaveFile(param: ParamOf<'save-file'>): Promise<void> {
  const [chosen] = (await actions.chooseFiles(param.label, 'save', param.fileTypes, param.filled)) ?? []
  if (chosen === undefined) return
  // Saving to another folder under the name the template gave keeps the template: the file is
  // then named afresh by each run, not fixed to today's name.
  const template = baseName(param.value ?? '')
  if (template.includes('{') && param.filled !== null && baseName(chosen) === baseName(param.filled)) {
    await commit(`${dirName(chosen)}/${template}`)
  } else {
    await commit(chosen)
  }
}

// ---- lists ---------------------------------------------------------------------------------------

/** A list's layout: a table when its rows are TabularMultiParams, frames for other groups. */
function arrayLayout(param: ParamOf<'array'>): 'table' | 'frames' | 'list' {
  if (param.template.kind !== 'group') return 'list'
  return param.template.layout === 'table' ? 'table' : 'frames'
}

function columnLabels(param: ParamOf<'array'>): string[] {
  return param.template.kind === 'group' ? param.template.children.map((c) => c.label) : []
}

const cells = (row: Param): Param[] => (row.kind === 'group' ? row.children : [row])

async function addRow(param: ParamOf<'array'>): Promise<void> {
  if (param.files) {
    const paths = await actions.chooseFiles(`Add ${param.template.label}`, 'multiple', param.fileTypes, null)
    if (paths?.length) await actions.change({ path: param.path, action: 'addFiles', paths })
  } else {
    await actions.change({ path: param.path, action: 'add' })
  }
}

async function deleteRow(param: ParamOf<'array'>, index: number): Promise<void> {
  await actions.change({ path: param.path, action: 'delete', index })
}

function checked(event: Event): boolean {
  return event.target instanceof HTMLInputElement && event.target.checked
}

function selectedValue(event: Event): string {
  return event.target instanceof HTMLSelectElement ? event.target.value : ''
}
</script>

<template>
  <div v-if="!param.hide" class="param" :class="[`kind-${param.kind}`, { bare }]">
    <!-- groups and lists of parameters -->
    <fieldset v-if="param.kind === 'group'" :class="{ framed: param.layout === 'frame' }">
      <legend v-if="param.layout === 'frame' && !bare">{{ param.label }}</legend>
      <ParamField v-for="child in param.children" :key="child.path" :param="child" />
    </fieldset>

    <fieldset v-else-if="param.kind === 'array'" class="array">
      <legend v-if="!bare">{{ param.label }}</legend>
      <table v-if="arrayLayout(param) === 'table'" class="array-table">
        <thead>
          <tr>
            <th v-if="param.perColumn"></th>
            <th v-for="column in columnLabels(param)" :key="column">{{ column }}</th>
            <th v-if="param.canDelete"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in param.items" :key="row.path">
            <th v-if="param.perColumn" class="row-label">{{ row.label }}</th>
            <td v-for="cellParam in cells(row)" :key="cellParam.path">
              <ParamField :param="cellParam" bare />
            </td>
            <td v-if="param.canDelete">
              <button class="icon" title="Remove" @click="deleteRow(param, index)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <template v-else>
        <div v-for="(row, index) in param.items" :key="row.path" class="array-row" :class="arrayLayout(param)">
          <ParamField :param="row" :bare="arrayLayout(param) === 'list'" />
          <button v-if="param.canDelete" class="icon" title="Remove" @click="deleteRow(param, index)">✕</button>
        </div>
      </template>
      <button v-if="param.canAdd" class="add" @click="addRow(param)">
        {{ param.files ? 'Add files…' : `Add ${param.template.label}` }}
      </button>
    </fieldset>

    <!-- single values -->
    <label v-else class="scalar">
      <span v-if="!bare" class="label">{{ param.label }}</span>

      <input
        v-if="param.kind === 'boolean'"
        type="checkbox"
        :checked="param.value === true"
        :disabled="param.readOnly"
        @change="commit(checked($event))"
      />

      <select
        v-else-if="param.kind === 'choice'"
        :value="param.selected ?? ''"
        :disabled="param.readOnly"
        @change="commit(selectedValue($event))"
      >
        <option v-if="missingSelection !== null" :value="missingSelection">{{ missingSelection }} (not available)</option>
        <option v-for="option in param.options" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>

      <span v-else-if="param.kind === 'column-or-value'" class="column-or-value">
        <select
          :value="param.column ?? VALUE"
          :disabled="param.readOnly"
          aria-label="Value or column"
          @change="chooseSource(param, selectedValue($event))"
        >
          <option :value="VALUE">{{ param.valueType === 'integer' ? 'A number' : 'A value' }}</option>
          <option v-for="column in param.columns" :key="column" :value="column">Column: {{ column }}</option>
          <option v-if="param.column !== null && !param.columns.includes(param.column)" :value="param.column">
            Column: {{ param.column }} (not available)
          </option>
        </select>
        <input
          v-if="param.column === null"
          v-model="local"
          :type="param.valueType === 'integer' ? 'number' : 'text'"
          :step="param.valueType === 'integer' ? 1 : undefined"
          :disabled="param.readOnly"
          @focus="focused = true"
          @change="commitText"
          @blur="commitText"
        />
      </span>

      <span v-else-if="param.kind === 'multichoice'" class="multichoice">
        <label v-for="choice in param.choices" :key="choice">
          <input
            type="checkbox"
            :checked="param.values.includes(choice)"
            :disabled="param.readOnly"
            @change="toggleChoice(param, choice, checked($event))"
          />
          {{ choice }}
        </label>
      </span>

      <span v-else-if="param.kind === 'file'" class="file">
        <span class="file-name" :title="param.absolute ?? ''">{{ param.value || '(none)' }}</span>
        <button :disabled="param.readOnly" @click.prevent="chooseFile(param)">Choose…</button>
      </span>

      <span v-else-if="param.kind === 'save-file'" class="save-path">
        <span class="file">
          <input
            v-model="local"
            :disabled="param.readOnly"
            spellcheck="false"
            @focus="focused = true"
            @change="commitText"
            @blur="commitText"
          />
          <button :disabled="param.readOnly" @click.prevent="chooseSaveFile(param)">Choose…</button>
        </span>
        <span v-if="param.templateError" class="template-error">{{ param.templateError }}</span>
        <span v-else-if="param.filled" class="template-result" :title="param.filled">
          → {{ baseName(param.filled) }} <span class="template-dir">in {{ dirName(param.filled) }}</span>
        </span>
        <span v-if="param.fields.length" class="template-fields">
          Fields:
          <code v-for="field in param.fields" :key="field.name" :title="field.description">{{ '{' + field.name + '}' }}</code>
        </span>
      </span>

      <textarea
        v-else-if="param.kind === 'text'"
        v-model="local"
        rows="6"
        :disabled="param.readOnly"
        @focus="focused = true"
        @blur="commitText"
      />

      <span v-else-if="param.kind === 'string'" class="string">
        <input
          v-model="local"
          type="text"
          :disabled="param.readOnly"
          @focus="focused = true"
          @change="commitText"
          @blur="commitText"
        />
        <span v-if="param.characterSet" class="allowed" :title="param.characterSet.join(' ')">
          Allowed: {{ param.characterSet.length > 30 ? `${param.characterSet.length} characters` : param.characterSet.join(' ') }}
        </span>
      </span>

      <input
        v-else-if="param.kind === 'decimal'"
        v-model="local"
        type="text"
        inputmode="decimal"
        :disabled="param.readOnly"
        @focus="focused = true"
        @change="commitText"
        @blur="commitText"
      />

      <input
        v-else
        v-model="local"
        type="number"
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
.column-or-value {
  display: flex;
  gap: 6px;
}
.column-or-value select {
  flex: 0 0 auto;
  width: auto;
  max-width: 50%;
}
.string,
.save-path {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.file {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
}
.save-path input {
  flex: 1;
  font-family: var(--mono);
}
.allowed,
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
