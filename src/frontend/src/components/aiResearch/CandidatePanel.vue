<template>
  <section
    class="candidate-panel"
    aria-labelledby="trusted-candidates-title"
    data-test="trusted-research-candidates"
  >
    <header>
      <span>03</span>
      <div>
        <h3 id="trusted-candidates-title">
          {{ t('strategy.aiResearchTrusted.candidate.title') }}
        </h3>
        <p>{{ t('strategy.aiResearchTrusted.candidate.description') }}</p>
      </div>
    </header>

    <p
      v-if="!candidates.length"
      class="candidate-panel__empty"
    >
      {{ t('strategy.aiResearchTrusted.candidate.empty') }}
    </p>
    <article
      v-for="candidate in candidates"
      v-else
      :key="candidate.id"
      class="candidate-panel__item"
      :data-active="candidate.id === activeCandidateId"
    >
      <div class="candidate-panel__item-head">
        <strong>{{ candidate.id }}</strong>
        <span
          role="status"
          aria-live="polite"
          :data-status="candidate.freeze_status"
        >{{ statusLabel(candidate) }}</span>
      </div>
      <dl>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.candidate.candidateHash') }}</dt>
          <dd>{{ candidate.candidate_hash }}</dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.candidate.datasetSnapshot') }}</dt>
          <dd>{{ candidate.dataset_snapshot_id }}</dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.candidate.datasetHash') }}</dt>
          <dd>{{ datasetHash(candidate) }}</dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.candidate.environmentHash') }}</dt>
          <dd>{{ candidate.environment_hash }}</dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.candidate.costModelHash') }}</dt>
          <dd>{{ candidate.cost_model_hash }}</dd>
        </div>
      </dl>
      <details>
        <summary>{{ t('strategy.aiResearchTrusted.candidate.params') }}</summary>
        <pre>{{ safeParams(candidate) }}</pre>
      </details>
      <p
        v-if="candidate.frozen_at"
        class="candidate-panel__timestamp"
      >
        {{ t('strategy.aiResearchTrusted.candidate.frozenAt', { value: candidate.frozen_at }) }}
      </p>
      <p
        v-if="!isFreezeReady(candidate)"
        :id="`trusted-research-candidate-incomplete-${candidate.id}`"
        class="candidate-panel__identity-warning"
        :data-test="`trusted-research-candidate-incomplete-${candidate.id}`"
      >
        {{ t('strategy.aiResearchTrusted.candidate.identityIncomplete') }}
      </p>
      <p
        v-if="candidate.freeze_status === 'FROZEN'"
        :id="`trusted-research-candidate-holdout-warning-${candidate.id}`"
        class="candidate-panel__holdout-warning"
        :data-test="`trusted-research-candidate-holdout-warning-${candidate.id}`"
      >
        {{ t('strategy.aiResearchTrusted.candidate.holdoutWarning') }}
      </p>
      <p
        v-if="holdoutCommandFor(candidate)"
        :id="`trusted-research-candidate-holdout-status-${candidate.id}`"
        class="candidate-panel__holdout-status"
        :data-test="`trusted-research-candidate-holdout-status-${candidate.id}`"
        role="status"
        aria-live="polite"
      >
        {{ t('strategy.aiResearchTrusted.candidate.holdoutExisting', {
          status: holdoutStatusLabel(holdoutCommandFor(candidate)),
        }) }}
      </p>
      <button
        type="button"
        :data-test="`trusted-research-candidate-freeze-${candidate.id}`"
        :aria-describedby="!isFreezeReady(candidate) ? `trusted-research-candidate-incomplete-${candidate.id}` : undefined"
        :disabled="candidate.freeze_status === 'FROZEN' || freezingCandidateId !== null || !isFreezeReady(candidate)"
        @click="openConfirmation(candidate, $event)"
      >
        {{ candidate.id === freezingCandidateId
          ? t('strategy.aiResearchTrusted.candidate.freezing')
          : t('strategy.aiResearchTrusted.candidate.freeze') }}
      </button>
      <button
        v-if="isHoldoutActionAvailable(candidate)"
        type="button"
        class="candidate-panel__holdout-action"
        :data-test="`trusted-research-candidate-holdout-${candidate.id}`"
        :aria-describedby="holdoutDescriptionIds(candidate)"
        :disabled="!canRequestHoldout(candidate)"
        @click="requestHoldout(candidate)"
      >
        {{ candidate.id === requestingHoldoutCandidateId
          ? t('strategy.aiResearchTrusted.candidate.requestingHoldout')
          : t('strategy.aiResearchTrusted.candidate.requestHoldout') }}
      </button>
    </article>

    <div
      v-if="pendingCandidate"
      ref="dialogRef"
      class="candidate-panel__dialog-backdrop"
      data-test="trusted-research-freeze-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="trusted-research-freeze-title"
      aria-describedby="trusted-research-freeze-warning"
      tabindex="-1"
      @keydown.esc="closeConfirmation"
      @keydown.tab="trapDialogFocus"
    >
      <div class="candidate-panel__dialog">
        <h4 id="trusted-research-freeze-title">
          {{ t('strategy.aiResearchTrusted.candidate.confirmTitle') }}
        </h4>
        <p
          id="trusted-research-freeze-warning"
          class="candidate-panel__warning"
        >
          {{ t('strategy.aiResearchTrusted.candidate.confirmWarning') }}
        </p>
        <dl>
          <div><dt>ID</dt><dd>{{ pendingCandidate.id }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.candidateHash') }}</dt><dd>{{ pendingCandidate.candidate_hash }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.datasetSnapshot') }}</dt><dd>{{ pendingCandidate.dataset_snapshot_id }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.datasetHash') }}</dt><dd>{{ datasetHash(pendingCandidate) }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.environmentHash') }}</dt><dd>{{ pendingCandidate.environment_hash }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.costModelHash') }}</dt><dd>{{ pendingCandidate.cost_model_hash }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.codeArtifact') }}</dt><dd>{{ pendingCandidate.code_artifact_id }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.dependencyArtifact') }}</dt><dd>{{ pendingCandidate.dependency_artifact_id }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.epoch') }}</dt><dd>{{ pendingCandidate.experiment_epoch_id }}</dd></div>
          <div><dt>{{ t('strategy.aiResearchTrusted.candidate.sourceVersion') }}</dt><dd>{{ pendingCandidate.source_version_id || t('strategy.aiResearchTrusted.unavailable') }}</dd></div>
        </dl>
        <pre>{{ safeParams(pendingCandidate) }}</pre>
        <div class="candidate-panel__dialog-actions">
          <button
            type="button"
            data-test="trusted-research-freeze-cancel"
            @click="closeConfirmation"
          >
            {{ t('strategy.aiResearchTrusted.candidate.cancel') }}
          </button>
          <button
            type="button"
            class="candidate-panel__confirm"
            data-test="trusted-research-freeze-confirm"
            :disabled="!isFreezeReady(pendingCandidate) || freezingCandidateId !== null"
            @click="confirmFreeze"
          >
            {{ t('strategy.aiResearchTrusted.candidate.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { isAiResearchV2CandidateFreezeIdentityComplete } from '@/types/aiResearchV2'
import type { AiResearchV2Candidate, AiResearchV2HoldoutCommand } from '@/types/aiResearchV2'

const props = withDefaults(defineProps<{
  candidates?: AiResearchV2Candidate[]
  activeCandidateId?: string | null
  freezingCandidateId?: string | null
  requestingHoldoutCandidateId?: string | null
  holdoutCommands?: AiResearchV2HoldoutCommand[]
  runId?: string | null
  runExperimentEpochId?: string | null
  runDatasetSnapshotId?: string | null
  datasetSnapshotId?: string | null
  datasetContentHash?: string | null
}>(), {
  candidates: () => [],
  activeCandidateId: null,
  freezingCandidateId: null,
  requestingHoldoutCandidateId: null,
  holdoutCommands: () => [],
  runId: null,
  runExperimentEpochId: null,
  runDatasetSnapshotId: null,
  datasetSnapshotId: null,
  datasetContentHash: null,
})

const emit = defineEmits<{
  freeze: [
    candidateId: string,
    expectedCandidateHash: string,
    onSettled: (succeeded: boolean) => void,
  ]
  requestHoldout: [candidateId: string, expectedCandidateHash: string]
}>()

const { t } = useI18n()
const pendingCandidate = ref<AiResearchV2Candidate | null>(null)
const dialogRef = ref<HTMLElement | null>(null)
let confirmationLocked = false
let confirmationOpener: HTMLElement | null = null
let freezeSubmissionGeneration = 0
let activeFreezeSubmission: number | null = null

const DIALOG_FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function statusLabel(candidate: AiResearchV2Candidate): string {
  return candidate.freeze_status === 'FROZEN'
    ? t('strategy.aiResearchTrusted.candidate.frozen')
    : t('strategy.aiResearchTrusted.candidate.mutable')
}

function datasetHash(candidate: AiResearchV2Candidate): string {
  if (candidate.dataset_snapshot_id !== props.datasetSnapshotId) {
    return t('strategy.aiResearchTrusted.unavailable')
  }
  return props.datasetContentHash || t('strategy.aiResearchTrusted.unavailable')
}

function safeParams(candidate: AiResearchV2Candidate): string {
  return JSON.stringify(candidate.params, null, 2) ?? '{}'
}

function isFreezeReady(candidate: AiResearchV2Candidate): boolean {
  return isAiResearchV2CandidateFreezeIdentityComplete(candidate, {
    runId: props.runId,
    runExperimentEpochId: props.runExperimentEpochId,
    runDatasetSnapshotId: props.runDatasetSnapshotId,
    datasetSnapshotId: props.datasetSnapshotId,
    datasetContentHash: props.datasetContentHash,
  })
}

function holdoutCommandFor(candidate: AiResearchV2Candidate): AiResearchV2HoldoutCommand | undefined {
  return props.holdoutCommands.find((command) => (
    command.candidate_id === candidate.id
    || command.experiment_epoch_id === candidate.experiment_epoch_id
  ))
}

function holdoutStatusLabel(command: AiResearchV2HoldoutCommand | undefined): string {
  if (command === undefined) return t('strategy.aiResearchTrusted.unavailable')
  const keys: Record<AiResearchV2HoldoutCommand['status'], string> = {
    QUEUED: 'queued',
    RUNNING: 'running',
    RECONCILING: 'reconciling',
    SUCCEEDED: 'succeeded',
    FAILED: 'failed',
    CANCELLED: 'cancelled',
    TIMED_OUT: 'timedOut',
  }
  return t(`strategy.aiResearchTrusted.candidate.holdoutStatus.${keys[command.status]}`)
}

function canRequestHoldout(candidate: AiResearchV2Candidate): boolean {
  return isHoldoutActionAvailable(candidate)
    && props.requestingHoldoutCandidateId === null
}

function isHoldoutActionAvailable(candidate: AiResearchV2Candidate): boolean {
  return candidate.freeze_status === 'FROZEN'
    && isFreezeReady(candidate)
    && holdoutCommandFor(candidate) === undefined
}

function holdoutDescriptionIds(candidate: AiResearchV2Candidate): string {
  const ids = [`trusted-research-candidate-holdout-warning-${candidate.id}`]
  if (!isFreezeReady(candidate)) ids.push(`trusted-research-candidate-incomplete-${candidate.id}`)
  if (holdoutCommandFor(candidate)) ids.push(`trusted-research-candidate-holdout-status-${candidate.id}`)
  return ids.join(' ')
}

function requestHoldout(candidate: AiResearchV2Candidate): void {
  if (!canRequestHoldout(candidate)) return
  emit('requestHoldout', candidate.id, candidate.candidate_hash)
}

function openConfirmation(candidate: AiResearchV2Candidate, event: MouseEvent): void {
  if (
    candidate.freeze_status === 'FROZEN'
    || props.freezingCandidateId !== null
    || !isFreezeReady(candidate)
  ) return
  confirmationLocked = false
  confirmationOpener = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  pendingCandidate.value = candidate
  void nextTick(() => dialogRef.value?.focus())
}

function closeConfirmation(): void {
  if (confirmationLocked) return
  pendingCandidate.value = null
  restoreConfirmationFocus()
}

function restoreConfirmationFocus(): void {
  const opener = confirmationOpener
  confirmationOpener = null
  void nextTick(() => {
    if (opener?.isConnected && !opener.hasAttribute('disabled')) opener.focus()
  })
}

function trapDialogFocus(event: KeyboardEvent): void {
  const dialog = dialogRef.value
  if (dialog === null) return
  const focusable = Array.from(
    dialog.querySelectorAll<HTMLElement>(DIALOG_FOCUSABLE_SELECTOR),
  ).filter((element) => !element.hasAttribute('hidden') && element.getAttribute('aria-hidden') !== 'true')
  if (focusable.length === 0) {
    event.preventDefault()
    dialog.focus()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const activeElement = document.activeElement
  const focusIsOutsideDialog = activeElement === null || !dialog.contains(activeElement)
  if (event.shiftKey && (activeElement === first || activeElement === dialog || focusIsOutsideDialog)) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && (activeElement === last || activeElement === dialog || focusIsOutsideDialog)) {
    event.preventDefault()
    first?.focus()
  }
}

function completeFreezeSubmission(operation: number, succeeded: boolean): void {
  if (activeFreezeSubmission !== operation) return
  activeFreezeSubmission = null
  confirmationLocked = false
  if (succeeded) {
    confirmationOpener = null
  } else {
    restoreConfirmationFocus()
  }
}

function confirmFreeze(): void {
  const candidate = pendingCandidate.value
  if (candidate === null || confirmationLocked) return
  const currentCandidate = props.candidates.find((item) => item.id === candidate.id)
  if (
    currentCandidate === undefined
    || currentCandidate.candidate_hash !== candidate.candidate_hash
    || !isFreezeReady(currentCandidate)
  ) {
    closeConfirmation()
    return
  }
  confirmationLocked = true
  const operation = ++freezeSubmissionGeneration
  activeFreezeSubmission = operation
  pendingCandidate.value = null
  emit(
    'freeze',
    currentCandidate.id,
    currentCandidate.candidate_hash,
    (succeeded) => completeFreezeSubmission(operation, succeeded),
  )
}
</script>

<style scoped>
.candidate-panel { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--bg-color); }
.candidate-panel > header { display: flex; gap: 10px; align-items: flex-start; }
.candidate-panel > header > span { color: var(--primary-color); font-weight: 700; }
.candidate-panel h3, .candidate-panel h4, .candidate-panel p { margin: 0; }
.candidate-panel > header p, .candidate-panel__empty, .candidate-panel__timestamp { color: var(--text-color-secondary); }
.candidate-panel__identity-warning { color: var(--danger-color); }
.candidate-panel__holdout-warning, .candidate-panel__holdout-status { color: var(--text-color-secondary); }
.candidate-panel__holdout-status { padding: 7px 9px; border-radius: 6px; background: var(--fill-color-lighter); }
.candidate-panel__item { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--border-color); border-radius: 7px; }
.candidate-panel__item[data-active='true'] { border-color: var(--primary-color); }
.candidate-panel__item-head { display: flex; justify-content: space-between; gap: 8px; }
.candidate-panel__item-head strong, .candidate-panel dd { overflow-wrap: anywhere; }
.candidate-panel__item-head span { font-weight: 700; }
.candidate-panel__item-head span[data-status='FROZEN'] { color: var(--success-text-color); }
.candidate-panel dl { display: grid; gap: 7px; margin: 0; }
.candidate-panel dl > div { display: grid; grid-template-columns: minmax(130px, .4fr) 1fr; gap: 10px; }
.candidate-panel dt { color: var(--text-color-secondary); }
.candidate-panel dd { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.candidate-panel details summary { cursor: pointer; color: var(--primary-color); }
.candidate-panel pre { max-height: 220px; margin: 8px 0 0; overflow: auto; padding: 8px; border-radius: 5px; background: var(--fill-color); white-space: pre-wrap; }
.candidate-panel button { justify-self: start; }
.candidate-panel__holdout-action { border-color: var(--primary-color) !important; color: var(--primary-color) !important; }
.candidate-panel__dialog-backdrop { position: fixed; inset: 0; z-index: 2100; display: grid; place-items: center; padding: 20px; background: rgb(0 0 0 / 50%); }
.candidate-panel__dialog { display: grid; gap: 12px; width: min(720px, 100%); max-height: 90vh; overflow: auto; padding: 20px; border-radius: 10px; background: var(--bg-color); box-shadow: var(--box-shadow-dark); }
.candidate-panel__warning { padding: 10px; border: 1px solid var(--warning-border-color); border-radius: 6px; color: var(--warning-text-color); background: var(--warning-fill-color-light); }
.candidate-panel__dialog-actions { display: flex; justify-content: flex-end; gap: 8px; }
.candidate-panel__dialog-actions button { justify-self: auto; }
.candidate-panel__confirm { border-color: var(--primary-color) !important; background: var(--primary-color) !important; color: #fff !important; }
@media (max-width: 720px) { .candidate-panel dl > div { grid-template-columns: 1fr; gap: 2px; } }
</style>
