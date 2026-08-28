import { describe, expect, it } from 'vitest'
import {
  formatWanFromYuan,
  formatWanValue,
  wanToYuan,
  yuanToWan
} from './money'

describe('money unit boundary', () => {
  it('converts yuan and wan exactly at the API boundary', () => {
    expect(yuanToWan(123456.78)).toBe(12.345678)
    expect(wanToYuan(12.345678)).toBe(123456.78)
    expect(wanToYuan(yuanToWan(1))).toBe(1)
  })

  it('formats API yuan and already-converted wan separately', () => {
    expect(formatWanFromYuan(123456.78)).toBe('¥12.35 万元')
    expect(formatWanValue(12.345678)).toBe('¥12.35 万元')
  })

  it('normalizes empty and invalid values to zero', () => {
    expect(yuanToWan(null)).toBe(0)
    expect(wanToYuan('bad')).toBe(0)
  })
})
