<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>系统概览</span>
          </template>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="Nginx 状态">
              <el-tag :type="nginxStatus.running ? 'success' : 'danger'">
                {{ nginxStatus.running ? '运行中' : '已停止' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ nginxStatus.version || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="进程ID">
              {{ nginxStatus.pid || '无' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { configApi } from '../api/config'
import { ElMessage } from 'element-plus'

const nginxStatus = ref({
  running: false,
  version: null,
  pid: null
})

onMounted(async () => {
  try {
    const response = await configApi.getStatus()
    nginxStatus.value = response
  } catch (error) {
    ElMessage.error('获取状态失败')
  }
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}
</style>

