import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

export interface ApiErrorPayload {
  detail?: unknown
  message?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  readonly status?: number
  readonly code?: string
  readonly detail: unknown
  readonly data?: ApiErrorPayload

  constructor(message: string, options: {
    status?: number
    code?: string
    detail?: unknown
    data?: ApiErrorPayload
  } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.detail = options.detail ?? message
    this.data = options.data
  }
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30_000,
})

function parsePayload(value: unknown): ApiErrorPayload {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value) as unknown
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? parsed as ApiErrorPayload
        : { detail: value, message: value }
    } catch {
      return { detail: value, message: value }
    }
  }
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as ApiErrorPayload
    : { detail: value == null ? undefined : String(value) }
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => typeof item === 'string'
        ? item
        : item && typeof item === 'object' && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : JSON.stringify(item))
      .join('；')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return fallback
}

function isNginxUnavailable(detail: unknown): boolean {
  const text = detailMessage(detail, '')
  return text.includes('未找到可用的 Nginx') || text.includes('未找到任何 Nginx')
}

function timeoutMessage(url = ''): string {
  if (url.includes('/certificates/verify-dns')) {
    return '请求超时，请稍后重试（DNS 检测可能较慢或网络不稳定）'
  }
  if (
    url.includes('/certificates/request')
    || url.includes('/certificates/dns-challenge/complete')
    || url.includes('/certificates/renew')
  ) {
    return '证书操作仍未返回结果，请稍后刷新证书列表确认'
  }
  return '请求超时，请稍后重试'
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  ((response) => {
    const value: unknown = response.data
    if (typeof value !== 'string') return value
    try {
      return JSON.parse(value) as unknown
    } catch {
      return { message: value, raw: value }
    }
  }) as any,
  (rawError: AxiosError) => {
    const url = rawError.config?.url || ''
    if (rawError.response) {
      const payload = parsePayload(rawError.response.data)
      const detail = payload.detail ?? payload.message
      const message = detailMessage(detail, `请求失败 (${rawError.response.status})`)

      if (rawError.response.status === 401) {
        localStorage.removeItem('token')
        window.dispatchEvent(new CustomEvent('auth:unauthorized'))
      }
      if (isNginxUnavailable(detail) && !url.includes('/nginx/setup/')) {
        window.dispatchEvent(new CustomEvent('nginx:unavailable'))
      }

      return Promise.reject(new ApiError(message, {
        status: rawError.response.status,
        detail,
        data: payload,
      }))
    }

    const timeout = rawError.code === 'ECONNABORTED'
      || rawError.message.toLowerCase().includes('timeout')
    const message = timeout
      ? timeoutMessage(url)
      : rawError.request
        ? '无法连接到服务器，请检查后端服务是否正在运行'
        : rawError.message || '请求配置错误'
    return Promise.reject(new ApiError(message, {
      code: timeout ? 'TIMEOUT' : rawError.request ? 'NETWORK_ERROR' : 'REQUEST_ERROR',
    }))
  },
)

export function apiErrorMessage(error: unknown, fallback = '操作失败'): string {
  if (error instanceof ApiError || error instanceof Error) return error.message || fallback
  if (error && typeof error === 'object') {
    const candidate = error as { detail?: unknown; message?: unknown }
    return detailMessage(candidate.detail ?? candidate.message, fallback)
  }
  return fallback
}

export type ApiRequestConfig = AxiosRequestConfig

export interface ApiClient {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  patch<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
}

export default api as unknown as ApiClient
