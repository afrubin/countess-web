import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ParamField from './ParamField.vue'
import { paramActionsKey, type ParamActions } from './paramActions'
import type { Param } from '../types'

function mountField(param: Param, chosen: string[] | null = null) {
  const actions: ParamActions = {
    change: vi.fn().mockResolvedValue(undefined),
    chooseFiles: vi.fn().mockResolvedValue(chosen),
  }
  const wrapper = mount(ParamField, { props: { param }, global: { provide: { [paramActionsKey as symbol]: actions } } })
  return { wrapper, actions }
}

const base = { hide: false, readOnly: false }

describe('ParamField', () => {
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

  it('sends a chosen file as its path', async () => {
    const { wrapper, actions } = mountField(
      { ...base, kind: 'file', path: 'reference.fasta', label: 'FASTA', value: '', absolute: '', mode: 'open', fileTypes: [] },
      ['/data/ref.fa'],
    )

    await wrapper.find('button').trigger('click')
    await new Promise((resolve) => setTimeout(resolve))

    expect(actions.change).toHaveBeenCalledWith({ path: 'reference.fasta', value: '/data/ref.fa' })
  })

  it('draws a table of rows and deletes the row asked for', async () => {
    const cell = (row: number): Param => ({ ...base, kind: 'string', path: `steps.${row}.output`, label: 'Output', value: `o${row}` })
    const row = (n: number): Param => ({ ...base, kind: 'group', framed: false, path: `steps.${n}`, label: `Step ${n + 1}`, children: [cell(n)] })
    const { wrapper, actions } = mountField({
      ...base,
      kind: 'array',
      path: 'steps',
      label: 'Steps',
      layout: 'table',
      columns: ['Output'],
      rowLabels: false,
      rows: [row(0), row(1)],
      canAdd: true,
      canDelete: true,
      addFiles: false,
      fileTypes: [],
      itemLabel: 'Step',
    })

    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    await wrapper.findAll('button[title=Remove]')[1].trigger('click')

    expect(actions.change).toHaveBeenCalledWith({ path: 'steps', action: 'delete', index: 1 })
  })

  it('does not draw a hidden parameter', () => {
    const { wrapper } = mountField({ ...base, hide: true, kind: 'string', path: 'x', label: 'X', value: 'y' })

    expect(wrapper.find('input').exists()).toBe(false)
  })
})
