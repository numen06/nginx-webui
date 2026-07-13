import api from './index'

export interface User {
  id: number
  username: string
  is_active: boolean
  is_admin: boolean
  created_at: string | null
  is_default_password?: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  username: string
  expires_in: number
}

export interface CurrentUserResponse {
  success: boolean
  user: User
}

export const authApi = {
  login(username: string, password: string) {
    return api.post<LoginResponse>('/auth/login', { username, password })
  },
  getCurrentUser() {
    return api.get<CurrentUserResponse>('/auth/me')
  },
}
