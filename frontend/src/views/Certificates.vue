<template>
  <div class="certificates-page page-shell">
    <ui-card>
      <template #header>
        <div class="card-header">
          <div>
            <span class="card-title">证书管理</span>
            <span class="card-subtitle">证书以域名为标识</span>
          </div>
          <div class="button-group">
            <ui-button type="primary" @click="handleRequest">
              <ui-icon><DocumentAdd /></ui-icon>
              <span class="btn-label">申请证书</span>
            </ui-button>
            <ui-button type="cyan" @click="handleUpload">
              <ui-icon><UploadFilled /></ui-icon>
              <span class="btn-label">上传证书</span>
            </ui-button>
            <ui-tooltip content="从原环境导出证书后在此导入，并引导在本机申请 Let’s Encrypt 以启用自动续签" placement="bottom">
              <ui-button type="success" plain @click="openMigrateWizard">
                <ui-icon><Promotion /></ui-icon>
                <span class="btn-label">迁移与自动续签</span>
              </ui-button>
            </ui-tooltip>
            <ui-tooltip
              content="执行 certbot 模拟续签（dry-run），检测本机是否具备自动续签条件，不会改动真实证书"
              placement="bottom"
            >
              <ui-button
                type="info"
                plain
                :loading="testingAutoRenewEnv"
                @click="handleTestAutoRenewEnv"
              >
                <ui-icon><Operation /></ui-icon>
                <span class="btn-label">测试自动续签环境</span>
              </ui-button>
            </ui-tooltip>
            <ui-tooltip
              content="取消当前挂起的 DNS 验证会话，释放 Certbot 占用"
              placement="bottom"
            >
              <ui-button
                type="warning"
                plain
                :loading="clearingCertbotSessions"
                @click="handleClearCertbotSessions"
              >
                <ui-icon><CloseBold /></ui-icon>
                <span class="btn-label">清理卡住任务</span>
              </ui-button>
            </ui-tooltip>
          </div>
        </div>
      </template>

      <ui-collapse v-model="migrationGuideOpen" class="cert-migration-collapse">
        <ui-collapse-item name="guide">
          <template #title>
            <span class="migration-guide-title">导出证书 → 在本系统导入（与自动续签说明）</span>
            <ui-tag size="small" type="info" class="migration-guide-tag">常见流程</ui-tag>
          </template>
          <div class="migration-guide-body">
            <p class="migration-guide-lead">
              一般<strong>不必迁移整包 Certbot</strong>：在原环境<strong>导出</strong>证书链与私钥（如 <code>fullchain.pem</code>、<code>privkey.pem</code>），到本页使用<strong>上传证书</strong>完成<strong>导入</strong>即可启用 HTTPS。
            </p>
            <ol class="migration-guide-steps">
              <li>
                <strong>导出</strong>：从原服务器 <code>/etc/letsencrypt/live/&lt;证书目录名&gt;/</code>（一般为 <code>fullchain.pem</code>、<code>privkey.pem</code>）或云厂商面板下载；若<strong>本机</strong>已挂载该目录，可在「<strong>迁移与自动续签</strong>」向导第一步<strong>一键导出 ZIP</strong>（固定扫描该目录，多本时默认第一本），带到另一台用「上传证书」导入。
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
            <ui-alert type="info" :closable="false" show-icon class="migration-guide-alert">
              <template #title>
                <span class="migration-alert-title">与「仅上传」的关系</span>
              </template>
              <p class="migration-alert-text">
                导出再导入与手动上传是同一类操作：都能立刻用起来；<strong>自动续签</strong>依赖本机 Certbot 已签发该域名，通常要在本系统<strong>申请证书</strong>一次，而不是只靠导入文件。
              </p>
            </ui-alert>
            <p class="migration-guide-foot">
              需要分步引导时，可直接使用上方「<strong>迁移与自动续签</strong>」按钮打开向导。可复制给客户的一段话与更多说明见
              <code>docs/cert-migration.md</code>。
            </p>
          </div>
        </ui-collapse-item>
      </ui-collapse>

      <ui-table :data="certificateList" style="width: 100%">
        <ui-table-column prop="domain" label="证书名称（域名）" width="200" fixed="left">
          <template #default="scope">
            <div class="domain-cell">
              <ui-tag type="primary" size="small">{{ scope.row.domain }}</ui-tag>
              <ui-tag
                v-if="!isIssuedCert(scope.row)"
                :type="certStatusType(scope.row.status)"
                size="small"
              >
                {{ certStatusLabel(scope.row.status) }}
              </ui-tag>
            </div>
          </template>
        </ui-table-column>
        <ui-table-column label="证书路径 / 私钥路径" min-width="600">
          <template #default="scope">
            <div v-if="isIssuedCert(scope.row)" class="paths-cell">
              <div class="path-item">
                <span class="path-label">证书：</span>
                <span class="path-text" :title="scope.row.cert_path || '-'">
                  {{ scope.row.cert_path || '-' }}
                </span>
                <ui-tooltip content="复制证书路径" :show-after="200">
                  <ui-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.cert_path"
                    @click="handleCopy(scope.row.cert_path)"
                  />
                </ui-tooltip>
              </div>
              <div class="path-item">
                <span class="path-label">私钥：</span>
                <span class="path-text" :title="scope.row.key_path || '-'">
                  {{ scope.row.key_path || '-' }}
                </span>
                <ui-tooltip content="复制私钥路径" :show-after="200">
                  <ui-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.key_path"
                    @click="handleCopy(scope.row.key_path)"
                  />
                </ui-tooltip>
              </div>
              <div class="path-item">
                <span class="path-label">PEM：</span>
                <span
                  class="path-text"
                  :title="scope.row.pem_path || '-'"
                >
                  {{ scope.row.pem_path || '-' }}
                </span>
                <ui-tooltip content="复制证书链 PEM 路径（与 .crt 同内容，常用作 ssl_certificate）" :show-after="200">
                  <ui-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.pem_path"
                    @click="handleCopy(scope.row.pem_path)"
                  />
                </ui-tooltip>
              </div>
            </div>
            <div v-else class="paths-cell">
              <div class="path-item">
                <span class="path-label">DNS：</span>
                <span class="path-text" :title="scope.row.dns_record_name || '-'">
                  {{ scope.row.dns_record_name || '-' }}
                </span>
                <ui-tooltip content="复制 TXT 记录名" :show-after="200">
                  <ui-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.dns_record_name"
                    @click="handleCopy(scope.row.dns_record_name)"
                  />
                </ui-tooltip>
              </div>
              <div class="path-item">
                <span class="path-label">TXT：</span>
                <span class="path-text" :title="scope.row.dns_record_value || '-'">
                  {{ scope.row.dns_record_value || '-' }}
                </span>
                <ui-tooltip content="复制 TXT 记录值" :show-after="200">
                  <ui-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.dns_record_value"
                    @click="handleCopy(scope.row.dns_record_value)"
                  />
                </ui-tooltip>
              </div>
              <div v-if="scope.row.issue_error || scope.row.issue_output" class="path-item">
                <span class="path-label">进度：</span>
                <span class="path-text" :title="scope.row.issue_error || scope.row.issue_output">
                  {{ scope.row.issue_error || scope.row.issue_output }}
                </span>
              </div>
            </div>
          </template>
        </ui-table-column>
        <ui-table-column label="状态" width="120" align="center">
          <template #default="scope">
            <ui-tag :type="certStatusType(scope.row.status)" size="small">
              {{ certStatusLabel(scope.row.status) }}
            </ui-tag>
          </template>
        </ui-table-column>
        <ui-table-column prop="valid_to" label="过期时间" width="180" align="center">
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
        </ui-table-column>
        <ui-table-column label="自动续期" width="100" align="center">
          <template #default="scope">
            <ui-switch
              v-model="scope.row.auto_renew"
              @change="handleToggleAutoRenew(scope.row)"
              :loading="scope.row._toggling"
              :disabled="!isIssuedCert(scope.row)"
              size="small"
            />
          </template>
        </ui-table-column>
        <ui-table-column label="操作" width="280" align="center">
          <template #default="scope">
            <div class="action-buttons">
              <ui-tooltip content="下载证书包（ZIP）" placement="top">
                <ui-button
                  circle
                  size="small"
                  type="info"
                  class="action-icon-btn"
                  :loading="scope.row._downloading"
                  :disabled="!isIssuedCert(scope.row)"
                  @click="handleDownload(scope.row)"
                >
                  <ui-icon><Download /></ui-icon>
                </ui-button>
              </ui-tooltip>
              <ui-tooltip content="重新上传" placement="top">
                <ui-button
                  circle
                  size="small"
                  type="primary"
                  class="action-icon-btn"
                  :disabled="!isIssuedCert(scope.row)"
                  @click="handleReupload(scope.row)"
                >
                  <ui-icon><UploadFilled /></ui-icon>
                </ui-button>
              </ui-tooltip>
              <ui-tooltip content="续期" placement="top">
                <ui-button
                  circle
                  size="small"
                  type="warning"
                  class="action-icon-btn"
                  :disabled="!isIssuedCert(scope.row)"
                  @click="handleRenew(scope.row)"
                >
                  <ui-icon><RefreshRight /></ui-icon>
                </ui-button>
              </ui-tooltip>
              <ui-tooltip content="验证证书" placement="top">
                <ui-button
                  circle
                  size="small"
                  type="success"
                  class="action-icon-btn"
                  :loading="scope.row._verifying"
                  :disabled="!isIssuedCert(scope.row)"
                  @click="handleVerifyCert(scope.row)"
                >
                  <ui-icon><CircleCheck /></ui-icon>
                </ui-button>
              </ui-tooltip>
              <ui-tooltip content="删除" placement="top">
                <ui-button
                  circle
                  size="small"
                  type="danger"
                  class="action-icon-btn"
                  @click="handleDelete(scope.row)"
                >
                  <ui-icon><Delete /></ui-icon>
                </ui-button>
              </ui-tooltip>
            </div>
          </template>
        </ui-table-column>
      </ui-table>
    </ui-card>

    <!-- 申请证书对话框 -->
    <ui-dialog
      v-model="requestDialogVisible"
      title="申请 Let's Encrypt 免费证书"
      width="620px"
      top="6vh"
      :close-on-click-modal="false"
      class="cert-request-dialog"
      @closed="resetRequestWizard"
    >
      <ui-steps
        v-if="requestForm.validation_method === 'dns'"
        :active="dnsWizardStep"
        finish-status="success"
        align-center
        class="cert-request-steps"
      >
        <ui-step title="填写信息" />
        <ui-step title="配置 DNS 并验证" />
      </ui-steps>

      <!-- DNS 步骤 1：配置 TXT -->
      <div v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1" class="dns-wizard-panel">
        <ui-alert type="warning" :closable="false" show-icon style="margin-bottom: 12px;">
          <template #title>
            <span class="dns-alert-title">请在域名 DNS 控制台新增 1 条 TXT 记录（把下面字段一字不差填进去）。同一未完成会话内记录值固定；刷新后点「恢复未完成」或再次「下一步」均可复用。</span>
          </template>
        </ui-alert>
        <ui-card shadow="never" class="dns-guide-card">
          <template #header>
            <span class="dns-guide-title">第 1 步：进入域名 DNS 管理</span>
          </template>
          <ol class="dns-steps-list">
            <li>登录你的域名服务商控制台（在哪里买的域名就去哪里）</li>
            <li>找到域名 <span class="mono-text">{{ requestForm.domain || '-' }}</span> 的 DNS 解析页面</li>
            <li>点击“新增记录”或“添加解析”</li>
          </ol>
        </ui-card>

        <ui-card shadow="never" class="dns-guide-card">
          <template #header>
            <span class="dns-guide-title">第 2 步：按下表填写记录</span>
          </template>
          <ui-descriptions :column="1" border size="small" class="dns-rec-desc">
            <ui-descriptions-item label="记录类型">TXT</ui-descriptions-item>
            <ui-descriptions-item label="主机记录 / Name">
              <span class="mono-text">{{ dnsHostRecord || dnsRecordName || '-' }}</span>
              <ui-button size="small" text type="primary" :disabled="!dnsHostRecord && !dnsRecordName" @click="handleCopy(dnsHostRecord || dnsRecordName)">复制</ui-button>
              <div class="form-tip">如果平台要求填写完整主机名，也可填：{{ dnsRecordName || '-' }}</div>
            </ui-descriptions-item>
            <ui-descriptions-item label="记录值 / Value">
              <span class="mono-text dns-value">{{ dnsRecordValue || '-' }}</span>
              <ui-button size="small" text type="primary" :disabled="!dnsRecordValue" @click="handleCopy(dnsRecordValue)">复制</ui-button>
            </ui-descriptions-item>
            <ui-descriptions-item label="TTL">默认即可（建议 600 秒或 Auto）</ui-descriptions-item>
          </ui-descriptions>
          <ui-alert type="info" :closable="false" class="dns-field-tip" show-icon>
            <template #title>
              不同平台字段名可能叫：主机记录/记录名/Name、记录值/Value/内容，含义相同。
            </template>
          </ui-alert>
        </ui-card>

        <ui-card shadow="never" class="dns-guide-card">
          <template #header>
            <span class="dns-guide-title">第 3 步：保存并检测是否生效</span>
          </template>
          <p class="form-tip">保存后通常 1-10 分钟生效，最长可能更久。系统已保存为“待 DNS 生效”，会在后台自动检测并签发；你也可以留在这里手动检测。</p>
          <div class="dns-verify-row">
            <ui-checkbox v-model="dnsAutoPoll">每 5 秒自动检测一次</ui-checkbox>
            <ui-tag v-if="dnsVerified" type="success" size="small">TXT 已匹配，可点击“完成申请”</ui-tag>
            <ui-tag v-else-if="dnsLastCheckMsg" type="info" size="small">{{ dnsLastCheckMsg }}</ui-tag>
          </div>
          <ui-button type="primary" plain size="small" :loading="dnsChecking" @click="runDnsVerifyOnce">
            立即检测 DNS
          </ui-button>
          <ui-alert type="error" :closable="false" class="dns-troubleshoot" show-icon>
            <template #title>
              检测失败时请依次检查：1) 记录类型是否为 TXT；2) 主机记录是否填错（建议先用上方复制值）；3) 记录值是否有多余空格/换行；4) 是否改到了错误的域名。
            </template>
          </ui-alert>
        </ui-card>

        <div class="dns-help-links">
          <span class="form-tip">常见 DNS 控制台教程：</span>
          <ui-link type="primary" href="https://docs.dnspod.cn/dns/console/manage/" target="_blank" :underline="false">腾讯云 DNSPod</ui-link>
          <ui-link type="primary" href="https://help.aliyun.com/document_detail/29725.html" target="_blank" :underline="false">阿里云</ui-link>
          <ui-link type="primary" href="https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/" target="_blank" :underline="false">Cloudflare</ui-link>
        </div>
      </div>

      <!-- 表单：HTTP 或 DNS 步骤 0 -->
      <ui-form
        v-if="requestForm.validation_method !== 'dns' || dnsWizardStep === 0"
        :model="requestForm"
        :rules="requestRules"
        ref="requestFormRef"
        label-width="100px"
        class="compact-form"
      >
        <ui-form-item label="域名" prop="domain">
          <ui-input
            v-model="requestForm.domain"
            :placeholder="requestForm.validation_method === 'dns' ? '例如：example.com 或 *.example.com' : '例如：example.com'"
          />
          <div class="form-tip">
            主域名，将用于证书申请和 Nginx 配置；
            DNS 验证支持通配符（如 *.example.com），HTTP 验证不支持通配符
          </div>
        </ui-form-item>

        <ui-form-item label="邮箱地址" prop="email">
          <ui-input
            v-model="requestForm.email"
            placeholder="例如：admin@example.com"
          />
          <div class="form-tip">Let's Encrypt 会通过此邮箱发送证书到期通知</div>
        </ui-form-item>

        <ui-form-item label="验证方式" prop="validation_method">
          <ui-radio-group v-model="requestForm.validation_method" @change="onValidationMethodChange">
            <ui-radio value="http">
              <span>HTTP 验证</span>
              <div class="radio-desc">需要域名已解析到本服务器且 Nginx 正在运行，80 端口可访问</div>
            </ui-radio>
            <ui-radio value="dns">
              <span>DNS 验证</span>
              <div class="radio-desc">在域名 DNS 中添加 TXT 记录；适合无法开放 80 端口的场景</div>
            </ui-radio>
          </ui-radio-group>
        </ui-form-item>

        <ui-form-item v-if="requestForm.validation_method === 'dns'" label=" ">
          <ui-button type="primary" link @click="tryRestoreDnsSession">
            恢复未完成的 DNS 验证（刷新页面后记录值不变）
          </ui-button>
          <div class="form-tip">同一域名在服务端会话未结束前会复用同一组 TXT；请勿反复点「下一步」以免启动新验证。</div>
        </ui-form-item>

        <ui-alert
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
        </ui-alert>
      </ui-form>
      <template #footer>
        <span class="dialog-footer">
          <ui-button type="info" @click="requestDialogVisible = false">
            <ui-icon><CloseBold /></ui-icon>
            <span class="btn-label">取消</span>
          </ui-button>
          <ui-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1"
            @click="dnsWizardBack"
          >
            上一步
          </ui-button>
          <ui-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 0"
            type="primary"
            :loading="requesting"
            :disabled="isRequestDisabled"
            @click="handleDnsWizardNext"
          >
            <ui-icon><Check /></ui-icon>
            <span class="btn-label">下一步：获取 DNS 要求</span>
          </ui-button>
          <ui-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1"
            type="success"
            plain
            @click="saveDnsPendingAndClose"
          >
            保存并后台自动签发
          </ui-button>
          <ui-button
            v-if="requestForm.validation_method === 'dns' && dnsWizardStep === 1"
            type="primary"
            :loading="requesting"
            :disabled="!dnsVerified"
            @click="handleDnsCompleteIssue"
          >
            <ui-icon><Check /></ui-icon>
            <span class="btn-label">完成申请（签发证书）</span>
          </ui-button>
          <ui-button
            v-if="requestForm.validation_method === 'http'"
            type="primary"
            :loading="requesting"
            :disabled="isRequestDisabled"
            @click="handleRequestSubmitHttp"
          >
            <ui-icon><Check /></ui-icon>
            <span class="btn-label">申请证书</span>
          </ui-button>
        </span>
      </template>
    </ui-dialog>

    <!-- 上传证书对话框 -->
    <ui-dialog
      v-model="uploadDialogVisible"
      :title="uploadForm.certId ? '重新上传证书' : '上传证书'"
      :description="uploadForm.certId ? '替换当前域名的证书与私钥文件。' : '支持分别上传证书和私钥，也支持上传证书压缩包。'"
      width="600px"
      top="8vh"
      :close-on-click-modal="false"
      class="cert-upload-dialog"
    >
      <ui-form :model="uploadForm" :rules="uploadRules" ref="uploadFormRef" label-width="90px" class="compact-form">
        <ui-form-item label="域名" prop="domain">
          <ui-input
            v-model="uploadForm.domain" 
            :placeholder="uploadForm.certId ? '重新上传将替换现有证书' : '例如：example.com'"
            :disabled="!!uploadForm.certId"
          />
          <div v-if="uploadForm.certId" class="form-tip">
            将替换域名 {{ uploadForm.domain }} 的现有证书和私钥
          </div>
        </ui-form-item>
        
        <ui-form-item label="上传方式">
          <ui-radio-group v-model="uploadForm.mode" size="small">
            <ui-radio-button label="files">文件上传</ui-radio-button>
            <ui-radio-button label="archive">压缩包</ui-radio-button>
          </ui-radio-group>
        </ui-form-item>

        <!-- 文件上传模式 -->
        <template v-if="uploadForm.mode === 'files'">
          <ui-form-item label="证书文件" required>
            <ui-upload
              ref="certUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleCertFileChange"
              :on-remove="handleCertFileRemove"
              accept=".crt,.pem,.cer"
              :show-file-list="false"
            >
              <ui-button size="small" type="primary">
                <ui-icon><FolderOpened /></ui-icon>
                选择证书
              </ui-button>
            </ui-upload>
            <div v-if="uploadForm.certFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.certFile?.name || uploadForm.certFile?.raw?.name || '未知文件' }}</span>
              <ui-button size="small" text type="danger" @click="handleCertFileRemove">×</ui-button>
            </div>
            <div v-if="uploadForm.domain && uploadForm.certFile && !checkFileNameMatch(uploadForm.certFile?.name || uploadForm.certFile?.raw?.name, uploadForm.domain)" class="file-warning-compact">
              ⚠️ 文件名与域名不匹配
            </div>
          </ui-form-item>
          <ui-form-item label="私钥文件" required>
            <ui-upload
              ref="keyUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleKeyFileChange"
              :on-remove="handleKeyFileRemove"
              accept=".key,.pem"
              :show-file-list="false"
            >
              <ui-button size="small" type="primary">
                <ui-icon><FolderOpened /></ui-icon>
                选择私钥
              </ui-button>
            </ui-upload>
            <div v-if="uploadForm.keyFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.keyFile?.name || uploadForm.keyFile?.raw?.name || '未知文件' }}</span>
              <ui-button size="small" text type="danger" @click="handleKeyFileRemove">×</ui-button>
            </div>
            <div v-if="uploadForm.domain && uploadForm.keyFile && !checkFileNameMatch(uploadForm.keyFile?.name || uploadForm.keyFile?.raw?.name, uploadForm.domain)" class="file-warning-compact">
              ⚠️ 文件名与域名不匹配
            </div>
          </ui-form-item>
        </template>

        <!-- 压缩包模式 -->
        <template v-else>
          <ui-form-item label="压缩包" required>
            <ui-upload
              ref="archiveUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleArchiveFileChange"
              :on-remove="handleArchiveFileRemove"
              accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2"
              :show-file-list="false"
            >
              <ui-button size="small" type="primary">
                <ui-icon><FolderOpened /></ui-icon>
                选择压缩包
              </ui-button>
            </ui-upload>
            <div v-if="uploadForm.archiveFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.archiveFile.name }}</span>
              <ui-button size="small" text type="danger" @click="handleArchiveFileRemove">×</ui-button>
            </div>
            <div class="upload-tip-small">支持 zip、tar.gz、tar.bz2 格式，自动识别证书与私钥</div>
          </ui-form-item>
        </template>
      </ui-form>
      <template #footer>
        <span class="dialog-footer">
          <ui-button type="info" @click="uploadDialogVisible = false">
            <ui-icon><CloseBold /></ui-icon>
            <span class="btn-label">取消</span>
          </ui-button>
            <ui-button
              type="primary"
              :loading="uploading"
              :disabled="isUploadDisabled"
              @click="handleUploadSubmit"
            >
              <ui-icon><Check /></ui-icon>
              <span class="btn-label">{{ uploadForm.certId ? '更新' : '上传' }}</span>
            </ui-button>
        </span>
      </template>
    </ui-dialog>

    <!-- 手动复制对话框 -->
    <ui-dialog
      v-model="copyTextDialogVisible"
      title="手动复制"
      width="600px"
    >
      <div style="margin-bottom: 12px; color: var(--ui-text-color-regular);">
        复制失败，请手动选择并复制以下内容：
      </div>
      <ui-input
        v-model="copyTextContent"
        type="textarea"
        :rows="4"
        readonly
        style="font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;"
      />
      <template #footer>
        <span class="dialog-footer">
          <ui-button type="primary" @click="copyTextDialogVisible = false">
            <ui-icon><Check /></ui-icon>
            <span class="btn-label">已复制</span>
          </ui-button>
        </span>
      </template>
    </ui-dialog>

    <!-- 迁移与自动续签向导 -->
    <ui-dialog
      v-model="migrateWizardVisible"
      title="迁移与自动续签"
      width="620px"
      top="5vh"
      :close-on-click-modal="false"
      class="cert-migrate-wizard-dialog"
      @closed="resetMigrateWizard"
    >
      <ui-steps :active="migrateStep" finish-status="success" align-center class="migrate-steps">
        <ui-step title="导出" description="在原环境保存证书" />
        <ui-step title="导入" description="上传到本系统" />
        <ui-step title="自动续签" description="申请 Let’s Encrypt" />
      </ui-steps>

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
        <ui-button size="small" type="primary" plain @click="handleCopyMigrateExportHint">
          复制说明（发给同事）
        </ui-button>

        <div class="migrate-le-export-block">
          <p class="migrate-le-export-title">本机已有 Certbot？一键导出（固定目录）</p>
          <p class="migrate-panel-text migrate-le-export-desc">
            从固定路径 <code>/etc/letsencrypt/live/</code> 打包 <code>fullchain.pem</code> + <code>privkey.pem</code>（标准 ZIP，便于另一台「上传证书」导入）。仅检测到<strong>一本</strong>时即导出该本；有<strong>多本</strong>时默认导出按名称排序后的<strong>第一本</strong>。
          </p>
          <p v-if="letsencryptLiveListLoading" class="migrate-le-hint migrate-le-scanning">
            正在检测 <code>/etc/letsencrypt/live/</code> …
          </p>
          <p v-else-if="letsencryptDefaultDomain && !letsencryptLiveHint" class="migrate-le-default-line">
            将导出：<code>{{ letsencryptDefaultDomain }}</code>
            <template v-if="letsencryptLiveDomains.length > 1">
              （共 {{ letsencryptLiveDomains.length }} 本，默认取字母序第一本）
            </template>
          </p>
          <ui-button
            type="primary"
            class="migrate-le-oneclick-btn"
            :loading="letsencryptExporting"
            :disabled="
              letsencryptExporting ||
              (letsencryptLiveScanDone && !letsencryptLiveDomains.length)
            "
            @click="handleExportLetsencryptLiveAuto"
          >
            <ui-icon><Download /></ui-icon>
            一键导出 Let's Encrypt 证书（ZIP）
          </ui-button>
          <p v-if="letsencryptLiveHint" class="migrate-le-hint">{{ letsencryptLiveHint }}</p>
        </div>

        <ui-alert type="info" :closable="false" show-icon class="migrate-inline-alert">
          <template #title>
            <span class="migrate-alert-inline">没有旧证书？可直接在本系统申请证书，签发后默认开启自动续期。</span>
          </template>
        </ui-alert>
      </div>

      <!-- 步骤 1：导入 -->
      <div v-show="migrateStep === 1" class="migrate-panel">
        <ui-form
          :model="migrateForm"
          :rules="migrateUploadRules"
          ref="migrateFormRef"
          label-width="90px"
          class="compact-form"
        >
          <ui-form-item label="域名" prop="domain">
            <ui-input
              v-model="migrateForm.domain"
              placeholder="例如：example.com"
              :disabled="!!migrateForm.certId"
            />
            <div v-if="migrateForm.certId" class="form-tip">已从向导导入，修改文件请直接点「完成导入」更新</div>
          </ui-form-item>
          <ui-form-item label="上传方式">
            <ui-radio-group v-model="migrateForm.mode" size="small">
              <ui-radio-button label="files">文件</ui-radio-button>
              <ui-radio-button label="archive">压缩包</ui-radio-button>
            </ui-radio-group>
          </ui-form-item>
          <template v-if="migrateForm.mode === 'files'">
            <ui-form-item label="证书" required>
              <ui-upload
                ref="migrateCertUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleMigrateCertFileChange"
                :on-remove="handleMigrateCertFileRemove"
                accept=".crt,.pem,.cer"
                :show-file-list="false"
              >
                <ui-button size="small" type="primary">
                  <ui-icon><FolderOpened /></ui-icon>
                  选择证书
                </ui-button>
              </ui-upload>
              <div v-if="migrateForm.certFile" class="file-selected-compact">
                <span class="file-name-text">{{ migrateForm.certFile?.name || migrateForm.certFile?.raw?.name }}</span>
                <ui-button size="small" text type="danger" @click="handleMigrateCertFileRemove">×</ui-button>
              </div>
            </ui-form-item>
            <ui-form-item label="私钥" required>
              <ui-upload
                ref="migrateKeyUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleMigrateKeyFileChange"
                :on-remove="handleMigrateKeyFileRemove"
                accept=".key,.pem"
                :show-file-list="false"
              >
                <ui-button size="small" type="primary">
                  <ui-icon><FolderOpened /></ui-icon>
                  选择私钥
                </ui-button>
              </ui-upload>
              <div v-if="migrateForm.keyFile" class="file-selected-compact">
                <span class="file-name-text">{{ migrateForm.keyFile?.name || migrateForm.keyFile?.raw?.name }}</span>
                <ui-button size="small" text type="danger" @click="handleMigrateKeyFileRemove">×</ui-button>
              </div>
            </ui-form-item>
          </template>
          <template v-else>
            <ui-form-item label="压缩包" required>
              <ui-upload
                ref="migrateArchiveUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleMigrateArchiveFileChange"
                :on-remove="handleMigrateArchiveFileRemove"
                accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2"
                :show-file-list="false"
              >
                <ui-button size="small" type="primary">
                  <ui-icon><FolderOpened /></ui-icon>
                  选择压缩包
                </ui-button>
              </ui-upload>
              <div v-if="migrateForm.archiveFile" class="file-selected-compact">
                <span class="file-name-text">{{ migrateForm.archiveFile.name }}</span>
                <ui-button size="small" text type="danger" @click="handleMigrateArchiveFileRemove">×</ui-button>
              </div>
              <div class="upload-tip-small">支持 zip、tar.gz 等；可自动识别域名</div>
            </ui-form-item>
          </template>
        </ui-form>
      </div>

      <!-- 步骤 2：自动续签 -->
      <div v-show="migrateStep === 2" class="migrate-panel">
        <p class="migrate-panel-text">
          导入的证书<strong>不会</strong>被本机 Certbot 自动续签。若希望由本系统<strong>定时自动续签</strong>，请使用 Let’s Encrypt 在本机<strong>重新申请</strong>同名域名证书（签发成功后会开启自动续期）。
        </p>
        <ui-alert v-if="migrateForm.certId" type="warning" :closable="false" show-icon class="migrate-inline-alert">
          <template #title>
            <span class="migrate-alert-inline">已导入一条记录。点击下方「申请证书」时，将先删除该导入记录，再打开申请向导（避免域名重复）。</span>
          </template>
        </ui-alert>
        <p class="migrate-panel-text muted">
          若无需自动续签，可关闭向导，继续使用已导入证书，到期前再导出替换即可。
        </p>
      </div>

      <template #footer>
        <div class="migrate-wizard-footer">
          <template v-if="migrateStep === 0">
            <ui-button type="info" @click="migrateWizardVisible = false">取消</ui-button>
            <ui-button type="primary" @click="migrateGoStep(1)">
              下一步：导入证书
            </ui-button>
            <ui-button type="success" link @click="openRequestFromMigrateShortcut">
              无旧证书，直接申请（推荐自动续签）
            </ui-button>
          </template>
          <template v-else-if="migrateStep === 1">
            <ui-button @click="migrateGoStep(0)">上一步</ui-button>
            <ui-button type="primary" :loading="migrateUploading" :disabled="isMigrateUploadDisabled" @click="handleMigrateUploadSubmit">
              <ui-icon><Check /></ui-icon>
              完成导入
            </ui-button>
          </template>
          <template v-else>
            <ui-button @click="migrateGoStep(1)">上一步</ui-button>
            <ui-button type="info" plain :loading="testingAutoRenewEnv" @click="handleTestAutoRenewEnv">
              测试自动续签环境
            </ui-button>
            <ui-button type="primary" @click="goToRequestCertFromMigrate">
              申请证书并启用自动续签
            </ui-button>
            <ui-button type="success" plain @click="finishMigrateWizard">完成</ui-button>
          </template>
        </div>
      </template>
    </ui-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch, onBeforeUnmount } from 'vue'
import { certificatesApi } from '../api/certificates'
import { ElMessage, ElMessageBox } from '@/lib/feedback'
import { DocumentAdd, UploadFilled, RefreshRight, Delete, FolderOpened, CloseBold, Check, CopyDocument, CircleCheck, Download, Operation, Promotion } from '@/components/icons'
import { formatDateTime } from '../utils/date'

const certificateList = ref([])
/** 默认折叠，避免占满首屏；需要时客户自行展开 */
const migrationGuideOpen = ref([])
const testingAutoRenewEnv = ref(false)
const clearingCertbotSessions = ref(false)
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref(null)
const certUploadRef = ref(null)
const keyUploadRef = ref(null)
const archiveUploadRef = ref(null)
const copyTextDialogVisible = ref(false)
const copyTextContent = ref('')
let certListRefreshTimer = null

const isIssuedCert = (cert) => !cert?.status || cert.status === 'issued'

const certStatusLabel = (status) => {
  const labels = {
    issued: '已签发',
    dns_pending: '待 DNS 生效',
    dns_issuing: '签发中',
    failed: '签发失败',
    expired: '已过期'
  }
  return labels[status || 'issued'] || status || '已签发'
}

const certStatusType = (status) => {
  const types = {
    issued: 'success',
    dns_pending: 'warning',
    dns_issuing: 'info',
    failed: 'danger',
    expired: 'info'
  }
  return types[status || 'issued'] || 'info'
}

const hasPendingCertificates = computed(() =>
  certificateList.value.some((cert) => !isIssuedCert(cert))
)

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

/** 向导内：从本机 /etc/letsencrypt/live 一键导出 */
const letsencryptLiveDomains = ref([])
const letsencryptLiveListLoading = ref(false)
const letsencryptLiveScanDone = ref(false)
const letsencryptLiveHint = ref('')
const letsencryptExporting = ref(false)

const letsencryptDefaultDomain = computed(() =>
  letsencryptLiveDomains.value.length ? letsencryptLiveDomains.value[0] : ''
)

const MIGRATE_EXPORT_HINT_TEXT =
  "【证书迁移】在原服务器取出证书链与私钥（Certbot 一般在 /etc/letsencrypt/live/<证书目录名>/ 的 fullchain.pem、privkey.pem）。若导出方就是本 WebUI 所在服务器且已挂载该目录，可在「迁移与自动续签」向导第一步点「一键导出 Let's Encrypt 证书」下载 ZIP（多本时默认字母序第一本）。在目标系统用「上传证书」或同一向导导入。若需目标机 Certbot 自动续签，导入后在向导最后一步点「申请证书并启用自动续签」。"

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
  letsencryptLiveScanDone.value = false
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
    letsencryptLiveScanDone.value = true
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
  letsencryptLiveScanDone.value = false
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
  letsencryptLiveScanDone.value = false
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
  if (certListRefreshTimer) {
    clearInterval(certListRefreshTimer)
    certListRefreshTimer = null
  }
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
      loadCertificates()
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

const saveDnsPendingAndClose = () => {
  ElMessage.success('已保存为待 DNS 生效，系统会在后台自动检测并签发')
  clearDnsSession()
  requestDialogVisible.value = false
  loadCertificates()
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

const handleExportLetsencryptLiveAuto = async () => {
  letsencryptExporting.value = true
  try {
    const blob = await certificatesApi.exportLetsencryptLiveAuto()
    if (!(blob instanceof Blob)) {
      ElMessage.error('导出失败')
      return
    }
    if (blob.type && blob.type.includes('application/json')) {
      ElMessage.error(await parseBlobError(blob))
      return
    }
    const d = letsencryptDefaultDomain.value || 'certificate'
    const safeName = String(d).replace(/[^\w.-]+/g, '_')
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

const plainDomainPattern = /^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/
const wildcardDomainPattern = /^\*\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+$/

const validateRequestDomain = (rule, value, callback) => {
  const domain = String(value || '').trim()
  if (!domain) {
    callback(new Error('请输入域名'))
    return
  }

  const isDns = requestForm.value.validation_method === 'dns'
  const isPlain = plainDomainPattern.test(domain)
  const isWildcard = wildcardDomainPattern.test(domain)

  if (isDns) {
    if (!isPlain && !isWildcard) {
      callback(new Error('DNS 验证请输入有效域名，支持 *.example.com'))
      return
    }
    callback()
    return
  }

  if (!isPlain) {
    callback(new Error('HTTP 验证仅支持普通域名，不支持 * 通配符'))
    return
  }
  callback()
}

const requestRules = {
  domain: [
    { required: true, message: '请输入域名', trigger: 'blur' },
    {
      validator: validateRequestDomain,
      trigger: ['blur', 'change']
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
    const activeJobs = Array.isArray(res.active_dns_jobs) ? res.active_dns_jobs : []
    const jobsHtml = activeJobs.length
      ? `<p style="margin-top:12px;font-weight:600">当前挂起的 DNS 验证会话</p><ul style="margin:4px 0;padding-left:18px;text-align:left">${activeJobs.map((j) => `<li>${escapeHtml(j.domain || '-')}，已等待 ${escapeHtml(j.age_seconds ?? '-')} 秒，job_id: ${escapeHtml(j.job_id || '-')}</li>`).join('')}</ul>`
      : ''
    const diagnostics = res.busy_diagnostics || {}
    const lockFile = diagnostics.lock_file || {}
    const processes = Array.isArray(diagnostics.processes) ? diagnostics.processes : []
    const diagLines = [
      diagnostics.app_lock_locked ? '应用内 Certbot 锁仍被占用：通常需要重启后端/容器释放旧线程锁' : null,
      lockFile.exists ? `Certbot 文件锁：${lockFile.path || '-'}，pid=${lockFile.pid ?? '-'}，存活=${lockFile.pid_alive ?? '-'}，age=${lockFile.age_seconds ?? '-'}s` : null,
      processes.length ? `系统 Certbot 进程：${processes.map((p) => `pid=${p.pid} ${p.etime} ${p.args}`).join('；')}` : null
    ].filter(Boolean)
    const diagHtml = diagLines.length
      ? `<p style="margin-top:12px;font-weight:600">Certbot 占用诊断</p><ul style="margin:4px 0;padding-left:18px;text-align:left">${diagLines.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>`
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
        ${code}${jobsHtml}${diagHtml}${sug}${out}${hint}
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

const handleClearCertbotSessions = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要清理所有挂起的 DNS 验证会话吗？正在等待 TXT 生效的申请会被标记为失败，需要重新申请。',
      '清理卡住任务',
      { type: 'warning' }
    )
  } catch {
    return
  }

  clearingCertbotSessions.value = true
  try {
    const res = await certificatesApi.cancelAllDnsChallenges()
    const after = res.stale_cleanup?.after || {}
    if (after.app_lock_locked) {
      ElMessage.warning('已尝试清理，但应用内 Certbot 锁仍被占用，请重启后端/容器')
    } else {
      ElMessage.success(res.message || '已清理挂起任务')
    }
    loadCertificates()
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '清理失败')
  } finally {
    clearingCertbotSessions.value = false
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
    const message = isIssuedCert(cert)
      ? '确定要删除证书吗？'
      : '确定要删除这条待签发记录吗？删除后会取消当前 DNS 验证会话。'
    await ElMessageBox.confirm(message, '提示', { type: 'warning' })
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
  certListRefreshTimer = setInterval(() => {
    if (hasPendingCertificates.value) {
      loadCertificates()
    }
  }, 15000)
})
</script>

<style scoped>
.cert-migrate-wizard-dialog :deep(.ui-dialog__body) {
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
  color: var(--ui-text-color-regular);
}

.migrate-panel-text.muted {
  margin-top: 12px;
  color: var(--ui-text-color-secondary);
  font-size: 12px;
}

.migrate-panel-text code {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--ui-fill-color-light);
}

.migrate-panel-list {
  margin: 0 0 14px;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ui-text-color-regular);
}

.migrate-inline-alert {
  margin-top: 16px;
}

.migrate-le-export-block {
  margin-top: 20px;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid var(--ui-border-color-lighter);
  background: var(--ui-fill-color-blank);
}

.migrate-le-export-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ui-text-color-primary);
}

.migrate-le-export-desc {
  margin-bottom: 12px !important;
  font-size: 12px;
  line-height: 1.6;
}

.migrate-le-default-line {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ui-text-color-regular);
}

.migrate-le-default-line code {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--ui-fill-color-light);
}

.migrate-le-oneclick-btn {
  width: 100%;
  margin-top: 4px;
}

.migrate-le-hint {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ui-text-color-secondary);
}

.migrate-le-scanning {
  margin: 0 0 10px;
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
  border: 1px solid var(--ui-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.cert-migration-collapse :deep(.ui-collapse-item__header) {
  padding: 12px 16px;
  font-weight: 500;
  align-items: center;
  gap: 8px;
}

.cert-migration-collapse :deep(.ui-collapse-item__wrap) {
  border-top: 1px solid var(--ui-border-color-lighter);
}

.cert-migration-collapse :deep(.ui-collapse-item__content) {
  padding-bottom: 16px;
}

.migration-guide-title {
  font-size: 14px;
  color: var(--ui-text-color-primary);
}

.migration-guide-tag {
  margin-left: 8px;
  font-weight: normal;
}

.migration-guide-body {
  font-size: 13px;
  line-height: 1.65;
  color: var(--ui-text-color-regular);
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
  background: var(--ui-fill-color-light);
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
  color: var(--ui-text-color-secondary);
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

.ui-upload__tip {
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
  flex-wrap: wrap;
  gap: 6px;
}

.domain-cell :deep(.ui-tag) {
  font-weight: 500;
  font-size: 13px;
}

.compact-form :deep(.ui-form-item) {
  margin-bottom: 14px;
}

.compact-form :deep(.ui-form-item__label) {
  font-size: 13px;
  padding-bottom: 4px;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ui-text-color-secondary);
  line-height: 1.4;
}



.file-selected-compact {
  margin-top: 6px;
  padding: 6px 10px;
  background-color: var(--ui-fill-color-lighter);
  border-radius: 4px;
  border: 1px solid var(--ui-border-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.file-name-text {
  flex: 1;
  font-size: 12px;
  color: var(--ui-text-color-primary);
  word-break: break-all;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
  line-height: 1.4;
}

.file-warning-compact {
  margin-top: 4px;
  font-size: 11px;
  color: var(--ui-color-warning);
  line-height: 1.3;
}

.upload-tip-small {
  margin-top: 4px;
  font-size: 11px;
  color: var(--ui-text-color-secondary);
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

.expiry-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.expiry-days {
  font-size: 11px;
  color: var(--ui-text-color-secondary);
}

.expiry-days.expiring-soon {
  color: var(--ui-color-warning);
}

.expiry-days.expired {
  color: var(--ui-color-danger);
}

.expiring-soon {
  color: var(--ui-color-warning) !important;
}

.expired {
  color: var(--ui-color-danger) !important;
}

.radio-desc {
  font-size: 11px;
  color: var(--ui-text-color-secondary);
  margin-top: 2px;
  line-height: 1.3;
}

.cert-request-dialog :deep(.ui-radio) {
  height: auto;
  margin-right: 0;
  margin-bottom: 8px;
  align-items: flex-start;
}

.cert-request-dialog :deep(.ui-radio__label) {
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
  border: 1px solid var(--ui-border-color-light);
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
