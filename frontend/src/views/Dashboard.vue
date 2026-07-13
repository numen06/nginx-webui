<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Database,
  HardDrive,
  Network,
  RefreshCw,
  ScanSearch,
  Server,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { apiErrorMessage } from '@/api'
import { configApi, type NginxStatusResponse } from '@/api/config'
import {
  statisticsApi,
  type AnalysisTaskStatusResponse,
  type AttackRecord,
  type StatisticsSummary,
  type TopIp,
  type TopPath,
  type TrendData,
} from '@/api/statistics'
import { systemApi, type SystemResourcesResponse } from '@/api/system'
import { ElMessage } from '@/lib/feedback'
import { formatDateTime } from '@/utils/date'
import { formatFileSize } from '@/utils/format'

type TimeRange = 1 | 24 | 168

const EMPTY_SUMMARY: StatisticsSummary = {
  total_requests: 0,
  success_requests: 0,
  error_requests: 0,
  error_rate: 0,
  attack_count: 0,
  error_log_count: 0,
}

const EMPTY_RESOURCES: SystemResourcesResponse = {
  success: false,
  cpu: {},
  memory: {},
  disk: {},
  network: {},
  system: {},
}

const nginxStatus = ref<NginxStatusResponse>({ running: false })
const taskStatus = ref<AnalysisTaskStatusResponse>({ success: false, status: 'unknown', is_running: false })
const resources = ref<SystemResourcesResponse>(EMPTY_RESOURCES)
const summary = ref<StatisticsSummary>({ ...EMPTY_SUMMARY })
const trend = ref<TrendData>({ hours: [], counts: [] })
const statusDistribution = ref<Record<string, number>>({})
const topIps = ref<TopIp[]>([])
const topPaths = ref<TopPath[]>([])
const attacks = ref<AttackRecord[]>([])
const timeRange = ref<TimeRange>(1)
const loading = ref(true)
const statisticsLoading = ref(false)
const refreshing = ref(false)
const pageError = ref('')
const lastUpdatedAt = ref<Date | null>(null)
const lastAnalyzeAt = ref(0)
let refreshTimer: ReturnType<typeof setInterval> | null = null
let analyzeTimer: ReturnType<typeof setTimeout> | null = null

const numberFormatter = new Intl.NumberFormat('zh-CN', {
  notation: 'compact',
  maximumFractionDigits: 1,
})

const analysisState = computed(() => {
  switch (taskStatus.value.status) {
    case 'analyzing': return { text: '分析中', variant: 'secondary' as const }
    case 'ready': return { text: '正常', variant: 'default' as const }
    case 'failed': return { text: '失败', variant: 'destructive' as const }
    case 'not_ready': return { text: '未就绪', variant: 'outline' as const }
    default: return { text: '未知', variant: 'secondary' as const }
  }
})

const successRate = computed(() => summary.value.total_requests
  ? (summary.value.success_requests / summary.value.total_requests) * 100
  : 0)

const hasTrendData = computed(() => trend.value.hours.length > 0 && trend.value.counts.length > 0)
const hasStatusData = computed(() => Object.keys(statusDistribution.value).length > 0)

const trendChartOption = computed(() => ({
  animationDuration: 350,
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#111827',
    borderColor: '#334155',
    textStyle: { color: '#f8fafc' },
  },
  grid: { left: 16, right: 18, top: 18, bottom: 12, containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: trend.value.hours,
    axisLabel: {
      color: '#94a3b8',
      formatter: (value: string) => timeRange.value === 168 ? value.slice(5) : value.slice(11),
    },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#1f2937' } },
  },
  series: [{
    name: '请求数',
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    data: trend.value.counts,
    lineStyle: { color: '#16a34a', width: 2 },
    itemStyle: { color: '#22c55e' },
    areaStyle: { color: 'rgba(34, 197, 94, 0.12)' },
  }],
}))

const statusChartOption = computed(() => {
  const colors: Record<string, string> = {
    '2': '#22c55e',
    '3': '#3b82f6',
    '4': '#f59e0b',
    '5': '#ef4444',
  }
  const data = Object.entries(statusDistribution.value)
    .map(([code, count]) => ({
      name: `HTTP ${code}`,
      value: Number(count),
      itemStyle: { color: colors[code.charAt(0)] || '#64748b' },
    }))
    .sort((a, b) => b.value - a.value)

  return {
    tooltip: {
      trigger: 'item',
      formatter: '{b}<br/>{c} 次（{d}%）',
      backgroundColor: '#111827',
      borderColor: '#334155',
      textStyle: { color: '#f8fafc' },
    },
    legend: { bottom: 0, textStyle: { color: '#94a3b8' } },
    series: [{
      type: 'pie',
      radius: ['48%', '72%'],
      center: ['50%', '43%'],
      label: { show: false },
      emphasis: { label: { show: true, color: '#f8fafc', formatter: '{b}\n{c}' } },
      data,
    }],
  }
})

function compactNumber(value: number | null | undefined): string {
  return numberFormatter.format(Number(value || 0))
}

function percent(value: number | null | undefined): number {
  return Math.min(100, Math.max(0, Number(value || 0)))
}

async function loadStatusAndResources() {
  const [statusResult, taskResult, resourcesResult] = await Promise.allSettled([
    configApi.getStatus(),
    statisticsApi.getTaskStatus(),
    systemApi.getResources(),
  ])

  if (statusResult.status === 'fulfilled') nginxStatus.value = statusResult.value
  if (taskResult.status === 'fulfilled' && taskResult.value.success) taskStatus.value = taskResult.value
  if (resourcesResult.status === 'fulfilled' && resourcesResult.value.success) resources.value = resourcesResult.value

  const failures = [statusResult, taskResult, resourcesResult].filter(result => result.status === 'rejected')
  if (failures.length === 3) throw (failures[0] as PromiseRejectedResult).reason
}

async function loadStatistics() {
  if (statisticsLoading.value) return
  statisticsLoading.value = true
  try {
    const [summaryResult, trendResult, statusResult, ipsResult, pathsResult, attacksResult] = await Promise.allSettled([
      statisticsApi.getSummary(timeRange.value),
      statisticsApi.getTrend(timeRange.value),
      statisticsApi.getStatusDistribution(timeRange.value),
      statisticsApi.getTopIPs(timeRange.value, 10),
      statisticsApi.getTopPaths(timeRange.value, 10),
      statisticsApi.getAttacks(timeRange.value, 50),
    ])

    summary.value = summaryResult.status === 'fulfilled' && summaryResult.value.success
      ? summaryResult.value.summary || { ...EMPTY_SUMMARY }
      : { ...EMPTY_SUMMARY }
    trend.value = trendResult.status === 'fulfilled'
      ? trendResult.value.hourly_trend
      : { hours: [], counts: [] }
    statusDistribution.value = statusResult.status === 'fulfilled'
      ? statusResult.value.status_distribution
      : {}
    topIps.value = ipsResult.status === 'fulfilled' ? ipsResult.value.top_ips : []
    topPaths.value = pathsResult.status === 'fulfilled' ? pathsResult.value.top_paths : []
    attacks.value = attacksResult.status === 'fulfilled' ? attacksResult.value.attacks : []
  } finally {
    statisticsLoading.value = false
  }
}

async function refreshAll(showFeedback = false) {
  if (refreshing.value) return
  refreshing.value = true
  pageError.value = ''
  try {
    await Promise.all([loadStatusAndResources(), loadStatistics()])
    lastUpdatedAt.value = new Date()
    if (showFeedback) ElMessage.success('仪表盘数据已刷新')
  } catch (error) {
    pageError.value = apiErrorMessage(error, '仪表盘数据加载失败')
    if (showFeedback) ElMessage.error(pageError.value)
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function changeRange(range: TimeRange) {
  if (timeRange.value === range) return
  timeRange.value = range
  await loadStatistics()
  lastUpdatedAt.value = new Date()
}

async function triggerAnalyze(full: boolean) {
  if (taskStatus.value.is_running) {
    ElMessage.info('分析任务正在运行中')
    return
  }
  if (!full && Date.now() - lastAnalyzeAt.value < 10_000) {
    ElMessage.warning('操作过于频繁，请稍后再试')
    return
  }

  lastAnalyzeAt.value = Date.now()
  taskStatus.value = { ...taskStatus.value, is_running: true, status: 'analyzing', analyzed_lines: 0 }
  try {
    const response = await statisticsApi.triggerAnalyze(full)
    if (!response.success) {
      ElMessage.warning(response.message || '分析任务未启动')
      await loadStatusAndResources()
      return
    }
    ElMessage.success(response.message || `${full ? '全量' : '增量'}分析已启动`)
    if (analyzeTimer) clearTimeout(analyzeTimer)
    analyzeTimer = setTimeout(() => void refreshAll(), full ? 5000 : 3000)
  } catch (error) {
    taskStatus.value = { ...taskStatus.value, is_running: false, status: 'failed' }
    ElMessage.error(apiErrorMessage(error, '启动分析失败'))
  }
}

onMounted(() => {
  void refreshAll()
  refreshTimer = setInterval(() => void refreshAll(), 30_000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (analyzeTimer) clearTimeout(analyzeTimer)
})
</script>

<template>
  <div class="page-shell space-y-5">
    <div class="page-heading gap-4">
      <div>
        <h2 class="page-title">仪表盘</h2>
        <p class="page-description">
          Nginx 运行状态、访问统计和主机资源概览
          <span v-if="lastUpdatedAt"> · 更新于 {{ formatDateTime(lastUpdatedAt) }}</span>
        </p>
      </div>
      <div class="toolbar">
        <Button variant="secondary" :disabled="refreshing" @click="refreshAll(true)">
          <RefreshCw :class="['size-4', { 'animate-spin': refreshing }]" />刷新
        </Button>
        <Button variant="outline" :disabled="taskStatus.is_running" @click="triggerAnalyze(false)">
          <ScanSearch class="size-4" />增量分析
        </Button>
        <Button :disabled="taskStatus.is_running" @click="triggerAnalyze(true)">
          <BarChart3 class="size-4" />全量分析
        </Button>
      </div>
    </div>

    <div v-if="pageError" class="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-red-200">
      <TriangleAlert class="mt-0.5 size-4 shrink-0" />
      <div><div class="font-medium">部分数据加载失败</div><div class="mt-1 text-red-200/80">{{ pageError }}</div></div>
    </div>

    <Card>
      <CardHeader class="border-b pb-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle class="flex items-center gap-2 text-base"><Server class="size-4 text-primary" />Nginx 运行状态</CardTitle>
            <CardDescription class="mt-1">当前生产实例与统计分析任务</CardDescription>
          </div>
          <div class="flex items-center gap-2">
            <Badge :variant="nginxStatus.running ? 'default' : 'destructive'">
              <span :class="['mr-1.5 size-1.5 rounded-full', nginxStatus.running ? 'bg-emerald-200' : 'bg-red-200']" />
              {{ nginxStatus.running ? '运行中' : '已停止' }}
            </Badge>
            <Badge :variant="analysisState.variant">分析：{{ analysisState.text }}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent class="grid grid-cols-2 gap-px overflow-hidden p-0 xl:grid-cols-4">
        <div v-for="item in [
          ['进程 ID', nginxStatus.pid || '—'],
          ['当前版本', nginxStatus.version || '未知'],
          ['运行目录', nginxStatus.directory || '—'],
          ['运行时间', nginxStatus.uptime || '—'],
          ['已分析行数', taskStatus.analyzed_lines ? compactNumber(taskStatus.analyzed_lines) : '—'],
          ['上次分析', taskStatus.last_analysis_time ? formatDateTime(taskStatus.last_analysis_time) : '—'],
          ['上次耗时', taskStatus.last_duration_seconds ? `${taskStatus.last_duration_seconds.toFixed(1)} 秒` : '—'],
          ['任务来源', taskStatus.last_trigger || '—'],
        ]" :key="String(item[0])" class="min-w-0 border-b border-r p-4 last:border-b-0">
          <div class="text-xs text-muted-foreground">{{ item[0] }}</div>
          <div class="mt-1 truncate text-sm font-medium" :title="String(item[1])">{{ item[1] }}</div>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <template v-if="loading">
        <Skeleton v-for="index in 4" :key="index" class="h-28 rounded-xl" />
      </template>
      <template v-else>
        <Card v-for="metric in [
          { label: '总请求数', value: compactNumber(summary.total_requests), note: `${timeRange} 小时`, icon: Activity, tone: 'text-primary bg-primary/10' },
          { label: '成功请求', value: compactNumber(summary.success_requests), note: `成功率 ${successRate.toFixed(1)}%`, icon: ShieldCheck, tone: 'text-emerald-400 bg-emerald-500/10' },
          { label: '错误请求', value: compactNumber(summary.error_requests), note: `错误率 ${summary.error_rate.toFixed(1)}%`, icon: AlertTriangle, tone: 'text-amber-400 bg-amber-500/10' },
          { label: '攻击检测', value: compactNumber(summary.attack_count), note: `错误日志 ${compactNumber(summary.error_log_count)}`, icon: ScanSearch, tone: 'text-red-400 bg-red-500/10' },
        ]" :key="metric.label" class="gap-0 py-0">
          <CardContent class="flex items-start justify-between p-5">
            <div><div class="text-sm text-muted-foreground">{{ metric.label }}</div><div class="mt-2 text-2xl font-semibold tracking-tight">{{ metric.value }}</div><div class="mt-1 text-xs text-muted-foreground">{{ metric.note }}</div></div>
            <span :class="['grid size-9 place-items-center rounded-lg', metric.tone]"><component :is="metric.icon" class="size-4" /></span>
          </CardContent>
        </Card>
      </template>
    </div>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card class="gap-0 py-0">
        <CardContent class="space-y-4 p-5">
          <div class="flex items-center justify-between"><div><div class="text-sm text-muted-foreground">CPU 使用率</div><div class="mt-1 text-xl font-semibold">{{ percent(resources.cpu.percent).toFixed(1) }}%</div></div><Activity class="size-5 text-primary" /></div>
          <Progress :model-value="percent(resources.cpu.percent)" /><div class="text-xs text-muted-foreground">{{ resources.cpu.count?.logical || 0 }} 个逻辑核心</div>
        </CardContent>
      </Card>
      <Card class="gap-0 py-0">
        <CardContent class="space-y-4 p-5">
          <div class="flex items-center justify-between"><div><div class="text-sm text-muted-foreground">内存使用</div><div class="mt-1 text-xl font-semibold">{{ formatFileSize(resources.memory.used) }}</div></div><Database class="size-5 text-primary" /></div>
          <Progress :model-value="percent(resources.memory.percent)" /><div class="text-xs text-muted-foreground">{{ percent(resources.memory.percent).toFixed(1) }}% / {{ formatFileSize(resources.memory.total) }}</div>
        </CardContent>
      </Card>
      <Card class="gap-0 py-0">
        <CardContent class="space-y-4 p-5">
          <div class="flex items-center justify-between"><div><div class="text-sm text-muted-foreground">磁盘使用</div><div class="mt-1 text-xl font-semibold">{{ percent(resources.disk.root?.percent).toFixed(1) }}%</div></div><HardDrive class="size-5 text-primary" /></div>
          <Progress :model-value="percent(resources.disk.root?.percent)" /><div class="text-xs text-muted-foreground">{{ formatFileSize(resources.disk.root?.used) }} / {{ formatFileSize(resources.disk.root?.total) }}</div>
        </CardContent>
      </Card>
      <Card class="gap-0 py-0">
        <CardContent class="space-y-4 p-5">
          <div class="flex items-center justify-between"><div><div class="text-sm text-muted-foreground">网络连接</div><div class="mt-1 text-xl font-semibold">{{ compactNumber(resources.network.connections) }}</div></div><Network class="size-5 text-primary" /></div>
          <div class="grid grid-cols-2 gap-3 text-xs text-muted-foreground"><span>上传 {{ formatFileSize(resources.network.bytes_sent) }}</span><span>下载 {{ formatFileSize(resources.network.bytes_recv) }}</span></div>
        </CardContent>
      </Card>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><h3 class="text-base font-medium">访问统计</h3><p class="text-sm text-muted-foreground">切换时间范围会同步刷新所有统计区域。</p></div>
      <div class="inline-flex rounded-lg border bg-muted/40 p-1">
        <Button v-for="option in [{ value: 1, label: '1 小时' }, { value: 24, label: '24 小时' }, { value: 168, label: '7 天' }]" :key="option.value" size="sm" :variant="timeRange === option.value ? 'secondary' : 'ghost'" @click="changeRange(option.value as TimeRange)">{{ option.label }}</Button>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-3">
      <Card class="xl:col-span-2">
        <CardHeader class="pb-2"><CardTitle class="text-base">访问趋势</CardTitle><CardDescription>所选时间范围内的请求变化</CardDescription></CardHeader>
        <CardContent>
          <Skeleton v-if="statisticsLoading" class="h-72 w-full" />
          <v-chart v-else-if="hasTrendData" class="h-72 w-full" :option="trendChartOption" autoresize />
          <div v-else class="grid h-72 place-items-center text-sm text-muted-foreground">暂无趋势数据，请先执行分析</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader class="pb-2"><CardTitle class="text-base">状态码分布</CardTitle><CardDescription>HTTP 响应状态构成</CardDescription></CardHeader>
        <CardContent>
          <Skeleton v-if="statisticsLoading" class="h-72 w-full" />
          <v-chart v-else-if="hasStatusData" class="h-72 w-full" :option="statusChartOption" autoresize />
          <div v-else class="grid h-72 place-items-center text-sm text-muted-foreground">暂无状态码数据</div>
        </CardContent>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader><CardTitle class="text-base">访问量 Top 10 IP</CardTitle><CardDescription>访问最频繁的客户端地址</CardDescription></CardHeader>
        <CardContent class="px-0">
          <Table><TableHeader><TableRow><TableHead class="pl-6">IP 地址</TableHead><TableHead class="pr-6 text-right">访问次数</TableHead></TableRow></TableHeader><TableBody>
            <TableRow v-for="item in topIps" :key="item.ip"><TableCell class="pl-6 font-mono text-xs">{{ item.ip }}</TableCell><TableCell class="pr-6 text-right font-medium">{{ compactNumber(item.count) }}</TableCell></TableRow>
            <TableRow v-if="!topIps.length"><TableCell colspan="2" class="h-24 text-center text-muted-foreground">暂无数据</TableCell></TableRow>
          </TableBody></Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle class="text-base">访问量 Top 10 路径</CardTitle><CardDescription>请求最集中的 URL 路径</CardDescription></CardHeader>
        <CardContent class="px-0">
          <Table><TableHeader><TableRow><TableHead class="pl-6">路径</TableHead><TableHead class="pr-6 text-right">访问次数</TableHead></TableRow></TableHeader><TableBody>
            <TableRow v-for="item in topPaths" :key="item.path"><TableCell class="max-w-[18rem] truncate pl-6 font-mono text-xs" :title="item.path">{{ item.path }}</TableCell><TableCell class="pr-6 text-right font-medium">{{ compactNumber(item.count) }}</TableCell></TableRow>
            <TableRow v-if="!topPaths.length"><TableCell colspan="2" class="h-24 text-center text-muted-foreground">暂无数据</TableCell></TableRow>
          </TableBody></Table>
        </CardContent>
      </Card>
    </div>

    <Card v-if="attacks.length">
      <CardHeader><CardTitle class="flex items-center gap-2 text-base"><AlertTriangle class="size-4 text-red-400" />攻击检测记录</CardTitle><CardDescription>最近 {{ attacks.length }} 条可疑请求</CardDescription></CardHeader>
      <CardContent class="px-0">
        <Table><TableHeader><TableRow><TableHead class="pl-6">时间</TableHead><TableHead>来源 IP</TableHead><TableHead>路径</TableHead><TableHead>状态</TableHead><TableHead class="pr-6">类型</TableHead></TableRow></TableHeader><TableBody>
          <TableRow v-for="(item, index) in attacks" :key="`${item.time}-${index}`"><TableCell class="whitespace-nowrap pl-6 text-xs text-muted-foreground">{{ formatDateTime(item.time) }}</TableCell><TableCell class="font-mono text-xs">{{ item.ip }}</TableCell><TableCell class="max-w-72 truncate font-mono text-xs" :title="item.path">{{ item.path }}</TableCell><TableCell>{{ item.status }}</TableCell><TableCell class="pr-6"><div class="flex flex-wrap gap-1"><Badge v-for="attack in item.attacks" :key="attack" variant="destructive">{{ attack }}</Badge></div></TableCell></TableRow>
        </TableBody></Table>
      </CardContent>
    </Card>
  </div>
</template>
