<template>
  <!-- eslint-disable vue/no-v-html -->
  <div class="asset-analysis-page">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">{{ t('assetResearch.page.eyebrow') }}</p>
        <h2>{{ assetConfig.title }}</h2>
        <p class="subtitle">
          {{ assetConfig.description }}
        </p>
      </div>
      <div class="safety-notice">
        <strong>{{ t('assetResearch.page.researchOnly') }}</strong>
        <span>{{ t('assetResearch.page.publishedConclusionNote') }}</span>
      </div>
    </section>

    <section class="analysis-grid">
      <div class="main-column">
        <section class="panel command-panel">
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.targetConfirmKicker') }}</p>
              <h3>{{ t('assetResearch.page.targetConfirmTitle') }}</h3>
            </div>
            <el-tag effect="plain">
              {{ assetConfig.identityLevelLabel }}
            </el-tag>
          </div>

          <div class="command-form">
            <label class="field instrument-input">
              <span>{{ assetConfig.identityLabel }}</span>
              <el-input
                v-model="form.query"
                size="large"
                :placeholder="assetConfig.placeholder"
                clearable
                @keyup.enter="searchCandidates"
              />
            </label>
            <label class="field">
              <span>{{ t('assetResearch.page.positionContext') }}</span>
              <el-select
                v-model="form.positionContext"
                size="large"
                class="full-width"
              >
                <el-option
                  v-for="item in positionOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </label>
            <label class="field">
              <span>{{ t('assetResearch.page.horizon') }}</span>
              <el-select
                v-model="form.horizonCode"
                size="large"
                class="full-width"
              >
                <el-option
                  :label="t('assetResearch.page.standardHorizon')"
                  value="standard"
                />
              </el-select>
            </label>
            <el-button
              class="candidate-search"
              size="large"
              :loading="candidateLoading"
              :disabled="!form.query.trim() || capabilityLoading || !researchEnabled"
              @click="searchCandidates"
            >
              {{ t('assetResearch.page.searchCandidates') }}
            </el-button>
            <el-button
              class="analysis-submit"
              type="primary"
              size="large"
              :loading="submitting || taskLoading"
              :disabled="!resolvedInstrument || capabilityLoading || !researchEnabled"
              @click="submitAnalysis"
            >
              {{ t('assetResearch.page.startResearch', { title: assetConfig.shortTitle }) }}
            </el-button>
          </div>

          <div
            v-if="instrumentCandidates.length"
            class="instrument-candidates"
          >
            <p>{{ t('assetResearch.page.chooseCandidate') }}</p>
            <el-button
              v-for="candidate in instrumentCandidates"
              :key="`${candidate.canonical_id || candidate.symbol}:${candidate.market || ''}`"
              plain
              :loading="candidateLoading"
              @click="confirmCandidate(candidate)"
            >
              {{ t('assetResearch.page.confirmCandidate') }} {{ candidate.symbol }} · {{ candidate.name }}{{ candidate.market ? ` · ${candidate.market}` : '' }}
            </el-button>
          </div>

          <p
            v-if="capabilityLoading"
            class="notice"
          >
            {{ t('assetResearch.page.verifyingCapability') }}
          </p>
          <p
            v-else-if="!researchEnabled"
            class="notice warning"
          >
            {{ capabilityMessage }}
          </p>

          <p
            v-if="submissionNotice"
            class="notice success"
          >
            {{ submissionNotice }}
          </p>
          <p
            v-if="visibleError"
            class="notice error"
          >
            {{ visibleError }}
          </p>

          <div
            v-if="resolvedInstrument"
            class="resolved-instrument"
          >
            <div>
              <span>{{ t('assetResearch.page.confirmedTarget') }}</span>
              <strong>{{ resolvedInstrument.display_symbol }} · {{ resolvedInstrument.name }}</strong>
            </div>
            <small>{{ resolvedInstrument.canonical_id }}</small>
          </div>
        </section>

        <section class="panel asset-policy-panel">
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.assetGateKicker') }}</p>
              <h3>{{ assetConfig.requirement }}</h3>
            </div>
          </div>
          <div class="policy-grid">
            <div>
              <span>{{ t('assetResearch.page.researchFocus') }}</span>
              <strong>{{ assetConfig.focus }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.identityMustContain') }}</span>
              <strong>{{ assetConfig.identityRequirement }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.nonSubstitutable') }}</span>
              <strong>{{ assetConfig.nonSubstitutable }}</strong>
            </div>
          </div>
        </section>

        <section
          v-if="task"
          class="panel task-panel"
        >
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.taskStatus') }}</p>
              <h3>{{ statusLabel(task.status) }}</h3>
              <p>{{ task.message || task.error_code || t('assetResearch.page.waitingForLatestStatus') }}</p>
            </div>
            <el-button
              v-if="canCancel"
              :loading="taskLoading"
              @click="cancelTask"
            >
              {{ t('assetResearch.page.cancelTask') }}
            </el-button>
            <el-button
              v-else-if="task.status === 'FAILED'"
              :loading="taskLoading"
              @click="retryTask"
            >
              {{ t('assetResearch.page.retryTask') }}
            </el-button>
          </div>
          <el-progress
            :percentage="task.progress"
            :stroke-width="10"
            :aria-label="t('assetResearch.page.taskProgress')"
          />
          <p class="task-id">
            {{ t('assetResearch.page.taskId', { id: task.task_id }) }}
          </p>
        </section>

        <section
          v-if="publishedDecision"
          class="panel decision-panel"
        >
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.publishedDecision') }}</p>
              <h3>{{ recommendationLabel(publishedDecision.recommendation) }}</h3>
            </div>
            <el-tag
              :type="decisionTagType(publishedDecision.recommendation)"
              effect="plain"
            >
              {{ actionabilityLabel(publishedDecision.actionability) }}
            </el-tag>
          </div>

          <div class="decision-grid">
            <div>
              <span>{{ t('assetResearch.page.marketView') }}</span>
              <strong>{{ marketViewLabel(publishedDecision.market_view) }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.normalizedDirection') }}</span>
              <strong>{{ normalizedDirectionLabel(publishedDecision.normalized_direction) }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.positionContext') }}</span>
              <strong>{{ positionContextLabel(publishedDecision.position_context) }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.dataQuality') }}</span>
              <strong>{{ qualityLabel(publishedDecision.quality_status) }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.positionIntent') }}</span>
              <strong>{{ tradeIntentLabel(publishedDecision.trade_intent) }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.horizon') }}</span>
              <strong>{{ publishedDecision.horizon_code }}</strong>
            </div>
            <div>
              <span>{{ t('assetResearch.page.executionStatus') }}</span>
              <strong>{{ publishedDecision.execution_disabled ? t('assetResearch.page.disabled') : t('assetResearch.page.notApplicable') }}</strong>
            </div>
          </div>

          <p class="decision-safety">
            {{ decisionSafetyText(publishedDecision.actionability) }}
          </p>
          <div class="decision-invalidation">
            <span>{{ t('assetResearch.page.invalidationConditions') }}</span>
            <ul v-if="publishedDecision.invalidation_conditions?.length">
              <li
                v-for="condition in publishedDecision.invalidation_conditions"
                :key="condition"
              >
                {{ condition }}
              </li>
            </ul>
            <p v-else>
              {{ t('assetResearch.page.noPublicInvalidation') }}
            </p>
          </div>
          <div
            v-if="publishedDecision.reason_codes.length"
            class="reason-codes"
          >
            <span
              v-for="code in publishedDecision.reason_codes"
              :key="code"
            >{{ code }}</span>
          </div>
        </section>

        <FuturesPanel
          v-if="currentAssetType === 'futures' && publishedDecision"
          :identity="resolvedInstrument"
          :details="publishedDecision.asset_details"
        />
        <BondPanel
          v-else-if="currentAssetType === 'bond' && publishedDecision"
          :details="publishedDecision.asset_details"
        />
        <ModelCardPanel
          v-if="publishedDecision"
          class="panel model-card-panel-wrap"
          :model-card="null"
        />

        <section
          v-if="result?.prediction_id"
          class="panel report-panel"
        >
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.reportKicker') }}</p>
              <h3>{{ resolvedInstrument?.name || assetConfig.shortTitle }}</h3>
            </div>
            <div
              v-if="result?.report_id"
              class="export-actions"
            >
              <el-button
                :loading="exporting === 'MARKDOWN'"
                @click="exportReport('MARKDOWN')"
              >
                Markdown
              </el-button>
              <el-button
                :loading="exporting === 'PDF'"
                @click="exportReport('PDF')"
              >
                PDF
              </el-button>
              <el-button
                v-if="publishedDecision"
                @click="openKnowledgeBasePublication"
              >
                {{ t('assetResearch.page.saveToKb') }}
              </el-button>
            </div>
          </div>
          <template v-if="reportSections.length">
            <article
              v-for="section in reportSections"
              :key="section.section_id"
              class="report-section"
            >
              <h4>{{ section.title }}</h4>
              <!-- renderReportMarkdown sanitizes all provider/LLM-derived markup with DOMPurify. -->
              <div
                class="report-markdown"
                v-html="renderReportMarkdown(section.markdown)"
              />
              <div
                v-if="section.evidence_ids?.length"
                class="report-evidence-ids"
              >
                <span>{{ t('assetResearch.page.evidenceIds') }}</span>
                <code
                  v-for="evidenceId in section.evidence_ids"
                  :key="evidenceId"
                >{{ evidenceId }}</code>
              </div>
            </article>
            <p
              v-if="result?.report?.disclaimer"
              class="disclaimer"
            >
              {{ result.report.disclaimer }}
            </p>
          </template>
          <p
            v-else-if="reportRenderFailed"
            class="notice error"
          >
            {{ t('assetResearch.page.reportRenderFailed') }}
          </p>
          <p
            v-else
            class="empty-copy"
          >
            {{ t('assetResearch.page.noReportBody') }}
          </p>
        </section>

        <section
          v-if="result?.prediction_id || evidenceLoading || evidenceError"
          class="panel evidence-panel"
        >
          <div class="panel-heading compact">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.publicEvidenceKicker') }}</p>
              <h3>{{ t('assetResearch.page.evidenceTitle') }}</h3>
            </div>
          </div>
          <p
            v-if="evidenceLoading"
            class="empty-copy"
          >
            {{ t('assetResearch.page.loadingEvidence') }}
          </p>
          <p
            v-else-if="evidenceError"
            class="notice error"
          >
            {{ evidenceError }}
          </p>
          <template v-else-if="signalEvidence">
            <dl class="evidence-list">
              <div v-if="signalEvidence.source_snapshot_hash">
                <dt>{{ t('assetResearch.page.snapshotHash') }}</dt>
                <dd class="evidence-hash">
                  {{ signalEvidence.source_snapshot_hash }}
                </dd>
              </div>
              <div
                v-for="entry in evidenceSourceEntries"
                :key="`source:${entry.key}`"
              >
                <dt>{{ t('assetResearch.page.sourceLabel', { key: entry.key }) }}</dt>
                <dd>{{ entry.value }}</dd>
              </div>
              <div
                v-for="entry in evidenceVersionEntries"
                :key="`version:${entry.key}`"
              >
                <dt>{{ t('assetResearch.page.versionLabel', { key: entry.key }) }}</dt>
                <dd>{{ entry.value }}</dd>
              </div>
            </dl>
            <div
              v-if="signalEvidence.license_tags.length || signalEvidence.reason_codes.length"
              class="evidence-tags"
            >
              <span
                v-for="tag in signalEvidence.license_tags"
                :key="`license:${tag}`"
              >{{ t('assetResearch.page.licenseLabel', { tag }) }}</span>
              <span
                v-for="reasonCode in signalEvidence.reason_codes"
                :key="`reason:${reasonCode}`"
              >{{ reasonCode }}</span>
            </div>
            <p class="evidence-note">
              {{ t('assetResearch.page.evidenceNote') }}
            </p>
          </template>
        </section>
      </div>

      <aside class="side-column">
        <section class="panel scorecard-panel">
          <div class="panel-heading compact">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.scorecardKicker') }}</p>
              <h3>{{ t('assetResearch.page.scorecardTitle') }}</h3>
            </div>
          </div>
          <el-select
            v-if="availableHeadSpecHashes.length > 1"
            v-model="selectedHeadSpecHash"
            class="scorecard-cohort-select"
            :aria-label="t('assetResearch.page.cohortAria')"
            @change="selectScorecardCohort"
          >
            <el-option
              v-for="headSpecHash in availableHeadSpecHashes"
              :key="headSpecHash"
              :label="t('assetResearch.page.cohortLabel', { hash: shortHeadSpecHash(headSpecHash) })"
              :value="headSpecHash"
            />
          </el-select>
          <p
            v-if="summaryLoading"
            class="empty-copy"
          >
            {{ t('assetResearch.page.loadingScorecard') }}
          </p>
          <p
            v-else-if="summaryError"
            class="notice error"
          >
            {{ summaryError }}
          </p>
          <dl
            v-else-if="signalSummary"
            class="scorecard-list"
          >
            <div><dt>{{ t('assetResearch.page.generatedThisCohort') }}</dt><dd>{{ signalSummary.generated_count }}</dd></div>
            <div><dt>{{ t('assetResearch.page.historicalTotal') }}</dt><dd>{{ signalSummary.total_generated_count }}</dd></div>
            <div><dt>{{ t('assetResearch.page.scorable') }}</dt><dd>{{ signalSummary.scorable_count }}</dd></div>
            <div><dt>{{ t('assetResearch.page.coverageRate') }}</dt><dd>{{ formatPercent(signalSummary.coverage_rate) }}</dd></div>
            <div><dt>{{ t('assetResearch.page.maturityRate') }}</dt><dd>{{ formatPercent(signalSummary.maturity_rate) }}</dd></div>
            <div><dt>{{ t('assetResearch.page.actionedSuccessRate') }}</dt><dd>{{ formatPercent(signalSummary.actioned_success_rate) }}</dd></div>
            <div><dt>{{ t('assetResearch.page.brierScore') }}</dt><dd>{{ formatScore(signalSummary.brier_score) }}</dd></div>
            <div><dt>{{ t('assetResearch.page.brierSkillScore') }}</dt><dd>{{ formatPercent(signalSummary.brier_skill_score) }}</dd></div>
            <div><dt>{{ t('assetResearch.page.averageNetReturn') }}</dt><dd>{{ formatPercent(signalSummary.average_net_return) }}</dd></div>
            <div><dt>{{ t('assetResearch.page.maxDrawdown') }}</dt><dd>{{ formatPercent(signalSummary.max_drawdown) }}</dd></div>
          </dl>
          <p
            v-if="!summaryLoading && !summaryError && signalSummary?.calibration_bins?.length"
            class="calibration-copy"
          >
            {{ t('assetResearch.page.calibration', { bins: calibrationSummary(signalSummary.calibration_bins) }) }}
          </p>
          <p
            v-else-if="!summaryLoading && !summaryError"
            class="empty-copy"
          >
            {{ t('assetResearch.page.scorecardHint') }}
          </p>
          <p class="scorecard-note">
            {{ t('assetResearch.page.scorecardNote') }}
          </p>
        </section>

        <section class="panel history-panel">
          <div class="panel-heading compact">
            <div>
              <p class="panel-kicker">{{ t('assetResearch.page.historyKicker') }}</p>
              <h3>{{ t('assetResearch.page.historyTitle') }}</h3>
            </div>
          </div>
          <p
            v-if="historyLoading"
            class="empty-copy"
          >
            {{ t('assetResearch.page.loadingHistory') }}
          </p>
          <p
            v-else-if="historyError"
            class="notice error"
          >
            {{ historyError }}
          </p>
          <ul
            v-else-if="signalHistory.length"
            class="history-list"
          >
            <li
              v-for="item in signalHistory"
              :key="item.prediction_id"
            >
              <strong>{{ recommendationLabel(item.published_decision.recommendation) }}</strong>
              <span>
                {{ formatDate(item.as_of_at) }} · {{ actionabilityLabel(item.actionability) }} ·
                {{ item.owner_scope === 'PUBLIC_SHADOW' ? t('assetResearch.page.publicShadow') : t('assetResearch.page.myResearch') }}
              </span>
            </li>
          </ul>
          <p
            v-else
            class="empty-copy"
          >
            {{ t('assetResearch.page.noHistory') }}
          </p>
        </section>
      </aside>
    </section>

    <section
      v-if="publicationDialogVisible"
      class="publication-dialog-shell"
    >
      <el-dialog
        v-model="publicationDialogVisible"
        :title="t('assetResearch.page.dialogTitle')"
        width="520px"
        :close-on-click-modal="false"
      >
        <p class="publication-dialog-copy">
          {{ t('assetResearch.page.dialogCopy') }}
        </p>
        <label class="publication-field">
          <span>{{ t('assetResearch.page.targetKb') }}</span>
          <p
            v-if="knowledgeBaseLoading"
            class="empty-copy"
          >
            {{ t('assetResearch.page.loadingKb') }}
          </p>
          <select
            v-else
            v-model="publicationForm.targetRef"
            class="knowledge-base-select"
            :aria-label="t('assetResearch.page.targetKb')"
            :disabled="publicationLoading || !knowledgeBases.length"
          >
            <option
              disabled
              value=""
            >
              {{ t('assetResearch.page.selectKb') }}
            </option>
            <option
              v-for="knowledgeBase in knowledgeBases"
              :key="knowledgeBase.id"
              :value="knowledgeBase.id"
            >
              {{ knowledgeBase.name }}
            </option>
          </select>
          <p
            v-if="!knowledgeBaseLoading && !knowledgeBases.length"
            class="empty-copy"
          >
            {{ t('assetResearch.page.noWritableKb') }}
          </p>
        </label>
        <label class="publication-field publication-title">
          <span>{{ t('assetResearch.page.titleOptional') }}</span>
          <el-input
            v-model="publicationForm.title"
            :disabled="publicationLoading"
            maxlength="500"
            :placeholder="t('assetResearch.page.titlePlaceholder')"
          />
        </label>
        <p
          v-if="publicationError"
          class="publication-error"
        >
          {{ publicationError }}
        </p>
        <template #footer>
          <el-button
            :disabled="publicationLoading"
            @click="publicationDialogVisible = false"
          >
            {{ t('assetResearch.page.cancel') }}
          </el-button>
          <el-button
            type="primary"
            :loading="publicationLoading"
            :disabled="knowledgeBaseLoading || !publicationForm.targetRef"
            @click="publishToKnowledgeBase"
          >
            {{ t('assetResearch.page.confirmSave') }}
          </el-button>
        </template>
      </el-dialog>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BondPanel from '@/components/asset-research/BondPanel.vue'
import FuturesPanel from '@/components/asset-research/FuturesPanel.vue'
import ModelCardPanel from '@/components/asset-research/ModelCardPanel.vue'
import {
  assetResearchApi,
  type AssetResearchAssetType,
  type AssetResearchDecision,
  type AssetResearchExportFormat,
  type AssetResearchSignalEvidence,
  type AssetResearchSignalHistoryItem,
  type AssetResearchSignalSummary,
  type InstrumentIdentity,
  type InstrumentSearchCandidate,
} from '@/api/assetResearch'
import { useAssetAnalysisTask } from '@/composables/useAssetAnalysisTask'
import { knowledgeBaseApi, type KnowledgeBaseItem } from '@/api/knowledgeBase'
import { renderMarkdown } from '@/utils/markdown-sanitizer'

const { t } = useI18n()

type PositionContext = 'FLAT' | 'LONG' | 'SHORT' | 'UNKNOWN'

interface AssetConfig {
  title: string
  shortTitle: string
  description: string
  identityLevelLabel: string
  identityLabel: string
  placeholder: string
  requirement: string
  focus: string
  identityRequirement: string
  nonSubstitutable: string
}

const supportedAssetTypes: AssetResearchAssetType[] = ['bond', 'fund', 'futures', 'option', 'fx', 'crypto']

// Values are i18n keys; `assetConfig` resolves them through `t()` so all
// asset-type copy renders in the active locale.
const assetConfigs: Record<AssetResearchAssetType, AssetConfig> = {
  bond: {
    title: 'assetResearch.config.bond.title',
    shortTitle: 'assetResearch.config.bond.shortTitle',
    description: 'assetResearch.config.bond.description',
    identityLevelLabel: 'assetResearch.config.bond.identityLevelLabel',
    identityLabel: 'assetResearch.config.bond.identityLabel',
    placeholder: 'assetResearch.config.bond.placeholder',
    requirement: 'assetResearch.config.bond.requirement',
    focus: 'assetResearch.config.bond.focus',
    identityRequirement: 'assetResearch.config.bond.identityRequirement',
    nonSubstitutable: 'assetResearch.config.bond.nonSubstitutable',
  },
  fund: {
    title: 'assetResearch.config.fund.title',
    shortTitle: 'assetResearch.config.fund.shortTitle',
    description: 'assetResearch.config.fund.description',
    identityLevelLabel: 'assetResearch.config.fund.identityLevelLabel',
    identityLabel: 'assetResearch.config.fund.identityLabel',
    placeholder: 'assetResearch.config.fund.placeholder',
    requirement: 'assetResearch.config.fund.requirement',
    focus: 'assetResearch.config.fund.focus',
    identityRequirement: 'assetResearch.config.fund.identityRequirement',
    nonSubstitutable: 'assetResearch.config.fund.nonSubstitutable',
  },
  futures: {
    title: 'assetResearch.config.futures.title',
    shortTitle: 'assetResearch.config.futures.shortTitle',
    description: 'assetResearch.config.futures.description',
    identityLevelLabel: 'assetResearch.config.futures.identityLevelLabel',
    identityLabel: 'assetResearch.config.futures.identityLabel',
    placeholder: 'assetResearch.config.futures.placeholder',
    requirement: 'assetResearch.config.futures.requirement',
    focus: 'assetResearch.config.futures.focus',
    identityRequirement: 'assetResearch.config.futures.identityRequirement',
    nonSubstitutable: 'assetResearch.config.futures.nonSubstitutable',
  },
  option: {
    title: 'assetResearch.config.option.title',
    shortTitle: 'assetResearch.config.option.shortTitle',
    description: 'assetResearch.config.option.description',
    identityLevelLabel: 'assetResearch.config.option.identityLevelLabel',
    identityLabel: 'assetResearch.config.option.identityLabel',
    placeholder: 'assetResearch.config.option.placeholder',
    requirement: 'assetResearch.config.option.requirement',
    focus: 'assetResearch.config.option.focus',
    identityRequirement: 'assetResearch.config.option.identityRequirement',
    nonSubstitutable: 'assetResearch.config.option.nonSubstitutable',
  },
  fx: {
    title: 'assetResearch.config.fx.title',
    shortTitle: 'assetResearch.config.fx.shortTitle',
    description: 'assetResearch.config.fx.description',
    identityLevelLabel: 'assetResearch.config.fx.identityLevelLabel',
    identityLabel: 'assetResearch.config.fx.identityLabel',
    placeholder: 'assetResearch.config.fx.placeholder',
    requirement: 'assetResearch.config.fx.requirement',
    focus: 'assetResearch.config.fx.focus',
    identityRequirement: 'assetResearch.config.fx.identityRequirement',
    nonSubstitutable: 'assetResearch.config.fx.nonSubstitutable',
  },
  crypto: {
    title: 'assetResearch.config.crypto.title',
    shortTitle: 'assetResearch.config.crypto.shortTitle',
    description: 'assetResearch.config.crypto.description',
    identityLevelLabel: 'assetResearch.config.crypto.identityLevelLabel',
    identityLabel: 'assetResearch.config.crypto.identityLabel',
    placeholder: 'assetResearch.config.crypto.placeholder',
    requirement: 'assetResearch.config.crypto.requirement',
    focus: 'assetResearch.config.crypto.focus',
    identityRequirement: 'assetResearch.config.crypto.identityRequirement',
    nonSubstitutable: 'assetResearch.config.crypto.nonSubstitutable',
  },
}

const props = withDefaults(defineProps<{ assetType?: string }>(), { assetType: 'bond' })

function isSupportedAssetType(value: string): value is AssetResearchAssetType {
  return supportedAssetTypes.includes(value as AssetResearchAssetType)
}

const currentAssetType = computed<AssetResearchAssetType>(() =>
  isSupportedAssetType(props.assetType) ? props.assetType : 'bond',
)
const assetConfig = computed<AssetConfig>(() => {
  const { title, shortTitle, description, identityLevelLabel, identityLabel, placeholder, requirement, focus, identityRequirement, nonSubstitutable } = assetConfigs[currentAssetType.value]
  return { title: t(title), shortTitle: t(shortTitle), description: t(description), identityLevelLabel: t(identityLevelLabel), identityLabel: t(identityLabel), placeholder: t(placeholder), requirement: t(requirement), focus: t(focus), identityRequirement: t(identityRequirement), nonSubstitutable: t(nonSubstitutable) }
})

const form = reactive({
  query: '',
  positionContext: 'UNKNOWN' as PositionContext,
  horizonCode: 'standard',
})
const positionOptions = computed<Array<{ label: string; value: PositionContext }>>(() => [
  { label: t('assetResearch.positionContext.unknown'), value: 'UNKNOWN' },
  { label: t('assetResearch.positionContext.flat'), value: 'FLAT' },
  { label: t('assetResearch.positionContext.long'), value: 'LONG' },
  { label: t('assetResearch.positionContext.short'), value: 'SHORT' },
])

const taskRuntime = useAssetAnalysisTask()
const { task, result, loading: taskLoading, error: taskError } = taskRuntime
const resolvedInstrument = ref<InstrumentIdentity | null>(null)
const instrumentCandidates = ref<InstrumentSearchCandidate[]>([])
const submissionNotice = ref('')
const submissionError = ref('')
const submitting = ref(false)
const exporting = ref<AssetResearchExportFormat | null>(null)
const publicationDialogVisible = ref(false)
const publicationLoading = ref(false)
const knowledgeBaseLoading = ref(false)
const knowledgeBases = ref<KnowledgeBaseItem[]>([])
const publicationError = ref('')
const publicationForm = reactive({
  targetRef: '',
  title: '',
})
const signalHistory = ref<AssetResearchSignalHistoryItem[]>([])
const signalSummary = ref<AssetResearchSignalSummary | null>(null)
const signalEvidence = ref<AssetResearchSignalEvidence | null>(null)
const evidenceLoading = ref(false)
const evidenceError = ref('')
const selectedHeadSpecHash = ref<string | undefined>(undefined)
const historyLoading = ref(false)
const historyError = ref('')
const summaryLoading = ref(false)
const summaryError = ref('')
const capabilityLoading = ref(true)
const researchEnabled = ref(false)
const capabilityReason = ref<string | null>(null)
const candidateLoading = ref(false)
let insightsGeneration = 0
let capabilityGeneration = 0
let publicationGeneration = 0
let evidenceGeneration = 0
let submissionGeneration = 0

const visibleError = computed(() => submissionError.value || errorToText(taskError.value))
const publishedDecision = computed<AssetResearchDecision | null>(() => result.value?.published_decision ?? null)
const reportSections = computed(() => result.value?.report?.sections ?? [])
const reportRenderFailed = computed(() => task.value?.error_code === 'REPORT_RENDER_FAILED')
const canCancel = computed(() => task.value?.status === 'QUEUED' || task.value?.status === 'RUNNING')
const availableHeadSpecHashes = computed(() => signalSummary.value?.available_head_spec_hashes ?? [])
const evidenceSourceEntries = computed(() => evidenceEntries(signalEvidence.value?.source))
const evidenceVersionEntries = computed(() => evidenceEntries(signalEvidence.value?.versions))
const capabilityMessage = computed(() => {
  if (capabilityReason.value === 'INSTRUMENT_CATALOG_UNAVAILABLE') {
    return '数据源许可已配置，但尚无可解析的获批标的主数据，研究任务保持关闭。'
  }
  if (capabilityReason.value === 'SOURCE_CAPABILITY_UNAVAILABLE') {
    return '当前尚无获批的数据源或有效能力清单，研究任务保持关闭。'
  }
  return '当前无法确认数据源许可与标的主数据，研究任务保持关闭。'
})

watch(currentAssetType, () => {
  submissionGeneration += 1
  submitting.value = false
  taskRuntime.reset()
  publicationGeneration += 1
  form.query = ''
  form.positionContext = 'UNKNOWN'
  resolvedInstrument.value = null
  instrumentCandidates.value = []
  submissionNotice.value = ''
  submissionError.value = ''
  publicationDialogVisible.value = false
  publicationLoading.value = false
  knowledgeBaseLoading.value = false
  knowledgeBases.value = []
  publicationError.value = ''
  publicationForm.targetRef = ''
  publicationForm.title = ''
  resetSignalInsights()
  evidenceGeneration += 1
  signalEvidence.value = null
  evidenceLoading.value = false
  evidenceError.value = ''
  void loadCapabilities()
})

watch(
  () => form.query,
  () => {
    resolvedInstrument.value = null
    instrumentCandidates.value = []
    resetSignalInsights()
  },
)

onMounted(() => {
  void loadCapabilities()
})

watch(
  () => result.value?.prediction_id,
  (predictionId) => {
    if (resolvedInstrument.value) {
      void loadSignalInsights(resolvedInstrument.value)
    }
    if (predictionId) {
      void loadSignalEvidence(predictionId)
    } else {
      evidenceGeneration += 1
      signalEvidence.value = null
      evidenceLoading.value = false
      evidenceError.value = ''
    }
  },
)

function createIdempotencyKey(prefix: string): string {
  const uuid = globalThis.crypto?.randomUUID?.()
  return uuid ? `${prefix}-${uuid}` : `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function errorToText(error: unknown): string {
  if (!error) return ''
  if (error instanceof Error && error.message) return error.message
  return '请求失败，请检查标的、数据许可状态或稍后重试。'
}

function statusLabel(status: string): string {
  return ({
    QUEUED: '已排队',
    RUNNING: '研究中',
    SUCCEEDED: '已完成',
    FAILED: '失败',
    CANCELLED: '已取消',
  } as Record<string, string>)[status] ?? status
}

function recommendationLabel(value: string): string {
  return ({ BUY: '买入', SELL: '卖出', HOLD: '持有', AVOID: '回避' } as Record<string, string>)[value] ?? value
}

function actionabilityLabel(value: string): string {
  return ({
    ACTIONABLE: '已准入研究信号',
    RESEARCH_ONLY: '仅研究',
    INSUFFICIENT_DATA: '数据不足',
    REGION_RESTRICTED: '区域受限',
  } as Record<string, string>)[value] ?? value
}

function marketViewLabel(value: string): string {
  return ({ BULLISH: '偏多', BEARISH: '偏空', NEUTRAL: '中性', INDETERMINATE: '无法判定' } as Record<string, string>)[value] ?? value
}

function normalizedDirectionLabel(value: string): string {
  return ({ LONG: '多头', SHORT: '空头', NEUTRAL: '中性', INDETERMINATE: '无法判定' } as Record<string, string>)[value] ?? value
}

function positionContextLabel(value: string): string {
  return ({ FLAT: '无持仓', LONG: '持有多头', SHORT: '持有空头', UNKNOWN: '未知' } as Record<string, string>)[value] ?? value
}

function qualityLabel(value: string): string {
  return ({ ELIGIBLE: '可研究', DEGRADED: '降级', REJECTED: '拒绝发布' } as Record<string, string>)[value] ?? value
}

function tradeIntentLabel(value: string): string {
  return ({ OPEN: '开仓研究', ADD: '加仓研究', REDUCE: '减仓研究', CLOSE: '平仓研究', KEEP: '继续持有', NONE: '无' } as Record<string, string>)[value] ?? value
}

function decisionTagType(value: string): 'success' | 'danger' | 'warning' | 'info' {
  if (value === 'BUY') return 'success'
  if (value === 'SELL' || value === 'AVOID') return 'danger'
  return 'info'
}

function decisionSafetyText(actionability: string): string {
  if (actionability === 'ACTIONABLE') {
    return '该结论仍为研究信号，不连接账户、不生成订单；实际操作必须经过独立风控与人工确认。'
  }
  if (actionability === 'INSUFFICIENT_DATA') {
    return '必要数据或许可不足，系统不会将此结论转化为交易建议。'
  }
  return '模型尚未满足发布为可行动信号的验证门槛；该结论仅用于研究，不能直接下单。'
}

function formatPercent(value?: number | null): string {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '样本不足'
}

function formatScore(value?: number | null): string {
  return typeof value === 'number' ? value.toFixed(3) : '样本不足'
}

function shortHeadSpecHash(value: string): string {
  return `${value.slice(0, 8)}…${value.slice(-6)}`
}

function calibrationSummary(
  bins: NonNullable<AssetResearchSignalSummary['calibration_bins']>,
): string {
  return bins
    .map((bin) => `${Math.round(bin.lower_bound * 100)}–${Math.round(bin.upper_bound * 100)}%：${bin.sample_count}`)
    .join('；')
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString('zh-CN')
}

function renderReportMarkdown(markdown: string): string {
  return renderMarkdown(markdown, { allowImages: false, allowLinks: false })
}

function evidenceEntries(
  values: Record<string, unknown> | Record<string, string | null | undefined> | undefined,
): Array<{ key: string; value: string }> {
  return Object.entries(values ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => ({ key, value: formatEvidenceValue(value) }))
}

function formatEvidenceValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item)).join('，') || '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return '已记录'
}

async function submitAnalysis() {
  if (!resolvedInstrument.value) {
    submissionError.value = '请先搜索并确认一个唯一标的。'
    return
  }
  if (!researchEnabled.value) {
    submissionError.value = `${capabilityMessage.value} 无法提交研究任务。`
    return
  }

  const requestGeneration = ++submissionGeneration
  submitting.value = true
  submissionError.value = ''
  submissionNotice.value = ''
  evidenceGeneration += 1
  signalEvidence.value = null
  evidenceLoading.value = false
  evidenceError.value = ''
  taskRuntime.reset()
  try {
    const created = await assetResearchApi.createTask(
      {
        asset_type: currentAssetType.value,
        canonical_id: resolvedInstrument.value.canonical_id,
        horizon_code: form.horizonCode,
        position_context: form.positionContext,
      },
      createIdempotencyKey('asset-task'),
    )
    if (requestGeneration !== submissionGeneration) return
    submissionNotice.value = '研究任务已提交；页面只会在任务完成后展示已发布结论。'
    await taskRuntime.start(created.task_id)
  } catch (error) {
    if (requestGeneration === submissionGeneration) {
      submissionError.value = errorToText(error)
    }
  } finally {
    if (requestGeneration === submissionGeneration) {
      submitting.value = false
    }
  }
}

async function searchCandidates() {
  const query = form.query.trim()
  if (!query) {
    submissionError.value = `请输入${assetConfig.value.identityLabel}。`
    return
  }
  if (!researchEnabled.value) {
    submissionError.value = `${capabilityMessage.value} 无法搜索标的。`
    return
  }

  candidateLoading.value = true
  submissionError.value = ''
  submissionNotice.value = ''
  resolvedInstrument.value = null
  instrumentCandidates.value = []
  try {
    const response = await assetResearchApi.searchInstruments(
      currentAssetType.value,
      query,
      20,
    )
    instrumentCandidates.value = response.items
    if (!response.items.length) {
      submissionError.value = '未找到可确认的获批标的；请检查代码、交易场所和主数据状态。'
    }
  } catch (error) {
    submissionError.value = errorToText(error)
  } finally {
    candidateLoading.value = false
  }
}

async function confirmCandidate(candidate: InstrumentSearchCandidate) {
  candidateLoading.value = true
  submissionError.value = ''
  try {
    const identityLevel = candidate.identity_level ?? candidate.asset_research_identity?.identity_level
    const identity = await assetResearchApi.resolveInstrument({
      asset_type: currentAssetType.value,
      query: candidate.symbol,
      venue: candidate.market || undefined,
      canonical_id: candidate.canonical_id,
      ...(identityLevel ? { identity_level: identityLevel } : {}),
    })
    resolvedInstrument.value = identity
    instrumentCandidates.value = []
    submissionNotice.value = '标的已确认。请检查持仓上下文后再提交研究任务。'
    await loadSignalInsights(identity)
  } catch (error) {
    submissionError.value = errorToText(error)
  } finally {
    candidateLoading.value = false
  }
}

async function loadCapabilities() {
  const requestGeneration = ++capabilityGeneration
  capabilityLoading.value = true
  researchEnabled.value = false
  capabilityReason.value = null
  try {
    const capabilities = await assetResearchApi.getCapabilities()
    if (requestGeneration !== capabilityGeneration) return
    const currentCapability = capabilities.asset_types.find(
      (capability) => capability.asset_type === currentAssetType.value,
    )
    researchEnabled.value = currentCapability?.research_enabled === true
    capabilityReason.value = researchEnabled.value
      ? null
      : currentCapability?.availability_reason ?? 'SOURCE_CAPABILITY_UNAVAILABLE'
  } catch {
    if (requestGeneration === capabilityGeneration) {
      researchEnabled.value = false
      capabilityReason.value = 'CAPABILITY_LOOKUP_FAILED'
    }
  } finally {
    if (requestGeneration === capabilityGeneration) {
      capabilityLoading.value = false
    }
  }
}

async function cancelTask() {
  await taskRuntime.cancel()
}

async function retryTask() {
  await taskRuntime.retry()
}

async function loadSignalInsights(identity: InstrumentIdentity, headSpecHash?: string) {
  const requestGeneration = ++insightsGeneration
  historyLoading.value = true
  historyError.value = ''
  summaryLoading.value = true
  summaryError.value = ''
  signalHistory.value = []
  signalSummary.value = null
  selectedHeadSpecHash.value = undefined

  const isCurrentRequest = () => (
    requestGeneration === insightsGeneration
    && identity.canonical_id === resolvedInstrument.value?.canonical_id
  )
  const historyRequest = assetResearchApi
    .getSignalHistory(currentAssetType.value, identity.canonical_id)
    .then((history) => {
      if (isCurrentRequest()) signalHistory.value = history.items ?? []
    })
    .catch((error) => {
      if (isCurrentRequest()) historyError.value = `无法读取历史预测：${errorToText(error)}`
    })
    .finally(() => {
      if (isCurrentRequest()) historyLoading.value = false
    })
  const summaryRequest = (async () => {
    const initialSummary = await assetResearchApi.getSignalSummary(
      currentAssetType.value,
      identity.canonical_id,
      headSpecHash,
    )
    const summary = (
      !headSpecHash
      && initialSummary.cohort_selection_required
      && initialSummary.available_head_spec_hashes.length
    )
      ? await assetResearchApi.getSignalSummary(
          currentAssetType.value,
          identity.canonical_id,
          initialSummary.available_head_spec_hashes[0],
        )
      : initialSummary
    if (!isCurrentRequest()) return
    signalSummary.value = summary
    selectedHeadSpecHash.value = summary.head_spec_hash ?? undefined
  })()
    .catch((error) => {
      if (isCurrentRequest()) summaryError.value = `无法读取预测成绩单：${errorToText(error)}`
    })
    .finally(() => {
      if (isCurrentRequest()) summaryLoading.value = false
    })

  await Promise.all([historyRequest, summaryRequest])
}

function resetSignalInsights() {
  insightsGeneration += 1
  signalHistory.value = []
  signalSummary.value = null
  historyLoading.value = false
  historyError.value = ''
  summaryLoading.value = false
  summaryError.value = ''
  selectedHeadSpecHash.value = undefined
}

async function selectScorecardCohort(headSpecHash: string) {
  if (resolvedInstrument.value) {
    await loadSignalInsights(resolvedInstrument.value, headSpecHash)
  }
}

async function loadSignalEvidence(predictionId: string) {
  const requestGeneration = ++evidenceGeneration
  evidenceLoading.value = true
  evidenceError.value = ''
  signalEvidence.value = null
  try {
    const evidence = await assetResearchApi.getSignalEvidence(predictionId)
    if (requestGeneration !== evidenceGeneration || result.value?.prediction_id !== predictionId) return
    signalEvidence.value = evidence
  } catch (error) {
    if (requestGeneration === evidenceGeneration && result.value?.prediction_id === predictionId) {
      evidenceError.value = `无法读取公开证据清单：${errorToText(error)}`
    }
  } finally {
    if (requestGeneration === evidenceGeneration) {
      evidenceLoading.value = false
    }
  }
}

async function exportReport(format: AssetResearchExportFormat) {
  const reportId = result.value?.report_id
  if (!reportId) return
  exporting.value = format
  submissionError.value = ''
  try {
    const exportResult = await assetResearchApi.createReportExport(
      reportId,
      format,
      createIdempotencyKey('asset-export'),
    )
    if (exportResult.status !== 'SUCCEEDED' || !exportResult.download_url) {
      submissionError.value = exportResult.error_code || '报告导出尚未完成，请稍后重试。'
      return
    }
    const content = await assetResearchApi.downloadReportExport(exportResult.download_url)
    const objectUrl = URL.createObjectURL(content)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = `${resolvedInstrument.value?.display_symbol || currentAssetType.value}-research.${format === 'PDF' ? 'pdf' : 'md'}`
    link.click()
    URL.revokeObjectURL(objectUrl)
  } catch (error) {
    submissionError.value = errorToText(error)
  } finally {
    exporting.value = null
  }
}

async function openKnowledgeBasePublication() {
  if (!result.value?.report_id || !publishedDecision.value) return

  const requestGeneration = ++publicationGeneration
  publicationDialogVisible.value = true
  publicationError.value = ''
  publicationForm.targetRef = ''
  publicationForm.title = `${resolvedInstrument.value?.name || assetConfig.value.shortTitle}研究报告`
  knowledgeBases.value = []
  knowledgeBaseLoading.value = true
  try {
    const response = await knowledgeBaseApi.list({ limit: 100 })
    if (requestGeneration !== publicationGeneration || !publicationDialogVisible.value) return
    knowledgeBases.value = response.items
    if (response.items.length === 1) {
      publicationForm.targetRef = response.items[0].id
    }
  } catch (error) {
    if (requestGeneration === publicationGeneration && publicationDialogVisible.value) {
      publicationError.value = `无法读取知识库：${errorToText(error)}`
    }
  } finally {
    if (requestGeneration === publicationGeneration) {
      knowledgeBaseLoading.value = false
    }
  }
}

async function publishToKnowledgeBase() {
  const reportId = result.value?.report_id
  const targetRef = publicationForm.targetRef.trim()
  if (!reportId || !publishedDecision.value) {
    publicationError.value = '只有已发布的研究结论可以保存到知识库。'
    return
  }
  if (!targetRef) {
    publicationError.value = '请选择一个目标知识库。'
    return
  }

  const requestGeneration = ++publicationGeneration
  publicationLoading.value = true
  publicationError.value = ''
  try {
    const title = publicationForm.title.trim()
    const publication = await assetResearchApi.createReportPublication(
      reportId,
      {
        target_type: 'KNOWLEDGE_BASE',
        target_ref: targetRef,
        ...(title ? { title } : {}),
      },
      createIdempotencyKey('asset-publication'),
    )
    if (requestGeneration !== publicationGeneration) return
    if (publication.status === 'FAILED') {
      publicationError.value = publication.error_code || '保存到知识库失败，请稍后重试。'
      return
    }
    publicationDialogVisible.value = false
    submissionNotice.value = publication.status === 'SUCCEEDED'
      ? '已保存到知识库；保存的是已发布研究结论。'
      : '保存任务已提交；保存的是已发布研究结论。'
  } catch (error) {
    if (requestGeneration === publicationGeneration) {
      publicationError.value = errorToText(error)
    }
  } finally {
    if (requestGeneration === publicationGeneration) {
      publicationLoading.value = false
    }
  }
}
</script>

<style scoped>
.asset-analysis-page {
  display: grid;
  gap: 20px;
  padding: 4px;
  color: var(--el-text-color-primary);
  --el-color-primary: #2858c5;
}

.hero-panel,
.panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 14px;
  background: var(--el-bg-color);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  padding: 26px;
  background: linear-gradient(130deg, rgba(59, 130, 246, 0.08), rgba(15, 118, 110, 0.06));
}

.eyebrow,
.panel-kicker {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

h2,
h3,
h4,
p { margin-top: 0; }
h2 { margin-bottom: 8px; }
h3 { margin-bottom: 6px; font-size: 18px; }
.subtitle { margin-bottom: 0; color: var(--el-text-color-regular); }

.safety-notice {
  display: grid;
  gap: 4px;
  max-width: 360px;
  padding: 14px 16px;
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 10px;
  background: rgba(254, 243, 199, 0.45);
  color: #92400e;
  font-size: 13px;
}

.analysis-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 290px;
  gap: 20px;
}
.main-column,
.side-column { display: grid; align-content: start; gap: 20px; min-width: 0; }
.panel { padding: 22px; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.panel-heading.compact { align-items: center; }
.panel-heading > div > p:last-child { margin-bottom: 0; color: var(--el-text-color-regular); font-size: 13px; }

.command-form { display: grid; grid-template-columns: minmax(220px, 2fr) minmax(130px, 1fr) minmax(120px, 0.8fr) auto; align-items: end; gap: 12px; margin-top: 20px; }
.field { display: grid; gap: 7px; color: var(--el-text-color-regular); font-size: 13px; }
.field > span { font-weight: 600; }
.full-width { width: 100%; }
.analysis-submit {
  min-height: 40px;
  --el-button-bg-color: #2858c5;
  --el-button-border-color: #2858c5;
  --el-button-hover-bg-color: #1f4aa7;
  --el-button-hover-border-color: #1f4aa7;
  --el-button-active-bg-color: #183b89;
  --el-button-active-border-color: #183b89;
  --el-button-text-color: #ffffff;
}
.instrument-candidates { display: grid; gap: 8px; margin-top: 16px; padding: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 9px; background: var(--el-fill-color-lighter); }
.instrument-candidates p { margin: 0; color: var(--el-text-color-regular); font-size: 13px; }
.notice { margin: 14px 0 0; font-size: 13px; }
.notice.success { color: #087443; }
.notice.error { color: var(--el-color-danger); }
.notice.warning { color: var(--el-color-warning); }
.resolved-instrument { display: grid; gap: 4px; margin-top: 16px; padding: 12px; border-radius: 9px; background: var(--el-fill-color-light); }
.resolved-instrument div { display: flex; justify-content: space-between; gap: 12px; }
.resolved-instrument span, .resolved-instrument small { color: var(--el-text-color-secondary); font-size: 12px; overflow-wrap: anywhere; }

.policy-grid, .decision-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.policy-grid { margin-top: 18px; }
.policy-grid > div, .decision-grid > div { display: grid; gap: 6px; padding: 12px; border-radius: 9px; background: var(--el-fill-color-light); }
.policy-grid span, .decision-grid span { color: var(--el-text-color-secondary); font-size: 12px; }
.policy-grid strong { font-size: 13px; line-height: 1.5; }
.decision-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 18px; }
.decision-grid strong { font-size: 15px; }
.decision-panel :deep(.el-tag--info) {
  --el-tag-text-color: #3a4352;
  --el-tag-bg-color: #eef2f6;
  --el-tag-border-color: #aeb7c5;
  color: #3a4352;
  background-color: #eef2f6;
  border-color: #aeb7c5;
}
.decision-panel :deep(.el-tag--info .el-tag__content) {
  color: #3a4352;
}

.task-panel :deep(.el-progress) { margin-top: 16px; }
.task-id { margin: 12px 0 0; color: var(--el-text-color-secondary); font-size: 12px; overflow-wrap: anywhere; }
.decision-safety { margin: 16px 0 0; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.65; }
.decision-invalidation { display: grid; gap: 8px; margin-top: 14px; padding: 12px; border-radius: 9px; background: var(--el-fill-color-light); }
.decision-invalidation > span { color: var(--el-text-color-secondary); font-size: 12px; font-weight: 600; }
.decision-invalidation p, .decision-invalidation ul { margin: 0; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.6; }
.decision-invalidation ul { padding-left: 18px; }
.reason-codes { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.reason-codes span { padding: 4px 8px; border-radius: 999px; background: var(--el-fill-color-light); color: var(--el-text-color-secondary); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }

.export-actions { display: flex; gap: 8px; }
.report-evidence-ids { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; color: var(--el-text-color-secondary); font-size: 12px; }
.report-evidence-ids code, .evidence-tags span { padding: 3px 7px; border-radius: 999px; background: var(--el-fill-color-light); color: var(--el-text-color-secondary); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.evidence-list { display: grid; gap: 10px; margin: 18px 0 0; }
.evidence-list div { display: grid; gap: 4px; }
.evidence-list dt { color: var(--el-text-color-secondary); font-size: 12px; }
.evidence-list dd { margin: 0; overflow-wrap: anywhere; font-size: 13px; }
.evidence-hash { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px !important; }
.evidence-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.evidence-note { margin: 14px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.publication-dialog-copy { margin: 0 0 16px; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.65; }
.publication-field { display: grid; gap: 8px; margin-top: 16px; color: var(--el-text-color-regular); font-size: 13px; }
.publication-field > span { font-weight: 600; }
.knowledge-base-select { width: 100%; min-height: 40px; padding: 0 10px; border: 1px solid var(--el-border-color); border-radius: 4px; background: var(--el-bg-color); color: var(--el-text-color-primary); }
.publication-error { margin: 16px 0 0; color: var(--el-color-danger); font-size: 13px; }
.report-section + .report-section { margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--el-border-color-lighter); }
.report-section h4 { margin-bottom: 10px; }
.report-markdown { color: var(--el-text-color-regular); line-height: 1.7; overflow-wrap: anywhere; }
.report-markdown :deep(p:last-child) { margin-bottom: 0; }
.disclaimer { margin: 18px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }

.scorecard-list { display: grid; gap: 10px; margin: 18px 0 0; }
.scorecard-list div { display: flex; justify-content: space-between; gap: 12px; }
.scorecard-list dt { color: var(--el-text-color-secondary); font-size: 13px; }
.scorecard-list dd { margin: 0; font-weight: 700; }
.scorecard-cohort-select { width: 100%; margin: 14px 0 2px; }
.scorecard-note, .empty-copy, .calibration-copy { margin: 16px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.history-list { display: grid; gap: 10px; padding: 0; margin: 18px 0 0; list-style: none; }
.history-list li { display: grid; gap: 3px; padding-bottom: 10px; border-bottom: 1px solid var(--el-border-color-lighter); }
.history-list span { color: var(--el-text-color-secondary); font-size: 12px; }

@media (max-width: 1100px) {
  .analysis-grid { grid-template-columns: 1fr; }
  .side-column { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .hero-panel, .panel-heading { align-items: flex-start; flex-direction: column; }
  .command-form, .policy-grid, .decision-grid, .side-column { grid-template-columns: 1fr; }
  .safety-notice { max-width: none; }
  .resolved-instrument div { display: grid; }
}
</style>
