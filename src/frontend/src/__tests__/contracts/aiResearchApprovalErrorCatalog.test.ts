import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const EXPECTED_VERSION = 'ai-research-approval-errors/v1'
const EXPECTED_HASH = '6dd9f6ce55ec595c9441ae08e26f6cc0845549eb1c950a6a28481ad973870d53'
const VERIFY_SCRIPT = 'scripts/verify-ai-research-approval-errors.mjs'
const MISSING_AUTHORITY = resolve(process.cwd(), '__missing_backend_approval_authority__.py')

interface ApprovalErrorCatalogManifest {
  version: string
  hash: string
  entries: Array<[string, number, boolean]>
}

describe('AI research approval public error catalog', () => {
  it('matches the frozen backend authority by version, hash, and exact entries', () => {
    const verification = spawnSync(
      process.execPath,
      [VERIFY_SCRIPT],
      { cwd: process.cwd(), encoding: 'utf8' },
    )

    expect(verification.status, verification.stderr || verification.stdout).toBe(0)

    const manifest = JSON.parse(readFileSync(resolve(
      process.cwd(),
      'src/contracts/ai-research-approval-errors.v1.json',
    ), 'utf8')) as ApprovalErrorCatalogManifest
    const computedHash = createHash('sha256')
      .update(JSON.stringify({ entries: manifest.entries, version: manifest.version }))
      .digest('hex')

    expect(manifest.version).toBe(EXPECTED_VERSION)
    expect(manifest.hash).toBe(EXPECTED_HASH)
    expect(computedHash).toBe(EXPECTED_HASH)
    expect(manifest.entries).toHaveLength(48)
    expect(new Set(manifest.entries.map(([code]) => code)).size).toBe(48)
  })

  it('fails strict verification when the backend authority is unavailable', () => {
    const verification = spawnSync(
      process.execPath,
      [VERIFY_SCRIPT, `--backend-authority=${MISSING_AUTHORITY}`],
      { cwd: process.cwd(), encoding: 'utf8' },
    )

    expect(verification.status).not.toBe(0)
    expect(verification.stderr).toContain('backend authority is required in strict mode')
  })

  it('makes isolated Docker verification an explicit pinned-only boundary', () => {
    const verification = spawnSync(
      process.execPath,
      [
        VERIFY_SCRIPT,
        '--mode=pinned-only',
        `--backend-authority=${MISSING_AUTHORITY}`,
      ],
      { cwd: process.cwd(), encoding: 'utf8' },
    )

    expect(verification.status, verification.stderr || verification.stdout).toBe(0)
    expect(verification.stdout).toContain('pinned-only')
    expect(verification.stdout).toContain('backend comparison NOT_RUN')
  })
})
