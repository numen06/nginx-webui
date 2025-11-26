<template>
  <div class="logs-page">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="访问日志" name="access">
        <el-card>
          <div class="log-content">
            <pre v-for="(log, index) in accessLogs" :key="index">{{ log }}</pre>
          </div>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="错误日志" name="error">
        <el-card>
          <div class="log-content">
            <pre v-for="(log, index) in errorLogs" :key="index">{{ log }}</pre>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { logsApi } from '../api/logs'
import { ElMessage } from 'element-plus'

const activeTab = ref('access')
const accessLogs = ref([])
const errorLogs = ref([])

const loadLogs = async () => {
  try {
    if (activeTab.value === 'access') {
      const response = await logsApi.getAccessLogs(1, 100)
      accessLogs.value = response.logs || []
    } else {
      const response = await logsApi.getErrorLogs(1, 100)
      errorLogs.value = response.logs || []
    }
  } catch (error) {
    ElMessage.error('加载日志失败')
  }
}

watch(activeTab, () => {
  loadLogs()
})

onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.logs-page {
  padding: 20px;
}

.log-content {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 20px;
  border-radius: 4px;
  max-height: 600px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.log-content pre {
  margin: 2px 0;
  line-height: 1.5;
}
</style>

