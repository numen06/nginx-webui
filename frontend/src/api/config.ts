import api from './index'

export interface ApiResult {
  success: boolean
  message?: string
}

export interface NginxStatusResponse {
  running: boolean
  version?: string | null
  directory?: string | null
  pid?: number | string | null
  uptime?: string | null
  error?: string
}

export interface ConfigInfoResponse extends ApiResult {
  content?: string
  config_path?: string | null
  config_dir?: string | null
  working_config_dir?: string | null
  nginx_version?: string | null
  nginx_version_detail?: string | null
  active_version?: string | null
  install_path?: string | null
  binary?: string | null
  pending_changes?: boolean
}

export interface ConfigEntry {
  path: string
  name?: string
  is_dir: boolean
  size?: number
  modified_at?: string | null
}

export interface ConfigTreeResponse extends ApiResult {
  root: string
  files: ConfigEntry[]
}

export interface ConfigFileResponse extends ApiResult {
  path: string
  content: string
  size?: number
}

export interface ConfigMutationResponse extends ApiResult {
  path?: string
  entry?: ConfigEntry
}

export interface ConfigTestResponse extends ApiResult {
  warnings?: string[]
  errors?: string[]
  output?: string
  formatted?: string
}

export interface ReloadConfigResponse extends ConfigTestResponse {
  backup_id?: number
  last_version_backup_id?: number
  test_result?: ConfigTestResponse
}

export interface BackupInfo {
  id: number
  filename: string
  file_path: string
  created_at?: string | null
  created_by_id?: number | null
  is_last_version?: boolean
}

export interface BackupsResponse extends ApiResult {
  backups: BackupInfo[]
}

export interface BackupMutationResponse extends ApiResult {
  backup?: BackupInfo
  backup_id?: number
}

export interface SplitLegacyResponse extends ApiResult {
  backup_id?: number
  test_result?: ConfigTestResponse
}

export interface MergedPreviewResponse extends ApiResult {
  content: string
}

export const configApi = {
  getConfig() {
    return api.get<ConfigInfoResponse>('/config')
  },

  getTree() {
    return api.get<ConfigTreeResponse>('/config/tree')
  },

  getFile(path: string) {
    return api.get<ConfigFileResponse>('/config/file', { params: { path } })
  },

  updateFile(path: string, content: string) {
    return api.put<ConfigMutationResponse>('/config/file', { path, content })
  },

  createDirectory(path: string, name: string) {
    return api.post<ConfigMutationResponse>('/config/mkdir', { path, name })
  },

  renamePath(path: string, newName: string) {
    return api.post<ConfigMutationResponse>('/config/rename', { path, new_name: newName })
  },

  deletePath(path: string) {
    return api.delete<ApiResult>('/config/file', { params: { path } })
  },

  testConfig() {
    return api.post<ConfigTestResponse>('/config/test')
  },

  reloadConfig() {
    return api.post<ReloadConfigResponse>('/config/reload')
  },

  applyConfig() {
    return api.post<ReloadConfigResponse>('/config/apply')
  },

  getStatus() {
    return api.get<NginxStatusResponse>('/config/status')
  },

  getBackups() {
    return api.get<BackupsResponse>('/config/backups')
  },

  createBackup() {
    return api.post<BackupMutationResponse>('/config/backup')
  },

  restoreBackup(backupId: number) {
    return api.post<BackupMutationResponse>(`/config/restore/${backupId}`)
  },

  formatConfig(content: string) {
    return api.post<ConfigTestResponse>('/config/format', { content })
  },

  validateFile(path: string, content: string) {
    return api.post<ConfigTestResponse>('/config/validate', { path, content })
  },

  splitLegacyConfig() {
    return api.post<SplitLegacyResponse>('/config/split-legacy')
  },

  getMergedPreview() {
    return api.get<MergedPreviewResponse>('/config/merged-preview')
  },
}
