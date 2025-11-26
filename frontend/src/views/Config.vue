<template>
  <div class="config-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Nginx 配置</span>
          <div>
            <el-button @click="handleTest">测试配置</el-button>
            <el-button type="success" @click="handleSave">保存</el-button>
            <el-button type="warning" @click="handleReload">重载配置</el-button>
          </div>
        </div>
      </template>
      <MonacoEditor
        v-model="configContent"
        language="nginx"
        height="600px"
        @change="handleContentChange"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { configApi } from '../api/config'
import MonacoEditor from '../components/MonacoEditor.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const configContent = ref('')
const isModified = ref(false)

onMounted(async () => {
  await loadConfig()
})

const loadConfig = async () => {
  try {
    const response = await configApi.getConfig()
    configContent.value = response.content
    isModified.value = false
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}

const handleContentChange = () => {
  isModified.value = true
}

const handleTest = async () => {
  try {
    const response = await configApi.testConfig()
    if (response.success) {
      ElMessage.success('配置测试成功')
    } else {
      ElMessage.error('配置测试失败: ' + response.message)
    }
  } catch (error) {
    ElMessage.error('测试配置失败')
  }
}

const handleSave = async () => {
  try {
    await configApi.updateConfig(configContent.value)
    ElMessage.success('配置已保存')
    isModified.value = false
  } catch (error) {
    ElMessage.error('保存配置失败')
  }
}

const handleReload = async () => {
  try {
    await ElMessageBox.confirm('确定要重载配置吗？', '提示', {
      type: 'warning'
    })
    
    const response = await configApi.reloadConfig()
    if (response.success) {
      ElMessage.success('配置重载成功')
    } else {
      ElMessage.error('配置重载失败: ' + response.message)
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重载配置失败')
    }
  }
}
</script>

<style scoped>
.config-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>

