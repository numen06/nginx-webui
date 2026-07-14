import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Config from './Config.vue'
import { configApi } from '@/api/config'

vi.mock('@/components/MonacoEditor.vue', () => ({
  default: { template: '<div data-testid="monaco" />' },
}))

vi.mock('@/api/config', () => ({
  configApi: {
    getConfig: vi.fn(),
    getTree: vi.fn(),
    getFile: vi.fn(),
    getBackups: vi.fn(),
    updateFile: vi.fn(),
    createDirectory: vi.fn(),
    renamePath: vi.fn(),
    deletePath: vi.fn(),
    testConfig: vi.fn(),
    reloadConfig: vi.fn(),
    applyConfig: vi.fn(),
    createBackup: vi.fn(),
    restoreBackup: vi.fn(),
    formatConfig: vi.fn(),
    validateFile: vi.fn(),
    splitLegacyConfig: vi.fn(),
    getMergedPreview: vi.fn(),
  },
}))

describe('Config', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(configApi.getConfig).mockResolvedValue({
      success: true,
      nginx_version: '1.29.3',
      config_dir: '/etc/nginx',
      pending_changes: false,
    })
    vi.mocked(configApi.getTree).mockResolvedValue({
      success: true,
      root: '/tmp/nginx',
      files: [
        { path: 'conf.d', name: 'conf.d', is_dir: true },
        { path: 'conf.d/alpha.conf', name: 'alpha.conf', is_dir: false },
        { path: 'conf.d/beta.conf', name: 'beta.conf', is_dir: false },
        { path: 'nginx.conf', name: 'nginx.conf', is_dir: false },
      ],
    })
    vi.mocked(configApi.getFile).mockImplementation(async (path: string) => ({
      success: true,
      path,
      content: path.includes('alpha')
        ? 'server {\n  server_name alpha.example.com;\n}'
        : path.includes('beta')
          ? 'server {\n  server_name beta.example.com;\n}'
          : 'events {}',
    }))
    vi.mocked(configApi.getBackups).mockResolvedValue({ success: true, backups: [] })
  })

  function mountPage() {
    return mount(Config, {
      global: {
        stubs: {
          MonacoEditor: { template: '<div data-testid="monaco" />' },
        },
      },
    })
  }

  it('loads site files and maps their server names', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('alpha.example.com')
    expect(wrapper.text()).toContain('beta.example.com')
    expect(wrapper.text()).toContain('显示 2 / 2 个站点')
    expect(configApi.getFile).toHaveBeenCalledWith('conf.d/alpha.conf')
    expect(configApi.getFile).toHaveBeenCalledWith('conf.d/beta.conf')
  })

  it('filters site configurations by domain or file path', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const filter = wrapper.get('input[aria-label="筛选站点配置"]')
    await filter.setValue('beta.example.com')
    expect(wrapper.text()).toContain('显示 1 / 2 个站点')
    expect(wrapper.findAll('button').some(button => button.text().includes('beta.example.com'))).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text().includes('alpha.example.com'))).toBe(false)

    await filter.setValue('alpha.conf')
    expect(wrapper.findAll('button').some(button => button.text().includes('alpha.example.com'))).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text().includes('beta.example.com'))).toBe(false)
  })

  it('lets the editor fill the desktop workspace instead of fixing a viewport height', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const page = wrapper.get('.page-shell')
    const editor = wrapper.get('[data-testid="monaco"]')

    expect(page.classes()).toContain('lg:h-full')
    expect(page.classes()).toContain('lg:overflow-hidden')
    expect(editor.classes()).toContain('flex-1')
    expect(editor.attributes('height')).toBe('100%')
  })

  it('supports a focus mode that prioritizes the editor without hiding save actions', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[aria-label="进入专注编辑"]').trigger('click')

    expect(wrapper.get('.page-shell').attributes('data-focus-mode')).toBe('true')
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('[aria-label="退出专注编辑"]').exists()).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text().includes('保存'))).toBe(true)
  })
})
