import api from './index'

export const usersApi = {
  // 获取用户列表
  getUsers(params = {}) {
    return api.get('/users/', { params })
  },

  // 获取用户详情
  getUser(userId) {
    return api.get(`/users/${userId}`)
  },

  // 创建用户
  createUser(userData) {
    return api.post('/users/', userData)
  },

  // 更新用户信息
  updateUser(userId, userData) {
    return api.put(`/users/${userId}`, userData)
  },

  // 删除用户
  deleteUser(userId) {
    return api.delete(`/users/${userId}`)
  },

  // 重置用户密码（管理员）
  resetPassword(userId, newPassword) {
    return api.post(`/users/${userId}/change-password`, { new_password: newPassword })
  },

  // 修改当前用户密码
  changePassword(oldPassword, newPassword) {
    return api.post('/users/me/change-password', {
      old_password: oldPassword,
      new_password: newPassword
    })
  }
}


