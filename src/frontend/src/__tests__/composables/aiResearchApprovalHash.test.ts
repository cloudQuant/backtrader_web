import { describe, expect, it } from 'vitest'

import { aiResearchApprovalDecisionIntentHash } from '@/composables/useAiResearchApproval'
import type { AiResearchApprovalDecisionIntentHashInput } from '@/composables/useAiResearchApproval'

const COMMON = {
  approvalRequestId: '33333333-3333-3333-3333-333333333333',
  gateInputEvidenceHash: 'a'.repeat(64),
  evidencePackageHash: 'b'.repeat(64),
} as const

const VECTORS: Array<{
  label: string
  input: AiResearchApprovalDecisionIntentHashInput
  expected: string
}> = [
  {
    label: 'ASCII without challenges or risk',
    input: {
      ...COMMON,
      decision: 'APPROVED',
      reason: 'reviewed',
      challengeKeys: [],
      challengeResponses: {},
      residualRiskAcknowledgement: null,
    },
    expected: '89901d373e7ddb7d05e0a2b692a3e63d376d8ebf2521e6058a687f06cbf6d6d3',
  },
  {
    label: 'trimmed Chinese text and server key order',
    input: {
      ...COMMON,
      decision: 'APPROVED',
      reason: '  已复核模型与执行风险  ',
      challengeKeys: ['execution_risk', 'model_risk'],
      challengeResponses: {
        model_risk: '  模型风险已核验  ',
        execution_risk: ' 执行风险已核验 ',
      },
      residualRiskAcknowledgement: '  我接受剩余风险  ',
    },
    expected: 'e916b06214b9fae440a1bc5bc5e1613722981350d2f8dc83f98e5e9717bb13b5',
  },
  {
    label: 'URI reason retained in the hash before safe response redaction',
    input: {
      ...COMMON,
      decision: 'REJECTED',
      reason: ' see s3://private-bucket/raw and SEALED_METRICS_MUST_NOT_ESCAPE ',
      challengeKeys: ['review_note'],
      challengeResponses: { review_note: '  请重新验证  ' },
      residualRiskAcknowledgement: '',
    },
    expected: 'ea6c4d781ddf3541f224f2b29813d051f69a3cfb865f1e26735c471729bd002f',
  },
  {
    label: 'Python strip keeps BOM and removes next-line around challenge and risk text',
    input: {
      ...COMMON,
      decision: 'APPROVED',
      reason: '\uFEFFBOM保留\uFEFF',
      challengeKeys: ['unicode'],
      challengeResponses: { unicode: '\u0085答案\u0085' },
      residualRiskAcknowledgement: '\u0085风险\u0085',
    },
    expected: '6e023614f08ecb90f17f866031ebfbf8b8314ca08edb669d759c2cb402812099',
  },
]

describe('AI research approval decision intent hash', () => {
  it.each(VECTORS)('matches the frozen backend vector: $label', async ({ input, expected }) => {
    await expect(aiResearchApprovalDecisionIntentHash(input)).resolves.toBe(expected)
  })
})
