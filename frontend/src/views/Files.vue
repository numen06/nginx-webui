<template>
  <div class="files-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>文件管理</span>
          <div>
            <el-button @click="handleUpload">上传文件</el-button>
            <el-button @click="handleCreateDir">新建文件夹</el-button>
            <el-button @click="handleRefresh">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table :data="fileList" style="width: 100%">
        <el-table-column prop="name" label="文件名" />
        <el-table-column prop="size" label="大小" width="120" />
        <el-table-column prop="modified_time" label="修改时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-button size="small" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { filesApi } from '../api/files'
import { ElMessage, ElMessageBox } from 'element-plus'

const fileList = ref([])

const loadFiles = async () => {
  try {
    const response = await filesApi.listFiles()
    fileList.value = response.files || []
  } catch (error) {
    ElMessage.error('加载文件列表失败')
  }
}

const handleUpload = () => {
  ElMessage.info('上传功能待实现')
}

const handleCreateDir = () => {
  ElMessage.info('创建文件夹功能待实现')
}

const handleRefresh = () => {
  loadFiles()
}

const handleEdit = (file) => {
  ElMessage.info('编辑功能待实现')
}

const handleDelete = async (file) => {
  try {
    await ElMessageBox.confirm('确定要删除吗？', '提示', { type: 'warning' })
    await filesApi.deleteFile(file.path)
    ElMessage.success('删除成功')
    loadFiles()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  loadFiles()
})
</script>

<style scoped>
.files-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>

