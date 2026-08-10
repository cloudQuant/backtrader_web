<template>
  <!-- eslint-disable vue/no-v-html -->
  <div class="asset-analysis-page">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">
          多资产 AI 研究
        </p>
        <h2>{{ assetConfig.title }}</h2>
        <p class="subtitle">
          {{ assetConfig.description }}
        </p>
      </div>
      <div class="safety-notice">
        <strong>研究用途，不能直接下单</strong>
        <span>结论仅来自已发布的研究决策；候选模型、概率和未成熟评分均不会对外展示。</span>
      </div>
    </section>

    <section class="analysis-grid">
      <div class="main-column">
        <section class="panel command-panel">
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">
                标的确认
              </p>
              <h3>先确认唯一标的，再启动分析</h3>
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
              <span>持仓上下文</span>
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
              <span>研究周期</span>
              <el-select
                v-model="form.horizonCode"
                size="large"
                class="full-width"
              >
                <el-option
                  label="标准周期"
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
              搜索候选
            </el-button>
            <el-button
              class="analysis-submit"
              type="primary"
              size="large"
              :loading="submitting || taskLoading"
              :disabled="!resolvedInstrument || capabilityLoading || !researchEnabled"
              @click="submitAnalysis"
            >
              开始 {{ assetConfig.shortTitle }}研究
            </el-button>
          </div>

          <div
            v-if="instrumentCandidates.length"
            class="instrument-candidates"
          >
            <p>请选择一个候选标的；系统不会自动替你选择。</p>
            <el-button
              v-for="candidate in instrumentCandidates"
              :key="`${candidate.canonical_id || candidate.symbol}:${candidate.market || ''}`"
              plain
              :loading="candidateLoading"
              @click="confirmCandidate(candidate)"
            >
              确认 {{ candidate.symbol }} · {{ candidate.name }}{{ candidate.market ? ` · ${candidate.market}` : '' }}
            </el-button>
          </div>

          <p
            v-if="capabilityLoading"
            class="notice"
          >
            正在核验数据源许可与研究能力…
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
              <span>已确认标的</span>
              <strong>{{ resolvedInstrument.display_symbol }} · {{ resolvedInstrument.name }}</strong>
            </div>
            <small>{{ resolvedInstrument.canonical_id }}</small>
          </div>
        </section>

        <section class="panel asset-policy-panel">
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">
                资产专属门控
              </p>
              <h3>{{ assetConfig.requirement }}</h3>
            </div>
          </div>
          <div class="policy-grid">
            <div>
              <span>研究焦点</span>
              <strong>{{ assetConfig.focus }}</strong>
            </div>
            <div>
              <span>身份必须包含</span>
              <strong>{{ assetConfig.identityRequirement }}</strong>
            </div>
            <div>
              <span>不可替代条件</span>
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
              <p class="panel-kicker">
                任务状态
              </p>
              <h3>{{ statusLabel(task.status) }}</h3>
              <p>{{ task.message || task.error_code || '正在等待研究任务的最新状态。' }}</p>
            </div>
            <el-button
              v-if="canCancel"
              :loading="taskLoading"
              @click="cancelTask"
            >
              取消任务
            </el-button>
            <el-button
              v-else-if="task.status === 'FAILED'"
              :loading="taskLoading"
              @click="retryTask"
            >
              重新尝试
            </el-button>
          </div>
          <el-progress
            :percentage="task.progress"
            :stroke-width="10"
            aria-label="研究任务进度"
          />
          <p class="task-id">
            任务 ID：{{ task.task_id }}
          </p>
        </section>

        <section
          v-if="publishedDecision"
          class="panel decision-panel"
        >
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">
                已发布研究结论
              </p>
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
              <span>市场观点</span>
              <strong>{{ marketViewLabel(publishedDecision.market_view) }}</strong>
            </div>
            <div>
              <span>规范方向</span>
              <strong>{{ normalizedDirectionLabel(publishedDecision.normalized_direction) }}</strong>
            </div>
            <div>
              <span>持仓上下文</span>
              <strong>{{ positionContextLabel(publishedDecision.position_context) }}</strong>
            </div>
            <div>
              <span>数据质量</span>
              <strong>{{ qualityLabel(publishedDecision.quality_status) }}</strong>
            </div>
            <div>
              <span>持仓意图</span>
              <strong>{{ tradeIntentLabel(publishedDecision.trade_intent) }}</strong>
            </div>
            <div>
              <span>研究周期</span>
              <strong>{{ publishedDecision.horizon_code }}</strong>
            </div>
            <div>
              <span>执行状态</span>
              <strong>{{ publishedDecision.execution_disabled ? '已禁用' : '不适用' }}</strong>
            </div>
          </div>

          <p class="decision-safety">
            {{ decisionSafetyText(publishedDecision.actionability) }}
          </p>
          <div class="decision-invalidation">
            <span>失效条件</span>
            <ul v-if="publishedDecision.invalidation_conditions?.length">
              <li
                v-for="condition in publishedDecision.invalidation_conditions"
                :key="condition"
              >
                {{ condition }}
              </li>
            </ul>
            <p v-else>
              当前未提供可公开的失效条件；结论维持研究观察，不构成执行指令。
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
              <p class="panel-kicker">
                研究报告
              </p>
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
                保存到知识库
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
                <span>证据 ID</span>
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
            研报正文暂不可用：报告渲染失败。已发布结构化结论仍可查看，稍后可重试生成研报。
          </p>
          <p
            v-else
            class="empty-copy"
          >
            尚无可公开的研报正文；已发布结论不受影响。
          </p>
        </section>

        <section
          v-if="result?.prediction_id || evidenceLoading || evidenceError"
          class="panel evidence-panel"
        >
          <div class="panel-heading compact">
            <div>
              <p class="panel-kicker">
                公开证据清单
              </p>
              <h3>来源、版本与数据快照</h3>
            </div>
          </div>
          <p
            v-if="evidenceLoading"
            class="empty-copy"
          >
            正在读取公开证据清单…
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
                <dt>快照哈希</dt>
                <dd class="evidence-hash">
                  {{ signalEvidence.source_snapshot_hash }}
                </dd>
              </div>
              <div
                v-for="entry in evidenceSourceEntries"
                :key="`source:${entry.key}`"
              >
                <dt>来源 · {{ entry.key }}</dt>
                <dd>{{ entry.value }}</dd>
              </div>
              <div
                v-for="entry in evidenceVersionEntries"
                :key="`version:${entry.key}`"
              >
                <dt>版本 · {{ entry.key }}</dt>
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
              >许可：{{ tag }}</span>
              <span
                v-for="reasonCode in signalEvidence.reason_codes"
                :key="`reason:${reasonCode}`"
              >{{ reasonCode }}</span>
            </div>
            <p class="evidence-note">
              页面仅展示来源、版本、哈希和稳定证据 ID；原始载荷与候选决策始终不向前端公开。
            </p>
          </template>
        </section>
      </div>

      <aside class="side-column">
        <section class="panel scorecard-panel">
          <div class="panel-heading compact">
            <div>
              <p class="panel-kicker">
                预测成绩单
              </p>
              <h3>仅统计已成熟样本</h3>
            </div>
          </div>
          <el-select
            v-if="availableHeadSpecHashes.length > 1"
            v-model="selectedHeadSpecHash"
            class="scorecard-cohort-select"
            aria-label="评分口径"
            @change="selectScorecardCohort"
          >
            <el-option
              v-for="headSpecHash in availableHeadSpecHashes"
              :key="headSpecHash"
              :label="`评分口径 ${shortHeadSpecHash(headSpecHash)}`"
              :value="headSpecHash"
            />
          </el-select>
          <p
            v-if="summaryLoading"
            class="empty-copy"
          >
            正在读取预测成绩单…
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
            <div><dt>已生成（此口径）</dt><dd>{{ signalSummary.generated_count }}</dd></div>
            <div><dt>历史总数</dt><dd>{{ signalSummary.total_generated_count }}</dd></div>
            <div><dt>可评分</dt><dd>{{ signalSummary.scorable_count }}</dd></div>
            <div><dt>覆盖率</dt><dd>{{ formatPercent(signalSummary.coverage_rate) }}</dd></div>
            <div><dt>成熟率</dt><dd>{{ formatPercent(signalSummary.maturity_rate) }}</dd></div>
            <div><dt>已行动成功率</dt><dd>{{ formatPercent(signalSummary.actioned_success_rate) }}</dd></div>
            <div><dt>Brier 分数</dt><dd>{{ formatScore(signalSummary.brier_score) }}</dd></div>
            <div><dt>Brier 技能分</dt><dd>{{ formatPercent(signalSummary.brier_skill_score) }}</dd></div>
            <div><dt>平均净收益</dt><dd>{{ formatPercent(signalSummary.average_net_return) }}</dd></div>
            <div><dt>最大回撤</dt><dd>{{ formatPercent(signalSummary.max_drawdown) }}</dd></div>
          </dl>
          <p
            v-if="!summaryLoading && !summaryError && signalSummary?.calibration_bins?.length"
            class="calibration-copy"
          >
            校准分桶：{{ calibrationSummary(signalSummary.calibration_bins) }}
          </p>
          <p
            v-else-if="!summaryLoading && !summaryError"
            class="empty-copy"
          >
            确认标的后，将显示这个资产的历史评分覆盖率与成熟度。
          </p>
          <p class="scorecard-note">
            不同目标定义会分开评分；没有可评分样本时，不会以 0% 冒充成功率。
          </p>
        </section>

        <section class="panel history-panel">
          <div class="panel-heading compact">
            <div>
              <p class="panel-kicker">
                历史预测
              </p>
              <h3>已发布结论</h3>
            </div>
          </div>
          <p
            v-if="historyLoading"
            class="empty-copy"
          >
            正在读取历史预测…
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
                {{ item.owner_scope === 'PUBLIC_SHADOW' ? '公共影子' : '我的研究' }}
              </span>
            </li>
          </ul>
          <p
            v-else
            class="empty-copy"
          >
            尚无已发布的历史预测。
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
        title="保存已发布研报到知识库"
        width="520px"
        :close-on-click-modal="false"
      >
        <p class="publication-dialog-copy">
          仅保存已发布研究结论；候选模型、内部概率和未成熟评分不会被导出。
        </p>
        <label class="publication-field">
          <span>目标知识库</span>
          <p
            v-if="knowledgeBaseLoading"
            class="empty-copy"
          >
            正在读取可写入的知识库…
          </p>
          <select
            v-else
            v-model="publicationForm.targetRef"
            class="knowledge-base-select"
            aria-label="目标知识库"
            :disabled="publicationLoading || !knowledgeBases.length"
          >
            <option
              disabled
              value=""
            >
              请选择知识库
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
            当前没有可写入的知识库；请先创建一个知识库后再保存。
          </p>
        </label>
        <label class="publication-field publication-title">
          <span>文档标题（可选）</span>
          <el-input
            v-model="publicationForm.title"
            :disabled="publicationLoading"
            maxlength="500"
            placeholder="默认使用标的名称和研究报告"
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
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="publicationLoading"
            :disabled="knowledgeBaseLoading || !publicationForm.targetRef"
            @click="publishToKnowledgeBase"
          >
            确认保存
          </el-button>
        </template>
      </el-dialog>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

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

const assetConfigs: Record<AssetResearchAssetType, AssetConfig> = {
  bond: {
    title: 'AI债券',
    shortTitle: '债券',
    description: '以单只债券为单位评估估值、久期、信用和流动性，不将缺失估值替换为其他标的。',
    identityLevelLabel: '债券发行/上市标识',
    identityLabel: '债券代码或 ISIN',
    placeholder: '例如：113000 或 US0000000000',
    requirement: '成交/估值、收益率曲线、现金流和信用信息需同时满足许可与可得性要求',
    focus: '到期收益率、久期、信用利差、流动性',
    identityRequirement: '发行主体、到期日、债券发行/上市层级',
    nonSubstitutable: '官方估值/可执行价格与结算日历',
  },
  fund: {
    title: 'AI基金',
    shortTitle: '基金',
    description: '以基金份额或上市份额为单位，区分净值、折溢价、跟踪误差与基准。',
    identityLevelLabel: '基金份额/上市标识',
    identityLabel: '基金代码',
    placeholder: '例如：510300 或 000001',
    requirement: '官方净值、基准、份额/成分与交易流动性均须可追溯',
    focus: '净值、折溢价、跟踪误差、风格漂移',
    identityRequirement: '基金、份额类别、净值日历与官方基准',
    nonSubstitutable: '官方净值与基金估值日历',
  },
  futures: {
    title: 'AI期货',
    shortTitle: '期货',
    description: '以具体合约而非模糊品种研究期限结构、基差、展期和保证金约束。',
    identityLevelLabel: '具体期货合约',
    identityLabel: '合约代码',
    placeholder: '例如：IF2609',
    requirement: '合约行情、交易日历、到期日、合约乘数与保证金数据必须可用',
    focus: '展期与基差、期限结构、到期与保证金',
    identityRequirement: '交易所、合约月份、到期日和交易日历',
    nonSubstitutable: '具体合约行情与到期/展期规则',
  },
  option: {
    title: 'AI期权',
    shortTitle: '期权',
    description: '将方向、波动率和合约结构分开评估；必须先锁定期权系列与合约条款。',
    identityLevelLabel: '具体期权合约',
    identityLabel: '期权合约代码',
    placeholder: '例如：510050C2609M03000',
    requirement: '完整期权链、合约条款与标的行情',
    focus: '方向、隐含波动率、希腊字母和合约相对价值',
    identityRequirement: '到期日、行权价与看涨/看跌',
    nonSubstitutable: '完整期权链、乘数与行权/交割规则',
  },
  fx: {
    title: 'AI外汇',
    shortTitle: '外汇',
    description: '明确基准/报价币、即期/远期/NDF 与报价口径，避免方向和点差的歧义。',
    identityLevelLabel: '货币对产品',
    identityLabel: '货币对',
    placeholder: '例如：USD/CNY',
    requirement: '同一报价口径的价格、结算日历与利率/远期点信息必须一致',
    focus: '方向、利差/远期点、估值缺口与流动性',
    identityRequirement: '基准币、报价币、产品类型与结算规则',
    nonSubstitutable: '报价币种方向和可验证的报价口径',
  },
  crypto: {
    title: 'AI数字货币',
    shortTitle: '数字货币',
    description: '区分链上资产、现货与衍生品；交易场所和产品结构是不可省略的身份信息。',
    identityLevelLabel: '加密资产/交易产品',
    identityLabel: '资产或交易对',
    placeholder: '例如：BTC/USDT 或 ETH',
    requirement: '指定交易场所行情、产品类型、资金费率/基差和场所风险信息须可用',
    focus: '价格结构、资金费率、基差、链上状态与场所风险',
    identityRequirement: '链/合约地址或交易对、场所和产品类型',
    nonSubstitutable: '交易场所、结算资产与产品线性/反向属性',
  },
}

const props = withDefaults(defineProps<{ assetType?: string }>(), { assetType: 'bond' })

function isSupportedAssetType(value: string): value is AssetResearchAssetType {
  return supportedAssetTypes.includes(value as AssetResearchAssetType)
}

const currentAssetType = computed<AssetResearchAssetType>(() =>
  isSupportedAssetType(props.assetType) ? props.assetType : 'bond',
)
const assetConfig = computed(() => assetConfigs[currentAssetType.value])

const form = reactive({
  query: '',
  positionContext: 'UNKNOWN' as PositionContext,
  horizonCode: 'standard',
})
const positionOptions: Array<{ label: string; value: PositionContext }> = [
  { label: '未知（默认）', value: 'UNKNOWN' },
  { label: '无持仓', value: 'FLAT' },
  { label: '持有多头', value: 'LONG' },
  { label: '持有空头', value: 'SHORT' },
]

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
