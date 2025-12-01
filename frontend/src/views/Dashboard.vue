<template>
  <div class="dashboard">
    <!-- Nginx状态卡片 -->
    <el-row :gutter="20" class="mb-20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Nginx 运行状态</span>
              <div class="card-actions">
                <el-button type="info" text @click="refreshStatus">
                  <el-icon><Refresh /></el-icon>
                  刷新
                </el-button>
                <el-button
                  type="primary"
                  text
                  :disabled="statsStatus.status === 'analyzing' || analyzingManual"
                  @click="triggerAnalyzeNow"
                >
                  <el-icon style="margin-right: 4px;"><DataAnalysis /></el-icon>
                  立即分析
                </el-button>
              </div>
            </div>
          </template>
          <el-descriptions :column="2" border size="small" class="nginx-status-descriptions">
            <el-descriptions-item label="运行状态">
              <el-tag :type="nginxStatus.running ? 'success' : 'danger'" size="small">
                {{ nginxStatus.running ? '运行中' : '已停止' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="进程ID">
              <el-text type="info" size="small">{{ nginxStatus.pid || '无' }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="当前 Nginx 目录">
              <el-text type="info" size="small">{{ nginxStatus.directory || '-' }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="当前 Nginx 版本">
              <el-tag v-if="nginxStatus.version" type="info" size="small">
                {{ nginxStatus.version }}
              </el-tag>
              <span v-else class="text-muted">未知</span>
            </el-descriptions-item>
            <el-descriptions-item label="运行时间" :span="2">
              <el-text type="info" size="small">{{ nginxStatus.uptime || '-' }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="统计分析状态">
              <el-tag
                class="analysis-status-tag"
                :type="analysisTagType"
                size="small"
              >
                {{ analysisTagText }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="任务耗时" :span="2">
              <el-text type="info" size="small">
                <span v-if="analysisDurationText">
                  {{ analysisDurationText }}
                </span>
                <span v-else class="text-muted">-</span>
              </el-text>
            </el-descriptions-item>
            <el-descriptions-item label="上次分析时间" :span="1">
              <el-text type="info" size="small">
                {{ statsStatus.lastAnalysisTime ? formatDateTime(statsStatus.lastAnalysisTime) : '-' }}
              </el-text>
            </el-descriptions-item>
            <el-descriptions-item label="下次预计分析时间" :span="1">
              <el-text type="info" size="small">
                {{ statsStatus.nextAnalysisTime ? formatDateTime(statsStatus.nextAnalysisTime) : '-' }}
              </el-text>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <!-- 统计指标卡片 -->
    <el-row :gutter="20" class="mb-20">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: var(--nginx-green);">
              <el-icon size="24"><DataLine /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.total_requests || 0) }}</div>
              <div class="stat-label">总请求数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: var(--nginx-green-light);">
              <el-icon size="24"><SuccessFilled /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.success_requests || 0) }}</div>
              <div class="stat-label">成功请求</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #E6A23C;">
              <el-icon size="24"><WarningFilled /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.error_requests || 0) }}</div>
              <div class="stat-label">错误请求</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #dc2626;">
              <el-icon size="24"><Lock /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.attack_count || 0) }}</div>
              <div class="stat-label">攻击检测</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 系统资源卡片 -->
    <el-row :gutter="20" class="mb-20">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #409EFF;">
              <el-icon size="24"><Odometer /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ systemResources.cpu?.percent || 0 }}%</div>
              <div class="stat-label">CPU使用率</div>
              <div class="stat-extra" v-if="systemResources.cpu?.count">
                {{ systemResources.cpu.count.logical }}核
              </div>
            </div>
          </div>
          <el-progress
            :percentage="systemResources.cpu?.percent || 0"
            :color="getProgressColor(systemResources.cpu?.percent || 0)"
            :show-text="false"
            class="stat-progress"
          />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #67C23A;">
              <el-icon size="24"><DataBoard /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatBytes(systemResources.memory?.used || 0) }}</div>
              <div class="stat-label">内存使用</div>
              <div class="stat-extra" v-if="systemResources.memory">
                {{ systemResources.memory.percent?.toFixed(1) }}%
              </div>
            </div>
          </div>
          <el-progress
            :percentage="systemResources.memory?.percent || 0"
            :color="getProgressColor(systemResources.memory?.percent || 0)"
            :show-text="false"
            class="stat-progress"
          />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #E6A23C;">
              <el-icon size="24"><Folder /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ systemResources.disk?.root?.percent?.toFixed(1) || 0 }}%</div>
              <div class="stat-label">磁盘使用</div>
              <div class="stat-extra" v-if="systemResources.disk?.root">
                {{ formatBytesShort(systemResources.disk.root.used || 0) }} / {{ formatBytesShort(systemResources.disk.root.total || 0) }}
              </div>
            </div>
          </div>
          <el-progress
            :percentage="systemResources.disk?.root?.percent || 0"
            :color="getProgressColor(systemResources.disk?.root?.percent || 0)"
            :show-text="false"
            class="stat-progress"
          />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card resource-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #909399;">
              <el-icon size="24"><Share /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ systemResources.network?.connections || 0 }}</div>
              <div class="stat-label">网络连接</div>
              <div class="stat-extra" v-if="systemResources.network">
                ↑{{ formatBytesShort(systemResources.network.bytes_sent || 0) }}
                ↓{{ formatBytesShort(systemResources.network.bytes_recv || 0) }}
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="mb-20">
      <!-- 访问趋势图 -->
      <el-col :xs="24" :md="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>访问趋势</span>
              <el-radio-group v-model="timeRange" size="small" @change="loadStatistics">
                <el-radio-button :label="1">1小时</el-radio-button>
                <el-radio-button :label="24">24小时</el-radio-button>
                <el-radio-button :label="168">7天</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <v-chart
            class="chart"
            :option="trendChartOption"
            autoresize
          />
        </el-card>
      </el-col>
      
      <!-- 状态码分布 -->
      <el-col :xs="24" :md="8">
        <el-card>
          <template #header>
            <span>状态码分布</span>
          </template>
          <v-chart
            class="chart"
            :option="statusChartOption"
            autoresize
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 详细统计表格 -->
    <el-row :gutter="20">
      <!-- Top IP -->
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>
            <span>访问量 Top 10 IP</span>
          </template>
          <el-table :data="stats.top_ips || []" stripe>
            <el-table-column prop="ip" label="IP地址" />
            <el-table-column prop="count" label="访问次数" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.count) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- Top 路径 -->
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>
            <span>访问量 Top 10 路径</span>
          </template>
          <el-table :data="stats.top_paths || []" stripe>
            <el-table-column prop="path" label="路径" show-overflow-tooltip />
            <el-table-column prop="count" label="访问次数" width="120" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.count) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 攻击检测列表 -->
    <el-row :gutter="20" class="mt-20" v-if="stats.attacks && stats.attacks.length > 0">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>
              <el-icon><Warning /></el-icon>
              攻击检测记录（最近{{ stats.attacks.length }}条）
            </span>
          </template>
          <el-table :data="stats.attacks" stripe>
            <el-table-column prop="time" label="时间" width="180" />
            <el-table-column prop="ip" label="IP地址" width="150" />
            <el-table-column prop="path" label="路径" show-overflow-tooltip />
            <el-table-column prop="status" label="状态码" width="100" align="center" />
            <el-table-column prop="attacks" label="攻击类型">
              <template #default="{ row }">
                <el-tag
                  v-for="(attack, index) in row.attacks"
                  :key="index"
                  type="danger"
                  size="small"
                  class="mr-5"
                >
                  {{ attack }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { configApi } from '../api/config'
import { statisticsApi } from '../api/statistics'
import { systemApi } from '../api/system'
import { ElMessage } from 'element-plus'
import { formatDateTime } from '../utils/date'

const nginxStatus = ref({
  running: false,
  version: null,
  directory: null,
  pid: null,
  uptime: null
})

const stats = ref({
  summary: {},
  top_ips: [],
  top_paths: [],
  hourly_trend: {},
  status_distribution: {},
  attacks: []
})

const systemResources = ref({
  cpu: {},
  memory: {},
  disk: {},
  network: {},
  system: {}
})

const systemVersion = ref({
  version: null,
  build_time_formatted: null
})

// 统计分析状态
const statsStatus = ref({
  status: 'unknown',          // 'unknown' | 'ready' | 'not_ready' | 'analyzing' | 'failed'
  lastAnalysisTime: null,     // 上次分析到的日志时间（数据维度）
  nextAnalysisTime: null,     // 下次预计分析时间（数据维度）
  isAnalyzing: false,         // 后台任务是否在执行
  lastJobStartTime: null,     // 最近一次任务开始时间
  lastJobEndTime: null,       // 最近一次任务结束时间
  lastJobError: null,         // 最近一次任务错误
  lastJobSuccess: null,       // 最近一次任务是否成功
  lastJobTrigger: null,       // 最近一次任务触发方式：auto / manual
  lastJobDurationSeconds: null,      // 最近一次任务总耗时（秒）
  runningDurationSeconds: null       // 当前运行中任务耗时（秒）
})

// 统计分析状态标签（保持固定宽度，避免布局抖动）
const analysisTagType = computed(() => {
  const s = statsStatus.value.status
  if (s === 'analyzing') return 'info'
  if (s === 'ready') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'not_ready') return 'warning'
  return 'info'
})

const analysisTagText = computed(() => {
  const s = statsStatus.value.status
  if (s === 'analyzing') return '分析中'
  if (s === 'ready') return '正常'
  if (s === 'failed') return '失败'
  if (s === 'not_ready') return '未就绪'
  return '未知'
})

// 分析任务耗时展示文本
const analysisDurationText = computed(() => {
  const s = statsStatus.value
  // 正在分析时，优先展示当前已运行时长
  if (s.isAnalyzing && s.runningDurationSeconds != null) {
    const sec = s.runningDurationSeconds
    if (sec < 60) return `当前耗时：${sec.toFixed(1)} 秒`
    const min = sec / 60
    return `当前耗时：${min.toFixed(1)} 分钟`
  }

  // 最近一次完成任务的耗时
  if (!s.isAnalyzing && s.lastJobDurationSeconds != null && s.lastJobDurationSeconds > 0) {
    const sec = s.lastJobDurationSeconds
    if (sec < 60) return `最近耗时：${sec.toFixed(1)} 秒`
    const min = sec / 60
    return `最近耗时：${min.toFixed(1)} 分钟`
  }

  return ''
})

// 访问趋势时间范围（单位：小时）
// 1 小时：后端按 5 分钟粒度聚合
// 24 小时：按小时聚合
// 168 小时（7 天）：按天聚合
const timeRange = ref(1)
const loading = ref(false)
const analyzingManual = ref(false)

// 仪表盘分块加载的各区域 loading 状态
const loadingSummary = ref(false)       // 顶部统计卡片
const loadingTrend = ref(false)         // 访问趋势图
const loadingTopIPs = ref(false)        // Top IP 表格
const loadingTopPaths = ref(false)      // Top Path 表格
const loadingStatusDist = ref(false)    // 状态码分布图
const loadingAttacks = ref(false)       // 攻击记录表格

let refreshTimer = null

// 格式化数字
const formatNumber = (num) => {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(2) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(2) + 'K'
  }
  return num.toString()
}

// 格式化字节
const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 格式化字节（简短版，用于小空间显示）
const formatBytesShort = (bytes) => {
  if (!bytes || bytes === 0) return '0B'
  const k = 1024
  const sizes = ['B', 'K', 'M', 'G', 'T']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + sizes[i]
}

// 获取进度条颜色
const getProgressColor = (percent) => {
  if (percent < 50) return '#67C23A'
  if (percent < 80) return '#E6A23C'
  return '#F56C6C'
}

// 访问趋势图配置
const trendChartOption = computed(() => {
  const hourly = stats.value.hourly_trend || {}
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      },
      backgroundColor: 'rgba(26, 35, 50, 0.95)',
      borderColor: '#2d3748',
      textStyle: {
        color: '#e4e7ed'
      }
    },
    xAxis: {
      type: 'category',
      data: hourly.hours || [],
      axisLabel: {
        rotate: 45,
        color: '#b3b8c3'
      },
      axisLine: {
        lineStyle: {
          color: '#2d3748'
        }
      }
    },
    yAxis: {
      type: 'value',
      name: '请求数',
      nameTextStyle: {
        color: '#b3b8c3'
      },
      axisLabel: {
        color: '#b3b8c3'
      },
      axisLine: {
        lineStyle: {
          color: '#2d3748'
        }
      },
      splitLine: {
        lineStyle: {
          color: '#2d3748',
          type: 'dashed'
        }
      }
    },
    series: [
      {
        name: '访问量',
        type: 'line',
        smooth: true,
        data: hourly.counts || [],
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(0, 150, 57, 0.3)' },
              { offset: 1, color: 'rgba(0, 150, 57, 0.1)' }
            ]
          }
        },
        itemStyle: {
          color: '#009639'
        }
      }
    ],
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    backgroundColor: 'transparent',
    textStyle: {
      color: '#e4e7ed'
    }
  }
})

// 状态码分布图配置
const statusChartOption = computed(() => {
  const statusDist = stats.value.status_distribution || {}
  const colors = {
    '2xx': '#009639',
    '3xx': '#00A86B',
    '4xx': '#E6A23C',
    '5xx': '#dc2626'
  }
  
  const data = Object.entries(statusDist)
    .map(([status, count]) => {
      let category = 'other'
      const code = parseInt(status)
      if (code >= 200 && code < 300) category = '2xx'
      else if (code >= 300 && code < 400) category = '3xx'
      else if (code >= 400 && code < 500) category = '4xx'
      else if (code >= 500) category = '5xx'
      
      return {
        value: count,
        name: `HTTP ${status}`,
        itemStyle: { color: colors[category] || 'var(--text-muted)' }
      }
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
  
  return {
    backgroundColor: 'transparent',
    textStyle: {
      color: '#e4e7ed'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
      backgroundColor: 'rgba(26, 35, 50, 0.95)',
      borderColor: '#2d3748',
      textStyle: {
        color: '#e4e7ed'
      }
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: 'transparent',
          borderWidth: 0
        },
        label: {
          show: true,
          formatter: '{b}\n{c}'
        },
        data: data
      }
    ]
  }
})

// 加载Nginx状态
const loadNginxStatus = async () => {
  try {
    const response = await configApi.getStatus()
    nginxStatus.value = response
  } catch (error) {
    ElMessage.error('获取状态失败: ' + (error.detail || error.message || '未知错误'))
  }
}

// 加载基础统计数据（优先加载，轻量级）
const loadStatisticsSummary = async () => {
  if (loadingSummary.value) return
  loadingSummary.value = true
  
  try {
    const response = await statisticsApi.getSummary(timeRange.value)
    if (response.success) {
      stats.value.summary = response.summary
      // 数据维度的时间信息
      statsStatus.value.lastAnalysisTime = response.last_analysis_time || response.end_time || null
      statsStatus.value.nextAnalysisTime = response.next_analysis_time || null

      // 后台任务维度的状态信息
      const job = response.analysis_job || {}
      statsStatus.value.isAnalyzing = !!job.is_running
      statsStatus.value.lastJobStartTime = job.last_start_time || null
      statsStatus.value.lastJobEndTime = job.last_end_time || null
      statsStatus.value.lastJobError = job.last_error || null
      statsStatus.value.lastJobSuccess = job.last_success
      statsStatus.value.lastJobTrigger = job.last_trigger || null
      statsStatus.value.lastJobDurationSeconds = job.last_duration_seconds ?? null
      statsStatus.value.runningDurationSeconds = job.running_duration_seconds ?? null

      // 统计分析状态：优先展示“任务状态”
      if (statsStatus.value.isAnalyzing) {
        statsStatus.value.status = 'analyzing'
      } else if (statsStatus.value.lastJobSuccess === false || statsStatus.value.lastJobError) {
        statsStatus.value.status = 'failed'
      } else if (statsStatus.value.lastJobEndTime) {
        statsStatus.value.status = 'ready'
      } else {
        statsStatus.value.status = 'not_ready'
      }
    } else {
      statsStatus.value.status = 'not_ready'
      statsStatus.value.lastAnalysisTime = null
      statsStatus.value.nextAnalysisTime = null
      statsStatus.value.isAnalyzing = false
      statsStatus.value.lastJobStartTime = null
      statsStatus.value.lastJobEndTime = null
      statsStatus.value.lastJobError = null
      statsStatus.value.lastJobSuccess = null
      statsStatus.value.lastJobTrigger = null
      statsStatus.value.lastJobDurationSeconds = null
      statsStatus.value.runningDurationSeconds = null
    }
  } catch (error) {
    console.error('获取基础统计数据失败:', error)
    statsStatus.value.status = 'not_ready'
    statsStatus.value.lastAnalysisTime = null
    statsStatus.value.nextAnalysisTime = null
    statsStatus.value.isAnalyzing = false
    statsStatus.value.lastJobStartTime = null
    statsStatus.value.lastJobEndTime = null
    statsStatus.value.lastJobError = null
    statsStatus.value.lastJobSuccess = null
    statsStatus.value.lastJobTrigger = null
    statsStatus.value.lastJobDurationSeconds = null
    statsStatus.value.runningDurationSeconds = null
  } finally {
    loadingSummary.value = false
  }
}

// 手动触发统计分析
const triggerAnalyzeNow = async () => {
  if (analyzingManual.value || statsStatus.value.status === 'analyzing') return
  analyzingManual.value = true
  statsStatus.value.status = 'analyzing'
  statsStatus.value.isAnalyzing = true

  try {
    const res = await statisticsApi.triggerAnalyze(timeRange.value)
    if (res.success) {
      ElMessage.success(res.message || '统计分析已在后台启动')
      // 稍等几秒再刷新一次基础统计，更新状态和时间
      setTimeout(() => {
        loadStatisticsSummary()
      }, 5000)
    } else {
      if (res.message) {
        ElMessage.warning(res.message)
      }
      // 如果后端提示已在分析中，则保持 analyzing 状态；否则回退为 not_ready
      if (!res.is_analyzing) {
        statsStatus.value.status = 'not_ready'
        statsStatus.value.isAnalyzing = false
      }
    }
  } catch (error) {
    console.error('手动触发统计分析失败:', error)
    ElMessage.error('手动触发统计分析失败: ' + (error.detail || error.message || '未知错误'))
    statsStatus.value.status = 'not_ready'
    statsStatus.value.isAnalyzing = false
  } finally {
    analyzingManual.value = false
  }
}

// 加载时间趋势数据
const loadStatisticsTrend = async () => {
  if (loadingTrend.value) return
  loadingTrend.value = true
  
  try {
    const response = await statisticsApi.getTrend(timeRange.value)
    if (response.success) {
      stats.value.hourly_trend = response.hourly_trend
    }
  } catch (error) {
    console.error('获取趋势数据失败:', error)
  } finally {
    loadingTrend.value = false
  }
}

// 加载Top IPs
const loadTopIPs = async () => {
  if (loadingTopIPs.value) return
  loadingTopIPs.value = true
  
  try {
    const response = await statisticsApi.getTopIPs(timeRange.value, 10)
    if (response.success) {
      stats.value.top_ips = response.top_ips
    }
  } catch (error) {
    console.error('获取Top IPs失败:', error)
  } finally {
    loadingTopIPs.value = false
  }
}

// 加载Top Paths
const loadTopPaths = async () => {
  if (loadingTopPaths.value) return
  loadingTopPaths.value = true
  
  try {
    const response = await statisticsApi.getTopPaths(timeRange.value, 10)
    if (response.success) {
      stats.value.top_paths = response.top_paths
    }
  } catch (error) {
    console.error('获取Top Paths失败:', error)
  } finally {
    loadingTopPaths.value = false
  }
}

// 加载状态码分布
const loadStatusDistribution = async () => {
  if (loadingStatusDist.value) return
  loadingStatusDist.value = true
  
  try {
    const response = await statisticsApi.getStatusDistribution(timeRange.value)
    if (response.success) {
      stats.value.status_distribution = response.status_distribution
    }
  } catch (error) {
    console.error('获取状态码分布失败:', error)
  } finally {
    loadingStatusDist.value = false
  }
}

// 加载攻击检测（延迟加载）
const loadAttacks = async () => {
  if (loadingAttacks.value) return
  loadingAttacks.value = true
  
  try {
    const response = await statisticsApi.getAttacks(timeRange.value, 50)
    if (response.success) {
      stats.value.attacks = response.attacks
    }
  } catch (error) {
    console.error('获取攻击检测失败:', error)
  } finally {
    loadingAttacks.value = false
  }
}

// 加载所有统计数据（按优先级分批加载）
const loadStatistics = async () => {
  // 第一批：基础统计（立即加载，最轻量）
  loadStatisticsSummary()
  
  // 第二批：图表数据（稍后加载）
  setTimeout(() => {
    loadStatisticsTrend()
    loadStatusDistribution()
  }, 100)
  
  // 第三批：Top数据（再稍后加载）
  setTimeout(() => {
    loadTopIPs()
    loadTopPaths()
  }, 300)
  
  // 第四批：攻击检测（最后加载，数据量大）
  setTimeout(() => {
    loadAttacks()
  }, 500)
}

// 加载系统资源
const loadSystemResources = async () => {
  try {
    const response = await systemApi.getResources()
    if (response.success) {
      systemResources.value = response
    } else {
      console.warn('获取系统资源失败:', response.error)
    }
  } catch (error) {
    console.error('获取系统资源失败:', error)
    // 不显示错误消息，因为系统资源可能不可用
  }
}

// 加载系统版本
const loadSystemVersion = async () => {
  try {
    const response = await systemApi.getVersion()
    if (response.success) {
      systemVersion.value = {
        version: response.version,
        build_time_formatted: response.build_time_formatted
      }
    }
  } catch (error) {
    console.error('获取系统版本失败:', error)
    // 不显示错误消息，版本信息不是关键功能
  }
}

// 刷新状态
const refreshStatus = () => {
  loadNginxStatus()
  loadStatistics()
  loadSystemResources()
  loadSystemVersion()
}

// 组件挂载
onMounted(() => {
  loadNginxStatus()
  loadStatistics()
  loadSystemResources()
  loadSystemVersion()
  
  // 每30秒自动刷新
  refreshTimer = setInterval(() => {
    loadNginxStatus()
    loadStatistics()
    loadSystemResources()
    // 版本信息不需要频繁刷新，只在初始加载时获取
  }, 30000)
})

// 组件卸载
onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
  background-color: var(--bg-primary);
  min-height: 100%;
}

.mb-20 {
  margin-bottom: 20px;
}

.mt-20 {
  margin-top: 20px;
}

.mr-5 {
  margin-right: 5px;
}

.ml-10 {
  margin-left: 10px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--text-primary);
}

.card-header span {
  color: var(--text-primary);
  font-weight: 500;
}

.stat-card {
  margin-bottom: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.stat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.resource-card {
  display: flex;
  flex-direction: column;
  min-height: 140px;
}

.stat-content {
  display: flex;
  align-items: flex-start;
  padding: 8px 0;
  flex: 1;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-white);
  margin-right: 15px;
  flex-shrink: 0;
}

.stat-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.stat-value {
  font-size: 26px;
  font-weight: bold;
  color: var(--text-primary);
  line-height: 1.2;
  margin-bottom: 6px;
  word-break: break-all;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.stat-extra {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.2;
  word-break: break-all;
}

.stat-progress {
  margin-top: 12px;
}

/* 统一资源卡片样式 */
.resource-card .stat-content {
  min-height: 80px;
}

.chart {
  height: 300px;
  width: 100%;
}

:deep(.el-card__header) {
  font-weight: 500;
  background-color: var(--bg-secondary);
  border-bottom-color: var(--border-color);
  color: var(--text-primary);
}

:deep(.el-descriptions__label) {
  font-weight: 500;
}

/* Nginx 运行状态描述列表样式 - 无边框 */
.nginx-status-descriptions {
  background-color: transparent;
}

.nginx-status-descriptions :deep(.el-descriptions__table) {
  border: none;
  background-color: transparent;
}

.nginx-status-descriptions :deep(.el-descriptions__table td),
.nginx-status-descriptions :deep(.el-descriptions__table th) {
  border: none;
  background-color: transparent;
  padding: 12px 16px;
}

.nginx-status-descriptions :deep(.el-descriptions__label) {
  background-color: transparent !important;
  color: var(--text-secondary);
  font-weight: 500;
  padding-right: 20px;
}

.nginx-status-descriptions :deep(.el-descriptions__content) {
  background-color: transparent !important;
  color: var(--text-primary);
}

.analysis-status-tag {
  min-width: 64px;
  display: inline-flex;
  justify-content: center;
}

.analysis-duration-text {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.status-value {
  color: var(--text-primary);
  font-size: 14px;
}

.stat-icon :deep(.el-icon) {
  color: #ffffff;
}
</style>
