<template>
  <div class="dashboard">
    <!-- Nginx状态卡片 -->
    <el-row :gutter="20" class="mb-20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Nginx 运行状态</span>
              <el-button text @click="refreshStatus">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>
          <el-descriptions :column="4" border>
            <el-descriptions-item label="运行状态">
              <el-tag :type="nginxStatus.running ? 'success' : 'danger'" size="large">
                {{ nginxStatus.running ? '运行中' : '已停止' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ nginxStatus.version || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="进程ID">
              {{ nginxStatus.pid || '无' }}
            </el-descriptions-item>
            <el-descriptions-item label="运行时间">
              {{ nginxStatus.uptime || '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <!-- 统计指标卡片 -->
    <el-row :gutter="20" class="mb-20">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: var(--nginx-green);">
              <el-icon size="30"><DataLine /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.total_requests || 0) }}</div>
              <div class="stat-label">总请求数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: var(--nginx-green-light);">
              <el-icon size="30"><SuccessFilled /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.success_requests || 0) }}</div>
              <div class="stat-label">成功请求</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #E6A23C;">
              <el-icon size="30"><WarningFilled /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.error_requests || 0) }}</div>
              <div class="stat-label">错误请求</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #dc2626;">
              <el-icon size="30"><Lock /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatNumber(stats.summary?.attack_count || 0) }}</div>
              <div class="stat-label">攻击检测</div>
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
import { ElMessage } from 'element-plus'

const nginxStatus = ref({
  running: false,
  version: null,
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
          borderColor: '#fff',
          borderWidth: 2
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

// 刷新状态
const refreshStatus = () => {
  loadNginxStatus()
  loadStatistics()
}

// 组件挂载
onMounted(() => {
  loadNginxStatus()
  loadStatistics()
  
  // 每30秒自动刷新
  refreshTimer = setInterval(() => {
    loadNginxStatus()
    loadStatistics()
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
}

.stat-card {
  margin-bottom: 20px;
}

.stat-content {
  display: flex;
  align-items: center;
  padding: 10px 0;
}

.stat-icon {
  width: 60px;
  height: 60px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  margin-right: 15px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: var(--text-primary);
  line-height: 1;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.chart {
  height: 300px;
  width: 100%;
}

:deep(.el-card__header) {
  font-weight: 500;
}

:deep(.el-descriptions__label) {
  font-weight: 500;
}
</style>
