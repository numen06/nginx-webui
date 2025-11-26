<template>
  <div class="certificates-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>证书管理</span>
          <div>
            <el-button type="primary" @click="handleRequest">申请证书</el-button>
            <el-button @click="handleUpload">上传证书</el-button>
          </div>
        </div>
      </template>
      <el-table :data="certificateList" style="width: 100%">
        <el-table-column prop="domain" label="域名" />
        <el-table-column prop="issuer" label="颁发者" />
        <el-table-column prop="valid_to" label="过期时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-button size="small" @click="handleRenew(scope.row)">续期</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { certificatesApi } from '../api/certificates'
import { ElMessage, ElMessageBox } from 'element-plus'

const certificateList = ref([])

const loadCertificates = async () => {
  try {
    const response = await certificatesApi.getCertificates()
    certificateList.value = response.certificates || []
  } catch (error) {
    ElMessage.error('加载证书列表失败')
  }
}

const handleRequest = () => {
  ElMessage.info('申请证书功能待实现')
}

const handleUpload = () => {
  ElMessage.info('上传证书功能待实现')
}

const handleRenew = async (cert) => {
  try {
    await certificatesApi.renewCertificate(cert.id)
    ElMessage.success('证书续期成功')
    loadCertificates()
  } catch (error) {
    ElMessage.error('证书续期失败')
  }
}

const handleDelete = async (cert) => {
  try {
    await ElMessageBox.confirm('确定要删除证书吗？', '提示', { type: 'warning' })
    await certificatesApi.deleteCertificate(cert.id)
    ElMessage.success('删除成功')
    loadCertificates()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  loadCertificates()
})
</script>

<style scoped>
.certificates-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>

