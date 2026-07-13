import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard.vue'
import { configApi } from '@/api/config'
import { statisticsApi } from '@/api/statistics'
import { systemApi } from '@/api/system'

vi.mock('@/api/config', () => ({
  configApi: { getStatus: vi.fn() },
}))

vi.mock('@/api/statistics', () => ({
  statisticsApi: {
    getSummary: vi.fn(),
    getTrend: vi.fn(),
    getStatusDistribution: vi.fn(),
    getTopIPs: vi.fn(),
    getTopPaths: vi.fn(),
    getAttacks: vi.fn(),
    getTaskStatus: vi.fn(),
    triggerAnalyze: vi.fn(),
  },
}))

vi.mock('@/api/system', () => ({
  systemApi: { getResources: vi.fn() },
}))

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(configApi.getStatus).mockResolvedValue({
      running: true,
      version: '1.29.3',
      pid: 123,
      directory: '/app/nginx',
      uptime: '2 小时',
    })
    vi.mocked(statisticsApi.getTaskStatus).mockResolvedValue({
      success: true,
      status: 'ready',
      is_running: false,
      analyzed_lines: 42,
    })
    vi.mocked(systemApi.getResources).mockResolvedValue({
      success: true,
      cpu: { percent: 12.5, count: { logical: 8 } },
      memory: { used: 1024, total: 4096, percent: 25 },
      disk: { root: { used: 2048, total: 8192, percent: 25 } },
      network: { connections: 7, bytes_sent: 100, bytes_recv: 200 },
      system: {},
    })
    vi.mocked(statisticsApi.getSummary).mockResolvedValue({
      success: true,
      summary: {
        total_requests: 42,
        success_requests: 40,
        error_requests: 2,
        error_rate: 4.76,
        attack_count: 1,
        error_log_count: 3,
      },
    })
    vi.mocked(statisticsApi.getTrend).mockResolvedValue({
      success: true,
      hourly_trend: { hours: ['2026-07-13 15:00'], counts: [42] },
    })
    vi.mocked(statisticsApi.getStatusDistribution).mockResolvedValue({ success: true, status_distribution: { '200': 40, '500': 2 } })
    vi.mocked(statisticsApi.getTopIPs).mockResolvedValue({ success: true, top_ips: [{ ip: '127.0.0.1', count: 42 }] })
    vi.mocked(statisticsApi.getTopPaths).mockResolvedValue({ success: true, top_paths: [{ path: '/api/health', count: 42 }] })
    vi.mocked(statisticsApi.getAttacks).mockResolvedValue({ success: true, attacks: [], total_count: 0 })
  })

  it('maps API results into visible dashboard metrics', async () => {
    const wrapper = mount(Dashboard, { global: { stubs: { VChart: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('Nginx 运行状态')
    expect(wrapper.text()).toContain('1.29.3')
    expect(wrapper.text()).toContain('总请求数42')
    expect(wrapper.text()).toContain('127.0.0.1')
    expect(wrapper.text()).toContain('/api/health')
    expect(statisticsApi.getSummary).toHaveBeenCalledWith(1)
  })

  it('reloads every statistics endpoint when the range changes', async () => {
    const wrapper = mount(Dashboard, { global: { stubs: { VChart: true } } })
    await flushPromises()
    const rangeButton = wrapper.findAll('button').find(button => button.text() === '24 小时')
    expect(rangeButton).toBeTruthy()
    await rangeButton!.trigger('click')
    await flushPromises()

    expect(statisticsApi.getSummary).toHaveBeenLastCalledWith(24)
    expect(statisticsApi.getTrend).toHaveBeenLastCalledWith(24)
    expect(statisticsApi.getTopIPs).toHaveBeenLastCalledWith(24, 10)
    expect(statisticsApi.getAttacks).toHaveBeenLastCalledWith(24, 50)
  })
})
