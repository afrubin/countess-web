import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ParamField from './ParamField.vue'
import { paramActionsKey, type ParamActions } from './paramActions'
import type { Param, ParamOf } from '../types'

function mountField(param: Param, chosen: string[] | null = null) {
  const actions = {
    change: vi.fn<ParamActions['change']>().mockResolvedValue(undefined),
    chooseFiles: vi.fn<ParamActions['chooseFiles']>().mockResolvedValue(chosen),
  }
  const wrapper = mount(ParamField, { props: { param }, global: { provide: { [paramActionsKey]: actions } } })
  return { wrapper, actions }
}

const base = { hide: false, readOnly: false }
const settle = () => new Promise((resolve) => setTimeout(resolve))

function saveFile(overrides: Partial<ParamOf<'save-file'>> = {}): ParamOf<'save-file'> {
  return {
    ...base,
    kind: 'save-file',
    path: 'filename',
    label: 'Filename',
    value: '{date}_{node}.csv',
    filled: '/data/run1/2026-10-21_save.csv',
    templateError: null,
    fields: [
      { name: 'date', description: 'the date of the run' },
      { name: 'node', description: 'the node' },
    ],
    fileTypes: [],
    ...overrides,
  }
}

describe('ParamField', () => {
  it('shows a boolean never set as unchecked', () => {
    const { wrapper } = mountField({ ...base, kind: 'boolean', path: 'index', label: 'Index', value: null })

    expect(wrapper.find<HTMLInputElement>('input[type=checkbox]').element.checked).toBe(false)
  })

  it('sends a ticked checkbox as true', async () => {
    const { wrapper, actions } = mountField({ ...base, kind: 'boolean', path: 'header', label: 'Header', value: false })

    await wrapper.find('input[type=checkbox]').setValue(true)

    expect(actions.change).toHaveBeenCalledWith({ path: 'header', value: true })
  })

  it('sends a typed integer as a number', async () => {
    const { wrapper, actions } = mountField({ ...base, kind: 'integer', path: 'max', label: 'Max', value: 1 })

    const input = wrapper.find('input')
    await input.setValue('17')
    await input.trigger('change')

    expect(actions.change).toHaveBeenCalledWith({ path: 'max', value: 17 })
  })

  it('sends an emptied number as null', async () => {
    const { wrapper, actions } = mountField({ ...base, kind: 'float', path: 'weight', label: 'Weight', value: 0.5 })

    const input = wrapper.find('input')
    await input.setValue('')
    await input.trigger('change')

    expect(actions.change).toHaveBeenCalledWith({ path: 'weight', value: null })
  })

  it('sends a decimal as its exact text', async () => {
    const { wrapper, actions } = mountField({ ...base, kind: 'decimal', path: 'threshold', label: 'T', value: '0.1' })

    const input = wrapper.find('input')
    await input.setValue('0.10')
    await input.trigger('change')

    expect(actions.change).toHaveBeenCalledWith({ path: 'threshold', value: '0.10' })
  })

  it('sends the key of the option chosen, not its label', async () => {
    const { wrapper, actions } = mountField({
      ...base,
      kind: 'choice',
      path: 'operation',
      label: 'Operation',
      selected: 'normalize',
      options: [
        { value: 'normalize', label: 'Normalise' },
        { value: 'g_to_c', label: 'g. → c.' },
      ],
    })

    await wrapper.find('select').setValue('g_to_c')

    expect(actions.change).toHaveBeenCalledWith({ path: 'operation', value: 'g_to_c' })
  })

  it('chooses a column of a column-or-value parameter by name', async () => {
    const { wrapper, actions } = mountField({
      ...base,
      kind: 'column-or-value',
      path: 'target',
      label: 'Target',
      valueType: 'string',
      value: 'NM_000099.1',
      column: null,
      columns: ['transcript'],
    })

    await wrapper.find('select').setValue('transcript')

    expect(actions.change).toHaveBeenCalledWith({ path: 'target', column: 'transcript' })
  })

  it('sends a chosen file as its path', async () => {
    const { wrapper, actions } = mountField(
      { ...base, kind: 'file', path: 'reference.fasta', label: 'FASTA', value: null, absolute: null, fileTypes: [] },
      ['/data/ref.fa'],
    )

    await wrapper.find('button').trigger('click')
    await settle()

    expect(actions.change).toHaveBeenCalledWith({ path: 'reference.fasta', value: '/data/ref.fa' })
  })

  it('draws a table of rows and deletes the row asked for', async () => {
    const cell = (row: number): Param => ({
      ...base,
      kind: 'string',
      path: `steps.${row}.output`,
      label: 'Output',
      value: `o${row}`,
    })
    const row = (n: number): Param => ({
      ...base,
      kind: 'group',
      layout: 'table',
      path: `steps.${n}`,
      label: `Step ${n + 1}`,
      children: [cell(n)],
    })
    const { wrapper, actions } = mountField({
      ...base,
      kind: 'array',
      path: 'steps',
      label: 'Steps',
      items: [row(0), row(1)],
      template: row(2),
      minSize: 0,
      maxSize: null,
      perColumn: false,
      files: false,
      fileTypes: [],
      canAdd: true,
      canDelete: true,
    })

    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    await wrapper.findAll('button[title=Remove]')[1]?.trigger('click')

    expect(actions.change).toHaveBeenCalledWith({ path: 'steps', action: 'delete', index: 1 })
  })

  it('does not draw a hidden parameter', () => {
    const { wrapper } = mountField({ ...base, hide: true, kind: 'string', path: 'x', label: 'X', value: 'y' })

    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('keeps a save path template when only its folder is chosen', async () => {
    const { wrapper, actions } = mountField(saveFile(), ['/data/run2/2026-10-21_save.csv'])

    await wrapper.find('button').trigger('click')
    await settle()

    expect(actions.change).toHaveBeenCalledWith({ path: 'filename', value: '/data/run2/{date}_{node}.csv' })
  })

  it('takes a save path typed as a new name', async () => {
    const { wrapper, actions } = mountField(saveFile(), ['/data/run2/final.csv'])

    await wrapper.find('button').trigger('click')
    await settle()

    expect(actions.change).toHaveBeenCalledWith({ path: 'filename', value: '/data/run2/final.csv' })
  })
})
