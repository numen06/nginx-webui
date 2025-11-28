<template>
  <div class="dashboard">
    <!-- Nginx状态卡片 -->
    <el-row :gutter="20" class="mb-20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Nginx 运行状态</span>
              <el-button type="info" text @click="refreshStatus">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
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

const timeRange = ref(24)
const loading = ref(false)
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

// 加载统计数据
const loadStatistics = async () => {
  if (loading.value) return
  loading.value = true
  
  try {
    const response = await statisticsApi.getOverview(timeRange.value)
    if (response.success) {
      stats.value = response
    } else {
      ElMessage.warning(response.error || '获取统计数据失败')
    }
  } catch (error) {
    ElMessage.error('获取统计数据失败: ' + (error.detail || error.message || '未知错误'))
  } finally {
    loading.value = false
  }
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

// 刷新状态
const refreshStatus = () => {
  loadNginxStatus()
  loadStatistics()
  loadSystemResources()
}

// 组件挂载
onMounted(() => {
  loadNginxStatus()
  loadStatistics()
  loadSystemResources()
  
  // 每30秒自动刷新
  refreshTimer = setInterval(() => {
    loadNginxStatus()
    loadStatistics()
    loadSystemResources()
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

.status-value {
  color: var(--text-primary);
  font-size: 14px;
}

.stat-icon :deep(.el-icon) {
  color: #ffffff;
}
</style>
