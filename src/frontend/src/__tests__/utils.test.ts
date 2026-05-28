/**
 * 工具函数测试
 */
import { describe, it, expect } from 'vitest'

describe('日期格式化工具', () => {
  it('应该正确格式化日期为 YYYY-MM-DD', () => {
    const date = new Date('2024-01-15T10:30:00Z')
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')

    const formatted = `${year}-${month}-${day}`
    expect(formatted).toBe('2024-01-15')
  })

  it('应该正确格式化日期时间为 YYYY-MM-DD HH:mm:ss', () => {
    // 使用 UTC 时间避免时区影响
    const date = new Date('2024-01-15T10:30:45Z')
    const year = date.getUTCFullYear()
    const month = String(date.getUTCMonth() + 1).padStart(2, '0')
    const day = String(date.getUTCDate()).padStart(2, '0')
    const hours = String(date.getUTCHours()).padStart(2, '0')
    const minutes = String(date.getUTCMinutes()).padStart(2, '0')
    const seconds = String(date.getUTCSeconds()).padStart(2, '0')

    const formatted = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    expect(formatted).toBe('2024-01-15 10:30:45')
  })
})

describe('数字格式化工具', () => {
  it('应该正确格式化货币', () => {
    const amount = 12345.678
    const formatted = new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: 'CNY'
    }).format(amount)

    expect(formatted).toContain('¥')
    expect(formatted).toContain('12,345')
  })

  it('应该正确格式化百分比', () => {
    const value = 0.1234
    const formatted = new Intl.NumberFormat('zh-CN', {
      style: 'percent',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value)

    expect(formatted).toContain('%')
    expect(formatted).toContain('12.34')
  })

  it('应该正确格式化大数字', () => {
    const value = 1234567.89
    const formatted = new Intl.NumberFormat('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value)

    expect(formatted).toBe('1,234,567.89')
  })
})

describe('字符串工具', () => {
  it('应该正确截断长字符串', () => {
    const str = 'This is a very long string that needs to be truncated'
    const maxLength = 20
    const truncated = str.length > maxLength
      ? str.substring(0, maxLength) + '...'
      : str

    expect(truncated.length).toBeLessThanOrEqual(maxLength + 3)
    expect(truncated).toContain('...')
  })

  it('应该正确转换为大写', () => {
    const str = 'hello world'
    const uppercased = str.toUpperCase()
    expect(uppercased).toBe('HELLO WORLD')
  })

  it('应该正确转换为小写', () => {
    const str = 'HELLO WORLD'
    const lowercased = str.toLowerCase()
    expect(lowercased).toBe('hello world')
  })
})

describe('数组工具', () => {
  it('应该正确计算数组总和', () => {
    const numbers = [1, 2, 3, 4, 5]
    const sum = numbers.reduce((a, b) => a + b, 0)
    expect(sum).toBe(15)
  })

  it('应该正确计算数组平均值', () => {
    const numbers = [10, 20, 30, 40, 50]
    const average = numbers.reduce((a, b) => a + b, 0) / numbers.length
    expect(average).toBe(30)
  })

  it('应该正确找出数组最大值', () => {
    const numbers = [1, 5, 3, 9, 2]
    const max = Math.max(...numbers)
    expect(max).toBe(9)
  })

  it('应该正确找出数组最小值', () => {
    const numbers = [1, 5, 3, 9, 2]
    const min = Math.min(...numbers)
    expect(min).toBe(1)
  })

  it('应该正确过滤数组', () => {
    const numbers = [1, 2, 3, 4, 5, 6]
    const evens = numbers.filter(n => n % 2 === 0)
    expect(evens).toEqual([2, 4, 6])
  })
})

describe('对象工具', () => {
  it('应该正确获取对象键', () => {
    const obj = { a: 1, b: 2, c: 3 }
    const keys = Object.keys(obj)
    expect(keys).toEqual(['a', 'b', 'c'])
  })

  it('应该正确获取对象值', () => {
    const obj = { a: 1, b: 2, c: 3 }
    const values = Object.values(obj)
    expect(values).toEqual([1, 2, 3])
  })

  it('应该正确合并对象', () => {
    const obj1 = { a: 1, b: 2 }
    const obj2 = { c: 3, d: 4 }
    const merged = { ...obj1, ...obj2 }
    expect(merged).toEqual({ a: 1, b: 2, c: 3, d: 4 })
  })
})

describe('验证工具', () => {
  it('应该正确验证邮箱格式', () => {
    const email = 'test@example.com'
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    expect(emailRegex.test(email)).toBe(true)
  })

  it('应该拒绝无效邮箱格式', () => {
    const invalidEmails = ['invalid', 'invalid@', '@example.com', 'test@']
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    invalidEmails.forEach(email => {
      expect(emailRegex.test(email)).toBe(false)
    })
  })

  it('应该正确验证手机号格式', () => {
    const phone = '13812345678'
    const phoneRegex = /^1[3-9]\d{9}$/
    expect(phoneRegex.test(phone)).toBe(true)
  })

  it('应该拒绝无效手机号格式', () => {
    const invalidPhones = ['12345678901', '1381234567', 'abcdefghijk']
    const phoneRegex = /^1[3-9]\d{9}$/
    invalidPhones.forEach(phone => {
      expect(phoneRegex.test(phone)).toBe(false)
    })
  })
})

describe('颜色工具', () => {
  it('应该正确转换十六进制颜色为RGB', () => {
    const hex = '#ff0000'
    const r = parseInt(hex.substring(1, 3), 16)
    const g = parseInt(hex.substring(3, 5), 16)
    const b = parseInt(hex.substring(5, 7), 16)

    expect(r).toBe(255)
    expect(g).toBe(0)
    expect(b).toBe(0)
  })

  it('应该正确判断颜色亮度', () => {
    const hex = '#ffffff'
    const r = parseInt(hex.substring(1, 3), 16)
    const g = parseInt(hex.substring(3, 5), 16)
    const b = parseInt(hex.substring(5, 7), 16)
    const brightness = (r * 299 + g * 587 + b * 114) / 1000

    expect(brightness).toBeGreaterThan(128)
  })
})
