import { describe, expect, it } from 'vitest'

import {
  isAiResearchV2CandidateFreezeIdentityComplete,
  type AiResearchV2Candidate,
  type AiResearchV2CandidateFreezeIdentity,
} from '@/types/aiResearchV2'

const validCandidate: AiResearchV2Candidate = {
  id: 'candidate-1',
  run_id: 'run-1',
  experiment_epoch_id: 'epoch-1',
  source_version_id: null,
  dataset_snapshot_id: 'dataset-1',
  code_artifact_id: 'code-1',
  dependency_artifact_id: 'dependencies-1',
  candidate_hash: 'a'.repeat(64),
  environment_hash: 'b'.repeat(64),
  cost_model_hash: 'c'.repeat(64),
  params: { lookback: 20 },
  freeze_status: 'MUTABLE',
  frozen_at: null,
}

const validIdentity: AiResearchV2CandidateFreezeIdentity = {
  runId: 'run-1',
  runExperimentEpochId: 'epoch-1',
  runDatasetSnapshotId: 'dataset-1',
  datasetSnapshotId: 'dataset-1',
  datasetContentHash: 'd'.repeat(64),
}

type BindingOverride = {
  candidate?: Partial<AiResearchV2Candidate>
  identity?: Partial<AiResearchV2CandidateFreezeIdentity>
}

const incompleteBindings: Array<[string, BindingOverride]> = [
  ['empty run', { candidate: { run_id: '' }, identity: { runId: '' } }],
  ['empty epoch', {
    candidate: { experiment_epoch_id: '' },
    identity: { runExperimentEpochId: '' },
  }],
  ['empty dataset', {
    candidate: { dataset_snapshot_id: '' },
    identity: { runDatasetSnapshotId: '', datasetSnapshotId: '' },
  }],
  ['candidate run', { candidate: { run_id: 'run-other' } }],
  ['experiment epoch', { candidate: { experiment_epoch_id: 'epoch-other' } }],
  ['candidate dataset', { candidate: { dataset_snapshot_id: 'dataset-other' } }],
  ['run dataset', { identity: { runDatasetSnapshotId: 'dataset-other' } }],
  ['visible dataset', { identity: { datasetSnapshotId: 'dataset-other' } }],
  ['candidate hash', { candidate: { candidate_hash: 'A'.repeat(64) } }],
  ['environment hash', { candidate: { environment_hash: 'b'.repeat(63) } }],
  ['cost-model hash', { candidate: { cost_model_hash: 'not-a-sha256' } }],
  ['dataset hash', { identity: { datasetContentHash: null } }],
  ['code artifact', { candidate: { code_artifact_id: '' } }],
  ['dependency artifact', { candidate: { dependency_artifact_id: '' } }],
]

describe('AI Research v2 candidate freeze identity', () => {
  it('accepts a complete candidate, run, epoch, dataset, artifact, and hash binding', () => {
    expect(isAiResearchV2CandidateFreezeIdentityComplete(validCandidate, validIdentity)).toBe(true)
  })

  it.each(incompleteBindings)('fails closed for an incomplete %s binding', (_label, override) => {
    const candidate = { ...validCandidate, ...override.candidate }
    const identity = { ...validIdentity, ...override.identity }

    expect(isAiResearchV2CandidateFreezeIdentityComplete(candidate, identity)).toBe(false)
  })
})
