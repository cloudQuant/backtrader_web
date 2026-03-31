import { describe, expect, it } from 'vitest'

import { exportToCSV } from '@/utils/exportUtils'

describe('exportUtils', () => {
  it('protects formula-like strings in CSV cells', () => {
    const csv = exportToCSV([
      {
        name: '=SUM(A1:A2)',
        email: '+cmd',
        note: '@malicious',
        plain: 'hello',
      },
    ])

    expect(csv).toContain("'=SUM(A1:A2)")
    expect(csv).toContain("'+cmd")
    expect(csv).toContain("'@malicious")
    expect(csv).toContain('hello')
  })

  it('escapes formula-like strings inside serialized objects', () => {
    const csv = exportToCSV([
      {
        payload: {
          formula: '=1+1',
        },
      },
    ])

    expect(csv).toContain(`"{""formula"":""=1+1""}"`)
  })
})
