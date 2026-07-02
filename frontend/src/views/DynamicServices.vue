<template>
  <div class="dynamic-services-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>动态服务</span>
          <div class="header-actions">
            <el-button @click="loadAll" :loading="loading">
              <el-icon><RefreshRight /></el-icon>
              <span class="btn-label">刷新</span>
            </el-button>
            <el-button @click="openPreview">
              <el-icon><View /></el-icon>
              <span class="btn-label">配置预览</span>
            </el-button>
            <el-button type="primary" @click="openCreateDialog">
              <el-icon><Plus /></el-icon>
              <span class="btn-label">新增服务</span>
            </el-button>
          </div>
        </div>
      </template>

      <el-alert class="auth-alert" type="info" show-icon :closable="false">
        <template #title>注册鉴权</template>
        <div class="auth-status">
          <el-tag type="success" size="small">
            登录 Token 已启用
          </el-tag>
          <el-tag
            :type="authStatus.explicit_ip_whitelist_enabled || authStatus.auto_same_subnet_enabled ? 'success' : 'warning'"
            size="small"
          >
            {{ whitelistLabel }}
          </el-tag>
          <el-text v-if="authNetworks.length" class="auth-networks" size="small">
            {{ authNetworks.join(', ') }}
          </el-text>
        </div>
      </el-alert>

      <el-table
        v-loading="loading"
        :data="services"
        style="width: 100%"
        border
        size="small"
        row-key="id"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="instances-panel">
              <el-table :data="row.instances" size="small" border>
                <el-table-column prop="instance_id" label="实例 ID" min-width="180" />
                <el-table-column prop="target_url" label="目标地址" min-width="220" show-overflow-tooltip />
                <el-table-column label="状态" width="110">
                  <template #default="{ row: instance }">
                    <el-tag :type="instance.status === 'active' && !instance.expired ? 'success' : 'info'" size="small">
                      {{ instance.expired ? 'expired' : instance.status }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="ttl_seconds" label="TTL" width="90" />
                <el-table-column label="最近心跳" width="180">
                  <template #default="{ row: instance }">
                    {{ formatDateTime(instance.last_heartbeat_at) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="120" fixed="right">
                  <template #default="{ row: instance }">
                    <el-button
                      type="warning"
                      link
                      :disabled="instance.status !== 'active'"
                      @click="offlineInstance(row, instance)"
                    >
                      下线
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="row.instances.length === 0" description="暂无实例" :image-size="60" />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="service_name" label="服务名" min-width="170" />
        <el-table-column prop="route_prefix" label="路径前缀" min-width="140">
          <template #default="{ row }">
            <el-link type="primary" @click="copyRoute(row.route_prefix)">{{ row.route_prefix }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="100">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              :loading="row._toggling"
              @change="(value) => toggleService(row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column label="实例" width="120">
          <template #default="{ row }">
            <el-tag type="success" size="small">{{ row.active_instance_count }}</el-tag>
            <span class="instance-total">/ {{ row.instance_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="deleteService(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="formVisible"
      :title="editingService ? '编辑服务' : '新增服务'"
      width="520px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="服务名" prop="service_name">
          <el-input v-model="form.service_name" :disabled="!!editingService" placeholder="order-service" />
        </el-form-item>
        <el-form-item label="路径前缀" prop="route_prefix">
          <el-input v-model="form.route_prefix" placeholder="/orders" />
        </el-form-item>
        <el-form-item label="启用" prop="enabled">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="动态服务配置预览" width="80%">
      <pre class="preview-content">{{ previewContent }}</pre>
      <template #footer>
        <el-button type="primary" @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshRight, View } from '@element-plus/icons-vue'
import { dynamicServicesApi } from '../api/dynamicServices'
import { formatDateTime } from '../utils/date'

const loading = ref(false)
const saving = ref(false)
const services = ref([])
const authStatus = ref({})
const formVisible = ref(false)
const previewVisible = ref(false)
const previewContent = ref('')
const editingService = ref(null)
const formRef = ref()
const form = ref({
  service_name: '',
  route_prefix: '',
  description: '',
  enabled: true
})

const whitelistLabel = computed(() => {
  if (authStatus.value.explicit_ip_whitelist_enabled) return '显式白名单已启用'
  if (authStatus.value.auto_same_subnet_enabled) return '自动同网段白名单已启用'
  return '白名单未启用'
})

const authNetworks = computed(() => {
  if (authStatus.value.explicit_ip_whitelist_enabled) return authStatus.value.ip_whitelist || []
  return authStatus.value.auto_same_subnet_networks || []
})

const validateRoutePrefix = (_rule, value, callback) => {
  if (!value || !value.trim()) {
    callback(new Error('请输入路径前缀'))
    return
  }
  const normalized = value.trim().startsWith('/') ? value.trim() : `/${value.trim()}`
  if (normalized === '/') {
    callback(new Error('不能使用根路径 /'))
    return
  }
  if (/^\/(api|assets|login|dashboard|config|logs|files|static-package|certificates|audit|nginx|git-sync|profile)(\/|$)/.test(normalized)) {
    callback(new Error('路径前缀与系统保留路径冲突'))
    return
  }
  callback()
}

const rules = {
  service_name: [
    { required: true, message: '请输入服务名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/, message: '仅允许字母、数字、点、下划线和中划线', trigger: 'blur' }
  ],
  route_prefix: [
    { required: true, message: '请输入路径前缀', trigger: 'blur' },
    { validator: validateRoutePrefix, trigger: 'blur' }
  ]
}

const normalizeError = (error) => {
  if (!error) return '操作失败'
  if (typeof error.detail === 'string') return error.detail
  if (error.detail?.message) return error.detail.message
  if (error.message) return error.message
  return '操作失败'
}

const loadAll = async () => {
  loading.value = true
  try {
    const [listRes, authRes] = await Promise.all([
      dynamicServicesApi.list(),
      dynamicServicesApi.getAuthStatus()
    ])
    services.value = listRes.services || []
    authStatus.value = authRes || {}
  } catch (error) {
    ElMessage.error(normalizeError(error))
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  editingService.value = null
  form.value = {
    service_name: '',
    route_prefix: '',
    description: '',
    enabled: true
  }
  formVisible.value = true
}

const openEditDialog = (service) => {
  editingService.value = service
  form.value = {
    service_name: service.service_name,
    route_prefix: service.route_prefix,
    description: service.description || '',
    enabled: service.enabled
  }
  formVisible.value = true
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      const payload = {
        service_name: form.value.service_name.trim(),
        route_prefix: form.value.route_prefix.trim(),
        description: form.value.description,
        enabled: form.value.enabled
      }
      if (editingService.value) {
        await dynamicServicesApi.update(editingService.value.id, {
          route_prefix: payload.route_prefix,
          description: payload.description,
          enabled: payload.enabled
        })
      } else {
        await dynamicServicesApi.create(payload)
      }
      ElMessage.success('保存成功')
      formVisible.value = false
      await loadAll()
    } catch (error) {
      ElMessage.error(normalizeError(error))
    } finally {
      saving.value = false
    }
  })
}

const toggleService = async (service, enabled) => {
  service._toggling = true
  try {
    await dynamicServicesApi.setEnabled(service.id, enabled)
    ElMessage.success(enabled ? '服务已启用' : '服务已停用')
    await loadAll()
  } catch (error) {
    service.enabled = !enabled
    ElMessage.error(normalizeError(error))
  } finally {
    service._toggling = false
  }
}

const deleteService = async (service) => {
  try {
    await ElMessageBox.confirm(
      `确认删除动态服务 ${service.service_name}？删除后会移除对应转发配置。`,
      '删除服务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await dynamicServicesApi.delete(service.id)
    ElMessage.success('服务已删除')
    await loadAll()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(normalizeError(error))
  }
}

const offlineInstance = async (service, instance) => {
  try {
    await ElMessageBox.confirm(
      `确认下线实例 ${instance.instance_id}？`,
      '下线实例',
      { type: 'warning', confirmButtonText: '下线', cancelButtonText: '取消' }
    )
    await dynamicServicesApi.offlineInstance(service.id, instance.instance_id)
    ElMessage.success('实例已下线')
    await loadAll()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(normalizeError(error))
  }
}

const openPreview = async () => {
  try {
    const res = await dynamicServicesApi.getGeneratedConfig()
    previewContent.value = res.content || ''
    previewVisible.value = true
  } catch (error) {
    ElMessage.error(normalizeError(error))
  }
}

const copyRoute = async (routePrefix) => {
  try {
    await navigator.clipboard.writeText(routePrefix)
    ElMessage.success('路径已复制')
  } catch (error) {
    ElMessage.info(routePrefix)
  }
}

onMounted(loadAll)
</script>

<style scoped>
.dynamic-services-page {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.auth-alert {
  margin-bottom: 16px;
}

.auth-status {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.auth-networks {
  max-width: 100%;
  overflow-wrap: anywhere;
}

.instances-panel {
  padding: 12px 24px;
  background: var(--bg-secondary);
}

.instance-total {
  margin-left: 6px;
  color: var(--text-secondary);
}

.preview-content {
  max-height: 60vh;
  overflow: auto;
  padding: 16px;
  border-radius: 6px;
  background: #1f2933;
  color: #e5e7eb;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

@media (max-width: 768px) {
  .dynamic-services-page {
    padding: 12px;
  }

  .card-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
  }
}
</style>
