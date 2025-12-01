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

// 整体进度状态管理
const progressState = {
  // 阶段进度范围定义
  stages: {
    prepare: { min: 0, max: 20, name: '准备源码包' },
    compile: { min: 20, max: 80, name: '编译' },
    publish: { min: 80, max: 100, name: '发布到生产' }
  },
  // 当前阶段信息
  currentStage: 'prepare',  // prepare | compile | publish
  stageStartTime: Date.now(),  // 当前阶段开始时间
  lastRealProgress: 0,  // 从API获取的真实进度（编译阶段的0-100%）
  smoothProgressTimer: null,  // 平滑进度定时器
  progressCheckTimer: null  // 进度检查定时器
}

// 监听进度变化，用于调试
watch(compileProgress, (newVal, oldVal) => {
  console.log(`[进度条] 进度值变化: ${oldVal.toFixed(1)}% -> ${newVal.toFixed(1)}%`)
})

const defaultVersion = '1.29.3'

const handlePrepare = async () => {
  preparing.value = true
  prepareError.value = ''
  
  // 初始化准备阶段的进度
  progressState.currentStage = 'prepare'
  progressState.stageStartTime = Date.now()
  compileProgress.value = 0
  
  // 启动准备阶段的平滑进度递增
  const prepareStage = progressState.stages.prepare
  const prepareTimer = setInterval(() => {
    if (progressState.currentStage === 'prepare' && compileProgress.value < prepareStage.max) {
      const elapsed = (Date.now() - progressState.stageStartTime) / 1000 // 秒
      const minDuration = 3 // 准备阶段最少3秒
      const targetProgress = Math.min(
        prepareStage.max,
        prepareStage.min + ((prepareStage.max - prepareStage.min) * Math.min(1, elapsed / minDuration))
      )
      compileProgress.value = Math.min(targetProgress, compileProgress.value + 1) // 每秒最多增长1%
    } else {
      clearInterval(prepareTimer)
    }
  }, 1000)
  
  try {
    await nginxApi.prepareDefaultNginx()
    
    // 确保进度到达准备阶段的终点
    compileProgress.value = prepareStage.max
    
    clearInterval(prepareTimer)
    ElMessage.success('源码包准备完成')
    
    // 切换到编译阶段
    progressState.currentStage = 'compile'
    progressState.stageStartTime = Date.now()
    progressState.lastRealProgress = 0
    currentStep.value = 1
    
    // 自动开始编译
    setTimeout(() => {
    handleCompile()
    }, 300)
  } catch (error) {
    clearInterval(prepareTimer)
    prepareError.value = error.response?.data?.detail || error.message || '准备源码包失败'
    ElMessage.error(prepareError.value)
  } finally {
    preparing.value = false
  }
}

const handleCompile = async () => {
  compiling.value = true
  compileError.value = ''
  compileStatusText.value = '正在启动编译...'
  
  // 确保从编译阶段的起点开始
  const compileStage = progressState.stages.compile
  compileProgress.value = compileStage.min
  progressState.currentStage = 'compile'
  progressState.stageStartTime = Date.now()
  progressState.lastRealProgress = 0
  
  // 清理之前的定时器
  if (progressState.smoothProgressTimer) {
    clearInterval(progressState.smoothProgressTimer)
  }
  if (progressState.progressCheckTimer) {
    clearInterval(progressState.progressCheckTimer)
  }
  
  try {
    // 编译是异步的，需要轮询检查状态
    await nginxApi.compileVersion(defaultVersion)
    compileStatusText.value = '编译已启动，正在检查进度...'
    
    // 平滑进度更新：在编译阶段（20%-80%）内持续递增
    progressState.smoothProgressTimer = setInterval(() => {
      if (compiling.value && progressState.currentStage === 'compile') {
        const elapsed = (Date.now() - progressState.stageStartTime) / 1000 // 秒
        
        // 编译阶段最少需要60秒，确保进度条有足够时间递增
        const minCompileDuration = 60
        const timeBasedProgress = compileStage.min + ((compileStage.max - compileStage.min) * Math.min(1, elapsed / minCompileDuration))
        
        // 将API返回的真实进度（0-100%）映射到编译阶段的进度范围（20-80%）
        const apiBasedProgress = compileStage.min + ((compileStage.max - compileStage.min) * (progressState.lastRealProgress / 100))
        
        // 取两者中的较大值，确保进度条持续递增且不落后于真实进度
        const targetProgress = Math.max(timeBasedProgress, apiBasedProgress)
        
        // 确保进度只增不减，每秒最多增长2%
        const maxIncrement = 2
        const finalProgress = Math.min(
          compileStage.max,
          Math.max(
            compileProgress.value,
            Math.min(targetProgress, compileProgress.value + maxIncrement)
          )
        )
        
        if (finalProgress > compileProgress.value) {
          compileProgress.value = Math.floor(finalProgress * 10) / 10 // 保留一位小数
          console.log(`[编译进度] 更新到: ${compileProgress.value.toFixed(1)}% (时间进度: ${timeBasedProgress.toFixed(1)}%, API进度: ${apiBasedProgress.toFixed(1)}%, 耗时: ${elapsed.toFixed(1)}s)`)
        }
      }
    }, 1000) // 每1秒更新一次
    
    // 轮询检查编译进度
    progressState.progressCheckTimer = setInterval(async () => {
      try {
        const progressResponse = await nginxApi.getCompileProgress(defaultVersion)
        
        // API拦截器已经返回了data，所以progressResponse就是数据对象
        let progressData = progressResponse
        if (progressResponse && typeof progressResponse === 'object' && 'data' in progressResponse && progressResponse.data) {
          progressData = progressResponse.data
        }
        
        if (progressData.completed) {
          // 编译完成
          if (progressState.smoothProgressTimer) clearInterval(progressState.smoothProgressTimer)
          if (progressState.progressCheckTimer) clearInterval(progressState.progressCheckTimer)
          
          // 确保进度到达编译阶段的终点
          compileProgress.value = compileStage.max
          compileStatusText.value = '编译完成！'
          ElMessage.success('Nginx 编译完成')
          
          // 切换到发布阶段
          progressState.currentStage = 'publish'
          progressState.stageStartTime = Date.now()
          currentStep.value = 2
          compiling.value = false
        } else if (progressData.error) {
          // 编译出错
          if (progressState.smoothProgressTimer) clearInterval(progressState.smoothProgressTimer)
          if (progressState.progressCheckTimer) clearInterval(progressState.progressCheckTimer)
          compileError.value = progressData.message || '编译失败，请查看编译日志'
          compiling.value = false
        } else {
          // 更新真实进度（0-100%）
          const progressValue = Number(progressData.progress) || 0
          if (progressValue > progressState.lastRealProgress) {
          progressState.lastRealProgress = progressValue
            console.log(`[编译进度] API返回真实进度: ${progressValue}%`)
          }
          
          // 更新状态文本
          compileStatusText.value = progressData.message || `${progressData.stage || '编译中'}...`
        }
      } catch (error) {
        console.error('获取编译进度失败:', error)
        // 继续尝试，不中断
      }
    }, 1000) // 每秒检查一次进度
    
    // 设置超时
    setTimeout(() => {
      if (progressState.smoothProgressTimer) clearInterval(progressState.smoothProgressTimer)
      if (progressState.progressCheckTimer) clearInterval(progressState.progressCheckTimer)
      if (compiling.value) {
        compileError.value = '编译超时，请检查编译日志'
        compiling.value = false
      }
    }, 600000) // 10分钟超时
  } catch (error) {
    if (progressState.smoothProgressTimer) clearInterval(progressState.smoothProgressTimer)
    if (progressState.progressCheckTimer) clearInterval(progressState.progressCheckTimer)
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
  
  // 初始化发布阶段的进度
  progressState.currentStage = 'publish'
  progressState.stageStartTime = Date.now()
  const publishStage = progressState.stages.publish
  
  // 确保从发布阶段的起点开始
  compileProgress.value = publishStage.min
  compileStatusText.value = '正在发布到生产环境...'
  
  // 启动发布阶段的平滑进度递增
  const publishTimer = setInterval(() => {
    if (progressState.currentStage === 'publish' && compileProgress.value < publishStage.max) {
      const elapsed = (Date.now() - progressState.stageStartTime) / 1000 // 秒
      const minDuration = 3 // 发布阶段最少3秒
      const targetProgress = Math.min(
        publishStage.max,
        publishStage.min + ((publishStage.max - publishStage.min) * Math.min(1, elapsed / minDuration))
      )
      compileProgress.value = Math.min(targetProgress, compileProgress.value + 2) // 每秒最多增长2%
    } else {
      clearInterval(publishTimer)
    }
  }, 1000)
  
  try {
    await nginxApi.upgradeToProduction(defaultVersion)
    
    // 更新进度到90%
    compileProgress.value = 90
    compileStatusText.value = '正在启动 Nginx...'
    
    try {
      await nginxApi.startVersion('last') // 启动发布版（last目录）
      
      // 确保进度到达100%
      compileProgress.value = 100
      compileStatusText.value = 'Nginx 已启动并运行'
      ElMessage.success('已发布到生产环境')
      ElMessage.success('Nginx 已启动')
    } catch (startError) {
      console.error('启动nginx失败:', startError)
      // 启动失败不影响完成，进度仍然到100%
      compileProgress.value = 100
      ElMessage.success('已发布到生产环境')
      ElMessage.warning('发布成功，但启动失败，请稍后手动启动')
    }
    
    clearInterval(publishTimer)
    currentStep.value = 3
  } catch (error) {
    clearInterval(publishTimer)
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
  // 清理所有定时器
  if (progressState.smoothProgressTimer) {
    clearInterval(progressState.smoothProgressTimer)
    progressState.smoothProgressTimer = null
  }
  if (progressState.progressCheckTimer) {
    clearInterval(progressState.progressCheckTimer)
    progressState.progressCheckTimer = null
  }
  
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
  
  // 重置进度状态
  progressState.currentStage = 'prepare'
  progressState.stageStartTime = Date.now()
  progressState.lastRealProgress = 0
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

