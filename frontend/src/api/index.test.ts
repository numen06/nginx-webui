import { ApiError, apiErrorMessage } from './index'

describe('API error normalization', () => {
  it('uses normalized API errors', () => {
    expect(apiErrorMessage(new ApiError('权限不足', { status: 403 }))).toBe('权限不足')
  })

  it('normalizes validation details', () => {
    expect(apiErrorMessage({ detail: [{ msg: '用户名已存在' }] })).toBe('用户名已存在')
  })

  it('uses a safe fallback for unknown values', () => {
    expect(apiErrorMessage(null, '请求失败')).toBe('请求失败')
  })
})
