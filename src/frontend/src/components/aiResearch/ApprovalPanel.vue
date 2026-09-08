<template>
  <section
    class="approval-panel"
    aria-labelledby="trusted-approval-title"
    data-test="trusted-approval-panel"
  >
    <header class="approval-panel__header">
      <span>05</span>
      <div>
        <h3 id="trusted-approval-title">
          {{ t('strategy.aiResearchTrusted.approval.title') }}
        </h3>
        <p>{{ t('strategy.aiResearchTrusted.approval.description') }}</p>
      </div>
      <button
        type="button"
        data-test="trusted-approval-refresh"
        :disabled="!hasSelection || runtime.loading.value"
        @click="runtime.refresh"
      >
        {{ t('strategy.aiResearchTrusted.approval.refresh') }}
      </button>
    </header>

    <label
      v-if="candidates.length"
      class="approval-panel__candidate"
    >
      {{ t('strategy.aiResearchTrusted.approval.candidate') }}
      <select
        data-test="trusted-approval-candidate"
        :value="candidateId || ''"
        @change="selectCandidate"
      >
        <option value="">
          {{ t('strategy.aiResearchTrusted.approval.selectCandidate') }}
        </option>
        <option
          v-for="candidate in candidates"
          :key="candidate.id"
          :value="candidate.id"
        >
          {{ candidate.id }}
        </option>
      </select>
    </label>

    <p
      v-if="!hasSelection"
      class="approval-panel__empty"
      data-test="trusted-approval-empty"
    >
      {{ t('strategy.aiResearchTrusted.approval.selectionRequired') }}
    </p>

    <div
      data-test="trusted-approval-live"
      class="approval-panel__live"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      {{ liveStatus }}
    </div>

    <p
      v-if="runtime.errorCode.value"
      class="approval-panel__error"
      data-test="trusted-approval-error"
      role="alert"
    >
      {{ t('strategy.aiResearchTrusted.approval.error', { code: runtime.errorCode.value }) }}
    </p>

    <template v-if="approvalContext">
      <dl class="approval-panel__summary">
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.approval.mode') }}</dt>
          <dd>{{ approvalContext.approval_mode }}</dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.approval.policy') }}</dt>
          <dd>{{ approvalContext.policy_version }}</dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.approval.candidateHash') }}</dt>
          <dd class="approval-panel__hash">
            {{ approvalContext.candidate_hash }}
          </dd>
        </div>
        <div>
          <dt>{{ t('strategy.aiResearchTrusted.approval.policyHash') }}</dt>
          <dd class="approval-panel__hash">
            {{ approvalContext.policy_material_hash }}
          </dd>
        </div>
      </dl>

      <p
        v-if="approvalContext.request_blocked_reason"
        class="approval-panel__blocked"
        data-test="trusted-approval-request-blocked"
      >
        {{ t('strategy.aiResearchTrusted.approval.requestBlocked', {
          code: approvalContext.request_blocked_reason,
        }) }}
      </p>
      <p
        v-if="approvalContext.decision_blocked_reason"
        class="approval-panel__blocked"
        data-test="trusted-approval-blocked"
      >
        {{ t('strategy.aiResearchTrusted.approval.blocked', {
          code: approvalContext.decision_blocked_reason,
        }) }}
      </p>
      <p class="approval-panel__mode-note">
        {{ approvalContext.approval_mode === 'single_actor'
          ? t('strategy.aiResearchTrusted.approval.singleActorNotice')
          : t('strategy.aiResearchTrusted.approval.multiActorNotice') }}
      </p>
      <p
        data-test="trusted-approval-cooldown"
        class="approval-panel__cooldown"
      >
        {{ t('strategy.aiResearchTrusted.approval.cooldown', {
          seconds: approvalContext.cooldown_seconds,
        }) }}
      </p>

      <section
        v-if="approvalContext.machine_evidence_summary"
        class="approval-panel__evidence"
        aria-labelledby="trusted-approval-evidence-title"
      >
        <h4 id="trusted-approval-evidence-title">
          {{ t('strategy.aiResearchTrusted.approval.machineEvidence') }}
        </h4>
        <dl
          class="approval-panel__package"
          data-test="trusted-approval-package"
        >
          <div><dt>ID</dt><dd>{{ approvalContext.machine_evidence_summary.package.id }}</dd></div>
          <div>
            <dt>{{ t('strategy.aiResearchTrusted.approval.packageStatus') }}</dt>
            <dd>{{ approvalContext.machine_evidence_summary.package.status }}</dd>
          </div>
          <div>
            <dt>{{ t('strategy.aiResearchTrusted.approval.packageCommand') }}</dt>
            <dd>{{ approvalContext.machine_evidence_summary.package.command_id }}</dd>
          </div>
          <div>
            <dt>{{ t('strategy.aiResearchTrusted.approval.packageEvaluation') }}</dt>
            <dd>{{ approvalContext.machine_evidence_summary.package.evaluation_id }}</dd>
          </div>
          <div>
            <dt>{{ t('strategy.aiResearchTrusted.approval.gateHash') }}</dt>
            <dd class="approval-panel__hash">
              {{ approvalContext.machine_evidence_summary.package.gate_input_evidence_hash }}
            </dd>
          </div>
          <div>
            <dt>{{ t('strategy.aiResearchTrusted.approval.manifestHash') }}</dt>
            <dd class="approval-panel__hash">
              {{ approvalContext.machine_evidence_summary.package.manifest_hash }}
            </dd>
          </div>
          <div>
            <dt>{{ t('strategy.aiResearchTrusted.approval.bindingHash') }}</dt>
            <dd class="approval-panel__hash">
              {{ approvalContext.machine_evidence_summary.package.approval_binding_hash }}
            </dd>
          </div>
        </dl>
        <ol class="approval-panel__gates">
          <li
            v-for="gate in approvalContext.machine_evidence_summary.gates"
            :key="gate.gate_code"
            data-test="trusted-approval-gate"
          >
            <div>
              <strong>{{ gate.gate_code }}</strong>
              <span>{{ gate.status }}</span>
            </div>
            <p>{{ gate.reason_code }}</p>
            <small class="approval-panel__hash">{{ gate.input_evidence_hash }}</small>
            <small>{{ gate.executor_version }} · {{ gate.evaluated_at }}</small>
          </li>
        </ol>
      </section>
      <p
        v-else
        class="approval-panel__empty"
      >
        {{ t('strategy.aiResearchTrusted.approval.evidenceIncomplete') }}
      </p>

      <section
        v-if="approvalContext.current_request"
        class="approval-panel__request-summary"
        data-test="trusted-approval-current-request"
      >
        <h4>{{ t('strategy.aiResearchTrusted.approval.currentRequest') }}</h4>
        <p>{{ approvalContext.current_request.id }} · {{ approvalContext.current_request.status }}</p>
        <p>
          {{ t('strategy.aiResearchTrusted.approval.requestWindow', {
            eligibleAt: approvalContext.current_request.eligible_at,
            expiresAt: approvalContext.current_request.expires_at,
          }) }}
        </p>
      </section>

      <button
        type="button"
        class="approval-panel__request-action"
        data-test="trusted-approval-request"
        :disabled="!canRequest"
        @click="requestApproval"
      >
        {{ runtime.requesting.value
          ? t('strategy.aiResearchTrusted.approval.requesting')
          : t('strategy.aiResearchTrusted.approval.request') }}
      </button>

      <form
        v-if="approvalContext.current_request"
        class="approval-panel__decision-form"
        @submit.prevent="submitDecision"
      >
        <h4>{{ t('strategy.aiResearchTrusted.approval.decisionTitle') }}</h4>
        <label>
          {{ t('strategy.aiResearchTrusted.approval.decision') }}
          <select
            v-model="form.decision"
            data-test="trusted-approval-decision"
          >
            <option value="APPROVED">
              {{ t('strategy.aiResearchTrusted.approval.approved') }}
            </option>
            <option value="REJECTED">
              {{ t('strategy.aiResearchTrusted.approval.rejected') }}
            </option>
            <option value="REQUESTED_CHANGES">
              {{ t('strategy.aiResearchTrusted.approval.requestedChanges') }}
            </option>
          </select>
        </label>
        <label>
          {{ t('strategy.aiResearchTrusted.approval.reason') }}
          <textarea
            v-model="form.reason"
            data-test="trusted-approval-reason"
            required
            maxlength="2000"
          />
        </label>
        <template v-if="form.decision === 'APPROVED'">
          <label
            v-for="challengeKey in approvalContext.required_challenge_keys"
            :key="challengeKey"
          >
            {{ t('strategy.aiResearchTrusted.approval.challenge', { key: challengeKey }) }}
            <input
              v-model="form.challengeResponses[challengeKey]"
              data-test="trusted-approval-challenge"
              required
              maxlength="1000"
            >
          </label>
        </template>
        <label
          v-if="form.decision === 'APPROVED' && approvalContext.risk_acknowledgement_required"
        >
          {{ t('strategy.aiResearchTrusted.approval.riskAcknowledgement') }}
          <textarea
            v-model="form.residualRiskAcknowledgement"
            data-test="trusted-approval-risk"
            required
            maxlength="2000"
          />
        </label>
        <button
          type="button"
          class="approval-panel__decision-action"
          data-test="trusted-approval-submit"
          :disabled="!canSubmitDecision"
          @click="submitDecision"
        >
          {{ runtime.deciding.value
            ? t('strategy.aiResearchTrusted.approval.deciding')
            : t('strategy.aiResearchTrusted.approval.submitDecision') }}
        </button>
      </form>

      <section
        v-if="approvalContext.latest_decision"
        class="approval-panel__latest"
        data-test="trusted-approval-latest-decision"
      >
        <h4>{{ t('strategy.aiResearchTrusted.approval.latestDecision') }}</h4>
        <strong>{{ approvalContext.latest_decision.decision }}</strong>
        <p>{{ approvalContext.latest_decision.reason }}</p>
        <small>{{ approvalContext.latest_decision.decided_at }}</small>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useAiResearchApproval } from '@/composables/useAiResearchApproval'
import { stripAiResearchApprovalText } from '@/types/aiResearchV2'
import type { AiResearchApprovalDecision, AiResearchV2Candidate } from '@/types/aiResearchV2'

const props = withDefaults(defineProps<{
  runId?: string | null
  candidateId?: string | null
  candidates?: AiResearchV2Candidate[]
}>(), {
  runId: null,
  candidateId: null,
  candidates: () => [],
})

const emit = defineEmits<{
  selectCandidate: [candidateId: string | null]
}>()

const { t } = useI18n()
const runtime = useAiResearchApproval()
const actionStatus = ref('')
const form = reactive({
  decision: 'APPROVED' as AiResearchApprovalDecision,
  reason: '',
  challengeResponses: {} as Record<string, string>,
  residualRiskAcknowledgement: '',
})

const approvalContext = computed(() => runtime.context.value)
const hasSelection = computed(() => Boolean(props.runId && props.candidateId))
const canRequest = computed(() => Boolean(
  approvalContext.value?.can_request
  && approvalContext.value.current_request === null
  && approvalContext.value.machine_evidence_summary !== null
  && !runtime.loading.value
  && !runtime.requesting.value
  && !runtime.deciding.value,
))
const canSubmitDecision = computed(() => {
  const context = approvalContext.value
  if (
    context === null
    || !context.can_decide
    || context.current_request === null
    || context.machine_evidence_summary === null
    || !stripAiResearchApprovalText(form.reason)
    || runtime.loading.value
    || runtime.requesting.value
    || runtime.deciding.value
  ) return false
  if (form.decision === 'APPROVED' && !context.can_approve) return false
  if (form.decision !== 'APPROVED') return true
  if (context.required_challenge_keys.some(
    (key) => !stripAiResearchApprovalText(form.challengeResponses[key] || ''),
  )) {
    return false
  }
  return !context.risk_acknowledgement_required
    || Boolean(stripAiResearchApprovalText(form.residualRiskAcknowledgement))
})
const liveStatus = computed(() => {
  if (runtime.loading.value) return t('strategy.aiResearchTrusted.approval.loading')
  if (runtime.requesting.value) return t('strategy.aiResearchTrusted.approval.requesting')
  if (runtime.deciding.value) return t('strategy.aiResearchTrusted.approval.deciding')
  if (runtime.recoveredAction.value) {
    return t('strategy.aiResearchTrusted.approval.recovered')
  }
  return actionStatus.value
})

function selectCandidate(event: Event): void {
  const value = (event.target as HTMLSelectElement).value.trim()
  emit('selectCandidate', value || null)
}

async function requestApproval(): Promise<void> {
  if (!canRequest.value) return
  const actionScope = selectedScope()
  actionStatus.value = ''
  const receipt = await runtime.requestApproval()
  if (
    receipt !== null
    && actionScope !== null
    && actionScope === selectedScope()
    && receipt.run_id === props.runId
    && receipt.candidate_id === props.candidateId
  ) actionStatus.value = t('strategy.aiResearchTrusted.approval.requested')
}

async function submitDecision(): Promise<void> {
  if (!canSubmitDecision.value) return
  const actionScope = selectedScope()
  actionStatus.value = ''
  const receipt = await runtime.submitDecision({
    decision: form.decision,
    reason: form.reason,
    challengeResponses: form.challengeResponses,
    residualRiskAcknowledgement: form.residualRiskAcknowledgement || null,
  })
  if (
    receipt !== null
    && actionScope !== null
    && actionScope === selectedScope()
    && receipt.run_id === props.runId
    && receipt.candidate_id === props.candidateId
  ) actionStatus.value = t('strategy.aiResearchTrusted.approval.decided')
}

function selectedScope(): string | null {
  return props.runId && props.candidateId ? `${props.runId}\u0000${props.candidateId}` : null
}

function resetForm(): void {
  form.decision = 'APPROVED'
  form.reason = ''
  form.challengeResponses = {}
  form.residualRiskAcknowledgement = ''
  actionStatus.value = ''
}

watch(
  () => [props.runId, props.candidateId] as const,
  ([runId, candidateId]) => {
    resetForm()
    void runtime.select(runId ?? null, candidateId ?? null)
  },
  { immediate: true },
)
</script>

<style scoped>
.approval-panel { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-color-light); border-radius: 10px; background: var(--bg-color); }.approval-panel__header { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: start; }.approval-panel__header > span { display: inline-grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; background: var(--primary-color); color: #fff; font-size: 12px; font-weight: 700; }.approval-panel h3, .approval-panel h4 { margin: 0; }.approval-panel p { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 13px; line-height: 1.5; }.approval-panel button, .approval-panel select, .approval-panel input, .approval-panel textarea { min-height: 34px; padding: 7px 9px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-color); color: var(--text-color-primary); }.approval-panel button { cursor: pointer; }.approval-panel button:disabled { cursor: not-allowed; opacity: .55; }.approval-panel__candidate, .approval-panel__decision-form label { display: grid; gap: 5px; color: var(--text-color-secondary); font-size: 12px; }.approval-panel__live:empty { min-height: 0; }.approval-panel__error, .approval-panel__blocked { padding: 9px; border: 1px solid var(--danger-border-color); border-radius: 6px; color: var(--danger-text-color) !important; }.approval-panel__summary, .approval-panel__package { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 0; }.approval-panel__summary div, .approval-panel__package div { min-width: 0; padding: 8px; border-radius: 6px; background: var(--fill-color-lighter); }.approval-panel dt { color: var(--text-color-secondary); font-size: 11px; }.approval-panel dd { margin: 3px 0 0; font-size: 12px; overflow-wrap: anywhere; }.approval-panel__hash { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }.approval-panel__evidence, .approval-panel__decision-form, .approval-panel__request-summary, .approval-panel__latest { display: grid; gap: 10px; padding-top: 10px; border-top: 1px solid var(--border-color-light); }.approval-panel__gates { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }.approval-panel__gates li { display: grid; gap: 4px; padding: 9px; border-radius: 6px; background: var(--fill-color-lighter); }.approval-panel__gates li > div { display: flex; justify-content: space-between; gap: 8px; }.approval-panel__gates span { color: var(--success-text-color); font-size: 12px; font-weight: 700; }.approval-panel__gates small { color: var(--text-color-secondary); font-size: 11px; }.approval-panel__request-action, .approval-panel__decision-action { justify-self: start; border-color: var(--primary-color) !important; background: var(--primary-color) !important; color: #fff !important; }.approval-panel__decision-form textarea { min-height: 74px; resize: vertical; }.approval-panel__mode-note, .approval-panel__cooldown { color: var(--text-color-secondary); }.approval-panel__empty { color: var(--text-color-secondary); } @media (max-width: 720px) { .approval-panel__header, .approval-panel__summary, .approval-panel__package { grid-template-columns: 1fr; }.approval-panel__header > span { display: none; } }
</style>
