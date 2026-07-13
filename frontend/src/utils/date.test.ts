import { formatDate, formatDateTime, formatLocalISO, formatTime } from './date'

describe('date formatting', () => {
  const date = new Date(2026, 6, 13, 9, 8, 7)

  it('formats local date and time consistently', () => {
    expect(formatDateTime(date)).toBe('2026-07-13 09:08:07')
    expect(formatDate(date)).toBe('2026-07-13')
    expect(formatTime(date)).toBe('09:08:07')
    expect(formatLocalISO(date)).toBe('2026-07-13 09:08:07')
  })

  it('handles empty and invalid values', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDate('invalid')).toBe('invalid')
    expect(formatLocalISO(new Date('invalid'))).toBeNull()
  })
})
