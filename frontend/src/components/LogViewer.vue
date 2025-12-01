<template>
  <div class="log-viewer-container" ref="containerRef">
    <div class="log-viewer-header">
      <div class="log-viewer-actions">
        <el-button size="small" @click="selectAll">
          <el-icon><Select /></el-icon>
          全选
        </el-button>
        <el-button size="small" @click="copySelected">
          <el-icon><CopyDocument /></el-icon>
          复制
        </el-button>
        <el-dropdown trigger="click" @command="handleDownload">
          <el-button size="small" type="primary">
            <el-icon><Download /></el-icon>
            下载
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="all">
                <el-icon><Document /></el-icon>
                下载全部日志
              </el-dropdown-item>
              <el-dropdown-item command="selected" :disabled="selectedLinesCount === 0">
                <el-icon><Select /></el-icon>
                下载选中日志
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="scrollToTop">
          <el-icon><ArrowUp /></el-icon>
          顶部
        </el-button>
        <el-button size="small" @click="scrollToBottom">
          <el-icon><ArrowDown /></el-icon>
          底部
        </el-button>
      </div>
      <div class="log-viewer-info">
        <span v-if="totalLines > 0">共 {{ totalLines }} 行</span>
        <span v-if="selectedLinesCount > 0" class="selected-info">已选择 {{ selectedLinesCount }} 行</span>
      </div>
    </div>
    <div 
      class="log-viewer-content" 
      ref="contentRef"
      @mousedown="handleMouseDown"
      @mousemove="handleMouseMove"
      @mouseup="handleMouseUp"
      @mouseleave="handleMouseLeave"
    >
      <div class="log-viewer-lines">
        <div
          v-for="(log, index) in logs"
          :key="index"
          :class="['log-line', { 'selected': isLineSelected(index) }]"
          :data-line-number="index + 1"
          @click="toggleLineSelection(index)"
          @dblclick="selectLine(index)"
        >
          <span class="line-number">{{ index + 1 }}</span>
          <span class="line-content" v-html="formatLogLine(log, keyword)"></span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { Select, CopyDocument, ArrowUp, ArrowDown, Download, Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  keyword: {
    type: String,
    default: ''
  },
  showLineNumbers: {
    type: Boolean,
    default: true
  },
  filename: {
    type: String,
    default: 'logs'
  }
})

const containerRef = ref(null)
const contentRef = ref(null)
const selectedLines = ref(new Set())
const isSelecting = ref(false)
const selectionStart = ref(null)

const totalLines = computed(() => props.logs.length)
const selectedLinesCount = computed(() => selectedLines.value.size)

const formatLogLine = (text, keyword) => {
  if (!text && text !== 0) return ''
  
  const textStr = String(text)
  
  // 转义HTML特殊字符
  let escaped = textStr
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
  
  // 如果没有关键词，直接返回转义后的文本
  if (!keyword || !keyword.trim()) {
    return escaped || ''
  }
  
  // 转义关键词中的特殊正则字符
  const keywordStr = String(keyword).trim()
  if (!keywordStr) {
    return escaped || ''
  }
  
  const escapedKeyword = keywordStr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  
  // 高亮关键词（不区分大小写）
  try {
    const regex = new RegExp(`(${escapedKeyword})`, 'gi')
    const result = escaped.replace(regex, '<mark>$1</mark>')
    return result || ''
  } catch (e) {
    console.warn('Invalid regex pattern:', e)
    return escaped || ''
  }
}

const isLineSelected = (index) => {
  return selectedLines.value.has(index)
}

const toggleLineSelection = (index) => {
  if (selectedLines.value.has(index)) {
    selectedLines.value.delete(index)
  } else {
    selectedLines.value.add(index)
  }
  selectedLines.value = new Set(selectedLines.value)
}

const selectLine = (index) => {
  selectedLines.value.clear()
  selectedLines.value.add(index)
  selectedLines.value = new Set(selectedLines.value)
}

const selectAll = () => {
  selectedLines.value.clear()
  for (let i = 0; i < props.logs.length; i++) {
    selectedLines.value.add(i)
  }
  selectedLines.value = new Set(selectedLines.value)
  ElMessage.success('已全选所有日志')
}

const clearSelection = () => {
  selectedLines.value.clear()
  selectedLines.value = new Set(selectedLines.value)
}

const copySelected = async () => {
  if (selectedLines.value.size === 0) {
    ElMessage.warning('请先选择要复制的日志行')
    return
  }
  
  const sortedIndices = Array.from(selectedLines.value).sort((a, b) => a - b)
  const selectedText = sortedIndices
    .map(index => {
      const lineNum = String(index + 1).padStart(6, ' ')
      const content = props.logs[index] || ''
      return `${lineNum} | ${content}`
    })
    .join('\n')
  
  try {
    await navigator.clipboard.writeText(selectedText)
    ElMessage.success(`已复制 ${selectedLines.value.size} 行日志`)
  } catch (error) {
    console.error('复制失败:', error)
    ElMessage.error('复制失败，请手动复制')
  }
}

const getLogContent = (includeLineNumbers = true, indices = null) => {
  const linesToExport = indices || Array.from({ length: props.logs.length }, (_, i) => i)
  
  return linesToExport
    .map(index => {
      const content = props.logs[index] || ''
      if (includeLineNumbers) {
        const lineNum = String(index + 1).padStart(6, ' ')
        return `${lineNum} | ${content}`
      }
      return content
    })
    .join('\n')
}

const downloadLogs = (content, filename) => {
  try {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('日志下载成功')
  } catch (error) {
    console.error('下载失败:', error)
    ElMessage.error('下载失败，请重试')
  }
}

const handleDownload = (command) => {
  if (command === 'all') {
    const content = getLogContent(true)
    if (content.trim() === '') {
      ElMessage.warning('没有可下载的日志')
      return
    }
    const now = new Date()
    const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
    const filename = `${props.filename}-${timestamp}.txt`
    downloadLogs(content, filename)
  } else if (command === 'selected') {
    if (selectedLines.value.size === 0) {
      ElMessage.warning('请先选择要下载的日志行')
      return
    }
    const sortedIndices = Array.from(selectedLines.value).sort((a, b) => a - b)
    const content = getLogContent(true, sortedIndices)
    const now2 = new Date()
    const timestamp = `${now2.getFullYear()}${String(now2.getMonth() + 1).padStart(2, '0')}${String(now2.getDate()).padStart(2, '0')}_${String(now2.getHours()).padStart(2, '0')}${String(now2.getMinutes()).padStart(2, '0')}${String(now2.getSeconds()).padStart(2, '0')}`
    const filename = `${props.filename}-selected-${timestamp}.txt`
    downloadLogs(content, filename)
  }
}

const scrollToTop = () => {
  if (contentRef.value) {
    contentRef.value.scrollTop = 0
  }
}

const scrollToBottom = () => {
  if (contentRef.value) {
    nextTick(() => {
      contentRef.value.scrollTop = contentRef.value.scrollHeight
    })
  }
}

const getLineIndexFromElement = (element) => {
  const lineElement = element.closest('.log-line')
  if (!lineElement) return null
  
  const lineNumber = parseInt(lineElement.dataset.lineNumber)
  return lineNumber ? lineNumber - 1 : null
}

const handleMouseDown = (event) => {
  const index = getLineIndexFromElement(event.target)
  if (index !== null) {
    isSelecting.value = true
    selectionStart.value = index
    if (event.shiftKey && selectedLines.value.size > 0) {
      // Shift+点击：扩展选择
      const sorted = Array.from(selectedLines.value).sort((a, b) => a - b)
      const first = sorted[0]
      const last = sorted[sorted.length - 1]
      const start = Math.min(index, first)
      const end = Math.max(index, last)
      
      selectedLines.value.clear()
      for (let i = start; i <= end; i++) {
        selectedLines.value.add(i)
      }
      selectedLines.value = new Set(selectedLines.value)
    } else if (event.ctrlKey || event.metaKey) {
      // Ctrl/Cmd+点击：切换选择
      toggleLineSelection(index)
    } else {
      // 普通点击：清除之前的选择，选择当前行
      selectedLines.value.clear()
      selectedLines.value.add(index)
      selectedLines.value = new Set(selectedLines.value)
    }
  }
}

const handleMouseMove = (event) => {
  if (!isSelecting.value || selectionStart.value === null) return
  
  const index = getLineIndexFromElement(event.target)
  if (index !== null) {
    const start = Math.min(selectionStart.value, index)
    const end = Math.max(selectionStart.value, index)
    
    selectedLines.value.clear()
    for (let i = start; i <= end; i++) {
      selectedLines.value.add(i)
    }
    selectedLines.value = new Set(selectedLines.value)
  }
}

const handleMouseUp = () => {
  isSelecting.value = false
  selectionStart.value = null
}

const handleMouseLeave = () => {
  isSelecting.value = false
}

// 监听日志变化，自动滚动到底部
watch(() => props.logs.length, (newLength, oldLength) => {
  if (newLength > oldLength && contentRef.value) {
    nextTick(() => {
      const isNearBottom = contentRef.value.scrollHeight - contentRef.value.scrollTop - contentRef.value.clientHeight < 100
      if (isNearBottom) {
        scrollToBottom()
      }
    })
  }
})

defineExpose({
  selectAll,
  clearSelection,
  copySelected,
  scrollToTop,
  scrollToBottom,
  downloadAll: () => handleDownload('all'),
  downloadSelected: () => handleDownload('selected')
})
</script>

<style scoped>
.log-viewer-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  overflow: hidden;
}

.log-viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 15px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.log-viewer-actions {
  display: flex;
  gap: 8px;
}

.log-viewer-info {
  display: flex;
  gap: 15px;
  font-size: 12px;
  color: var(--text-secondary);
}

.selected-info {
  color: var(--nginx-green);
  font-weight: 500;
}

.log-viewer-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Courier New', 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
  user-select: text;
}

.log-viewer-lines {
  min-height: 100%;
}

.log-line {
  display: flex;
  min-height: 20px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background-color 0.1s;
}

.log-line:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.log-line.selected {
  background-color: rgba(0, 150, 57, 0.2);
  border-left-color: var(--nginx-green);
}

.line-number {
  flex-shrink: 0;
  width: 60px;
  padding: 2px 10px;
  text-align: right;
  color: var(--text-muted);
  user-select: none;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  background-color: rgba(0, 0, 0, 0.2);
}

.log-line.selected .line-number {
  color: var(--nginx-green);
  font-weight: bold;
}

.line-content {
  flex: 1;
  padding: 2px 10px;
  white-space: pre-wrap;
  word-wrap: break-word;
  min-width: 0;
}

.log-line.selected .line-content {
  color: var(--text-primary);
}

.line-content :deep(mark) {
  background-color: var(--nginx-green);
  color: var(--text-white);
  padding: 2px 4px;
  border-radius: 2px;
  font-weight: bold;
}

/* 滚动条样式 */
.log-viewer-content::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

.log-viewer-content::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.3);
}

.log-viewer-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 6px;
}

.log-viewer-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* 空状态 */
.log-viewer-content:empty::before {
  content: '暂无日志';
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 14px;
}
</style>
