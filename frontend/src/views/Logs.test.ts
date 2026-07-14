import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Logs from './Logs.vue'
import { logsApi } from '@/api/logs'
import { ElMessageBox } from '@/lib/feedback'
import { Tabs } from '@/components/ui/tabs'

vi.mock('@/api/logs', () => ({
  logsApi: {
    getAccessLogs: vi.fn(),
    getErrorLogs: vi.fn(),
    triggerLogRotate: vi.fn(),
    getLogRotateFiles: vi.fn(),
    deleteLogRotateFile: vi.fn(),
  },
}))

vi.mock('@/lib/feedback', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn(),
  },
}))

vi.mock('@/components/LogViewer.vue', () => ({
  default: {
    props: ['logs', 'keyword', 'filename'],
    template: '<div data-testid="log-viewer">{{ filename }} · {{ logs.length }} 行</div>',
  },
}))

describe('Logs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(logsApi.getAccessLogs).mockResolvedValue({
      success: true,
      logs: ['access line'],
      log_path: '/var/log/nginx/access.log',
      log_size_bytes: 2048,
      nginx_version: 'nginx/1.29.3',
      install_path: '/usr/local/nginx',
      pagination: { total_pages: 2 },
    })
    vi.mocked(logsApi.getErrorLogs).mockResolvedValue({
      success: true,
      logs: ['error line'],
      log_path: '/var/log/nginx/error.log',
      log_size_bytes: 1024,
      pagination: { total_pages: 1 },
    })
    vi.mocked(logsApi.getLogRotateFiles).mockResolvedValue({
      success: true,
      access_files: [{ filename: 'access.log.20260714', date: '2026-07-14', size: 512 }],
      error_files: [],
    })
    vi.mocked(logsApi.deleteLogRotateFile).mockResolvedValue({ success: true })
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm')
  })

  function mountPage() {
    return mount(Logs, {
      global: {
        directives: { loading: {} },
        stubs: {
          'ui-date-picker': {
            template: '<div data-testid="date-picker" />',
          },
        },
      },
    })
  }

  it('uses one flexible workspace and switches between access and error logs', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('.page-shell').classes()).toContain('lg:h-full')
    expect(wrapper.get('.page-shell').classes()).toContain('lg:overflow-hidden')
    expect(wrapper.get('.logs-workspace').classes()).toContain('lg:flex-1')
    expect(wrapper.get('[data-testid="log-viewer"]').text()).toContain('access-log · 1 行')

    wrapper.getComponent(Tabs).vm.$emit('update:modelValue', 'error')
    await flushPromises()

    expect(logsApi.getErrorLogs).toHaveBeenCalled()
    expect(wrapper.get('[data-testid="log-viewer"]').text()).toContain('error-log · 1 行')
  })

  it('applies quick time filters and opens a historical fragment without conflicting date filters', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('select[aria-label="快捷时间范围"]').setValue('60')
    await flushPromises()
    const quickTimeCall = vi.mocked(logsApi.getAccessLogs).mock.calls.at(-1)
    expect(quickTimeCall?.[3]).toBeTruthy()
    expect(quickTimeCall?.[4]).toBeTruthy()

    await wrapper.get('.rotate-file-main').trigger('click')
    await flushPromises()
    const fragmentCall = vi.mocked(logsApi.getAccessLogs).mock.calls.at(-1)
    expect(fragmentCall?.[3]).toBeNull()
    expect(fragmentCall?.[4]).toBeNull()
    expect(fragmentCall?.[5]).toBe('access.log.20260714')
  })

  it('keeps refresh and rotate actions available in focus mode and can delete fragments', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[aria-label="进入专注查看"]').trigger('click')
    expect(wrapper.get('.page-shell').attributes('data-focus-mode')).toBe('true')
    expect(wrapper.find('.rotate-strip').exists()).toBe(false)
    expect(wrapper.find('[aria-label="退出专注查看"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="刷新日志"]').exists()).toBe(true)

    await wrapper.get('[aria-label="退出专注查看"]').trigger('click')
    await wrapper.get('.rotate-file-delete').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(logsApi.deleteLogRotateFile).toHaveBeenCalledWith('access.log.20260714')
  })
})
