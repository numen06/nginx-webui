<template>
  <div class="certificates-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <div>
            <span class="card-title">证书管理</span>
            <span class="card-subtitle">证书以域名为标识</span>
          </div>
          <div>
            <el-button type="primary" @click="handleRequest">
              <el-icon><DocumentAdd /></el-icon>
              <span class="btn-label">申请证书</span>
            </el-button>
            <el-button type="cyan" @click="handleUpload">
              <el-icon><UploadFilled /></el-icon>
              <span class="btn-label">上传证书</span>
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="certificateList" style="width: 100%">
        <el-table-column prop="domain" label="证书名称（域名）" width="200" fixed="left">
          <template #default="scope">
            <div class="domain-cell">
              <el-tag type="primary" size="small">{{ scope.row.domain }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="证书路径 / 私钥路径" min-width="600">
          <template #default="scope">
            <div class="paths-cell">
              <div class="path-item">
                <span class="path-label">证书：</span>
                <span class="path-text" :title="scope.row.cert_path || '-'">
                  {{ scope.row.cert_path || '-' }}
                </span>
                <el-tooltip content="复制证书路径" :show-after="200">
                  <el-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.cert_path"
                    @click="handleCopy(scope.row.cert_path)"
                  />
                </el-tooltip>
              </div>
              <div class="path-item">
                <span class="path-label">私钥：</span>
                <span class="path-text" :title="scope.row.key_path || '-'">
                  {{ scope.row.key_path || '-' }}
                </span>
                <el-tooltip content="复制私钥路径" :show-after="200">
                  <el-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.key_path"
                    @click="handleCopy(scope.row.key_path)"
                  />
                </el-tooltip>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="valid_to" label="过期时间" width="180" align="center">
          <template #default="scope">
            <div class="expiry-cell">
              <span :class="{ 'expiring-soon': scope.row.days_until_expiry !== null && scope.row.days_until_expiry <= 30 && scope.row.days_until_expiry > 0, 'expired': scope.row.days_until_expiry !== null && scope.row.days_until_expiry <= 0 }">
                {{ formatDateTime(scope.row.valid_to) || '-' }}
              </span>
              <span v-if="scope.row.days_until_expiry !== null" class="expiry-days" :class="{ 'expiring-soon': scope.row.days_until_expiry <= 30 && scope.row.days_until_expiry > 0, 'expired': scope.row.days_until_expiry <= 0 }">
                {{ scope.row.days_until_expiry > 0 ? scope.row.days_until_expiry + '天' : '已过期' }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="自动续期" width="100" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.auto_renew"
              @change="handleToggleAutoRenew(scope.row)"
              :loading="scope.row._toggling"
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" align="center">
          <template #default="scope">
            <div class="action-buttons">
              <el-tooltip content="重新上传" placement="top">
                <el-button
                  circle
                  size="small"
                  type="primary"
                  class="action-icon-btn"
                  @click="handleReupload(scope.row)"
                >
                  <el-icon><UploadFilled /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="续期" placement="top">
                <el-button
                  circle
                  size="small"
                  type="warning"
                  class="action-icon-btn"
                  @click="handleRenew(scope.row)"
                >
                  <el-icon><RefreshRight /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="验证证书" placement="top">
                <el-button
                  circle
                  size="small"
                  type="success"
                  class="action-icon-btn"
                  :loading="scope.row._verifying"
                  @click="handleVerifyCert(scope.row)"
                >
                  <el-icon><CircleCheck /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  circle
                  size="small"
                  type="danger"
                  class="action-icon-btn"
                  @click="handleDelete(scope.row)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 申请证书对话框 -->
    <el-dialog
      v-model="requestDialogVisible"
      title="申请 Let's Encrypt 免费证书"
      width="620px"
      top="6vh"
      :close-on-click-modal="false"
      class="cert-request-dialog"
      @closed="resetRequestWizard"
    >
      <el-steps
        v-if="requestForm.validation_method === 'dns'"
        :active="dnsWizardStep"
        finish-status="success"
        align-center
        class="cert-request-steps"
      >
        <el-step title="填写信息" />
        <el-step title="配置 DNS 并验证" />
      </el-steps>

      <!-- DNS 步骤 1：配置 TXT -->
      <div v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1" class="dns-wizard-panel">
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 12px;">
          <template #title>
            <span class="dns-alert-title">请在域名 DNS 控制台新增 1 条 TXT 记录（把下面字段一字不差填进去）</span>
          </template>
        </el-alert>
        <el-card shadow="never" class="dns-guide-card">
          <template #header>
            <span class="dns-guide-title">第 1 步：进入域名 DNS 管理</span>
          </template>
          <ol class="dns-steps-list">
            <li>登录你的域名服务商控制台（在哪里买的域名就去哪里）</li>
            <li>找到域名 <span class="mono-text">{{ requestForm.domain || '-' }}</span> 的 DNS 解析页面</li>
            <li>点击“新增记录”或“添加解析”</li>
          </ol>
        </el-card>

        <el-card shadow="never" class="dns-guide-card">
          <template #header>
            <span class="dns-guide-title">第 2 步：按下表填写记录</span>
          </template>
          <el-descriptions :column="1" border size="small" class="dns-rec-desc">
            <el-descriptions-item label="记录类型">TXT</el-descriptions-item>
            <el-descriptions-item label="主机记录 / Name">
              <span class="mono-text">{{ dnsHostRecord || dnsRecordName || '-' }}</span>
              <el-button size="small" text type="primary" :disabled="!dnsHostRecord && !dnsRecordName" @click="handleCopy(dnsHostRecord || dnsRecordName)">复制</el-button>
              <div class="form-tip">如果平台要求填写完整主机名，也可填：{{ dnsRecordName || '-' }}</div>
            </el-descriptions-item>
            <el-descriptions-item label="记录值 / Value">
              <span class="mono-text dns-value">{{ dnsRecordValue || '-' }}</span>
              <el-button size="small" text type="primary" :disabled="!dnsRecordValue" @click="handleCopy(dnsRecordValue)">复制</el-button>
            </el-descriptions-item>
            <el-descriptions-item label="TTL">默认即可（建议 600 秒或 Auto）</el-descriptions-item>
          </el-descriptions>
          <el-alert type="info" :closable="false" class="dns-field-tip" show-icon>
            <template #title>
              不同平台字段名可能叫：主机记录/记录名/Name、记录值/Value/内容，含义相同。
            </template>
          </el-alert>
        </el-card>

        <el-card shadow="never" class="dns-guide-card">
          <template #header>
            <span class="dns-guide-title">第 3 步：保存并检测是否生效</span>
          </template>
          <p class="form-tip">保存后通常 1-10 分钟生效，最长可能更久。你可以开启自动检测，系统会每 5 秒检查一次。</p>
          <div class="dns-verify-row">
            <el-checkbox v-model="dnsAutoPoll">每 5 秒自动检测一次</el-checkbox>
            <el-tag v-if="dnsVerified" type="success" size="small">TXT 已匹配，可点击“完成申请”</el-tag>
            <el-tag v-else-if="dnsLastCheckMsg" type="info" size="small">{{ dnsLastCheckMsg }}</el-tag>
          </div>
          <el-button type="primary" plain size="small" :loading="dnsChecking" @click="runDnsVerifyOnce">
            立即检测 DNS
          </el-button>
          <el-alert type="error" :closable="false" class="dns-troubleshoot" show-icon>
            <template #title>
              检测失败时请依次检查：1) 记录类型是否为 TXT；2) 主机记录是否填错（建议先用上方复制值）；3) 记录值是否有多余空格/换行；4) 是否改到了错误的域名。
            </template>
          </el-alert>
        </el-card>

        <div class="dns-help-links">
          <span class="form-tip">常见 DNS 控制台教程：</span>
          <el-link type="primary" href="https://docs.dnspod.cn/dns/console/manage/" target="_blank" :underline="false">腾讯云 DNSPod</el-link>
          <el-link type="primary" href="https://help.aliyun.com/document_detail/29725.html" target="_blank" :underline="false">阿里云</el-link>
          <el-link type="primary" href="https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/" target="_blank" :underline="false">Cloudflare</el-link>
        </div>
      </div>

      <!-- 表单：HTTP 或 DNS 步骤 0 -->
      <el-form
        v-if="requestForm.validation_method !== 'dns' || dnsWizardStep === 0"
        :model="requestForm"
        :rules="requestRules"
        ref="requestFormRef"
        label-width="100px"
        class="compact-form"
      >
        <el-form-item label="域名" prop="domain">
          <el-input
            v-model="requestForm.domain"
            placeholder="例如：example.com"
          />
          <div class="form-tip">主域名，将用于证书申请和 Nginx 配置</div>
        </el-form-item>

        <el-form-item label="邮箱地址" prop="email">
          <el-input
            v-model="requestForm.email"
            placeholder="例如：admin@example.com"
          />
          <div class="form-tip">Let's Encrypt 会通过此邮箱发送证书到期通知</div>
        </el-form-item>

        <el-form-item label="验证方式" prop="validation_method">
          <el-radio-group v-model="requestForm.validation_method" @change="onValidationMethodChange">
            <el-radio value="http">
              <span>HTTP 验证</span>
              <div class="radio-desc">需要域名已解析到本服务器且 Nginx 正在运行，80 端口可访问</div>
            </el-radio>
            <el-radio value="dns">
              <span>DNS 验证</span>
              <div class="radio-desc">在域名 DNS 中添加 TXT 记录；适合无法开放 80 端口的场景</div>
            </el-radio>
          </el-radio-group>
        </el-form-item>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 16px;"
        >
          <template #title>
            <span style="font-size: 12px;">
              申请成功后将自动完成：1) 证书文件持久化存储  2) 自动修改 Nginx 配置添加 SSL  3) 开启自动续期
            </span>
          </template>
        </el-alert>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="requestDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1"
            @click="dnsWizardBack"
          >
            上一步
          </el-button>
          <el-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 0"
            type="primary"
            :loading="requesting"
            :disabled="isRequestDisabled"
            @click="handleDnsWizardNext"
          >
            <el-icon><Check /></el-icon>
            <span class="btn-label">下一步：获取 DNS 要求</span>
          </el-button>
          <el-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1"
            type="primary"
            :loading="requesting"
            :disabled="!dnsVerified"
            @click="handleDnsCompleteIssue"
          >
            <el-icon><Check /></el-icon>
            <span class="btn-label">完成申请（签发证书）</span>
          </el-button>
          <el-button
            v-if="requestForm.validation_method === 'http'"
            type="primary"
            :loading="requesting"
            :disabled="isRequestDisabled"
            @click="handleRequestSubmitHttp"
          >
            <el-icon><Check /></el-icon>
            <span class="btn-label">申请证书</span>
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 上传证书对话框 -->
    <el-dialog
      v-model="uploadDialogVisible"
      :title="uploadForm.certId ? '重新上传证书' : '上传证书'"
      width="600px"
      top="8vh"
      :close-on-click-modal="false"
      class="cert-upload-dialog"
    >
      <el-form :model="uploadForm" :rules="uploadRules" ref="uploadFormRef" label-width="90px" class="compact-form">
        <el-form-item label="域名" prop="domain">
          <el-input 
            v-model="uploadForm.domain" 
            :placeholder="uploadForm.certId ? '重新上传将替换现有证书' : '例如：example.com'"
            :disabled="!!uploadForm.certId"
          />
          <div v-if="uploadForm.certId" class="form-tip">
            将替换域名 {{ uploadForm.domain }} 的现有证书和私钥
          </div>
        </el-form-item>
        
        <el-form-item label="上传方式">
          <el-radio-group v-model="uploadForm.mode" size="small">
            <el-radio-button label="files">文件上传</el-radio-button>
            <el-radio-button label="archive">压缩包</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 文件上传模式 -->
        <template v-if="uploadForm.mode === 'files'">
          <el-form-item label="证书文件" required>
            <el-upload
              ref="certUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleCertFileChange"
              :on-remove="handleCertFileRemove"
              accept=".crt,.pem,.cer"
              :show-file-list="false"
            >
              <el-button size="small" type="primary">
                <el-icon><FolderOpened /></el-icon>
                选择证书
              </el-button>
            </el-upload>
            <div v-if="uploadForm.certFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.certFile?.name || uploadForm.certFile?.raw?.name || '未知文件' }}</span>
              <el-button size="small" text type="danger" @click="handleCertFileRemove">×</el-button>
            </div>
            <div v-if="uploadForm.domain && uploadForm.certFile && !checkFileNameMatch(uploadForm.certFile?.name || uploadForm.certFile?.raw?.name, uploadForm.domain)" class="file-warning-compact">
              ⚠️ 文件名与域名不匹配
            </div>
          </el-form-item>
          <el-form-item label="私钥文件" required>
            <el-upload
              ref="keyUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleKeyFileChange"
              :on-remove="handleKeyFileRemove"
              accept=".key,.pem"
              :show-file-list="false"
            >
              <el-button size="small" type="primary">
                <el-icon><FolderOpened /></el-icon>
                选择私钥
              </el-button>
            </el-upload>
            <div v-if="uploadForm.keyFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.keyFile?.name || uploadForm.keyFile?.raw?.name || '未知文件' }}</span>
              <el-button size="small" text type="danger" @click="handleKeyFileRemove">×</el-button>
            </div>
            <div v-if="uploadForm.domain && uploadForm.keyFile && !checkFileNameMatch(uploadForm.keyFile?.name || uploadForm.keyFile?.raw?.name, uploadForm.domain)" class="file-warning-compact">
              ⚠️ 文件名与域名不匹配
            </div>
          </el-form-item>
        </template>

        <!-- 压缩包模式 -->
        <template v-else>
          <el-form-item label="压缩包" required>
            <el-upload
              ref="archiveUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleArchiveFileChange"
              :on-remove="handleArchiveFileRemove"
              accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2"
              :show-file-list="false"
            >
              <el-button size="small" type="primary">
                <el-icon><FolderOpened /></el-icon>
                选择压缩包
              </el-button>
            </el-upload>
            <div v-if="uploadForm.archiveFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.archiveFile.name }}</span>
              <el-button size="small" text type="danger" @click="handleArchiveFileRemove">×</el-button>
            </div>
            <div class="upload-tip-small">支持 zip、tar.gz、tar.bz2 格式，自动识别证书与私钥</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="uploadDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
            <el-button
              type="primary"
              :loading="uploading"
              :disabled="isUploadDisabled"
              @click="handleUploadSubmit"
            >
              <el-icon><Check /></el-icon>
              <span class="btn-label">{{ uploadForm.certId ? '更新' : '上传' }}</span>
            </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 手动复制对话框 -->
    <el-dialog
      v-model="copyTextDialogVisible"
      title="手动复制"
      width="600px"
    >
      <div style="margin-bottom: 12px; color: var(--el-text-color-regular);">
        复制失败，请手动选择并复制以下内容：
      </div>
      <el-input
        v-model="copyTextContent"
        type="textarea"
        :rows="4"
        readonly
        style="font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;"
      />
      <template #footer>
        <span class="dialog-footer">
          <el-button type="primary" @click="copyTextDialogVisible = false">
            <el-icon><Check /></el-icon>
            <span class="btn-label">已复制</span>
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, onBeforeUnmount } from 'vue'
import { certificatesApi } from '../api/certificates'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentAdd, UploadFilled, RefreshRight, Delete, FolderOpened, CloseBold, Check, CopyDocument, CircleCheck } from '@element-plus/icons-vue'
import { formatDateTime } from '../utils/date'

const certificateList = ref([])
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref(null)
const certUploadRef = ref(null)
const keyUploadRef = ref(null)
const archiveUploadRef = ref(null)
const copyTextDialogVisible = ref(false)
const copyTextContent = ref('')

// 申请证书对话框
const requestDialogVisible = ref(false)
const requesting = ref(false)
const requestFormRef = ref(null)
const requestForm = ref({
  domain: '',
  email: '',
  validation_method: 'http'
})

/** DNS 申请向导 */
const dnsWizardStep = ref(0)
const dnsJobId = ref(null)
const dnsRecordName = ref('')
const dnsRecordValue = ref('')
const dnsVerified = ref(false)
const dnsChecking = ref(false)
const dnsAutoPoll = ref(false)
const dnsLastCheckMsg = ref('')
let dnsPollTimer = null

const isRequestDisabled = computed(() => {
  return !requestForm.value.domain || !requestForm.value.email
})

const dnsHostRecord = computed(() => {
  const fqdn = String(dnsRecordName.value || '').trim().replace(/\.$/, '')
  const domain = String(requestForm.value.domain || '').trim().replace(/^\*\./, '')
  if (!fqdn) return ''
  if (!domain) return fqdn
  if (fqdn === domain) return '@'
  if (fqdn.endsWith(`.${domain}`)) {
    return fqdn.slice(0, -1 * (`.${domain}`).length) || '@'
  }
  return fqdn
})

const escapeHtml = (s) => {
  if (s == null || s === undefined) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const showCertFailureDialog = (payload) => {
  const msg = payload?.message || '操作失败'
  const code = payload?.error_code
  const suggestions = payload?.suggestions || []
  const output = payload?.output || ''
  const sugHtml = suggestions.length
    ? `<ul style="margin:8px 0;padding-left:18px;text-align:left">${suggestions.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>`
    : ''
  const outHtml = output
    ? `<details style="margin-top:12px;text-align:left"><summary style="cursor:pointer">查看 certbot 原始输出</summary><pre style="white-space:pre-wrap;word-break:break-all;font-size:11px;max-height:240px;overflow:auto;margin-top:8px">${escapeHtml(output)}</pre></details>`
    : ''
  ElMessageBox.alert(
    `<div style="text-align:left"><p style="font-weight:600;margin-bottom:8px">${escapeHtml(msg)}</p>${
      code ? `<p style="font-size:12px;color:#909399">错误代码: ${escapeHtml(code)}</p>` : ''
    }${sugHtml}${outHtml}</div>`,
    '证书操作失败',
    { dangerouslyUseHTMLString: true, type: 'error', customClass: 'cert-fail-msgbox' }
  )
}

const clearDnsPoll = () => {
  if (dnsPollTimer) {
    clearInterval(dnsPollTimer)
    dnsPollTimer = null
  }
}

const resetRequestWizard = () => {
  dnsWizardStep.value = 0
  dnsJobId.value = null
  dnsRecordName.value = ''
  dnsRecordValue.value = ''
  dnsVerified.value = false
  dnsAutoPoll.value = false
  dnsLastCheckMsg.value = ''
  clearDnsPoll()
}

const onValidationMethodChange = () => {
  resetRequestWizard()
}

const dnsWizardBack = () => {
  clearDnsPoll()
  dnsVerified.value = false
  dnsLastCheckMsg.value = ''
  dnsWizardStep.value = 0
  dnsJobId.value = null
  dnsRecordName.value = ''
  dnsRecordValue.value = ''
}

const runDnsVerifyOnce = async () => {
  if (!dnsRecordName.value || !dnsRecordValue.value) {
    ElMessage.warning('缺少 DNS 记录信息')
    return
  }
  dnsChecking.value = true
  dnsLastCheckMsg.value = '检测中…'
  try {
    const res = await certificatesApi.verifyDns(dnsRecordName.value, dnsRecordValue.value)
    if (res.matched) {
      dnsVerified.value = true
      dnsLastCheckMsg.value = 'TXT 记录已匹配'
      ElMessage.success('DNS TXT 验证通过')
      clearDnsPoll()
      dnsAutoPoll.value = false
    } else {
      dnsVerified.value = false
      dnsLastCheckMsg.value = res.message || '尚未匹配'
    }
  } catch (e) {
    dnsLastCheckMsg.value = e?.detail || e?.message || '检测失败'
  } finally {
    dnsChecking.value = false
  }
}

watch(
  () => [dnsAutoPoll.value, dnsWizardStep.value, dnsRecordName.value, dnsRecordValue.value],
  () => {
    clearDnsPoll()
    if (
      dnsAutoPoll.value &&
      dnsWizardStep.value === 1 &&
      dnsRecordName.value &&
      dnsRecordValue.value
    ) {
      dnsPollTimer = setInterval(() => {
        runDnsVerifyOnce()
      }, 5000)
    }
  }
)

onBeforeUnmount(() => {
  clearDnsPoll()
})

const handleDnsWizardNext = async () => {
  if (!requestFormRef.value) return
  try {
    await requestFormRef.value.validate()
  } catch {
    return
  }
  requesting.value = true
  try {
    const res = await certificatesApi.dnsChallengeStart(
      requestForm.value.domain.trim(),
      requestForm.value.email
    )
    if (res.success && res.job_id) {
      dnsJobId.value = res.job_id
      dnsRecordName.value = res.record_name || ''
      dnsRecordValue.value = res.record_value || ''
      dnsWizardStep.value = 1
      dnsVerified.value = false
      dnsLastCheckMsg.value = ''
      ElMessage.success('已获取 DNS 验证要求，请添加 TXT 记录')
    } else {
      showCertFailureDialog({
        message: res.message || '获取 DNS 要求失败',
        error_code: res.error_code,
        suggestions: res.suggestions || [],
        output: res.output
      })
    }
  } catch (error) {
    showCertFailureDialog({
      message: error?.detail || error?.message || '获取 DNS 要求失败',
      error_code: error?.error_code,
      suggestions: error?.suggestions,
      output: error?.output
    })
  } finally {
    requesting.value = false
  }
}

const handleDnsCompleteIssue = async () => {
  if (!dnsJobId.value) {
    ElMessage.error('会话已失效，请从第一步重新获取 DNS 要求')
    return
  }
  requesting.value = true
  try {
    const response = await certificatesApi.dnsChallengeComplete(dnsJobId.value)
    if (response.success) {
      let msg = response.message || '证书申请成功'
      if (response.verification?.message) {
        msg += `（${response.verification.message}）`
      }
      ElMessage.success(msg)
      requestDialogVisible.value = false
      loadCertificates()
    } else {
      showCertFailureDialog({
        message: response.message || '签发失败',
        error_code: response.error_code,
        suggestions: response.suggestions || [],
        output: response.output
      })
    }
  } catch (error) {
    showCertFailureDialog({
      message: error?.detail || error?.message || '签发失败',
      error_code: error?.error_code,
      suggestions: error?.suggestions,
      output: error?.output
    })
  } finally {
    requesting.value = false
  }
}

const handleRequestSubmitHttp = async () => {
  if (!requestFormRef.value) return
  try {
    await requestFormRef.value.validate()
  } catch {
    return
  }
  requesting.value = true
  try {
    const response = await certificatesApi.requestCertificate(
      [requestForm.value.domain.trim()],
      requestForm.value.email,
      'http'
    )
    if (response.success) {
      let msg = response.message || '证书申请成功'
      if (response.verification?.message) {
        msg += `（${response.verification.message}）`
      }
      ElMessage.success(msg)
      requestDialogVisible.value = false
      loadCertificates()
    } else {
      showCertFailureDialog({
        message: response.message || '证书申请失败',
        error_code: response.error_code,
        suggestions: response.suggestions || [],
        output: response.output
      })
    }
  } catch (error) {
    showCertFailureDialog({
      message: error?.detail || error?.message || '证书申请失败',
      error_code: error?.error_code,
      suggestions: error?.suggestions,
      output: error?.output
    })
  } finally {
    requesting.value = false
  }
}

const handleVerifyCert = async (cert) => {
  cert._verifying = true
  try {
    const res = await certificatesApi.verifyCert(cert.id)
    const d = res.details || {}
    const lines = [
      res.message,
      d.domain ? `域名(CN): ${d.domain}` : null,
      d.valid_to ? `有效期至: ${d.valid_to}` : null,
      d.not_expired === false ? '注意：证书已过期或即将过期' : null,
      d.key_matches_cert === false ? '注意：私钥与证书不匹配' : null
    ].filter(Boolean)
    ElMessageBox.alert(
      `<div style="text-align:left;font-size:13px;line-height:1.6">${lines.map((l) => `<p>${escapeHtml(l)}</p>`).join('')}</div>`,
      '证书校验结果',
      { dangerouslyUseHTMLString: true, type: res.valid ? 'success' : 'warning' }
    )
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || '验证失败')
  } finally {
    cert._verifying = false
  }
}

const requestRules = {
  domain: [
    { required: true, message: '请输入域名', trigger: 'blur' },
    {
      pattern: /^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/,
      message: '请输入有效的域名',
      trigger: 'blur'
    }
  ],
  email: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
  ],
  validation_method: [
    { required: true, message: '请选择验证方式', trigger: 'change' }
  ]
}

const uploadForm = ref({
  domain: '',
  certFile: null,
  keyFile: null,
  archiveFile: null,
  mode: 'files',
  certId: null // 用于重新上传时标识要更新的证书ID
})

const isUploadDisabled = computed(() => {
  if (!uploadForm.value.domain) return true
  if (uploadForm.value.mode === 'archive') {
    return !uploadForm.value.archiveFile
  }
  return !uploadForm.value.certFile || !uploadForm.value.keyFile
})

const uploadRules = {
  domain: [
    { 
      required: true, 
      message: '请输入域名或上传压缩包自动识别', 
      trigger: 'blur',
      validator: (rule, value, callback) => {
        // 如果是压缩包模式，域名可以为空（后端会自动提取）
        if (uploadForm.value.mode === 'archive' && !value) {
          callback()
        } else if (!value) {
          callback(new Error('请输入域名'))
        } else if (!/^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/.test(value)) {
          callback(new Error('请输入有效的域名'))
        } else {
          callback()
        }
      }
    }
  ]
}

const loadCertificates = async () => {
  try {
    const response = await certificatesApi.getCertificates()
    certificateList.value = response.certificates || []
  } catch (error) {
    ElMessage.error('加载证书列表失败')
  }
}

const handleRequest = () => {
  requestForm.value = {
    domain: '',
    email: '',
    validation_method: 'http'
  }
  resetRequestWizard()
  requestDialogVisible.value = true
}

const handleUpload = () => {
  uploadForm.value = {
    domain: '',
    certFile: null,
    keyFile: null,
    archiveFile: null,
    mode: 'files',
    certId: null
  }
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
  }
  if (archiveUploadRef.value) {
    archiveUploadRef.value.clearFiles()
  }
  uploadDialogVisible.value = true
}

const handleReupload = (cert) => {
  uploadForm.value = {
    domain: cert.domain,
    certFile: null,
    keyFile: null,
    archiveFile: null,
    mode: 'files',
    certId: cert.id
  }
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
  }
  if (archiveUploadRef.value) {
    archiveUploadRef.value.clearFiles()
  }
  uploadDialogVisible.value = true
}

const handleCertFileChange = (file) => {
  uploadForm.value.certFile = file.raw
}

const handleCertFileRemove = () => {
  uploadForm.value.certFile = null
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
}

const handleKeyFileChange = (file) => {
  uploadForm.value.keyFile = file.raw
}

const handleKeyFileRemove = () => {
  uploadForm.value.keyFile = null
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
  }
}

const handleArchiveFileChange = async (file) => {
  uploadForm.value.archiveFile = file.raw
  
  // 自动解析压缩包中的域名
  if (file.raw) {
    try {
      const response = await certificatesApi.parseCertificateArchive(file.raw)
      if (response.domain) {
        uploadForm.value.domain = response.domain
        ElMessage.success(`已自动识别域名: ${response.domain}`)
      }
    } catch (error) {
      // 解析失败不影响用户手动输入域名
      console.warn('自动解析域名失败:', error)
    }
  }
}

const handleArchiveFileRemove = () => {
  uploadForm.value.archiveFile = null
  if (archiveUploadRef.value) {
    archiveUploadRef.value.clearFiles()
  }
}

// 检查文件名是否包含域名
const checkFileNameMatch = (fileName, domain) => {
  if (!fileName || !domain) return true
  try {
    // 移除文件扩展名和常见前缀后进行比较
    const nameWithoutExt = String(fileName).replace(/\.(crt|pem|cer|key)$/i, '').toLowerCase()
    const domainLower = String(domain).toLowerCase()
    // 检查文件名中是否包含域名
    return nameWithoutExt.includes(domainLower.replace(/\./g, '')) || 
           nameWithoutExt.includes(domainLower)
  } catch (error) {
    console.warn('检查文件名匹配时出错:', error)
    return true // 出错时默认返回true，不显示警告
  }
}

const handleUploadSubmit = async () => {
  if (!uploadFormRef.value) return
  
  try {
    await uploadFormRef.value.validate()
  } catch (error) {
    return
  }

  const mode = uploadForm.value.mode
  if (mode === 'archive') {
    if (!uploadForm.value.archiveFile) {
      ElMessage.warning('请选择包含证书与私钥的压缩包')
      return
    }
    // 压缩包模式下，如果没有域名，后端会尝试从证书中提取
  } else if (!uploadForm.value.certFile || !uploadForm.value.keyFile) {
    ElMessage.warning('请选择证书文件和私钥文件')
    return
  }

  uploading.value = true
  try {
    if (mode === 'archive') {
      await certificatesApi.uploadCertificateArchive(
        uploadForm.value.domain,
        uploadForm.value.archiveFile,
        false, // 手动上传的证书不支持自动续期
        uploadForm.value.certId
      )
      ElMessage.success(uploadForm.value.certId ? '证书更新成功' : '证书压缩包上传成功')
    } else {
    await certificatesApi.uploadCertificate(
      uploadForm.value.domain,
      uploadForm.value.certFile,
      uploadForm.value.keyFile,
      false, // 手动上传的证书不支持自动续期
      uploadForm.value.certId
    )
    ElMessage.success(uploadForm.value.certId ? '证书更新成功' : '证书上传成功')
    }
    uploadDialogVisible.value = false
    loadCertificates()
  } catch (error) {
    ElMessage.error(error.detail || error.message || '证书上传失败')
  } finally {
    uploading.value = false
  }
}

const handleRenew = async (cert) => {
  try {
    const response = await certificatesApi.renewCertificate(cert.id)
    if (response.success) {
      ElMessage.success(response.message || '证书续期成功')
    } else {
      showCertFailureDialog({
        message: response.message || '证书续期失败',
        error_code: response.error_code,
        suggestions: response.suggestions || [],
        output: response.output
      })
    }
    loadCertificates()
  } catch (error) {
    showCertFailureDialog({
      message: error?.detail || error?.message || '证书续期失败',
      error_code: error?.error_code,
      suggestions: error?.suggestions,
      output: error?.output
    })
  }
}

const handleToggleAutoRenew = async (cert) => {
  cert._toggling = true
  try {
    await certificatesApi.updateCertificate(cert.id, cert.auto_renew)
    ElMessage.success(cert.auto_renew ? '已开启自动续期' : '已关闭自动续期')
  } catch (error) {
    cert.auto_renew = !cert.auto_renew
    ElMessage.error(error.detail || error.message || '操作失败')
  } finally {
    cert._toggling = false
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

const handleCopy = async (text) => {
  if (!text) return
  
  // 方法1: 尝试使用现代 Clipboard API
  if (navigator.clipboard && navigator.clipboard.writeText) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
      return
    } catch (error) {
      console.warn('Clipboard API 失败，尝试备用方法:', error)
    }
  }
  
  // 方法2: 使用传统的 execCommand 方法（备用）
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    
    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    
    if (successful) {
      ElMessage.success('已复制到剪贴板')
      return
    }
  } catch (error) {
    console.warn('execCommand 方法失败:', error)
  }
  
  // 方法3: 如果都失败了，显示对话框让用户手动复制
  copyTextContent.value = text
  copyTextDialogVisible.value = true
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

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-right: 12px;
}

.card-subtitle {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}

.file-name {
  margin-top: 8px;
  color: #606266;
  font-size: 12px;
}

.el-upload__tip {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}

.paths-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.path-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  min-width: 40px;
  flex-shrink: 0;
}

.path-text {
  flex: 1;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
  line-height: 1.6;
}

.domain-cell {
  display: flex;
  align-items: center;
}

.domain-cell :deep(.el-tag) {
  font-weight: 500;
  font-size: 13px;
}

.compact-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.compact-form :deep(.el-form-item__label) {
  font-size: 13px;
  padding-bottom: 4px;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}



.file-selected-compact {
  margin-top: 6px;
  padding: 6px 10px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.file-name-text {
  flex: 1;
  font-size: 12px;
  color: var(--el-text-color-primary);
  word-break: break-all;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
  line-height: 1.4;
}

.file-warning-compact {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-color-warning);
  line-height: 1.3;
}

.upload-tip-small {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.3;
}

.action-buttons {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}

.action-icon-btn {
  margin: 0;
}

.cert-upload-dialog :deep(.el-dialog__body) {
  max-height: calc(85vh - 120px);
  overflow-y: auto;
  padding: 20px;
}

.cert-upload-dialog :deep(.el-upload) {
  width: 100%;
}

.cert-upload-dialog :deep(.el-upload .el-button) {
  width: 100%;
}

.expiry-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.expiry-days {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.expiry-days.expiring-soon {
  color: var(--el-color-warning);
}

.expiry-days.expired {
  color: var(--el-color-danger);
}

.expiring-soon {
  color: var(--el-color-warning) !important;
}

.expired {
  color: var(--el-color-danger) !important;
}

.radio-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
  line-height: 1.3;
}

.cert-request-dialog :deep(.el-radio) {
  height: auto;
  margin-right: 0;
  margin-bottom: 8px;
  align-items: flex-start;
}

.cert-request-dialog :deep(.el-radio__label) {
  white-space: normal;
}

.cert-request-steps {
  margin-bottom: 20px;
}

.dns-wizard-panel {
  margin-top: 8px;
}

.dns-alert-title {
  font-size: 13px;
  line-height: 1.5;
}

.dns-guide-card {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-light);
}

.dns-guide-title {
  font-weight: 600;
  font-size: 13px;
}

.dns-steps-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
  font-size: 13px;
}

.dns-rec-desc {
  margin-top: 2px;
}

.dns-field-tip {
  margin-top: 10px;
}

.dns-troubleshoot {
  margin-top: 10px;
}

.mono-text {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
  font-size: 12px;
  word-break: break-all;
}

.dns-value {
  display: inline-block;
  max-width: 100%;
}

.dns-help-links {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.dns-verify-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 10px 0;
}
</style>

