import manifest from './ai-research-approval-errors.v1.json'

export type AiResearchApprovalErrorCatalogEntry = readonly [
  code: string,
  httpStatus: number,
  retryable: boolean,
]

interface AiResearchApprovalErrorCatalogManifest {
  readonly version: string
  readonly hash: string
  readonly entries: readonly AiResearchApprovalErrorCatalogEntry[]
}

const approvalErrorCatalog = manifest as unknown as AiResearchApprovalErrorCatalogManifest

export const AI_RESEARCH_APPROVAL_ERROR_CATALOG_VERSION = approvalErrorCatalog.version
export const AI_RESEARCH_APPROVAL_ERROR_CATALOG_HASH = approvalErrorCatalog.hash
export const AI_RESEARCH_APPROVAL_ERROR_CATALOG = approvalErrorCatalog.entries

const PUBLIC_APPROVAL_ERROR_CODES: ReadonlySet<string> = new Set(
  AI_RESEARCH_APPROVAL_ERROR_CATALOG.map(([code]) => code),
)
const CHALLENGE_INCOMPLETE = 'APPROVAL_CHALLENGE_INCOMPLETE'

/** Return only a stable public code from the versioned server contract. */
export function normalizeAiResearchApprovalPublicErrorCode(value: unknown): string | null {
  if (typeof value !== 'string') return null
  if (
    value.startsWith(`${CHALLENGE_INCOMPLETE}:`)
    && value.length > CHALLENGE_INCOMPLETE.length + 1
  ) return CHALLENGE_INCOMPLETE
  return PUBLIC_APPROVAL_ERROR_CODES.has(value) ? value : null
}
