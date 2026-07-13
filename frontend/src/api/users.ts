import api from './index'
import type { User } from './auth'

export interface CreateUserPayload {
  username: string
  password: string
  is_active: boolean
  is_admin: boolean
}

export interface UpdateUserPayload {
  username?: string
  is_active?: boolean
  is_admin?: boolean
}

export interface UserListResponse {
  success: boolean
  users: User[]
  total: number
}

export const usersApi = {
  getUsers(params: { skip?: number; limit?: number } = {}) {
    return api.get<UserListResponse>('/users/', { params })
  },
  createUser(userData: CreateUserPayload) {
    return api.post<{ success: boolean; user: User }>('/users/', userData)
  },
  updateUser(userId: number, userData: UpdateUserPayload) {
    return api.put<{ success: boolean; user: User }>(`/users/${userId}`, userData)
  },
  deleteUser(userId: number) {
    return api.delete<{ success: boolean }>(`/users/${userId}`)
  },
  resetPassword(userId: number, newPassword: string) {
    return api.post<{ success: boolean }>(`/users/${userId}/change-password`, { new_password: newPassword })
  },
  changePassword(oldPassword: string, newPassword: string) {
    return api.post<{ success: boolean }>('/users/me/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}
