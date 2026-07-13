<template>
  <div class="dynamic-services-page page-shell">
    <ui-card>
      <template #header>
        <div class="card-header">
          <span>动态服务</span>
          <div class="header-actions">
            <ui-button @click="loadAll" :loading="loading">
              <ui-icon><RefreshRight /></ui-icon>
              <span class="btn-label">刷新</span>
            </ui-button>
            <ui-button @click="openPreview">
              <ui-icon><View /></ui-icon>
              <span class="btn-label">配置预览</span>
            </ui-button>
            <ui-button @click="openSettingsDialog">
              <ui-icon><Setting /></ui-icon>
              <span class="btn-label">注册设置</span>
            </ui-button>
            <ui-button type="primary" @click="openCreateDialog">
              <ui-icon><Plus /></ui-icon>
              <span class="btn-label">新增服务</span>
            </ui-button>
          </div>
        </div>
      </template>

      <ui-alert class="auth-alert" type="info" show-icon :closable="false">
        <template #title>注册鉴权</template>
        <div class="auth-status">
          <ui-tag type="success" size="small">
            登录 Token / Basic 认证已启用
          </ui-tag>
          <ui-tag
            :type="authStatus.explicit_ip_whitelist_enabled || authStatus.auto_same_subnet_enabled ? 'success' : 'warning'"
            size="small"
          >
            {{ whitelistLabel }}
          </ui-tag>
          <ui-text v-if="authNetworks.length" class="auth-networks" size="small">
            {{ authNetworks.join(', ') }}
          </ui-text>
        </div>
      </ui-alert>

      <ui-table
        v-loading="loading"
        :data="services"
        style="width: 100%"
        border
        size="small"
        row-key="id"
      >
        <ui-table-column type="expand">
          <template #default="{ row }">
            <div class="instances-panel">
              <ui-table :data="row.instances" size="small" border>
                <ui-table-column prop="instance_id" label="实例 ID" min-width="180" />
                <ui-table-column prop="target_url" label="目标地址" min-width="220" show-overflow-tooltip />
                <ui-table-column label="状态" width="110">
                  <template #default="{ row: instance }">
                    <ui-tag :type="instance.status === 'active' && !instance.expired ? 'success' : 'info'" size="small">
                      {{ instance.expired ? 'expired' : instance.status }}
                    </ui-tag>
                  </template>
                </ui-table-column>
                <ui-table-column prop="ttl_seconds" label="TTL" width="90" />
                <ui-table-column label="最近心跳" width="180">
                  <template #default="{ row: instance }">
                    {{ formatDateTime(instance.last_heartbeat_at) }}
                  </template>
                </ui-table-column>
                <ui-table-column label="操作" width="120" fixed="right">
                  <template #default="{ row: instance }">
                    <ui-button
                      type="warning"
                      link
                      :disabled="instance.status !== 'active'"
                      @click="offlineInstance(row, instance)"
                    >
                      下线
                    </ui-button>
                  </template>
                </ui-table-column>
              </ui-table>
              <ui-empty v-if="row.instances.length === 0" description="暂无实例" :image-size="60" />
            </div>
          </template>
        </ui-table-column>
        <ui-table-column prop="service_name" label="服务名" min-width="170" />
        <ui-table-column label="假域名" min-width="180">
          <template #default="{ row }">
            <ui-link
              v-if="row.virtual_hosts?.length"
              type="primary"
              @click="copyHost(row.virtual_hosts[0])"
            >
              {{ row.virtual_hosts[0] }}
            </ui-link>
            <span v-else>-</span>
          </template>
        </ui-table-column>
        <ui-table-column prop="route_prefix" label="路径前缀" min-width="140">
          <template #default="{ row }">
            <ui-link type="primary" @click="copyRoute(row.route_prefix)">{{ row.route_prefix }}</ui-link>
          </template>
        </ui-table-column>
        <ui-table-column label="启用" width="100">
          <template #default="{ row }">
            <ui-switch
              v-model="row.enabled"
              :loading="row._toggling"
              @change="(value) => toggleService(row, value)"
            />
          </template>
        </ui-table-column>
        <ui-table-column label="实例" width="120">
          <template #default="{ row }">
            <ui-tag type="success" size="small">{{ row.active_instance_count }}</ui-tag>
            <span class="instance-total">/ {{ row.instance_count }}</span>
          </template>
        </ui-table-column>
        <ui-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <ui-table-column label="更新时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </ui-table-column>
        <ui-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <div class="button-group">
              <ui-button link type="primary" @click="openEditDialog(row)">编辑</ui-button>
              <ui-button link type="danger" @click="deleteService(row)">删除</ui-button>
            </div>
          </template>
        </ui-table-column>
      </ui-table>
    </ui-card>

    <ui-dialog
      v-model="formVisible"
      :title="editingService ? '编辑服务' : '新增服务'"
      width="520px"
      destroy-on-close
    >
      <ui-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <ui-form-item label="服务名" prop="service_name">
          <ui-input v-model="form.service_name" :disabled="!!editingService" placeholder="order-service" />
        </ui-form-item>
        <ui-form-item label="路径前缀" prop="route_prefix">
          <ui-input v-model="form.route_prefix" placeholder="/orders" />
        </ui-form-item>
        <ui-form-item label="启用" prop="enabled">
          <ui-switch v-model="form.enabled" />
        </ui-form-item>
        <ui-form-item label="描述">
          <ui-input v-model="form.description" type="textarea" :rows="3" placeholder="可选" />
        </ui-form-item>
      </ui-form>
      <template #footer>
        <ui-button @click="formVisible = false">取消</ui-button>
        <ui-button type="primary" :loading="saving" @click="submitForm">保存</ui-button>
      </template>
    </ui-dialog>

    <ui-dialog v-model="previewVisible" title="动态服务配置预览" width="80%">
      <pre class="preview-content">{{ previewContent }}</pre>
      <template #footer>
        <ui-button type="primary" @click="previewVisible = false">关闭</ui-button>
      </template>
    </ui-dialog>

    <ui-dialog v-model="settingsVisible" title="动态注册设置" width="620px" destroy-on-close>
      <ui-form :model="settingsForm" label-width="150px">
        <ui-form-item label="IP 白名单">
          <ui-input
            v-model="settingsForm.ip_whitelist"
            type="textarea"
            :rows="3"
            placeholder="192.168.1.0/24, 10.0.0.5"
          />
          <div class="form-tip">留空时自动允许本机和同网段；填写后仅允许这些 IP/CIDR，其他来源需 Token 或 Basic 认证。</div>
        </ui-form-item>
        <ui-form-item label="假域名后缀">
          <ui-input v-model="settingsForm.domain_suffix" placeholder="apps.local" clearable />
        </ui-form-item>
        <ui-form-item label="默认 TTL">
          <ui-input-number v-model="settingsForm.default_ttl_seconds" :min="30" :max="86400" :step="30" />
          <span class="unit-label">秒</span>
        </ui-form-item>
        <ui-form-item label="清理间隔">
          <ui-input-number v-model="settingsForm.cleanup_interval_seconds" :min="10" :max="86400" :step="10" />
          <span class="unit-label">秒</span>
        </ui-form-item>
        <ui-form-item label="离线保留时间">
          <ui-input-number v-model="settingsForm.offline_retention_seconds" :min="60" :max="2592000" :step="3600" />
          <span class="unit-label">秒</span>
        </ui-form-item>
        <ui-form-item label="主动健康探测">
          <ui-switch v-model="settingsForm.health_check_enabled" />
        </ui-form-item>
        <ui-form-item label="探测超时">
          <ui-input-number v-model="settingsForm.health_check_timeout_seconds" :min="1" :max="60" :step="1" />
          <span class="unit-label">秒</span>
        </ui-form-item>
      </ui-form>
      <template #footer>
        <ui-button @click="settingsVisible = false">取消</ui-button>
        <ui-button type="primary" :loading="savingSettings" @click="submitSettings">保存</ui-button>
      </template>
    </ui-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from '@/lib/feedback'
import { Plus, RefreshRight, Setting, View } from '@/components/icons'
import { dynamicServicesApi } from '../api/dynamicServices'
import { formatDateTime } from '../utils/date'

const loading = ref(false)
const saving = ref(false)
const services = ref([])
const authStatus = ref<any>({})
const formVisible = ref(false)
const settingsVisible = ref(false)
const previewVisible = ref(false)
const previewContent = ref('')
const editingService = ref(null)
const formRef = ref()
const savingSettings = ref(false)
const form = ref({
  service_name: '',
  route_prefix: '',
  description: '',
  enabled: true
})
const settingsForm = ref({
  ip_whitelist: '',
  domain_suffix: '',
  default_ttl_seconds: 600,
  cleanup_interval_seconds: 30,
  offline_retention_seconds: 86400,
  health_check_enabled: true,
  health_check_timeout_seconds: 3
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

const openSettingsDialog = () => {
  settingsForm.value = {
    ip_whitelist: (authStatus.value.ip_whitelist || []).join(', '),
    domain_suffix: authStatus.value.domain_suffix || '',
    default_ttl_seconds: authStatus.value.default_ttl_seconds || 600,
    cleanup_interval_seconds: authStatus.value.cleanup_interval_seconds || 30,
    offline_retention_seconds: authStatus.value.offline_retention_seconds || 86400,
    health_check_enabled: authStatus.value.health_check_enabled !== false,
    health_check_timeout_seconds: authStatus.value.health_check_timeout_seconds || 3
  }
  settingsVisible.value = true
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

const submitSettings = async () => {
  savingSettings.value = true
  try {
    await dynamicServicesApi.updateSettings({
      ip_whitelist: settingsForm.value.ip_whitelist.trim() || null,
      domain_suffix: settingsForm.value.domain_suffix.trim() || null,
      default_ttl_seconds: settingsForm.value.default_ttl_seconds,
      cleanup_interval_seconds: settingsForm.value.cleanup_interval_seconds,
      offline_retention_seconds: settingsForm.value.offline_retention_seconds,
      health_check_enabled: settingsForm.value.health_check_enabled,
      health_check_timeout_seconds: settingsForm.value.health_check_timeout_seconds
    })
    ElMessage.success('动态注册设置已保存')
    settingsVisible.value = false
    await loadAll()
  } catch (error) {
    ElMessage.error(normalizeError(error))
  } finally {
    savingSettings.value = false
  }
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

const copyHost = async (host) => {
  const url = `http://${host}/`
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success('假域名访问地址已复制')
  } catch (error) {
    ElMessage.info(url)
  }
}

onMounted(loadAll)
</script>

<style scoped>
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

.form-tip {
  width: 100%;
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.unit-label {
  margin-left: 8px;
  color: var(--text-secondary);
  font-size: 13px;
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
