import { apiErrorMessage } from '@/api'

export function formatFileSize(bytes: number | null | undefined, precision = 1): string {
  if (!bytes || bytes < 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** unitIndex
  return `${Number(value.toFixed(unitIndex === 0 ? 0 : precision))} ${units[unitIndex]}`
}

export function validatePassword(password: string, minimum = 6): string | null {
  if (password.length < minimum) return `密码至少 ${minimum} 个字符`
  return null
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function copyText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text)
}

export { apiErrorMessage }
