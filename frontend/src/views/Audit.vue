<template>
  <div class="audit-page">
    <el-card>
      <template #header>
        <span>操作日志</span>
      </template>
      <el-table :data="auditLogs" style="width: 100%">
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column prop="action" label="操作" width="150" />
        <el-table-column prop="target" label="目标" />
        <el-table-column prop="ip_address" label="IP地址" width="150" />
        <el-table-column prop="timestamp" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { auditApi } from '../api/audit'
import { ElMessage } from 'element-plus'

const auditLogs = ref([])

const loadLogs = async () => {
  try {
    const response = await auditApi.getLogs({ page: 1, page_size: 50 })
    auditLogs.value = response.logs || []
  } catch (error) {
    ElMessage.error('加载操作日志失败')
  }
}

onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.audit-page {
  padding: 20px;
}
</style>

