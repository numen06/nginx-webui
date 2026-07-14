import { reactive } from 'vue'
import { toast } from 'vue-sonner'

type DialogKind = 'confirm' | 'alert' | 'prompt'

export interface FeedbackDialogState {
  open: boolean
  kind: DialogKind
  title: string
  message: string
  value: string
  inputPlaceholder: string
  confirmText: string
  cancelText: string
  resolve?: (value: unknown) => void
  reject?: (reason?: unknown) => void
}

export const feedbackDialog = reactive<FeedbackDialogState>({
  open: false,
  kind: 'confirm',
  title: '',
  message: '',
  value: '',
  inputPlaceholder: '',
  confirmText: '确定',
  cancelText: '取消',
})

type MessageOptions = string | { message?: string; title?: string; description?: string }

function messageOf(value: MessageOptions): string {
  return typeof value === 'string'
    ? value
    : value.message || value.description || value.title || ''
}

export const ElMessage = {
  success: (value: MessageOptions) => toast.success(messageOf(value)),
  error: (value: MessageOptions) => toast.error(messageOf(value)),
  warning: (value: MessageOptions) => toast.warning(messageOf(value)),
  info: (value: MessageOptions) => toast.info(messageOf(value)),
}

export const ElNotification = {
  success: (value: MessageOptions) => toast.success(messageOf(value)),
  error: (value: MessageOptions) => toast.error(messageOf(value)),
  warning: (value: MessageOptions) => toast.warning(messageOf(value)),
  info: (value: MessageOptions) => toast.info(messageOf(value)),
}

interface DialogOptions {
  confirmButtonText?: string
  cancelButtonText?: string
  inputValue?: string
  inputPlaceholder?: string
  inputPattern?: RegExp
  inputErrorMessage?: string
  type?: string
  dangerouslyUseHTMLString?: boolean
  [key: string]: unknown
}

function openDialog(
  kind: DialogKind,
  message: string,
  title = kind === 'alert' ? '提示' : '请确认',
  options: DialogOptions = {},
) : Promise<any> {
  if (feedbackDialog.open) feedbackDialog.reject?.('cancel')
  return new Promise<unknown>((resolve, reject) => {
    Object.assign(feedbackDialog, {
      open: true,
      kind,
      title,
      message,
      value: options.inputValue || '',
      inputPlaceholder: options.inputPlaceholder || '',
      confirmText: options.confirmButtonText || '确定',
      cancelText: options.cancelButtonText || '取消',
      resolve,
      reject,
    })
  })
}

export const ElMessageBox = {
  confirm: (message: string, title?: string, options?: DialogOptions) =>
    openDialog('confirm', message, title, options),
  alert: (message: string, title?: string, options?: DialogOptions) =>
    openDialog('alert', message, title, options),
  prompt: (message: string, title?: string, options?: DialogOptions) =>
    openDialog('prompt', message, title, options),
}

export function resolveFeedbackDialog() {
  const result = feedbackDialog.kind === 'prompt'
    ? { value: feedbackDialog.value }
    : 'confirm'
  const resolve = feedbackDialog.resolve
  feedbackDialog.open = false
  feedbackDialog.resolve = undefined
  feedbackDialog.reject = undefined
  resolve?.(result)
}

export function rejectFeedbackDialog() {
  const reject = feedbackDialog.reject
  feedbackDialog.open = false
  feedbackDialog.resolve = undefined
  feedbackDialog.reject = undefined
  reject?.('cancel')
}
