<template>
  <div class="log-viewer-container" ref="containerRef">
    <div class="log-viewer-header">
      <div class="log-viewer-actions">
        <ui-button size="small" @click="selectAll">
          <ui-icon><Select /></ui-icon>
          全选
        </ui-button>
        <ui-button size="small" @click="copySelected">
          <ui-icon><CopyDocument /></ui-icon>
          复制
        </ui-button>
        <ui-dropdown trigger="click" @command="handleDownload">
          <ui-button size="small" type="primary">
            <ui-icon><Download /></ui-icon>
            下载
          </ui-button>
          <template #dropdown>
            <ui-dropdown-menu>
              <ui-dropdown-item command="all">
                <ui-icon><Document /></ui-icon>
                下载全部日志
              </ui-dropdown-item>
              <ui-dropdown-item command="selected" :disabled="selectedLinesCount === 0">
                <ui-icon><Select /></ui-icon>
                下载选中日志
              </ui-dropdown-item>
            </ui-dropdown-menu>
          </template>
        </ui-dropdown>
        <ui-button size="small" @click="scrollToTop">
          <ui-icon><ArrowUp /></ui-icon>
          顶部
        </ui-button>
        <ui-button size="small" @click="scrollToBottom">
          <ui-icon><ArrowDown /></ui-icon>
          底部
        </ui-button>
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

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { Select, CopyDocument, ArrowUp, ArrowDown, Download, Document } from '@/components/icons'
import { ElMessage } from '@/lib/feedback'

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

const containerRef = ref<HTMLElement | null>(null)
const contentRef = ref<HTMLElement | null>(null)
const selectedLines = ref<Set<number>>(new Set())
const isSelecting = ref(false)
const selectionStart = ref<number | null>(null)

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
  min-width: 0;
  min-height: 0;
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
  gap: 12px;
  padding: 8px 15px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.log-viewer-actions {
  display: flex;
  min-width: 0;
  flex: 1;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.log-viewer-actions :deep(.ui-button) {
  flex: 0 0 auto;
}

.log-viewer-info {
  display: flex;
  flex: 0 0 auto;
  gap: 15px;
  font-size: 12px;
  color: var(--text-secondary);
}

.selected-info {
  color: var(--nginx-green);
  font-weight: 500;
}

.log-viewer-content {
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Courier New', 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
  user-select: text;
  overscroll-behavior: contain;
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
  white-space: pre;
  min-width: max-content;
}

.log-line.selected .line-content {
  color: #f1f5f9;
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

@media (max-width: 640px) {
  .log-viewer-header {
    align-items: stretch;
    flex-direction: column-reverse;
    gap: 6px;
    padding: 8px;
  }

  .log-viewer-info {
    justify-content: flex-end;
  }

  .line-number {
    width: 48px;
    padding-inline: 6px;
  }

  .line-content {
    padding-inline: 8px;
  }
}
</style>
