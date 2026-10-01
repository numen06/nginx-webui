<template>
  <div class="page-shell">
    <ui-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div>
            <span>证书 DNS 配置</span>
            <p class="card-subtitle">使用阿里云 DNS API 自动完成 Let's Encrypt 的 TXT 验证与续期。</p>
          </div>
        </div>
      </template>

      <ui-form label-width="140px" class="max-w-2xl">
        <ui-form-item label="DNS 主域名">
          <ui-input v-model="form.zone" placeholder="例如 51jbm.cn" />
        </ui-form-item>
        <ui-form-item label="AccessKey ID">
          <ui-input v-model="form.access_key_id" autocomplete="off" placeholder="RAM 用户的 AccessKey ID" />
        </ui-form-item>
        <ui-form-item label="AccessKey Secret">
          <ui-input
            v-model="form.access_key_secret"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="configured ? '已保存，留空保持不变' : 'RAM 用户的 AccessKey Secret'"
          />
        </ui-form-item>
      </ui-form>

      <div class="flex flex-wrap gap-3">
        <ui-button type="primary" :loading="saving" @click="save">保存配置</ui-button>
        <ui-button :loading="testing" :disabled="!configured" @click="test">测试 DNS 读写权限</ui-button>
      </div>

      <ui-alert type="info" show-icon class="mt-5">
        凭据只保存在服务器的数据目录，接口不会回传 Secret。建议使用仅能管理目标域名 DNS 记录的 RAM 用户，并授予查询、添加和删除解析记录的权限。保存后，在证书管理页选择“阿里云 DNS 自动验证”重新签发；原先上传的证书不会自动接管。
      </ui-alert>
    </ui-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { certificatesApi } from '@/api/certificates'
import { ElMessage } from '@/lib/feedback'

const form = ref({ zone: '', access_key_id: '', access_key_secret: '' })
const configured = ref(false)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

async function load() {
  loading.value = true
  try {
    const result = await certificatesApi.getAliyunDnsConfig()
    configured.value = Boolean(result.configured)
    form.value.zone = result.zone || ''
    form.value.access_key_id = result.access_key_id || ''
    form.value.access_key_secret = ''
  } catch (error: any) {
    ElMessage.error(error?.detail || error?.message || '加载 DNS 配置失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.zone.trim() || !form.value.access_key_id.trim()) {
    ElMessage.warning('请填写 DNS 主域名和 AccessKey ID')
    return
  }
  if (!configured.value && !form.value.access_key_secret) {
    ElMessage.warning('请填写 AccessKey Secret')
    return
  }
  saving.value = true
  try {
    await certificatesApi.saveAliyunDnsConfig({
      zone: form.value.zone.trim(),
      access_key_id: form.value.access_key_id.trim(),
      access_key_secret: form.value.access_key_secret || null,
    })
    ElMessage.success('阿里云 DNS 配置已保存')
    await load()
  } catch (error: any) {
    ElMessage.error(error?.detail || error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function test() {
  testing.value = true
  try {
    const result = await certificatesApi.testAliyunDnsConfig()
    ElMessage.success(result.message || '阿里云 DNS 读写测试成功')
  } catch (error: any) {
    ElMessage.error(error?.detail || error?.message || 'API 测试失败')
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>
