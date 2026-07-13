import { formatFileSize, validatePassword } from './format'

describe('format utilities', () => {
  it('formats byte quantities', () => {
    expect(formatFileSize(0)).toBe('0 B')
    expect(formatFileSize(1024)).toBe('1 KB')
    expect(formatFileSize(1536)).toBe('1.5 KB')
  })

  it('validates passwords', () => {
    expect(validatePassword('12345')).toBe('密码至少 6 个字符')
    expect(validatePassword('123456')).toBeNull()
  })
})
