<template>
  <section
    class="trusted-panel"
    aria-labelledby="trusted-evidence-title"
  >
    <header>
      <span>04</span>
      <div>
        <h3 id="trusted-evidence-title">
          {{ t('strategy.aiResearchTrusted.evidence.title') }}
        </h3>
        <p>{{ t('strategy.aiResearchTrusted.evidence.description') }}</p>
      </div>
    </header>
    <p class="trusted-panel__class">
      {{ t('strategy.aiResearchTrusted.evidence.evidenceClass', { value: evidenceClass }) }}
    </p>
    <section
      v-if="holdoutState"
      class="trusted-panel__holdout"
      data-test="trusted-holdout-state"
      :data-status="holdoutState.status"
      role="status"
      aria-live="polite"
    >
      <h4>{{ t('strategy.aiResearchTrusted.evidence.holdoutTitle') }}</h4>
      <p>{{ t(`strategy.aiResearchTrusted.evidence.holdout.${holdoutState.messageKey}`) }}</p>
      <code v-if="holdoutState.errorCode">{{ holdoutState.errorCode }}</code>
    </section>
    <ul
      v-if="gates.length"
      class="trusted-panel__list"
    >
      <li
        v-for="gate in gates"
        :key="String(gate.id)"
      >
        <strong>{{ gate.gate_code }}</strong>
        <span :class="`trusted-panel__status--${String(gate.status).toLowerCase()}`">{{ gate.status }}</span>
        <small>{{ gate.reason }}</small>
      </li>
    </ul>
    <p
      v-else
      class="trusted-panel__empty"
    >
      {{ t('strategy.aiResearchTrusted.evidence.empty') }}
    </p>

    <div
      v-if="governanceDecisions.length"
      class="trusted-panel__summary-group"
      data-test="trusted-governance-deviations"
    >
      <h4>{{ t('strategy.aiResearchTrusted.evidence.governanceDeviations') }}</h4>
      <p>{{ t('strategy.aiResearchTrusted.evidence.governanceLimitation') }}</p>
      <ul class="trusted-panel__list">
        <li
          v-for="decision in governanceDecisions"
          :key="decision.id"
        >
          <strong>{{ decision.target_requirement_or_gate }}</strong>
          <span :class="`trusted-panel__status--${decision.original_status.toLowerCase()}`">{{ decision.original_status }}</span>
          <small>{{ t('strategy.aiResearchTrusted.evidence.governanceEffectiveAt', { value: decision.effective_at }) }}</small>
          <small>{{ t('strategy.aiResearchTrusted.evidence.governanceExpiresAt', { value: decision.expires_at }) }}</small>
          <small v-if="decision.revoked_at">{{ t('strategy.aiResearchTrusted.evidence.governanceRevokedAt', { value: decision.revoked_at }) }}</small>
        </li>
      </ul>
    </div>

    <div class="trusted-panel__summary-group">
      <h4>{{ t('strategy.aiResearchTrusted.evidence.modelLineage') }}</h4>
      <ul
        v-if="modelInvocations.length"
        class="trusted-panel__list"
      >
        <li
          v-for="invocation in modelInvocations"
          :key="invocation.id"
        >
          <strong>{{ invocation.provider }} / {{ invocation.resolved_model }}</strong>
          <small>{{ t('strategy.aiResearchTrusted.evidence.modelPrompt', { value: invocation.prompt_template_version }) }}</small>
          <small>{{ t('strategy.aiResearchTrusted.evidence.modelTokens', { value: formatTokenUsage(invocation.token_usage) }) }}</small>
          <small>{{ t('strategy.aiResearchTrusted.evidence.modelCost', { value: formatCost(invocation.cost) }) }}</small>
          <small v-if="invocation.error_code">{{ t('strategy.aiResearchTrusted.evidence.modelError', { value: invocation.error_code }) }}</small>
        </li>
      </ul>
      <p
        v-else
        class="trusted-panel__empty"
      >
        {{ t('strategy.aiResearchTrusted.evidence.modelEmpty') }}
      </p>
    </div>

    <div class="trusted-panel__summary-group">
      <h4>{{ t('strategy.aiResearchTrusted.evidence.packages') }}</h4>
      <ul
        v-if="evidencePackages.length"
        class="trusted-panel__list"
      >
        <li
          v-for="evidencePackage in evidencePackages"
          :key="evidencePackage.id"
        >
          <strong>{{ evidencePackage.status }}</strong>
          <small>{{ t('strategy.aiResearchTrusted.evidence.packageCandidate', { value: evidencePackage.candidate_id }) }}</small>
          <small>{{ t('strategy.aiResearchTrusted.evidence.packagePolicy', { value: evidencePackage.promotion_policy_version }) }}</small>
          <small class="trusted-panel__hash">{{ t('strategy.aiResearchTrusted.evidence.packageManifest', { value: evidencePackage.manifest_hash }) }}</small>
          <small class="trusted-panel__hash">{{ t('strategy.aiResearchTrusted.evidence.packageBinding', { value: evidencePackage.approval_binding_hash }) }}</small>
        </li>
      </ul>
      <p
        v-else
        class="trusted-panel__empty"
      >
        {{ holdoutState?.status === 'SUCCEEDED_NO_PACKAGE'
          ? t('strategy.aiResearchTrusted.evidence.holdout.succeededNoPackage')
          : t('strategy.aiResearchTrusted.evidence.packagesEmpty') }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  AiResearchV2EvaluationSummary,
  AiResearchV2EvidencePackageSummary,
  AiResearchV2GovernanceDecisionSummary,
  AiResearchV2HoldoutCommand,
  AiResearchV2ModelInvocationSummary,
} from '@/types/aiResearchV2'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  evidenceClass: string
  gates?: Array<Record<string, unknown>>
  governanceDecisions?: AiResearchV2GovernanceDecisionSummary[]
  modelInvocations?: AiResearchV2ModelInvocationSummary[]
  evidencePackages?: AiResearchV2EvidencePackageSummary[]
  holdoutCommands?: AiResearchV2HoldoutCommand[]
  evaluations?: AiResearchV2EvaluationSummary[]
  promotionPolicyVersion?: string | null
}>(), {
  gates: () => [],
  governanceDecisions: () => [],
  modelInvocations: () => [],
  evidencePackages: () => [],
  holdoutCommands: () => [],
  evaluations: () => [],
  promotionPolicyVersion: null,
})

type HoldoutDisplayStatus = AiResearchV2HoldoutCommand['status']
  | 'REJECTED'
  | 'SUCCEEDED_NO_PACKAGE'

interface HoldoutDisplayState {
  status: HoldoutDisplayStatus
  messageKey: string
  errorCode: string | null
}

const holdoutState = computed<HoldoutDisplayState | null>(() => {
  const command = latestCommand(props.holdoutCommands)
  if (command === null) return null
  if (command.status === 'SUCCEEDED') {
    const matchingEvaluations = props.evaluations.filter(
      (item) => evaluationMatchesCommand(item, command),
    )
    const evaluation = matchingEvaluations.length === 1 ? matchingEvaluations[0] : undefined
    if (evaluation?.status === 'REJECTED') {
      return { status: 'REJECTED', messageKey: 'rejected', errorCode: null }
    }
    const hasPackage = evaluation?.status === 'PASSED'
      && props.evidencePackages.some(
        (item) => evidencePackageMatches(item, command, evaluation),
      )
    return hasPackage
      ? { status: 'SUCCEEDED', messageKey: 'succeeded', errorCode: null }
      : { status: 'SUCCEEDED_NO_PACKAGE', messageKey: 'succeededNoPackage', errorCode: null }
  }
  const messageKeys: Record<Exclude<AiResearchV2HoldoutCommand['status'], 'SUCCEEDED'>, string> = {
    QUEUED: 'queued',
    RUNNING: 'running',
    RECONCILING: 'reconciling',
    FAILED: 'failed',
    CANCELLED: 'cancelled',
    TIMED_OUT: 'timedOut',
  }
  return {
    status: command.status,
    messageKey: messageKeys[command.status],
    errorCode: command.status === 'FAILED' ? command.error_code || null : null,
  }
})

function evaluationMatchesCommand(
  evaluation: AiResearchV2EvaluationSummary,
  command: AiResearchV2HoldoutCommand,
): boolean {
  return evaluation.candidate_id === command.candidate_id
    && evaluation.experiment_epoch_id === command.experiment_epoch_id
    && evaluation.dataset_snapshot_id === command.dataset_snapshot_id
    && evaluation.evaluation_type === 'SEALED_HOLDOUT'
    && evaluation.evaluator_identity === command.evaluator_identity
    && evaluation.policy_version === command.policy_version
}

function evidencePackageMatches(
  evidencePackage: AiResearchV2EvidencePackageSummary,
  command: AiResearchV2HoldoutCommand,
  evaluation: AiResearchV2EvaluationSummary,
): boolean {
  return evidencePackage.status === 'ACTIVE'
    && props.promotionPolicyVersion !== null
    && props.promotionPolicyVersion === command.policy_version
    && evidencePackage.promotion_policy_version === props.promotionPolicyVersion
    && evidencePackage.candidate_id === command.candidate_id
    && evidencePackage.command_id === command.id
    && evidencePackage.evaluation_id === evaluation.id
}

function latestCommand(commands: AiResearchV2HoldoutCommand[]): AiResearchV2HoldoutCommand | null {
  return commands.reduce<AiResearchV2HoldoutCommand | null>((latest, command) => {
    if (latest === null) return command
    const latestTime = Date.parse(latest.updated_at)
    const commandTime = Date.parse(command.updated_at)
    if (Number.isFinite(commandTime) && commandTime > latestTime) return command
    if (commandTime === latestTime && command.id > latest.id) return command
    return latest
  }, null)
}

function numberValue(value: Record<string, unknown>, key: string): number | undefined {
  const candidate = value[key]
  return typeof candidate === 'number' && Number.isFinite(candidate) ? candidate : undefined
}

function stringValue(value: Record<string, unknown>, key: string): string | undefined {
  const candidate = value[key]
  return typeof candidate === 'string' && candidate.length > 0 ? candidate : undefined
}

function formatTokenUsage(value: Record<string, unknown>): string {
  const total = numberValue(value, 'total_tokens')
  if (total !== undefined) return String(total)
  const input = numberValue(value, 'input_tokens')
  const output = numberValue(value, 'output_tokens')
  if (input !== undefined || output !== undefined) {
    return [input, output].filter((item): item is number => item !== undefined).join(' / ')
  }
  return t('strategy.aiResearchTrusted.unavailable')
}

function formatCost(value: Record<string, unknown>): string {
  const amount = numberValue(value, 'amount') ?? numberValue(value, 'total_cost')
  if (amount === undefined) return t('strategy.aiResearchTrusted.unavailable')
  return `${stringValue(value, 'currency') || 'USD'} ${amount}`
}
</script>

<style scoped>
.trusted-panel { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-color-light); border-radius: 10px; background: var(--bg-color); }
.trusted-panel header { display: flex; gap: 10px; align-items: flex-start; }
.trusted-panel header > span { display: inline-grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; background: var(--primary-color); color: #fff; font-size: 12px; font-weight: 700; }
.trusted-panel h3, .trusted-panel h4 { margin: 0; }
.trusted-panel h3 { font-size: 15px; }
.trusted-panel h4 { font-size: 13px; }
.trusted-panel p { margin: 4px 0 0; color: var(--text-color-secondary); font-size: 13px; line-height: 1.5; }
.trusted-panel__class { padding: 7px 9px; border-radius: 6px; background: var(--fill-color-lighter); }
.trusted-panel__holdout { display: grid; gap: 4px; padding: 9px; border: 1px solid var(--border-color-light); border-radius: 6px; background: var(--fill-color-lighter); }
.trusted-panel__holdout code { overflow-wrap: anywhere; color: var(--danger-text-color); }
.trusted-panel__summary-group { display: grid; gap: 7px; }
.trusted-panel__list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.trusted-panel__list li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 8px; padding: 8px; border-radius: 6px; background: var(--fill-color-lighter); font-size: 12px; }
.trusted-panel__list small { grid-column: 1 / -1; color: var(--text-color-secondary); }
.trusted-panel__hash { overflow: hidden; font-family: var(--font-family-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.trusted-panel__status--pass { color: var(--success-text-color); }
.trusted-panel__status--fail { color: var(--danger-text-color); }
.trusted-panel__status--blocked, .trusted-panel__status--not_run { color: var(--warning-text-color); }
.trusted-panel__status--unknown { color: var(--warning-text-color); }
.trusted-panel__empty { color: var(--text-color-secondary); }
</style>
