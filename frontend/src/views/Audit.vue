<template>
  <div class="audit-page">
    <el-card>
      <template #header>
        <span>操作日志</span>
      </template>

      <div class="toolbar">
        <el-form :inline="true" :model="filters" class="filter-form" label-width="80px">
          <el-form-item label="用户">
            <el-input
              v-model="filters.username"
              placeholder="输入用户名"
              clearable
              @keyup.enter.native="handleSearch"
            />
          </el-form-item>
          <el-form-item label="操作">
            <el-input
              v-model="filters.action"
              placeholder="输入操作类型"
              clearable
              @keyup.enter.native="handleSearch"
            />
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="filters.dateRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
              clearable
            />
          </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>
            <span class="btn-label">查询</span>
          </el-button>
          <el-button @click="handleReset">
            <el-icon><RefreshRight /></el-icon>
            <span class="btn-label">重置</span>
          </el-button>
        </el-form-item>
        </el-form>
        <div class="action-buttons">
          <el-button type="danger" plain @click="openCleanupDialog">清理日志</el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="auditLogs"
        style="width: 100%"
        size="small"
        border
      >
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column prop="action" label="操作" width="150" />
        <el-table-column prop="target" label="目标" min-width="200" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP地址" width="150" />
        <el-table-column prop="timestamp" label="时间" width="200">
          <template #default="scope">
            {{ formatDateTime(scope.row.timestamp) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          :current-page="pagination.page"
          :page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pagination.total"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="cleanupDialogVisible"
      title="清理操作日志"
      width="420px"
      destroy-on-close
    >
      <el-form
        ref="cleanupFormRef"
        :model="cleanupForm"
        :rules="cleanupRules"
        label-width="90px"
      >
        <el-form-item label="保留天数" prop="retain_days">
          <el-input-number
            v-model="cleanupForm.retain_days"
            :min="1"
            :max="3650"
            :step="1"
          />
        </el-form-item>
        <p class="cleanup-tip">将删除早于指定天数的日志，默认保留 90 天。</p>
      </el-form>
      <template #footer>
        <el-button @click="cleanupDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="cleanupLoading" @click="submitCleanup">
          确认清理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { auditApi } from '../api/audit'
import { ElMessage } from 'element-plus'
import { Search, RefreshRight } from '@element-plus/icons-vue'
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
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

const buildParams = () => {
  const params = {
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

