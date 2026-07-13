<template>
  <div class="audit-page page-shell">
    <ui-card>
      <template #header>
        <span>操作日志</span>
      </template>

      <div class="toolbar">
        <ui-form :inline="true" :model="filters" class="filter-form" label-width="80px">
          <ui-form-item label="用户">
            <ui-input
              v-model="filters.username"
              placeholder="输入用户名"
              clearable
              @keyup.enter.native="handleSearch"
            />
          </ui-form-item>
          <ui-form-item label="操作">
            <ui-input
              v-model="filters.action"
              placeholder="输入操作类型"
              clearable
              @keyup.enter.native="handleSearch"
            />
          </ui-form-item>
          <ui-form-item label="时间范围">
            <ui-date-picker
              v-model="filters.dateRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              clearable
            />
          </ui-form-item>
        <ui-form-item>
          <ui-button type="primary" @click="handleSearch">
            <ui-icon><Search /></ui-icon>
            <span class="btn-label">查询</span>
          </ui-button>
          <ui-button @click="handleReset">
            <ui-icon><RefreshRight /></ui-icon>
            <span class="btn-label">重置</span>
          </ui-button>
        </ui-form-item>
        </ui-form>
        <div class="action-buttons">
          <ui-button type="danger" plain @click="openCleanupDialog">清理日志</ui-button>
        </div>
      </div>

      <ui-table
        v-loading="loading"
        :data="auditLogs"
        style="width: 100%"
        size="small"
        border
      >
        <ui-table-column prop="username" label="用户" width="120" />
        <ui-table-column prop="action" label="操作" width="150" />
        <ui-table-column prop="target" label="目标" min-width="200" show-overflow-tooltip />
        <ui-table-column prop="ip_address" label="IP地址" width="150" />
        <ui-table-column prop="timestamp" label="时间" width="200">
          <template #default="scope">
            {{ formatDateTime(scope.row.timestamp) }}
          </template>
        </ui-table-column>
      </ui-table>

      <div class="pagination">
        <ui-pagination
          :current-page="pagination.page"
          :page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pagination.total"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </ui-card>

    <ui-dialog
      v-model="cleanupDialogVisible"
      title="清理操作日志"
      width="420px"
      destroy-on-close
    >
      <ui-form
        ref="cleanupFormRef"
        :model="cleanupForm"
        :rules="cleanupRules"
        label-width="90px"
      >
        <ui-form-item label="保留天数" prop="retain_days">
          <ui-input-number
            v-model="cleanupForm.retain_days"
            :min="1"
            :max="3650"
            :step="1"
          />
        </ui-form-item>
        <p class="cleanup-tip">将删除早于指定天数的日志，默认保留 90 天。</p>
      </ui-form>
      <template #footer>
        <ui-button @click="cleanupDialogVisible = false">取消</ui-button>
        <ui-button type="primary" :loading="cleanupLoading" @click="submitCleanup">
          确认清理
        </ui-button>
      </template>
    </ui-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { auditApi } from '../api/audit'
import { ElMessage } from '@/lib/feedback'
import { Search, RefreshRight } from '@/components/icons'
import { formatDateTime } from '../utils/date'

const loading = ref(false)
const auditLogs = ref([])
const filters = ref({
  username: '',
  action: '',
  dateRange: []
})
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})
const cleanupDialogVisible = ref(false)
const cleanupFormRef = ref()
const cleanupLoading = ref(false)
const cleanupForm = ref({
  retain_days: 90
})
const cleanupRules = {
  retain_days: [
    { required: true, message: '请输入保留天数', trigger: 'blur' },
    { type: 'number', min: 1, max: 3650, message: '范围 1-3650 天', trigger: 'blur' }
  ]
}

const normalizeISO = (value) => {
  if (!value) {
    return null
  }
  // 如果已经是标准格式（YYYY-MM-DD HH:mm:ss），直接返回
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    return value
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  // 格式化为本地时间格式（不带时区标识）
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

const buildParams = () => {
  const params: Record<string, string | number> = {
    page: pagination.value.page,
    page_size: pagination.value.pageSize
  }

  if (filters.value.username.trim()) {
    params.username = filters.value.username.trim()
  }

  if (filters.value.action.trim()) {
    params.action = filters.value.action.trim()
  }

  if (filters.value.dateRange.length === 2) {
    const [start, end] = filters.value.dateRange
    const startISO = normalizeISO(start)
    const endISO = normalizeISO(end)
    if (startISO) {
      params.start_time = startISO
    }
    if (endISO) {
      params.end_time = endISO
    }
  }

  return params
}

const loadLogs = async () => {
  loading.value = true
  try {
    const response = await auditApi.getLogs(buildParams())
    auditLogs.value = response.logs || []
    pagination.value.total = response.pagination?.total || 0
  } catch (error) {
    ElMessage.error('加载操作日志失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.page = 1
  loadLogs()
}

const handleReset = () => {
  filters.value = {
    username: '',
    action: '',
    dateRange: []
  }
  pagination.value.page = 1
  loadLogs()
}

const handlePageChange = (page) => {
  pagination.value.page = page
  loadLogs()
}

const handleSizeChange = (size) => {
  pagination.value.pageSize = size
  pagination.value.page = 1
  loadLogs()
}

const openCleanupDialog = () => {
  cleanupForm.value.retain_days = 90
  cleanupDialogVisible.value = true
}

const submitCleanup = () => {
  if (!cleanupFormRef.value) {
    return
  }
  cleanupFormRef.value.validate(async (valid) => {
    if (!valid) {
      return
    }
    cleanupLoading.value = true
    try {
      const response = await auditApi.cleanupLogs({
        retain_days: cleanupForm.value.retain_days
      })
      ElMessage.success(response?.message || '日志清理完成')
      cleanupDialogVisible.value = false
      loadLogs()
    } catch (error) {
      ElMessage.error(error.detail || '日志清理失败')
    } finally {
      cleanupLoading.value = false
    }
  })
}

onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.audit-page {
  padding: 20px;
}

.toolbar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-start;
  margin-bottom: 16px;
}

.filter-form {
  flex: 1;
}

.action-buttons {
  display: flex;
  align-items: center;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.cleanup-tip {
  margin: 0;
  font-size: 13px;
  color: #909399;
}
</style>
