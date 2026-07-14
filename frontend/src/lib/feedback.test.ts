import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import FeedbackHost from '@/components/app/FeedbackHost.vue'
import {
  ElMessageBox,
  feedbackDialog,
  rejectFeedbackDialog,
} from './feedback'

describe('ElMessageBox', () => {
  afterEach(() => {
    if (feedbackDialog.open) rejectFeedbackDialog()
    document.body.innerHTML = ''
  })

  it('resolves a confirmation when the user clicks the action button', async () => {
    const wrapper = mount(FeedbackHost, { attachTo: document.body })
    const result = ElMessageBox.confirm('确定删除吗？', '删除文件')
    await nextTick()

    const action = [...document.body.querySelectorAll('button')]
      .find(button => button.textContent?.trim() === '确定')
    expect(action).toBeDefined()
    action?.click()

    await expect(result).resolves.toBe('confirm')
    wrapper.unmount()
  })

  it('rejects a confirmation only when the user clicks cancel', async () => {
    const wrapper = mount(FeedbackHost, { attachTo: document.body })
    const result = ElMessageBox.confirm('确定删除吗？', '删除文件')
    await nextTick()

    const cancel = [...document.body.querySelectorAll('button')]
      .find(button => button.textContent?.trim() === '取消')
    expect(cancel).toBeDefined()
    cancel?.click()

    await expect(result).rejects.toBe('cancel')
    wrapper.unmount()
  })
})
