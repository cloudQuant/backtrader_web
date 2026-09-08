#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const PINNED_VERSION = 'ai-research-approval-errors/v1'
const PINNED_HASH = '6dd9f6ce55ec595c9441ae08e26f6cc0845549eb1c950a6a28481ad973870d53'
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const modeArgument = process.argv.find((argument) => argument.startsWith('--mode='))
const authorityArgument = process.argv.find(
  (argument) => argument.startsWith('--backend-authority='),
)
const verificationMode = modeArgument?.slice('--mode='.length)
  || process.env.AI_RESEARCH_APPROVAL_ERROR_CATALOG_MODE
  || 'strict'
const manifestPath = resolve(
  frontendRoot,
  'src/contracts/ai-research-approval-errors.v1.json',
)
const backendAuthorityPath = authorityArgument
  ? resolve(process.cwd(), authorityArgument.slice('--backend-authority='.length))
  : resolve(frontendRoot, '../backend/app/api/strategy/research.py')

function fail(message) {
  throw new Error(`AI_RESEARCH_APPROVAL_ERROR_CATALOG_INVALID: ${message}`)
}

function canonicalJson(value) {
  if (Array.isArray(value)) return value.map(canonicalJson)
  if (value === null || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.keys(value).sort().map((key) => [key, canonicalJson(value[key])]),
  )
}

function catalogHash(version, entries) {
  return createHash('sha256')
    .update(JSON.stringify(canonicalJson({ entries, version })), 'utf8')
    .digest('hex')
}

function validateEntries(entries, sourceName) {
  if (!Array.isArray(entries) || entries.length !== 48) {
    fail(`${sourceName} must contain exactly 48 entries`)
  }
  for (const entry of entries) {
    if (
      !Array.isArray(entry)
      || entry.length !== 3
      || typeof entry[0] !== 'string'
      || !/^APPROVAL_[A-Z0-9_]+$/.test(entry[0])
      || !Number.isInteger(entry[1])
      || typeof entry[2] !== 'boolean'
    ) fail(`${sourceName} contains a malformed entry`)
  }
  const codes = entries.map(([code]) => code)
  if (new Set(codes).size !== codes.length) fail(`${sourceName} contains duplicate codes`)
  if (JSON.stringify([...codes].sort()) !== JSON.stringify(codes)) {
    fail(`${sourceName} entries are not sorted by code`)
  }
}

function parseBackendAuthority(source) {
  const version = source.match(
    /_APPROVAL_PUBLIC_ERROR_CATALOG_VERSION\s*=\s*"([^"]+)"/,
  )?.[1]
  const body = source.match(
    /_APPROVAL_PUBLIC_ERROR_CATALOG\s*=\s*\(\r?\n([\s\S]*?)\r?\n\)\r?\n_APPROVAL_PUBLIC_ERROR_BY_CODE/,
  )?.[1]
  if (!version || body === undefined) fail('backend authority markers are missing')

  const entries = body.split(/\r?\n/).filter((line) => line.trim()).map((line) => {
    const match = line.match(
      /^\s*\("([A-Z][A-Z0-9_]*)",\s*(\d+),\s*(True|False)\),\s*$/,
    )
    if (!match) fail('backend authority contains an unparseable entry')
    return [match[1], Number(match[2]), match[3] === 'True']
  })
  validateEntries(entries, 'backend authority')
  return { version, entries }
}

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
if (verificationMode !== 'strict' && verificationMode !== 'pinned-only') {
  fail(`unsupported verification mode ${verificationMode}`)
}
if (
  JSON.stringify(Object.keys(manifest).sort())
  !== JSON.stringify(['entries', 'hash', 'version'])
) fail('manifest fields do not match the closed contract')
validateEntries(manifest.entries, 'frontend manifest')
if (manifest.version !== PINNED_VERSION) fail('frontend manifest version drifted')
if (manifest.hash !== PINNED_HASH) fail('frontend manifest declared hash drifted')
if (catalogHash(manifest.version, manifest.entries) !== PINNED_HASH) {
  fail('frontend manifest content hash drifted')
}

if (verificationMode === 'strict') {
  if (!existsSync(backendAuthorityPath)) {
    fail('backend authority is required in strict mode')
  }
  const backend = parseBackendAuthority(readFileSync(backendAuthorityPath, 'utf8'))
  if (backend.version !== manifest.version) fail('backend/frontend version mismatch')
  if (JSON.stringify(backend.entries) !== JSON.stringify(manifest.entries)) {
    fail('backend/frontend entries mismatch')
  }
  if (catalogHash(backend.version, backend.entries) !== manifest.hash) {
    fail('backend/frontend hash mismatch')
  }
  console.log(`Verified ${manifest.version}: 48 backend/frontend entries, ${manifest.hash}`)
} else {
  console.log(
    `Verified pinned-only ${manifest.version}: 48 manifest entries, ${manifest.hash}; `
      + 'backend comparison NOT_RUN',
  )
}
