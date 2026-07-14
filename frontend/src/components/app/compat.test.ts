import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { UiStep, UiSteps, UiUpload } from './compat'

describe('UiUpload', () => {
  it('selects, lists, and removes a file through the component callbacks', async () => {
    const onChange = vi.fn()
    const onRemove = vi.fn()
    const wrapper = mount(UiUpload, {
      props: { onChange, onRemove },
    })
    const file = new File(['nginx'], 'nginx-1.28.0.tar.gz', {
      type: 'application/gzip',
    })
    const input = wrapper.get('input[type="file"]')

    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [file],
    })
    await input.trigger('change')

    expect(onChange).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('nginx-1.28.0.tar.gz')

    await wrapper.get('[aria-label="移除 nginx-1.28.0.tar.gz"]').trigger('click')

    expect(onRemove).toHaveBeenCalledOnce()
    expect(wrapper.text()).not.toContain('nginx-1.28.0.tar.gz')
  })

  it('forwards template on-change and on-remove callbacks to the form state', async () => {
    const wrapper = mount(defineComponent({
      components: { UiUpload },
      setup() {
        const selectedFiles = ref<File[]>([])
        const syncFiles = (_file: unknown, fileList: Array<{ raw: File }> = []) => {
          selectedFiles.value = fileList.map(item => item.raw)
        }
        return { selectedFiles, syncFiles }
      },
      template: `
        <UiUpload :on-change="syncFiles" :on-remove="syncFiles">
          <button type="button">选择文件</button>
        </UiUpload>
        <button data-testid="submit" :disabled="!selectedFiles.length">上传</button>
      `,
    }))
    const file = new File(['index'], 'index.html', { type: 'text/html' })
    const input = wrapper.get('input[type="file"]')

    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [file],
    })
    await input.trigger('change')

    expect(wrapper.get('[data-testid="submit"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[aria-label="移除 index.html"]').trigger('click')
    expect(wrapper.get('[data-testid="submit"]').attributes('disabled')).toBeDefined()
  })
})

describe('UiSteps', () => {
  it('distinguishes completed, current, and pending steps', async () => {
    const wrapper = mount(defineComponent({
      components: { UiStep, UiSteps },
      template: `
        <UiSteps :active="1" finish-status="success" align-center>
          <UiStep title="准备源码包" />
          <UiStep title="编译 Nginx" />
          <UiStep title="发布到生产" />
        </UiSteps>
      `,
    }))

    await nextTick()
    const steps = wrapper.findAll('.ui-step')

    expect(steps).toHaveLength(3)
    expect(steps.map(step => step.attributes('data-status'))).toEqual([
      'success',
      'process',
      'wait',
    ])
    expect(steps[1].attributes('aria-current')).toBe('step')
    expect(steps[0].find('svg').exists()).toBe(true)
  })
})
