import { describe, expect, it } from 'vitest'
import { confidenceColor, formatSize, statusOf, DOC_STATUS } from '@/utils/format'

describe('format utils', () => {
  it('formats size', () => {
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(2048)).toBe('2.0 KB')
    expect(formatSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })

  it('maps confidence to color', () => {
    expect(confidenceColor(0.95)).toBe('success')
    expect(confidenceColor(0.7)).toBe('warning')
    expect(confidenceColor(0.3)).toBe('danger')
    expect(confidenceColor(null)).toBe('info')
  })

  it('maps status with fallback', () => {
    expect(statusOf('parsed', DOC_STATUS)).toEqual({ label: '已解析', type: 'success' })
    expect(statusOf('unknown', DOC_STATUS).label).toBe('unknown')
  })
})
