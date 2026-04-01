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
            <el-tooltip content="从原环境导出证书后在此导入，并引导在本机申请 Let’s Encrypt 以启用自动续签" placement="bottom">
              <el-button type="success" plain @click="openMigrateWizard">
                <el-icon><Promotion /></el-icon>
                <span class="btn-label">迁移与自动续签</span>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="执行 certbot 模拟续签（dry-run），检测本机是否具备自动续签条件，不会改动真实证书"
              placement="bottom"
            >
              <el-button
                type="info"
                plain
                :loading="testingAutoRenewEnv"
                @click="handleTestAutoRenewEnv"
              >
                <el-icon><Operation /></el-icon>
                <span class="btn-label">测试自动续签环境</span>
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </template>

      <el-collapse v-model="migrationGuideOpen" class="cert-migration-collapse">
        <el-collapse-item name="guide">
          <template #title>
            <span class="migration-guide-title">导出证书 → 在本系统导入（与自动续签说明）</span>
            <el-tag size="small" type="info" class="migration-guide-tag">常见流程</el-tag>
          </template>
          <div class="migration-guide-body">
            <p class="migration-guide-lead">
              一般<strong>不必迁移整包 Certbot</strong>：在原环境<strong>导出</strong>证书链与私钥（如 <code>fullchain.pem</code>、<code>privkey.pem</code>），到本页使用<strong>上传证书</strong>完成<strong>导入</strong>即可启用 HTTPS。
            </p>
            <ol class="migration-guide-steps">
              <li>
                <strong>导出</strong>：从原服务器 <code>/etc/letsencrypt/live/&lt;证书目录名&gt;/</code>（一般为 <code>fullchain.pem</code>、<code>privkey.pem</code>）或云厂商面板下载；若<strong>本机</strong>已挂载该目录，可在「<strong>迁移与自动续签</strong>」向导第一步<strong>直接打包下载 ZIP</strong>，带到另一台用「上传证书」导入。
              </li>
              <li>
                <strong>导入</strong>：本页「上传证书」选择文件或压缩包，域名填实际证书域名。
              </li>
              <li>
                <strong>若要本系统自动续签（Certbot）</strong>：仅导入 PEM 时，本机尚未登记这条证；需在本系统对同一域名再点<strong>「申请证书」</strong>走 Let’s Encrypt，签发成功后即可配合「自动续期」与定时任务。不重新申请则可在到期前<strong>再次导出 → 导入</strong>替换。
              </li>
              <li>
                <strong>环境自检</strong>：「<strong>测试自动续签环境</strong>」检查本机 <code>certbot renew</code> 是否正常（不改动真实证书）。
              </li>
            </ol>
            <el-alert type="info" :closable="false" show-icon class="migration-guide-alert">
              <template #title>
                <span class="migration-alert-title">与「仅上传」的关系</span>
              </template>
              <p class="migration-alert-text">
                导出再导入与手动上传是同一类操作：都能立刻用起来；<strong>自动续签</strong>依赖本机 Certbot 已签发该域名，通常要在本系统<strong>申请证书</strong>一次，而不是只靠导入文件。
              </p>
            </el-alert>
            <p class="migration-guide-foot">
              需要分步引导时，可直接使用上方「<strong>迁移与自动续签</strong>」按钮打开向导。可复制给客户的一段话与更多说明见
              <code>docs/cert-migration.md</code>。
            </p>
          </div>
        </el-collapse-item>
      </el-collapse>

      <el-table :data="certificateList" style="width: 100%">
        <el-table-column prop="domain" label="证书名称（域名）" width="200" fixed="left">
          <template #default="scope">
            <div class="domain-cell">
              <el-tag type="primary" size="small">{{ scope.row.domain }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="路径 / 磁盘 / Nginx" min-width="720">
          <template #default="scope">
            <div class="paths-cell">
              <div class="path-disk-row">
                <span class="path-meta-label">磁盘</span>
                <el-tag
                  v-if="scope.row.cert_file_exists === true"
                  size="small"
                  type="success"
                >
                  证书在盘
                </el-tag>
                <el-tag
                  v-else-if="scope.row.cert_file_exists === false"
                  size="small"
                  type="danger"
                >
                  证书缺失
                </el-tag>
                <el-tag
                  v-if="scope.row.key_file_exists === true"
                  size="small"
                  type="success"
                >
                  私钥在盘
                </el-tag>
                <el-tag
                  v-else-if="scope.row.key_file_exists === false"
                  size="small"
                  type="danger"
                >
                  私钥缺失
                </el-tag>
                <el-button
                  v-if="scope.row.nginx_ssl_snippet"
                  size="small"
                  text
                  type="primary"
                  @click="handleCopy(scope.row.nginx_ssl_snippet)"
                >
                  复制 Nginx（库内路径）
                </el-button>
                <el-button
                  v-if="nginxPemSnippet(scope.row)"
                  size="small"
                  text
                  type="primary"
                  @click="handleCopy(nginxPemSnippet(scope.row))"
                >
                  复制 Nginx（fullchain.pem）
                </el-button>
              </div>
              <div class="path-item">
                <span class="path-label">证书：</span>
                <span
                  class="path-text"
                  :class="{ 'path-text-missing': scope.row.cert_file_exists === false }"
                  :title="scope.row.cert_path || '-'"
                >
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
                <span
                  class="path-text"
                  :class="{ 'path-text-missing': scope.row.key_file_exists === false }"
                  :title="scope.row.key_path || '-'"
                >
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
              <div v-if="scope.row.fullchain_pem_path && scope.row.privkey_pem_path" class="path-pem-block">
                <div class="path-item">
                  <span class="path-label">链：</span>
                  <span class="path-text" :title="scope.row.fullchain_pem_path">
                    {{ scope.row.fullchain_pem_path }}
                  </span>
                  <el-tooltip content="复制 fullchain.pem 路径" :show-after="200">
                    <el-button
                      size="small"
                      text
                      :icon="CopyDocument"
                      @click="handleCopy(scope.row.fullchain_pem_path)"
                    />
                  </el-tooltip>
                </div>
                <div class="path-item">
                  <span class="path-label">密钥：</span>
                  <span class="path-text" :title="scope.row.privkey_pem_path">
                    {{ scope.row.privkey_pem_path }}
                  </span>
                  <el-tooltip content="复制 privkey.pem 路径" :show-after="200">
                    <el-button
                      size="small"
                      text
                      :icon="CopyDocument"
                      @click="handleCopy(scope.row.privkey_pem_path)"
                    />
                  </el-tooltip>
                </div>
                <p class="path-pem-hint">与 Certbot 命名一致；上传导入的证书通常无此项。</p>
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
        <el-table-column label="操作" width="280" align="center">
          <template #default="scope">
            <div class="action-buttons">
              <el-tooltip content="下载证书包（ZIP）" placement="top">
                <el-button
                  circle
                  size="small"
                  type="info"
                  class="action-icon-btn"
                  :loading="scope.row._downloading"
                  @click="handleDownload(scope.row)"
                >
                  <el-icon><Download /></el-icon>
                </el-button>
              </el-tooltip>
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
            <span class="dns-alert-title">请在域名 DNS 控制台新增 1 条 TXT 记录（把下面字段一字不差填进去）。同一未完成会话内记录值固定；刷新后点「恢复未完成」或再次「下一步」均可复用。</span>
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

        <el-form-item v-if="requestForm.validation_method === 'dns'" label=" ">
          <el-button type="primary" link @click="tryRestoreDnsSession">
            恢复未完成的 DNS 验证（刷新页面后记录值不变）
          </el-button>
          <div class="form-tip">同一域名在服务端会话未结束前会复用同一组 TXT；请勿反复点「下一步」以免启动新验证。</div>
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

    <!-- 迁移与自动续签向导 -->
    <el-dialog
      v-model="migrateWizardVisible"
      title="迁移与自动续签"
      width="620px"
      top="5vh"
      :close-on-click-modal="false"
      class="cert-migrate-wizard-dialog"
      @closed="resetMigrateWizard"
    >
      <el-steps :active="migrateStep" finish-status="success" align-center class="migrate-steps">
        <el-step title="导出" description="在原环境保存证书" />
        <el-step title="导入" description="上传到本系统" />
        <el-step title="自动续签" description="申请 Let’s Encrypt" />
      </el-steps>

      <!-- 步骤 0：导出说明 -->
      <div v-show="migrateStep === 0" class="migrate-panel">
        <p class="migrate-panel-text">
          在<strong>原服务器</strong>或旧面板中，将证书链与私钥保存到本地（常见为 <code>fullchain.pem</code> / <code>privkey.pem</code>，Certbot 一般在
          <code>/etc/letsencrypt/live/域名/</code>）。
        </p>
        <ul class="migrate-panel-list">
          <li>妥善保管私钥，不要泄露。</li>
          <li>无需整包迁移 Certbot 目录，导出文件即可。</li>
        </ul>
        <el-button size="small" type="primary" plain @click="handleCopyMigrateExportHint">
          复制说明（发给同事）
        </el-button>

        <div class="migrate-le-export-block">
          <p class="migrate-le-export-title">本机已有 Certbot？从 live 目录导出（迁出到另一台）</p>
          <p class="migrate-panel-text migrate-le-export-desc">
            当前 WebUI 所在服务器若存在 <code>/etc/letsencrypt/live/</code>（例如 Docker 挂载了宿主机证书），可选中证书目录名，下载包含 <code>fullchain.pem</code>、<code>privkey.pem</code> 的 ZIP；在<strong>另一台</strong>打开本页「上传证书」或向导下一步即可导入，实现双机互迁。
          </p>
          <div class="migrate-le-export-row">
            <el-select
              v-model="letsencryptExportDomain"
              class="migrate-le-select"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="选择或输入 live 子目录名（certbot 证书名）"
              :loading="letsencryptLiveListLoading"
            >
              <el-option
                v-for="name in letsencryptLiveDomains"
                :key="name"
                :label="name"
                :value="name"
              />
            </el-select>
            <el-button
              type="primary"
              :loading="letsencryptExporting"
              :disabled="!letsencryptExportDomain || !String(letsencryptExportDomain).trim()"
              @click="handleExportLetsencryptLive"
            >
              <el-icon><Download /></el-icon>
              导出 ZIP
            </el-button>
          </div>
          <p v-if="letsencryptLiveHint" class="migrate-le-hint">{{ letsencryptLiveHint }}</p>
        </div>

        <el-alert type="info" :closable="false" show-icon class="migrate-inline-alert">
          <template #title>
            <span class="migrate-alert-inline">没有旧证书？可直接在本系统申请证书，签发后默认开启自动续期。</span>
          </template>
        </el-alert>
      </div>

      <!-- 步骤 1：导入 -->
      <div v-show="migrateStep === 1" class="migrate-panel">
        <el-form
          :model="migrateForm"
          :rules="migrateUploadRules"
          ref="migrateFormRef"
          label-width="90px"
          class="compact-form"
        >
          <el-form-item label="域名" prop="domain">
            <el-input
              v-model="migrateForm.domain"
              placeholder="例如：example.com"
              :disabled="!!migrateForm.certId"
            />
            <div v-if="migrateForm.certId" class="form-tip">已从向导导入，修改文件请直接点「完成导入」更新</div>
          </el-form-item>
          <el-form-item label="上传方式">
            <el-radio-group v-model="migrateForm.mode" size="small">
              <el-radio-button label="files">文件</el-radio-button>
              <el-radio-button label="archive">压缩包</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <template v-if="migrateForm.mode === 'files'">
            <el-form-item label="证书" required>
              <el-upload
                ref="migrateCertUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleMigrateCertFileChange"
                :on-remove="handleMigrateCertFileRemove"
                accept=".crt,.pem,.cer"
                :show-file-list="false"
              >
                <el-button size="small" type="primary">
                  <el-icon><FolderOpened /></el-icon>
                  选择证书
                </el-button>
              </el-upload>
              <div v-if="migrateForm.certFile" class="file-selected-compact">
                <span class="file-name-text">{{ migrateForm.certFile?.name || migrateForm.certFile?.raw?.name }}</span>
                <el-button size="small" text type="danger" @click="handleMigrateCertFileRemove">×</el-button>
              </div>
            </el-form-item>
            <el-form-item label="私钥" required>
              <el-upload
                ref="migrateKeyUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleMigrateKeyFileChange"
                :on-remove="handleMigrateKeyFileRemove"
                accept=".key,.pem"
                :show-file-list="false"
              >
                <el-button size="small" type="primary">
                  <el-icon><FolderOpened /></el-icon>
                  选择私钥
                </el-button>
              </el-upload>
              <div v-if="migrateForm.keyFile" class="file-selected-compact">
                <span class="file-name-text">{{ migrateForm.keyFile?.name || migrateForm.keyFile?.raw?.name }}</span>
                <el-button size="small" text type="danger" @click="handleMigrateKeyFileRemove">×</el-button>
              </div>
            </el-form-item>
          </template>
          <template v-else>
            <el-form-item label="压缩包" required>
              <el-upload
                ref="migrateArchiveUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleMigrateArchiveFileChange"
                :on-remove="handleMigrateArchiveFileRemove"
                accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2"
                :show-file-list="false"
              >
                <el-button size="small" type="primary">
                  <el-icon><FolderOpened /></el-icon>
                  选择压缩包
                </el-button>
              </el-upload>
              <div v-if="migrateForm.archiveFile" class="file-selected-compact">
                <span class="file-name-text">{{ migrateForm.archiveFile.name }}</span>
                <el-button size="small" text type="danger" @click="handleMigrateArchiveFileRemove">×</el-button>
              </div>
              <div class="upload-tip-small">支持 zip、tar.gz 等；可自动识别域名</div>
            </el-form-item>
          </template>
        </el-form>
      </div>

      <!-- 步骤 2：自动续签 -->
      <div v-show="migrateStep === 2" class="migrate-panel">
        <p class="migrate-panel-text">
          导入的证书<strong>不会</strong>被本机 Certbot 自动续签。若希望由本系统<strong>定时自动续签</strong>，请使用 Let’s Encrypt 在本机<strong>重新申请</strong>同名域名证书（签发成功后会开启自动续期）。
        </p>
        <el-alert v-if="migrateForm.certId" type="warning" :closable="false" show-icon class="migrate-inline-alert">
          <template #title>
            <span class="migrate-alert-inline">已导入一条记录。点击下方「申请证书」时，将先删除该导入记录，再打开申请向导（避免域名重复）。</span>
          </template>
        </el-alert>
        <p class="migrate-panel-text muted">
          若无需自动续签，可关闭向导，继续使用已导入证书，到期前再导出替换即可。
        </p>
      </div>

      <template #footer>
        <div class="migrate-wizard-footer">
          <template v-if="migrateStep === 0">
            <el-button type="info" @click="migrateWizardVisible = false">取消</el-button>
            <el-button type="primary" @click="migrateGoStep(1)">
              下一步：导入证书
            </el-button>
            <el-button type="success" link @click="openRequestFromMigrateShortcut">
              无旧证书，直接申请（推荐自动续签）
            </el-button>
          </template>
          <template v-else-if="migrateStep === 1">
            <el-button @click="migrateGoStep(0)">上一步</el-button>
            <el-button type="primary" :loading="migrateUploading" :disabled="isMigrateUploadDisabled" @click="handleMigrateUploadSubmit">
              <el-icon><Check /></el-icon>
              完成导入
            </el-button>
          </template>
          <template v-else>
            <el-button @click="migrateGoStep(1)">上一步</el-button>
            <el-button type="info" plain :loading="testingAutoRenewEnv" @click="handleTestAutoRenewEnv">
              测试自动续签环境
            </el-button>
            <el-button type="primary" @click="goToRequestCertFromMigrate">
              申请证书并启用自动续签
            </el-button>
            <el-button type="success" plain @click="finishMigrateWizard">完成</el-button>
          </template>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, onBeforeUnmount } from 'vue'
import { certificatesApi } from '../api/certificates'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentAdd, UploadFilled, RefreshRight, Delete, FolderOpened, CloseBold, Check, CopyDocument, CircleCheck, Download, Operation, Promotion } from '@element-plus/icons-vue'
import { formatDateTime } from '../utils/date'

const certificateList = ref([])
/** 默认折叠，避免占满首屏；需要时客户自行展开 */
const migrationGuideOpen = ref([])
const testingAutoRenewEnv = ref(false)
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref(null)
const certUploadRef = ref(null)
const keyUploadRef = ref(null)
const archiveUploadRef = ref(null)
const copyTextDialogVisible = ref(false)
const copyTextContent = ref('')

/** 迁移与自动续签向导 */
const migrateWizardVisible = ref(false)
const migrateStep = ref(0)
const migrateUploading = ref(false)
const migrateFormRef = ref(null)
const migrateCertUploadRef = ref(null)
const migrateKeyUploadRef = ref(null)
const migrateArchiveUploadRef = ref(null)
const migrateForm = ref({
  domain: '',
  certFile: null,
  keyFile: null,
  archiveFile: null,
  mode: 'files',
  certId: null
})

/** 向导内：从本机 /etc/letsencrypt/live 导出 */
const letsencryptLiveDomains = ref([])
const letsencryptLiveListLoading = ref(false)
const letsencryptLiveHint = ref('')
const letsencryptExportDomain = ref('')
const letsencryptExporting = ref(false)

const MIGRATE_EXPORT_HINT_TEXT =
  '【证书迁移】在原服务器取出证书链与私钥（Certbot 一般在 /etc/letsencrypt/live/<证书目录名>/ 的 fullchain.pem、privkey.pem）。若导出方就是本 WebUI 所在服务器且已挂载该目录，可在「迁移与自动续签」向导第一步直接下载 ZIP。在目标系统用「上传证书」或同一向导导入。若需目标机 Certbot 自动续签，导入后在向导最后一步点「申请证书并启用自动续签」。'

const migrateGoStep = (n) => {
  migrateStep.value = n
}

const migrateUploadRules = {
  domain: [
    {
      required: true,
      message: '请输入域名或上传压缩包自动识别',
      trigger: 'blur',
      validator: (rule, value, callback) => {
        if (migrateForm.value.mode === 'archive' && !value) {
          callback()
        } else if (!value) {
          callback(new Error('请输入域名'))
        } else if (
          !/^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/.test(
            value
          )
        ) {
          callback(new Error('请输入有效的域名'))
        } else {
          callback()
        }
      }
    }
  ]
}

const isMigrateUploadDisabled = computed(() => {
  if (migrateForm.value.mode === 'archive') {
    return !migrateForm.value.archiveFile
  }
  if (!migrateForm.value.domain) return true
  return !migrateForm.value.certFile || !migrateForm.value.keyFile
})

const fetchLetsencryptLiveDomains = async () => {
  letsencryptLiveListLoading.value = true
  letsencryptLiveHint.value = ''
  try {
    const res = await certificatesApi.listLetsencryptLiveDomains()
    if (res && res.success) {
      letsencryptLiveDomains.value = Array.isArray(res.domains) ? res.domains : []
      letsencryptLiveHint.value = res.hint || ''
    } else {
      letsencryptLiveDomains.value = []
    }
  } catch (e) {
    letsencryptLiveDomains.value = []
    letsencryptLiveHint.value =
      typeof e?.detail === 'string' ? e.detail : e?.message || '无法获取 live 目录列表'
  } finally {
    letsencryptLiveListLoading.value = false
  }
}

const openMigrateWizard = () => {
  migrateGoStep(0)
  migrateForm.value = {
    domain: '',
    certFile: null,
    keyFile: null,
    archiveFile: null,
    mode: 'files',
    certId: null
  }
  if (migrateCertUploadRef.value) migrateCertUploadRef.value.clearFiles()
  if (migrateKeyUploadRef.value) migrateKeyUploadRef.value.clearFiles()
  if (migrateArchiveUploadRef.value) migrateArchiveUploadRef.value.clearFiles()
  letsencryptExportDomain.value = ''
  letsencryptLiveDomains.value = []
  letsencryptLiveHint.value = ''
  migrateWizardVisible.value = true
  fetchLetsencryptLiveDomains()
}

const resetMigrateWizard = () => {
  migrateGoStep(0)
  migrateForm.value = {
    domain: '',
    certFile: null,
    keyFile: null,
    archiveFile: null,
    mode: 'files',
    certId: null
  }
  if (migrateCertUploadRef.value) migrateCertUploadRef.value.clearFiles()
  if (migrateKeyUploadRef.value) migrateKeyUploadRef.value.clearFiles()
  if (migrateArchiveUploadRef.value) migrateArchiveUploadRef.value.clearFiles()
  letsencryptExportDomain.value = ''
  letsencryptLiveHint.value = ''
}

const handleCopyMigrateExportHint = async () => {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(MIGRATE_EXPORT_HINT_TEXT)
      ElMessage.success('已复制到剪贴板')
    } else {
      copyTextContent.value = MIGRATE_EXPORT_HINT_TEXT
      copyTextDialogVisible.value = true
    }
  } catch {
    copyTextContent.value = MIGRATE_EXPORT_HINT_TEXT
    copyTextDialogVisible.value = true
  }
}

const openRequestFromMigrateShortcut = () => {
  migrateWizardVisible.value = false
  handleRequest()
}

const handleMigrateCertFileChange = (file) => {
  migrateForm.value.certFile = file.raw
}

const handleMigrateCertFileRemove = () => {
  migrateForm.value.certFile = null
  if (migrateCertUploadRef.value) migrateCertUploadRef.value.clearFiles()
}

const handleMigrateKeyFileChange = (file) => {
  migrateForm.value.keyFile = file.raw
}

const handleMigrateKeyFileRemove = () => {
  migrateForm.value.keyFile = null
  if (migrateKeyUploadRef.value) migrateKeyUploadRef.value.clearFiles()
}

const handleMigrateArchiveFileChange = async (file) => {
  migrateForm.value.archiveFile = file.raw
  if (file.raw) {
    try {
      const response = await certificatesApi.parseCertificateArchive(file.raw)
      if (response.domain) {
        migrateForm.value.domain = response.domain
        ElMessage.success(`已自动识别域名: ${response.domain}`)
      }
    } catch {
      /* ignore */
    }
  }
}

const handleMigrateArchiveFileRemove = () => {
  migrateForm.value.archiveFile = null
  if (migrateArchiveUploadRef.value) migrateArchiveUploadRef.value.clearFiles()
}

const handleMigrateUploadSubmit = async () => {
  if (!migrateFormRef.value) return
  try {
    await migrateFormRef.value.validate()
  } catch {
    return
  }

  const mode = migrateForm.value.mode
  if (mode === 'archive') {
    if (!migrateForm.value.archiveFile) {
      ElMessage.warning('请选择压缩包')
      return
    }
  } else if (!migrateForm.value.certFile || !migrateForm.value.keyFile) {
    ElMessage.warning('请选择证书与私钥文件')
    return
  }

  migrateUploading.value = true
  try {
    let res
    if (mode === 'archive') {
      res = await certificatesApi.uploadCertificateArchive(
        migrateForm.value.domain,
        migrateForm.value.archiveFile,
        false,
        migrateForm.value.certId
      )
      ElMessage.success(migrateForm.value.certId ? '证书已更新' : '压缩包导入成功')
    } else {
      res = await certificatesApi.uploadCertificate(
        migrateForm.value.domain,
        migrateForm.value.certFile,
        migrateForm.value.keyFile,
        false,
        migrateForm.value.certId
      )
      ElMessage.success(migrateForm.value.certId ? '证书已更新' : '证书导入成功')
    }
    const cert = res.certificate || {}
    migrateForm.value.certId = cert.id ?? migrateForm.value.certId
    migrateForm.value.domain = cert.domain || migrateForm.value.domain
    migrateGoStep(2)
    await loadCertificates()
  } catch (error) {
    ElMessage.error(error.detail || error.message || '导入失败')
  } finally {
    migrateUploading.value = false
  }
}

const goToRequestCertFromMigrate = async () => {
  const domain = (migrateForm.value.domain || '').trim()
  if (!domain) {
    ElMessage.warning('缺少域名')
    return
  }
  if (migrateForm.value.certId) {
    try {
      await ElMessageBox.confirm(
        '将删除本向导中已导入的证书记录（磁盘上的证书与私钥文件也会删除），再打开「申请证书」向导。是否继续？',
        '申请证书并启用自动续签',
        { type: 'warning', confirmButtonText: '删除并继续' }
      )
    } catch (e) {
      if (e === 'cancel') return
      return
    }
    try {
      await certificatesApi.deleteCertificate(migrateForm.value.certId)
      ElMessage.success('已删除，请完成证书申请')
      migrateForm.value.certId = null
      await loadCertificates()
    } catch (e) {
      ElMessage.error(e?.detail || e?.message || '删除失败')
      return
    }
  }
  migrateWizardVisible.value = false
  requestForm.value = {
    domain,
    email: '',
    validation_method: 'http'
  }
  resetRequestWizard()
  requestDialogVisible.value = true
}

const finishMigrateWizard = () => {
  migrateWizardVisible.value = false
}

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

/** 浏览器刷新后恢复同一组 TXT（与服务端挂起的 certbot 会话对应） */
const DNS_SESSION_KEY = 'nginx-webui-cert-dns-v1'

const saveDnsSession = () => {
  const domain = requestForm.value.domain?.trim().toLowerCase()
  if (!domain || !dnsJobId.value) return
  try {
    sessionStorage.setItem(
      DNS_SESSION_KEY,
      JSON.stringify({
        domain,
        job_id: dnsJobId.value,
        record_name: dnsRecordName.value,
        record_value: dnsRecordValue.value,
        ts: Date.now()
      })
    )
  } catch (_) {
    /* ignore */
  }
}

const clearDnsSession = () => {
  try {
    sessionStorage.removeItem(DNS_SESSION_KEY)
  } catch (_) {
    /* ignore */
  }
}

const tryRestoreDnsSession = async () => {
  const domain = requestForm.value.domain?.trim()
  if (!domain) {
    ElMessage.warning('请先填写域名')
    return
  }
  requesting.value = true
  try {
    const p = await certificatesApi.dnsChallengePending(domain)
    if (p.success && p.job_id && p.record_name && p.record_value) {
      dnsJobId.value = p.job_id
      dnsRecordName.value = p.record_name
      dnsRecordValue.value = p.record_value
      dnsWizardStep.value = 1
      dnsVerified.value = false
      dnsLastCheckMsg.value = ''
      saveDnsSession()
      ElMessage.success('已恢复：记录值与当前会话一致')
    } else {
      clearDnsSession()
      ElMessage.warning(
        p.message || '服务端已无未完成会话，请重新点击「下一步：获取 DNS 要求」'
      )
    }
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '恢复失败')
  } finally {
    requesting.value = false
  }
}

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
  clearDnsSession()
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
      saveDnsSession()
      ElMessage.success(
        res.reused
          ? '已复用当前验证会话，记录值未变，请继续配置 DNS'
          : '已获取 DNS 验证要求，请添加 TXT 记录'
      )
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
      clearDnsSession()
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

const parseBlobError = async (blob) => {
  if (!blob || typeof blob.text !== 'function') return '下载失败'
  try {
    const text = await blob.text()
    const j = JSON.parse(text)
    if (typeof j.detail === 'string') return j.detail
    if (Array.isArray(j.detail)) {
      return j.detail.map((x) => x.msg || JSON.stringify(x)).join('; ')
    }
    return j.message || text || '下载失败'
  } catch {
    return '下载失败'
  }
}

const handleDownload = async (cert) => {
  cert._downloading = true
  try {
    const blob = await certificatesApi.downloadCertificateBundle(cert.id)
    if (!(blob instanceof Blob)) {
      ElMessage.error('下载失败')
      return
    }
    if (blob.type && blob.type.includes('application/json')) {
      ElMessage.error(await parseBlobError(blob))
      return
    }
    const safeName = String(cert.domain || 'certificate').replace(/[^\w.-]+/g, '_')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.style.display = 'none'
    a.href = url
    a.download = `${safeName}-ssl.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('已开始下载')
  } catch (error) {
    const data = error?.data
    if (data instanceof Blob) {
      ElMessage.error(await parseBlobError(data))
    } else {
      ElMessage.error(error?.detail || error?.message || '下载失败')
    }
  } finally {
    cert._downloading = false
  }
}

const handleExportLetsencryptLive = async () => {
  const d = String(letsencryptExportDomain.value || '').trim()
  if (!d) {
    ElMessage.warning('请选择或输入 live 目录名（certbot 证书名）')
    return
  }
  letsencryptExporting.value = true
  try {
    const blob = await certificatesApi.exportLetsencryptLiveBundle(d)
    if (!(blob instanceof Blob)) {
      ElMessage.error('导出失败')
      return
    }
    if (blob.type && blob.type.includes('application/json')) {
      ElMessage.error(await parseBlobError(blob))
      return
    }
    const safeName = d.replace(/[^\w.-]+/g, '_')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.style.display = 'none'
    a.href = url
    a.download = `${safeName}-letsencrypt-live.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('已开始下载，可在另一台通过「上传证书」导入该 ZIP')
  } catch (error) {
    const data = error?.data
    if (data instanceof Blob) {
      ElMessage.error(await parseBlobError(data))
    } else {
      ElMessage.error(error?.detail || error?.message || '导出失败')
    }
  } finally {
    letsencryptExporting.value = false
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

const handleTestAutoRenewEnv = async () => {
  testingAutoRenewEnv.value = true
  try {
    const res = await certificatesApi.testAutoRenewEnvironment()
    const checks = res.checks || []
    const checkRows = checks
      .map(
        (c) =>
          `<tr><td style="padding:4px 8px;vertical-align:top">${c.ok ? '✓' : '✗'}</td><td style="padding:4px 8px"><strong>${escapeHtml(c.label)}</strong></td><td style="padding:4px 8px;word-break:break-all">${escapeHtml(c.detail)}</td></tr>`
      )
      .join('')
    const sug = res.suggestions && res.suggestions.length
      ? `<p style="margin-top:12px;font-weight:600">建议</p><ul style="margin:4px 0;padding-left:18px;text-align:left">${res.suggestions.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>`
      : ''
    const code = res.error_code
      ? `<p style="font-size:12px;color:#909399;margin-top:8px">错误代码: ${escapeHtml(res.error_code)}</p>`
      : ''
    const out = res.dry_run_output
      ? `<details style="margin-top:12px;text-align:left"><summary style="cursor:pointer">certbot dry-run 输出</summary><pre style="white-space:pre-wrap;word-break:break-all;font-size:11px;max-height:240px;overflow:auto;margin-top:8px">${escapeHtml(res.dry_run_output)}</pre></details>`
      : ''
    const hint =
      '<p style="font-size:12px;color:#909399;margin-top:10px;line-height:1.5">说明：本应用在每天凌晨 3:00 通过同一 <code>certbot renew</code> 为已开启「自动续期」的证书续签并同步到 ssl 目录；本检测仅模拟续签，不修改磁盘证书。</p>'
    ElMessageBox.alert(
      `<div style="text-align:left;max-width:520px">
        <p style="font-weight:600;margin-bottom:8px">${escapeHtml(res.summary || (res.environment_ready ? '检测完成' : '检测未通过'))}</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">${checkRows}</table>
        ${code}${sug}${out}${hint}
      </div>`,
      '自动续签环境检测',
      {
        dangerouslyUseHTMLString: true,
        type: res.environment_ready ? 'success' : 'warning',
        customClass: 'cert-fail-msgbox'
      }
    )
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '检测失败')
  } finally {
    testingAutoRenewEnv.value = false
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

/** 若 ssl_dir 下存在 Certbot 风格的 fullchain.pem / privkey.pem，生成备用 nginx 片段 */
const nginxPemSnippet = (row) => {
  if (!row?.fullchain_pem_path || !row?.privkey_pem_path) return ''
  return `ssl_certificate ${row.fullchain_pem_path};\nssl_certificate_key ${row.privkey_pem_path};`
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

.cert-migrate-wizard-dialog :deep(.el-dialog__body) {
  max-height: calc(85vh - 140px);
  overflow-y: auto;
  padding-top: 12px;
}

.migrate-steps {
  margin-bottom: 20px;
}

.migrate-panel {
  min-height: 100px;
}

.migrate-panel-text {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}

.migrate-panel-text.muted {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.migrate-panel-text code {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}

.migrate-panel-list {
  margin: 0 0 14px;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.migrate-inline-alert {
  margin-top: 16px;
}

.migrate-le-export-block {
  margin-top: 20px;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}

.migrate-le-export-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.migrate-le-export-desc {
  margin-bottom: 12px !important;
  font-size: 12px;
  line-height: 1.6;
}

.migrate-le-export-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.migrate-le-select {
  flex: 1;
  min-width: 200px;
}

.migrate-le-hint {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.migrate-alert-inline {
  font-size: 13px;
  line-height: 1.5;
}

.migrate-wizard-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
  width: 100%;
}

.cert-migration-collapse {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.cert-migration-collapse :deep(.el-collapse-item__header) {
  padding: 12px 16px;
  font-weight: 500;
  align-items: center;
  gap: 8px;
}

.cert-migration-collapse :deep(.el-collapse-item__wrap) {
  border-top: 1px solid var(--el-border-color-lighter);
}

.cert-migration-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 16px;
}

.migration-guide-title {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.migration-guide-tag {
  margin-left: 8px;
  font-weight: normal;
}

.migration-guide-body {
  font-size: 13px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
  padding: 0 4px;
}

.migration-guide-lead {
  margin: 0 0 12px;
}

.migration-guide-steps {
  margin: 0 0 14px;
  padding-left: 20px;
}

.migration-guide-steps li {
  margin-bottom: 8px;
}

.migration-guide-steps code {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}

.migration-guide-alert {
  margin-bottom: 12px;
}

.migration-alert-title {
  font-size: 13px;
}

.migration-alert-text {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
}

.migration-guide-foot {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.migration-guide-foot code {
  font-size: 11px;
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

.path-text-missing {
  color: #f56c6c;
}

.path-disk-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.path-meta-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  margin-right: 2px;
}

.path-pem-block {
  padding-top: 4px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.path-pem-hint {
  margin: 6px 0 0;
  font-size: 11px;
  color: #909399;
  line-height: 1.4;
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

