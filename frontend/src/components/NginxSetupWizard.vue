<template>
  <el-dialog
    v-model="visible"
    title="Nginx 初始设置向导"
    width="800px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    :modal="true"
    class="setup-wizard-dialog"
  >
    <div class="wizard-content">
      <el-steps :active="currentStep" finish-status="success" align-center>
        <el-step title="准备源码包" />
        <el-step title="编译 Nginx" />
        <el-step title="发布到生产" />
      </el-steps>

      <div class="step-content">
        <!-- 步骤1: 准备源码包 -->
        <div v-if="currentStep === 0" class="step-panel">
          <div class="step-description">
            <el-icon class="step-icon"><Box /></el-icon>
            <h3>准备 Nginx 源码包</h3>
            <p>系统检测到默认的 Nginx 1.29.3 源码包，需要将其复制到构建目录以准备编译。</p>
          </div>
          <div class="step-actions">
            <el-button
              type="primary"
              size="large"
              :loading="preparing"
              @click="handlePrepare"
            >
              <el-icon v-if="!preparing"><Download /></el-icon>
              <span>{{ preparing ? '正在准备...' : '准备源码包' }}</span>
            </el-button>
          </div>
          <div v-if="prepareError" class="error-message">
            <el-alert type="error" :title="prepareError" :closable="false" />
          </div>
        </div>

        <!-- 步骤2: 编译 Nginx -->
        <div v-if="currentStep === 1" class="step-panel">
          <div class="step-description">
            <el-icon class="step-icon"><Tools /></el-icon>
            <h3>编译 Nginx</h3>
            <p>开始编译 Nginx 1.29.3，这个过程可能需要几分钟时间，请耐心等待。</p>
          </div>
          <div v-if="compiling" class="compile-progress">
            <el-progress
              :percentage="compileProgress"
              :status="compileProgress === 100 ? 'success' : null"
              :stroke-width="20"
            />
            <p class="progress-text">{{ compileStatusText }}</p>
          </div>
          <div v-if="compileError" class="error-message">
            <el-alert type="error" :title="compileError" :closable="false" />
            <el-button type="primary" @click="handleRetryCompile">重试</el-button>
          </div>
        </div>

        <!-- 步骤3: 发布到生产 -->
        <div v-if="currentStep === 2" class="step-panel">
          <div class="step-description">
            <el-icon class="step-icon"><Promotion /></el-icon>
            <h3>发布到生产环境</h3>
            <p>将编译好的 Nginx 版本发布到生产环境（last 目录），以便后续使用。</p>
          </div>
          <div class="step-actions">
            <el-button
              type="primary"
              size="large"
              :loading="publishing"
              @click="handlePublish"
            >
              <el-icon v-if="!publishing"><Promotion /></el-icon>
              <span>{{ publishing ? '正在发布...' : '发布到生产' }}</span>
            </el-button>
          </div>
          <div v-if="publishError" class="error-message">
            <el-alert type="error" :title="publishError" :closable="false" />
            <el-button type="primary" @click="handleRetryPublish">重试</el-button>
          </div>
        </div>

        <!-- 完成 -->
        <div v-if="currentStep === 3" class="step-panel success-panel">
          <div class="step-description">
            <el-icon class="step-icon success-icon"><CircleCheck /></el-icon>
            <h3>设置完成！</h3>
            <p>Nginx 已成功设置并发布到生产环境，您现在可以开始使用系统了。</p>
          </div>
          <div class="step-actions">
            <el-button type="primary" size="large" @click="handleComplete">
              完成
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { nginxApi } from '../api/nginx'
import { ElMessage } from 'element-plus'
import { Box, Download, Tools, Promotion, CircleCheck } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'complete'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const currentStep = ref(0)
const preparing = ref(false)
const compiling = ref(false)
const publishing = ref(false)
const prepareError = ref('')
const compileError = ref('')
const publishError = ref('')
const compileProgress = ref(0)
const compileStatusText = ref('')

// 进度状态（在组件级别定义，确保在函数间共享）
const progressState = {
  lastStageProgress: 0,  // 记录上一个阶段的进度值
  stageStartTime: Date.now(),  // 当前阶段开始时间
  lastRealProgress: 0  // 最后一次从API获取的真实进度
}

// 监听进度变化，用于调试
watch(compileProgress, (newVal, oldVal) => {
  console.log(`[进度条] 进度值变化: ${oldVal} -> ${newVal}`)
})

const defaultVersion = '1.29.3'

const handlePrepare = async () => {
  preparing.value = true
  prepareError.value = ''
  
  try {
    await nginxApi.prepareDefaultNginx()
    ElMessage.success('源码包准备完成')
    // 准备完成后，进度应该已经到15%（因为解压可能已经完成）
    compileProgress.value = 15
    progressState.lastStageProgress = 15
    progressState.lastRealProgress = 15
    progressState.stageStartTime = Date.now()
    currentStep.value = 1
    // 自动开始编译
    handleCompile()
  } catch (error) {
    prepareError.value = error.response?.data?.detail || error.message || '准备源码包失败'
    ElMessage.error(prepareError.value)
  } finally {
    preparing.value = false
  }
}

const handleCompile = async () => {
  compiling.value = true
  compileError.value = ''
  // 如果是从准备阶段过来的，进度已经是15%了
  if (compileProgress.value < 15) {
    compileProgress.value = 15
  }
  compileStatusText.value = '正在启动编译...'
  
  // 初始化进度状态
  progressState.lastStageProgress = compileProgress.value
  progressState.stageStartTime = Date.now()
  progressState.lastRealProgress = compileProgress.value
  
  let checkInterval = null
  let progressInterval = null
  let smoothProgressInterval = null
  const compileStartTime = Date.now()
  
  try {
    // 编译是异步的，需要轮询检查状态
    await nginxApi.compileVersion(defaultVersion)
    compileStatusText.value = '编译已启动，正在检查进度...'
    
    // 平滑进度更新（在每个阶段内按时间增长）
    smoothProgressInterval = setInterval(() => {
      if (compiling.value && compileProgress.value < 95) {
        const now = Date.now()
        const stageElapsed = (now - progressState.stageStartTime) / 1000 // 当前阶段耗时（秒）
        
        // 根据当前进度值判断处于哪个阶段，并在该阶段范围内增长
        let currentStageMin = progressState.lastStageProgress
        let currentStageMax = 95
        let stageDuration = 60 // 默认阶段时长（秒）
        
        // 确定当前阶段和阶段范围（调整阶段，因为准备源码包时可能已经解压了）
        // 准备源码包后，解压可能已完成，所以从15%开始
        if (compileProgress.value < 30) {
          // 配置阶段：15% -> 30%，15秒（每1秒增长1%）
          currentStageMin = 15
          currentStageMax = 30
          stageDuration = 15
        } else if (compileProgress.value < 50) {
          // 配置完成到编译开始：30% -> 50%，20秒（每1秒增长1%）
          currentStageMin = 30
          currentStageMax = 50
          stageDuration = 20
        } else if (compileProgress.value < 70) {
          // 编译阶段：50% -> 70%，20秒（每1秒增长1%）
          currentStageMin = 50
          currentStageMax = 70
          stageDuration = 20
        } else if (compileProgress.value < 80) {
          // 编译完成到安装开始：70% -> 80%，10秒（每1秒增长1%）
          currentStageMin = 70
          currentStageMax = 80
          stageDuration = 10
        } else if (compileProgress.value < 95) {
          // 安装阶段：80% -> 95%，15秒（每1秒增长1%）
          currentStageMin = 80
          currentStageMax = 95
          stageDuration = 15
        }
        
        // 在当前阶段范围内按时间线性增长
        const progressRatio = Math.min(1, stageElapsed / stageDuration)
        const stageProgress = currentStageMin + ((currentStageMax - currentStageMin) * progressRatio)
        
        // 确保进度只增不减，并且不超过当前阶段的最大值
        // 每1秒至少增长0.5%，确保进度条持续更新
        const minIncrement = 0.5 // 每秒最小增长0.5%
        
        // 计算目标进度：取阶段进度和最小增长中的较大值
        const targetProgress = Math.min(
          currentStageMax,
          Math.max(
            compileProgress.value + minIncrement, // 确保每秒至少增长
            stageProgress // 按时间计算的进度
          )
        )
        
        // 更新进度（确保只增不减）
        if (targetProgress > compileProgress.value) {
          compileProgress.value = Math.floor(targetProgress * 10) / 10 // 保留一位小数
          console.log(`[平滑进度] 更新到: ${compileProgress.value.toFixed(1)}% (阶段: ${currentStageMin}-${currentStageMax}%, 耗时: ${stageElapsed.toFixed(1)}s/${stageDuration}s, 比例: ${(progressRatio * 100).toFixed(1)}%)`)
        }
      }
    }, 1000) // 每1秒更新一次，确保进度条每秒都有变化
    
    // 开始轮询检查编译进度（更频繁）
    progressInterval = setInterval(async () => {
      try {
        const progressResponse = await nginxApi.getCompileProgress(defaultVersion)
        console.log('[编译进度] API响应:', progressResponse)
        
        // API拦截器已经返回了data，所以progressResponse就是数据对象
        // 但如果还有嵌套的data，也兼容处理
        let progressData = progressResponse
        if (progressResponse && typeof progressResponse === 'object' && 'data' in progressResponse && progressResponse.data) {
          progressData = progressResponse.data
        }
        
        console.log('[编译进度] 解析后的数据:', progressData)
        console.log('[编译进度] progress值:', progressData.progress)
        
        if (progressData.completed) {
          // 编译完成
          if (progressInterval) clearInterval(progressInterval)
          if (checkInterval) clearInterval(checkInterval)
          if (smoothProgressInterval) clearInterval(smoothProgressInterval)
          compileProgress.value = 100
          compileStatusText.value = '编译完成！'
          ElMessage.success('Nginx 编译完成')
          currentStep.value = 2
          compiling.value = false
        } else if (progressData.error) {
          // 编译出错
          if (progressInterval) clearInterval(progressInterval)
          if (checkInterval) clearInterval(checkInterval)
          if (smoothProgressInterval) clearInterval(smoothProgressInterval)
          compileError.value = progressData.message || '编译失败，请查看编译日志'
          compiling.value = false
        } else {
          // 更新进度 - 确保progress是数字，并且只增不减
          const progressValue = Number(progressData.progress) || 0
          console.log('[编译进度] API返回进度值:', progressValue)
          
          // 更新真实进度
          progressState.lastRealProgress = progressValue
          
          // 判断是否进入新阶段（根据进度值判断）
          let newStage = false
          if (progressValue >= 15 && progressState.lastStageProgress < 15) {
            // 进入配置阶段
            newStage = true
            progressState.lastStageProgress = 15
          } else if (progressValue >= 30 && progressState.lastStageProgress < 30) {
            // 进入编译准备阶段
            newStage = true
            progressState.lastStageProgress = 30
          } else if (progressValue >= 50 && progressState.lastStageProgress < 50) {
            // 进入编译阶段
            newStage = true
            progressState.lastStageProgress = 50
          } else if (progressValue >= 70 && progressState.lastStageProgress < 70) {
            // 进入安装准备阶段
            newStage = true
            progressState.lastStageProgress = 70
          } else if (progressValue >= 80 && progressState.lastStageProgress < 80) {
            // 进入安装阶段
            newStage = true
            progressState.lastStageProgress = 80
          }
          
          // 如果进入新阶段，重置阶段开始时间
          if (newStage) {
            console.log(`[编译进度] 进入新阶段，重置计时: ${progressState.lastStageProgress}%`)
            progressState.stageStartTime = Date.now()
          }
          
          // 如果真实进度超过当前显示进度，更新显示进度（但不强制，让平滑进度继续工作）
          if (progressValue > compileProgress.value + 10) {
            // 只有当真实进度明显超过时才更新，避免打断平滑进度
            compileProgress.value = progressValue
            progressState.lastStageProgress = progressValue
            progressState.stageStartTime = Date.now()
            console.log(`[编译进度] 真实进度明显超前，更新到: ${compileProgress.value}%`)
          }
          compileStatusText.value = progressData.message || `${progressData.stage || '编译中'}...`
        }
      } catch (error) {
        console.error('获取编译进度失败:', error)
        // 继续尝试，不中断
      }
    }, 1000) // 每秒检查一次进度
    
    // 同时检查版本状态（作为备用检查）
    checkInterval = setInterval(async () => {
      try {
        const versions = await nginxApi.listVersions()
        const version = (versions.data || versions).find(v => v.directory === defaultVersion)
        
        if (version && version.compiled) {
          // 编译完成
          if (progressInterval) clearInterval(progressInterval)
          if (checkInterval) clearInterval(checkInterval)
          if (smoothProgressInterval) clearInterval(smoothProgressInterval)
          compileProgress.value = 100
          compileStatusText.value = '编译完成！'
          ElMessage.success('Nginx 编译完成')
          currentStep.value = 2
          compiling.value = false
        } else if (version && version.error) {
          // 编译失败
          if (progressInterval) clearInterval(progressInterval)
          if (checkInterval) clearInterval(checkInterval)
          if (smoothProgressInterval) clearInterval(smoothProgressInterval)
          compileError.value = '编译失败，请查看编译日志'
          compiling.value = false
        }
      } catch (error) {
        console.error('检查版本状态失败:', error)
        // 继续尝试，不中断
      }
    }, 3000) // 每3秒检查一次版本状态
    
    // 设置超时
    setTimeout(() => {
      if (progressInterval) clearInterval(progressInterval)
      if (checkInterval) clearInterval(checkInterval)
      if (smoothProgressInterval) clearInterval(smoothProgressInterval)
      if (compiling.value) {
        compileError.value = '编译超时，请检查编译日志'
        compiling.value = false
      }
    }, 600000) // 10分钟超时
  } catch (error) {
    if (progressInterval) clearInterval(progressInterval)
    if (checkInterval) clearInterval(checkInterval)
    if (smoothProgressInterval) clearInterval(smoothProgressInterval)
    compileError.value = error.response?.data?.detail || error.message || '编译失败'
    ElMessage.error(compileError.value)
    compiling.value = false
  }
}

const handleRetryCompile = () => {
  compileError.value = ''
  handleCompile()
}

const handlePublish = async () => {
  publishing.value = true
  publishError.value = ''
  
  try {
    await nginxApi.upgradeToProduction(defaultVersion)
    ElMessage.success('已发布到生产环境')
    
    // 发布成功后自动启动nginx
    compileStatusText.value = '正在启动 Nginx...'
    try {
      await nginxApi.startVersion('last') // 启动发布版（last目录）
      ElMessage.success('Nginx 已启动')
      compileStatusText.value = 'Nginx 已启动并运行'
    } catch (startError) {
      console.error('启动nginx失败:', startError)
      // 启动失败不影响完成，只是提示
      ElMessage.warning('发布成功，但启动失败，请稍后手动启动')
    }
    
    currentStep.value = 3
  } catch (error) {
    publishError.value = error.response?.data?.detail || error.message || '发布失败'
    ElMessage.error(publishError.value)
  } finally {
    publishing.value = false
  }
}

const handleRetryPublish = () => {
  publishError.value = ''
  handlePublish()
}

const handleComplete = () => {
  emit('complete')
  visible.value = false
  // 重置状态
  currentStep.value = 0
  preparing.value = false
  compiling.value = false
  publishing.value = false
  prepareError.value = ''
  compileError.value = ''
  publishError.value = ''
  compileProgress.value = 0
  compileStatusText.value = ''
}
</script>

<style scoped>
.setup-wizard-dialog {
  z-index: 3000;
}

.wizard-content {
  padding: 20px 0;
}

.step-content {
  margin-top: 40px;
  min-height: 300px;
}

.step-panel {
  text-align: center;
  padding: 40px 20px;
}

.step-description {
  margin-bottom: 40px;
}

.step-icon {
  font-size: 64px;
  color: var(--el-color-primary);
  margin-bottom: 20px;
}

.success-icon {
  color: var(--el-color-success);
}

.step-description h3 {
  font-size: 24px;
  margin: 20px 0 10px;
  color: var(--el-text-color-primary);
}

.step-description p {
  font-size: 14px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.step-actions {
  margin-top: 40px;
}

.compile-progress {
  margin: 40px 0;
}

.progress-text {
  margin-top: 20px;
  color: var(--el-text-color-regular);
}

.error-message {
  margin-top: 20px;
  text-align: center;
}

.error-message .el-button {
  margin-top: 10px;
}

.success-panel {
  padding: 60px 20px;
}
</style>

