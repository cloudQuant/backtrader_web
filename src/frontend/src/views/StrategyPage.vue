<template>
  <div class="space-y-6">
    <!-- Page action bar -->
    <div class="flex justify-end items-center">
      <el-button
        type="primary"
        :aria-label="t('strategy.createStrategy')"
        @click="showCreateDialog"
      >
        <el-icon
          class="mr-1"
          aria-hidden="true"
        >
          <Plus />
        </el-icon>
        {{ t('strategy.createStrategy') }}
      </el-button>
    </div>

    <!-- Main tabs: Gallery / My strategies -->
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <!-- ========== AI Research Loop ========== -->
      <el-tab-pane
        :label="t('strategy.aiResearch')"
        name="aiResearch"
      >
        <div class="ai-research-grid">
          <section class="ai-research-panel">
            <el-form
              label-position="top"
              :model="aiResearchForm"
            >
              <el-form-item :label="t('strategy.aiResearchPrompt')">
                <el-input
                  v-model="aiResearchForm.prompt"
                  type="textarea"
                  :rows="5"
                  :placeholder="t('strategy.aiResearchPromptPlaceholder')"
                  data-test="ai-research-prompt"
                />
              </el-form-item>

              <div class="ai-research-form-grid">
                <el-form-item :label="t('strategy.aiResearchSymbol')">
                  <el-input
                    v-model="aiResearchForm.symbol"
                    data-test="ai-research-symbol"
                  />
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchSymbolName')">
                  <el-input v-model="aiResearchForm.symbol_name" />
                </el-form-item>
                <el-form-item label="知识库 ID">
                  <el-input
                    v-model="aiResearchForm.knowledge_base_id"
                    clearable
                    placeholder="可选"
                    data-test="ai-research-knowledge-base"
                  />
                </el-form-item>
                <el-form-item label="生成模式">
                  <el-checkbox
                    v-model="aiResearchForm.thinking_mode"
                    data-test="ai-research-thinking-mode"
                  >
                    深度思考
                  </el-checkbox>
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchTimeframe')">
                  <el-select
                    v-model="aiResearchForm.timeframe"
                    class="w-full"
                  >
                    <el-option
                      label="1d"
                      value="1d"
                    />
                    <el-option
                      label="1h"
                      value="1h"
                    />
                    <el-option
                      label="30m"
                      value="30m"
                    />
                    <el-option
                      label="5m"
                      value="5m"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchTargetSharpe')">
                  <el-input-number
                    v-model="aiResearchForm.target_sharpe"
                    :min="-5"
                    :max="10"
                    :step="0.1"
                    class="w-full"
                  />
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchMaxIterations')">
                  <el-input-number
                    v-model="aiResearchForm.max_iterations"
                    :min="1"
                    :max="8"
                    class="w-full"
                  />
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchMinTrades')">
                  <el-input-number
                    v-model="aiResearchForm.min_total_trades"
                    :min="0"
                    :max="9999"
                    class="w-full"
                  />
                </el-form-item>
                <el-form-item label="最大回撤上限 %">
                  <div class="ai-research-gate-control">
                    <el-checkbox v-model="aiResearchForm.use_max_drawdown_limit" />
                    <el-input-number
                      v-model="aiResearchForm.max_drawdown_limit"
                      :disabled="!aiResearchForm.use_max_drawdown_limit"
                      :min="0"
                      :max="100"
                      :step="1"
                      class="w-full"
                      data-test="ai-research-max-drawdown"
                    />
                  </div>
                </el-form-item>
                <el-form-item label="最小总收益 %">
                  <div class="ai-research-gate-control">
                    <el-checkbox v-model="aiResearchForm.use_min_total_return" />
                    <el-input-number
                      v-model="aiResearchForm.min_total_return"
                      :disabled="!aiResearchForm.use_min_total_return"
                      :min="-100"
                      :max="1000"
                      :step="1"
                      class="w-full"
                    />
                  </div>
                </el-form-item>
                <el-form-item label="最小年化收益 %">
                  <div class="ai-research-gate-control">
                    <el-checkbox v-model="aiResearchForm.use_min_annual_return" />
                    <el-input-number
                      v-model="aiResearchForm.min_annual_return"
                      :disabled="!aiResearchForm.use_min_annual_return"
                      :min="-100"
                      :max="1000"
                      :step="1"
                      class="w-full"
                    />
                  </div>
                </el-form-item>
                <el-form-item label="最小胜率 %">
                  <div class="ai-research-gate-control">
                    <el-checkbox v-model="aiResearchForm.use_min_win_rate" />
                    <el-input-number
                      v-model="aiResearchForm.min_win_rate"
                      :disabled="!aiResearchForm.use_min_win_rate"
                      :min="0"
                      :max="100"
                      :step="1"
                      class="w-full"
                    />
                  </div>
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchInitialCash')">
                  <el-input-number
                    v-model="aiResearchForm.initial_cash"
                    :min="1"
                    :step="10000"
                    class="w-full"
                  />
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchCommission')">
                  <div class="ai-research-gate-control">
                    <el-checkbox
                      v-model="aiResearchForm.use_manual_commission"
                      data-test="ai-research-manual-commission"
                    />
                    <el-input-number
                      v-model="aiResearchForm.commission"
                      :disabled="!aiResearchForm.use_manual_commission"
                      :min="0"
                      :max="0.1"
                      :step="0.0001"
                      class="w-full"
                      data-test="ai-research-commission"
                    />
                  </div>
                </el-form-item>
                <el-form-item label="单轮回测超时(秒)">
                  <el-input-number
                    v-model="aiResearchForm.backtest_timeout_seconds"
                    :min="1"
                    :max="3600"
                    :step="60"
                    class="w-full"
                    data-test="ai-research-backtest-timeout"
                  />
                </el-form-item>
                <el-form-item label="回测轮询间隔(秒)">
                  <el-input-number
                    v-model="aiResearchForm.poll_interval_seconds"
                    :min="0.1"
                    :max="30"
                    :step="0.5"
                    class="w-full"
                    data-test="ai-research-poll-interval"
                  />
                </el-form-item>
                <el-form-item label="模拟工作区名称">
                  <el-input
                    v-model="aiResearchForm.paper_workspace_name"
                    clearable
                    placeholder="自动命名"
                    data-test="ai-research-paper-workspace-name"
                  />
                </el-form-item>
                <el-form-item label="模拟工作区 ID">
                  <el-input
                    v-model="aiResearchForm.trading_workspace_id"
                    clearable
                    placeholder="可选，复用已有模拟工作区"
                    data-test="ai-research-trading-workspace-id"
                  />
                </el-form-item>
                <el-form-item label="模拟网关配置 JSON">
                  <el-input
                    v-model="aiResearchForm.gateway_config_json"
                    type="textarea"
                    :rows="3"
                    placeholder='{"name":"paper_gateway","params":{}}'
                    data-test="ai-research-gateway-config"
                  />
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchStartDate')">
                  <el-input
                    v-model="aiResearchForm.start_date"
                    placeholder="2020-01-01"
                  />
                </el-form-item>
                <el-form-item :label="t('strategy.aiResearchEndDate')">
                  <el-input
                    v-model="aiResearchForm.end_date"
                    placeholder="2026-01-01"
                  />
                </el-form-item>
                <el-form-item label="样本外比例 %">
                  <div class="ai-research-gate-control">
                    <el-checkbox
                      v-model="aiResearchForm.out_of_sample_validation"
                      data-test="ai-research-oos-enabled"
                    />
                    <el-input-number
                      v-model="aiResearchForm.out_of_sample_ratio_pct"
                      :disabled="!aiResearchForm.out_of_sample_validation"
                      :min="5"
                      :max="50"
                      :step="5"
                      class="w-full"
                      data-test="ai-research-oos-ratio"
                    />
                  </div>
                </el-form-item>
                <el-form-item label="样本外最小 Sharpe">
                  <div class="ai-research-gate-control">
                    <el-checkbox
                      v-model="aiResearchForm.use_min_out_of_sample_sharpe"
                      :disabled="!aiResearchForm.out_of_sample_validation"
                    />
                    <el-input-number
                      v-model="aiResearchForm.min_out_of_sample_sharpe"
                      :disabled="
                        !aiResearchForm.out_of_sample_validation
                          || !aiResearchForm.use_min_out_of_sample_sharpe
                      "
                      :min="-5"
                      :max="10"
                      :step="0.1"
                      class="w-full"
                      data-test="ai-research-oos-sharpe"
                    />
                  </div>
                </el-form-item>
                <el-form-item label="样本外最少交易">
                  <div class="ai-research-gate-control">
                    <el-checkbox
                      v-model="aiResearchForm.use_min_out_of_sample_trades"
                      :disabled="!aiResearchForm.out_of_sample_validation"
                    />
                    <el-input-number
                      v-model="aiResearchForm.min_out_of_sample_trades"
                      :disabled="
                        !aiResearchForm.out_of_sample_validation
                          || !aiResearchForm.use_min_out_of_sample_trades
                      "
                      :min="0"
                      :max="9999"
                      class="w-full"
                      data-test="ai-research-oos-trades"
                    />
                  </div>
                </el-form-item>
              </div>

              <div class="ai-research-actions">
                <div class="ai-research-action-options">
                  <el-checkbox v-model="aiResearchForm.start_paper_trading">
                    {{ t('strategy.aiResearchPaper') }}
                  </el-checkbox>
                  <el-tag
                    v-if="aiResearchContinuationEnabled"
                    closable
                    type="info"
                    @close="clearAIResearchContinuation"
                  >
                    {{ aiResearchContinuationLabel }}
                  </el-tag>
                </div>
                <el-button
                  type="primary"
                  :loading="aiResearchRunning"
                  data-test="ai-research-run"
                  @click="runAIResearchLoop"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <MagicStick />
                  </el-icon>
                  {{ aiResearchRunning ? t('strategy.aiResearchRunning') : t('strategy.aiResearchRun') }}
                </el-button>
                <el-button
                  v-if="canCancelAIResearchTask"
                  data-test="ai-research-cancel"
                  :loading="aiResearchCancelling"
                  @click="cancelAIResearchTask"
                >
                  取消任务
                </el-button>
                <el-tag
                  v-if="aiResearchTaskId"
                  size="small"
                  type="info"
                >
                  任务 {{ aiResearchTaskStageLabel }}
                  {{ formatTaskProgress(aiResearchTaskProgress) }}
                  <template v-if="aiResearchTaskIteration">
                    第 {{ aiResearchTaskIteration }} 轮
                  </template>
                  <template v-if="aiResearchBacktestTaskId">
                    回测 {{ aiResearchBacktestTaskId }}
                  </template>
                </el-tag>
              </div>
              <div
                v-if="aiResearchTaskId"
                class="ai-research-task-progress"
                data-test="ai-research-task-progress"
              >
                <strong>任务进度</strong>
                <span>阶段 {{ aiResearchTaskStageLabel }}</span>
                <span>{{ formatTaskProgress(aiResearchTaskProgress) }}</span>
                <span v-if="aiResearchTaskIteration">第 {{ aiResearchTaskIteration }} 轮</span>
                <span v-if="aiResearchBacktestTaskId">回测 {{ aiResearchBacktestTaskId }}</span>
                <span v-if="aiResearchTaskMessage">{{ aiResearchTaskMessage }}</span>
                <span v-if="aiResearchTaskLatestIteration">
                  最近{{ taskLatestIterationLabel(aiResearchTaskLatestIteration) }}
                  Sharpe {{ formatMetric(taskLatestIterationMetric(aiResearchTaskLatestIteration, 'sharpe_ratio', 'sharpe')) }}
                  交易 {{ formatMetric(taskLatestIterationMetric(aiResearchTaskLatestIteration, 'total_trades', 'trades')) }}
                </span>
              </div>
              <div
                v-if="aiResearchTaskError"
                class="ai-research-task-error"
                data-test="ai-research-task-error"
              >
                <strong>任务异常</strong>
                <span>{{ aiResearchTaskError }}</span>
              </div>
            </el-form>
          </section>

          <section class="ai-research-panel ai-research-result">
            <div
              v-if="aiResearchResult"
              data-test="ai-research-result"
            >
              <div class="ai-research-summary">
                <div>
                  <span class="ai-research-kicker">{{ t('strategy.aiResearchResult') }}</span>
                  <h2 class="ai-research-title">
                    {{ aiResearchResult.achieved ? t('strategy.aiResearchAchieved') : t('strategy.aiResearchNotAchieved') }}
                  </h2>
                </div>
                <el-tag :type="aiResearchResult.achieved ? 'success' : 'warning'">
                  {{ aiResearchResult.status }}
                </el-tag>
              </div>

              <div class="ai-research-metrics">
                <div>
                  <span>{{ t('strategy.aiResearchBestSharpe') }}</span>
                  <strong>{{ formatMetric(aiBestSharpe) }}</strong>
                </div>
                <div>
                  <span>质量分</span>
                  <strong>{{ formatMetric(aiResearchResult.best_quality_score) }}</strong>
                </div>
                <div>
                  <span>{{ t('strategy.aiResearchBestIteration') }}</span>
                  <strong>{{ aiResearchResult.best_iteration ?? '-' }}</strong>
                </div>
                <div>
                  <span>{{ t('strategy.aiResearchIterations') }}</span>
                  <strong>{{ aiResearchResult.iterations.length }}</strong>
                </div>
                <div>
                  <span>{{ t('strategy.aiResearchPaperStatus') }}</span>
                  <strong>
                    {{ aiResearchPaperStatusText }}
                  </strong>
                </div>
              </div>

              <div class="ai-research-links">
                <el-button
                  v-if="canViewBestStrategyFromCurrentResult"
                  size="small"
                  :loading="aiResearchStrategyViewingRunId === aiResearchResult.run_id"
                  data-test="ai-research-view-best-strategy"
                  @click="viewBestStrategyFromCurrentResult"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <Link />
                  </el-icon>
                  查看最佳脚本
                </el-button>
                <el-button
                  size="small"
                  @click="openResearchWorkspace"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <Link />
                  </el-icon>
                  {{ t('strategy.aiResearchOpenResearch') }}
                </el-button>
                <el-button
                  v-if="canStartPaperFromCurrentResult"
                  size="small"
                  type="success"
                  :loading="aiResearchPaperStartingRunId === aiResearchResult.run_id"
                  data-test="ai-research-current-start-paper"
                  @click="startPaperFromCurrentResult"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <VideoPlay />
                  </el-icon>
                  {{
                    aiResearchCurrentPaperTargetMissing
                      ? '重启模拟'
                      : aiResearchCurrentPaperFailed ? '重试模拟' : '启动模拟'
                  }}
                </el-button>
                <el-button
                  v-if="canOpenPaperFromCurrentResult"
                  size="small"
                  type="success"
                  data-test="ai-research-current-open-paper"
                  @click="openPaperWorkspace"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <VideoPlay />
                  </el-icon>
                  {{ t('strategy.aiResearchOpenPaper') }}
                </el-button>
                <el-button
                  v-if="canReviewPaperFromCurrentResult"
                  size="small"
                  type="primary"
                  plain
                  :loading="aiResearchPaperReviewingRunId === aiResearchResult.run_id"
                  data-test="ai-research-current-review-paper"
                  @click="reviewPaperFromCurrentResult"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <MagicStick />
                  </el-icon>
                  复核模拟
                </el-button>
                <el-button
                  v-if="canContinueResearchFromCurrentRunRecord"
                  size="small"
                  type="warning"
                  plain
                  :loading="aiResearchRunning && aiResearchForm.continue_from_run_id === aiResearchResult.run_id"
                  data-test="ai-research-current-continue-run"
                  @click="continueResearchFromCurrentRunRecord"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <MagicStick />
                  </el-icon>
                  继续投研
                </el-button>
                <el-button
                  v-if="canContinueResearchFromCurrentPaperIssue && !aiResearchCurrentPaperReview"
                  size="small"
                  type="warning"
                  plain
                  :loading="aiResearchRunning && aiResearchForm.continue_from_run_id === aiResearchResult.run_id"
                  data-test="ai-research-current-continue-paper-issue"
                  @click="continueResearchFromCurrentPaperReview"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <MagicStick />
                  </el-icon>
                  继续改进
                </el-button>
              </div>

              <div
                v-if="aiResearchCurrentRuntimeEnvironment.length"
                class="ai-research-paper-env"
                data-test="ai-research-current-runtime-env"
              >
                <strong>回测环境</strong>
                <span
                  v-for="item in aiResearchCurrentRuntimeEnvironment"
                  :key="item.key"
                >
                  {{ item.label }} {{ item.value }}
                </span>
              </div>

              <div
                v-if="aiResearchCurrentPaperEnvironment.length"
                class="ai-research-paper-env"
                data-test="ai-research-current-paper-env"
              >
                <strong>模拟环境</strong>
                <span
                  v-for="item in aiResearchCurrentPaperEnvironment"
                  :key="item.key"
                >
                  {{ item.label }} {{ item.value }}
                </span>
              </div>

              <div
                v-if="aiResearchCurrentPaperReview"
                class="ai-research-paper-review ai-research-current-paper-review"
                data-test="ai-research-current-paper-review"
              >
                <div class="ai-research-paper-review-head">
                  <el-tag
                    size="small"
                    :type="aiResearchCurrentPaperReview.ready_for_live ? 'success' : 'warning'"
                  >
                    {{ paperReviewStatusLabel(aiResearchCurrentPaperReview.status) }}
                  </el-tag>
                  <span>
                    {{ paperReviewDispositionLabel(aiResearchCurrentPaperReview) }}
                  </span>
                </div>
                <div class="ai-research-paper-review-rules">
                  <span
                    v-for="rule in aiResearchCurrentPaperReview.evaluations"
                    :key="rule.key"
                  >
                    {{ rule.label }} {{ formatMetric(rule.actual) }} / {{ formatMetric(rule.threshold) }}
                  </span>
                  <span v-if="aiResearchCurrentPaperReview.live_readiness_expires_at">
                    候选有效期 {{ formatDateTime(aiResearchCurrentPaperReview.live_readiness_expires_at) }}
                  </span>
                </div>
                <div
                  v-if="liveReadinessChecklistForReview(aiResearchCurrentPaperReview).length"
                  class="ai-research-live-readiness"
                  data-test="ai-research-current-live-readiness"
                >
                  <strong>实盘交接清单</strong>
                  <span
                    v-for="item in liveReadinessChecklistForReview(aiResearchCurrentPaperReview)"
                    :key="item.key"
                  >
                    {{ item.label }} {{ liveReadinessStatusLabel(item.status) }}：{{ item.evidence }}
                  </span>
                </div>
                <div
                  v-if="aiResearchCurrentPaperReview.next_actions?.length"
                  class="ai-research-paper-review-actions"
                  data-test="ai-research-current-paper-review-actions"
                >
                  <span
                    v-for="action in aiResearchCurrentPaperReview.next_actions"
                    :key="action"
                  >
                    {{ action }}
                  </span>
                </div>
                <el-button
                  v-if="canContinueResearchFromCurrentPaperReview"
                  size="small"
                  type="warning"
                  plain
                  :loading="aiResearchRunning && aiResearchForm.continue_from_run_id === aiResearchResult.run_id"
                  class="ai-research-current-paper-review-action"
                  data-test="ai-research-current-continue-paper-review"
                  @click="continueResearchFromCurrentPaperReview"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <MagicStick />
                  </el-icon>
                  继续改进
                </el-button>
              </div>

              <div
                v-if="aiResearchPipelineSteps.length"
                class="ai-research-pipeline"
                data-test="ai-research-pipeline"
              >
                <strong>AI投研流水线</strong>
                <div class="ai-research-pipeline-steps">
                  <span
                    v-for="step in aiResearchPipelineSteps"
                    :key="step.key"
                    class="ai-research-pipeline-step"
                  >
                    <span>{{ step.label || aiResearchStageLabel(step.key) }}</span>
                    <el-tag
                      size="small"
                      :type="pipelineStepTagType(step.status)"
                    >
                      {{ pipelineStepStatusLabel(step.status) }}
                    </el-tag>
                    <small v-if="pipelineStepIterationText(step)">
                      {{ pipelineStepIterationText(step) }}
                    </small>
                    <small v-if="step.review_status">
                      复核 {{ paperReviewStatusLabel(step.review_status) }}
                    </small>
                    <small
                      v-if="step.error"
                      class="ai-research-warning-text"
                    >
                      {{ step.error }}
                    </small>
                  </span>
                </div>
              </div>

              <div
                v-if="aiResearchNextActions.length"
                class="ai-research-action-plan"
                data-test="ai-research-next-actions"
              >
                <strong>下一步动作</strong>
                <ul>
                  <li
                    v-for="action in aiResearchNextActions"
                    :key="action"
                  >
                    {{ action }}
                  </li>
                </ul>
              </div>

              <div
                v-if="aiResearchBestGateEvaluations.length"
                class="ai-research-gate-summary"
                data-test="ai-research-gate-summary"
              >
                <span
                  v-for="gate in aiResearchBestGateEvaluations"
                  :key="gate.key"
                  class="ai-research-gate-summary-item"
                >
                  <el-tag
                    size="small"
                    :type="gate.passed ? 'success' : 'warning'"
                  >
                    {{ gate.label }}
                  </el-tag>
                  <span>{{ formatMetric(gate.actual) }} / {{ formatMetric(gate.target) }}</span>
                </span>
              </div>

              <div
                v-if="aiResearchOutOfSampleValidation"
                class="ai-research-oos-summary"
                data-test="ai-research-oos-summary"
              >
                <div class="ai-research-oos-head">
                  <strong>样本外验证</strong>
                  <el-tag
                    size="small"
                    :type="outOfSampleTagType(aiResearchOutOfSampleValidation.status)"
                  >
                    {{ aiResearchOutOfSampleValidation.status || 'not_required' }}
                  </el-tag>
                </div>
                <div class="ai-research-oos-details">
                  <span v-if="formatOutOfSampleWindow(aiResearchOutOfSampleValidation.window)">
                    {{ formatOutOfSampleWindow(aiResearchOutOfSampleValidation.window) }}
                  </span>
                  <span
                    v-for="gate in aiResearchOutOfSampleValidation.gate_evaluations || []"
                    :key="gate.key"
                  >
                    {{ gate.label }} {{ formatMetric(gate.actual) }} / {{ formatMetric(gate.target) }}
                  </span>
                  <span
                    v-for="failure in aiResearchOutOfSampleValidation.failures || []"
                    :key="failure"
                    class="ai-research-warning-text"
                  >
                    {{ failure }}
                  </span>
                </div>
              </div>

              <div class="ai-research-iterations">
                <div
                  v-for="item in aiResearchResult.iterations"
                  :key="item.iteration"
                  class="ai-research-iteration"
                >
                  <div class="ai-research-iteration-head">
                    <strong>{{ t('strategy.aiResearchIteration') }} {{ item.iteration }}</strong>
                    <span class="ai-research-iteration-actions">
                      <el-button
                        size="small"
                        data-test="ai-research-view-iteration-strategy"
                        @click="viewResearchIterationStrategy(item)"
                      >
                        查看脚本
                      </el-button>
                      <el-tag
                        size="small"
                        :type="item.passed ? 'success' : 'info'"
                      >
                        {{ item.unit_status?.run_status || item.run_result.status }}
                      </el-tag>
                    </span>
                  </div>
                  <div class="ai-research-iteration-metrics">
                    <span>{{ t('strategy.aiResearchStrategy') }}: {{ item.strategy.name }}</span>
                    <span>{{ t('strategy.aiResearchSharpe') }}: {{ formatMetric(item.sharpe_ratio) }}</span>
                    <span>质量分: {{ formatMetric(item.quality_score) }}</span>
                    <span>{{ t('strategy.aiResearchTrades') }}: {{ item.total_trades }}</span>
                  </div>
                  <p
                    v-if="item.failure_reason"
                    class="ai-research-warning"
                  >
                    {{ item.failure_reason }}
                  </p>
                  <div
                    v-if="iterationOutOfSampleValidation(item)"
                    class="ai-research-oos-summary ai-research-oos-summary-compact"
                    data-test="ai-research-iteration-oos"
                  >
                    <div class="ai-research-oos-head">
                      <strong>样本外验证</strong>
                      <el-tag
                        size="small"
                        :type="outOfSampleTagType(iterationOutOfSampleValidation(item)?.status)"
                      >
                        {{ iterationOutOfSampleValidation(item)?.status || 'not_required' }}
                      </el-tag>
                    </div>
                    <div class="ai-research-oos-details">
                      <span v-if="formatOutOfSampleWindow(iterationOutOfSampleValidation(item)?.window)">
                        {{ formatOutOfSampleWindow(iterationOutOfSampleValidation(item)?.window) }}
                      </span>
                      <span
                        v-for="gate in iterationOutOfSampleValidation(item)?.gate_evaluations || []"
                        :key="gate.key"
                      >
                        {{ gate.label }} {{ formatMetric(gate.actual) }} / {{ formatMetric(gate.target) }}
                      </span>
                      <span
                        v-for="failure in iterationOutOfSampleValidation(item)?.failures || []"
                        :key="failure"
                        class="ai-research-warning-text"
                      >
                        {{ failure }}
                      </span>
                    </div>
                  </div>
                  <ul
                    v-if="item.improvement_notes.length"
                    class="ai-research-notes"
                  >
                    <li
                      v-for="note in item.improvement_notes"
                      :key="note"
                    >
                      {{ note }}
                    </li>
                  </ul>
                  <ul
                    v-if="researchIterationNextActions(item).length"
                    class="ai-research-next-actions"
                  >
                    <li
                      v-for="action in researchIterationNextActions(item)"
                      :key="action"
                    >
                      {{ action }}
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <el-empty
              v-else
              :description="t('strategy.aiResearchNoResult')"
            />

            <div
              class="ai-research-history"
              data-test="ai-research-history"
            >
              <div class="ai-research-summary ai-research-history-head">
                <div>
                  <span class="ai-research-kicker">{{ t('strategy.aiResearchResult') }}</span>
                  <h3 class="ai-research-history-title">
                    {{ t('strategy.aiResearchIterations') }}
                  </h3>
                </div>
                <el-tag
                  size="small"
                  type="info"
                >
                  {{ aiResearchRuns.length }}
                </el-tag>
              </div>

              <div
                v-if="aiResearchRunsLoading"
                class="ai-research-history-empty"
              >
                {{ t('common.loading') }}
              </div>
              <div
                v-else-if="aiResearchRuns.length"
                class="ai-research-history-list"
              >
                <div
                  v-for="record in aiResearchRuns"
                  :key="record.run_id"
                  class="ai-research-history-item"
                >
                  <button
                    type="button"
                    class="ai-research-history-select"
                    @click="useAIResearchRecord(record)"
                  >
                    <span class="ai-research-history-main">
                      <strong>{{ record.prompt }}</strong>
                      <el-tag
                        size="small"
                        :type="record.achieved ? 'success' : 'warning'"
                      >
                        {{ aiResearchRunStatusLabel(record.status) }}
                      </el-tag>
                    </span>
                    <span class="ai-research-history-meta">
                      <span>{{ record.symbol }}</span>
                      <span>{{ t('strategy.aiResearchBestSharpe') }} {{ formatMetric(record.best_sharpe) }}</span>
                      <span>质量分 {{ formatMetric(record.best_quality_score) }}</span>
                      <span v-if="pipelineStage(record)">
                        阶段 {{ pipelineStageLabel(record) }}
                      </span>
                      <span v-if="record.paper_workspace_name">
                        模拟 {{ record.paper_workspace_name }}
                      </span>
                      <span v-if="record.pipeline?.paper_trading_error">
                        模拟错误 {{ record.pipeline.paper_trading_error }}
                      </span>
                      <span v-if="recordOutOfSampleSummary(record)">
                        {{ recordOutOfSampleSummary(record) }}
                      </span>
                      <span>{{ t('strategy.aiResearchIterations') }} {{ record.iteration_count }}</span>
                      <span v-if="record.paper_review_status">
                        复核 {{ paperReviewStatusLabel(record.paper_review_status) }}
                      </span>
                      <span v-if="record.paper_reviewed_at">
                        复核时间 {{ formatDateTime(record.paper_reviewed_at) }}
                      </span>
                      <span v-if="record.live_readiness_expires_at">
                        候选有效期 {{ formatDateTime(record.live_readiness_expires_at) }}
                      </span>
                      <span>{{ formatDateTime(record.completed_at) }}</span>
                    </span>
                  </button>
                  <el-button
                    v-if="canStartPaperFromRecord(record)"
                    size="small"
                    type="success"
                    :loading="aiResearchPaperStartingRunId === record.run_id"
                    data-test="ai-research-history-start-paper"
                    @click="startPaperFromResearchRecord(record)"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <VideoPlay />
                    </el-icon>
                    {{ paperStartButtonLabel(record) }}
                  </el-button>
                  <el-button
                    v-else-if="canReviewPaperFromRecord(record)"
                    size="small"
                    type="primary"
                    plain
                    :loading="aiResearchPaperReviewingRunId === record.run_id"
                    data-test="ai-research-history-review-paper"
                    @click="reviewPaperFromResearchRecord(record)"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <MagicStick />
                    </el-icon>
                    复核模拟
                  </el-button>
                  <el-button
                    v-if="bestStrategyIdForRecord(record)"
                    size="small"
                    plain
                    :loading="aiResearchStrategyViewingRunId === record.run_id"
                    data-test="ai-research-history-view-strategy"
                    @click="viewStrategyFromResearchRecord(record)"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <Link />
                    </el-icon>
                    查看脚本
                  </el-button>
                  <el-button
                    v-if="canContinueResearchFromRunRecord(record)"
                    size="small"
                    type="warning"
                    plain
                    :loading="aiResearchRunning && aiResearchForm.continue_from_run_id === record.run_id"
                    data-test="ai-research-history-continue-run"
                    @click="continueResearchFromRecord(record)"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <MagicStick />
                    </el-icon>
                    继续投研
                  </el-button>
                  <el-button
                    v-if="canContinueResearchFromPaperReview(record)"
                    size="small"
                    type="warning"
                    plain
                    :loading="aiResearchRunning && aiResearchForm.continue_from_run_id === record.run_id"
                    data-test="ai-research-history-continue-paper-review"
                    @click="continueResearchFromPaperReview(record)"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <MagicStick />
                    </el-icon>
                    继续改进
                  </el-button>
                  <div
                    v-if="hasResearchRuntimeEnvironment(record)"
                    class="ai-research-paper-env"
                    data-test="ai-research-history-runtime-env"
                  >
                    <strong>回测环境</strong>
                    <span
                      v-for="item in researchRuntimeItems(record)"
                      :key="item.key"
                    >
                      {{ item.label }} {{ item.value }}
                    </span>
                  </div>
                  <div
                    v-if="hasPaperEnvironment(record.paper_handoff)"
                    class="ai-research-paper-env"
                    data-test="ai-research-history-paper-env"
                  >
                    <strong>模拟环境</strong>
                    <span
                      v-for="item in paperEnvironmentItems(record.paper_handoff)"
                      :key="item.key"
                    >
                      {{ item.label }} {{ item.value }}
                    </span>
                  </div>
                  <div
                    v-if="paperReviewForRecord(record)"
                    class="ai-research-paper-review"
                    data-test="ai-research-paper-review"
                  >
                    <div class="ai-research-paper-review-head">
                      <el-tag
                        size="small"
                        :type="paperReviewForRecord(record)?.ready_for_live ? 'success' : 'warning'"
                      >
                        {{ paperReviewStatusLabel(paperReviewForRecord(record)?.status) }}
                      </el-tag>
                      <span>
                        {{ paperReviewDispositionLabel(paperReviewForRecord(record)) }}
                      </span>
                    </div>
                    <div class="ai-research-paper-review-rules">
                      <span
                        v-for="rule in paperReviewForRecord(record)?.evaluations ?? []"
                        :key="rule.key"
                      >
                        {{ rule.label }} {{ formatMetric(rule.actual) }} / {{ formatMetric(rule.threshold) }}
                      </span>
                      <span v-if="paperReviewForRecord(record)?.live_readiness_expires_at">
                        候选有效期 {{ formatDateTime(paperReviewForRecord(record)?.live_readiness_expires_at) }}
                      </span>
                    </div>
                    <div
                      v-if="liveReadinessChecklistForReview(paperReviewForRecord(record)).length"
                      class="ai-research-live-readiness"
                      data-test="ai-research-live-readiness"
                    >
                      <strong>实盘交接清单</strong>
                      <span
                        v-for="item in liveReadinessChecklistForReview(paperReviewForRecord(record))"
                        :key="item.key"
                      >
                        {{ item.label }} {{ liveReadinessStatusLabel(item.status) }}：{{ item.evidence }}
                      </span>
                    </div>
                    <div
                      v-if="paperReviewForRecord(record)?.next_actions?.length"
                      class="ai-research-paper-review-actions"
                      data-test="ai-research-paper-review-actions"
                    >
                      <span
                        v-for="action in paperReviewForRecord(record)?.next_actions ?? []"
                        :key="action"
                      >
                        {{ action }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div
                v-else
                class="ai-research-history-empty"
              >
                {{ t('strategy.aiResearchNoResult') }}
              </div>
            </div>
          </section>
        </div>
      </el-tab-pane>

      <!-- ========== Gallery ========== -->
      <el-tab-pane
        :label="t('strategy.gallery')"
        name="gallery"
      >
        <!-- Search and filter bar -->
        <div class="flex flex-wrap gap-4 mb-6">
          <el-input
            v-model="searchKeyword"
            :placeholder="t('strategy.searchPlaceholder')"
            :aria-label="t('strategy.searchAriaLabel')"
            clearable
            class="w-64"
            prefix-icon="Search"
          />
          <el-radio-group
            v-model="categoryFilter"
            size="default"
            :aria-label="t('strategy.filterAriaLabel')"
          >
            <el-radio-button label="">
              {{ t('strategy.categoryAll') }}
            </el-radio-button>
            <el-radio-button label="trend">
              {{ t('strategy.categoryTrend') }}
            </el-radio-button>
            <el-radio-button label="mean_reversion">
              {{ t('strategy.categoryMeanReversion') }}
            </el-radio-button>
            <el-radio-button label="volatility">
              {{ t('strategy.categoryVolatility') }}
            </el-radio-button>
            <el-radio-button label="indicator">
              {{ t('strategy.categoryIndicator') }}
            </el-radio-button>
            <el-radio-button label="arbitrage">
              {{ t('strategy.categoryArbitrage') }}
            </el-radio-button>
            <el-radio-button label="custom">
              {{ t('strategy.categoryOther') }}
            </el-radio-button>
          </el-radio-group>
          <span class="text-gray-400 text-sm self-center ml-auto">
            {{ t('strategy.customCount', { count: filteredTemplates.length }) }}
          </span>
        </div>

        <!-- Strategy card grid -->
        <div
          v-if="filteredTemplates.length"
          class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"
        >
          <StrategyTemplateCard
            v-for="tpl in displayedTemplates"
            :key="tpl.id"
            :tpl="tpl"
            @detail="openTemplateDetail"
            @use="useTemplate"
            @backtest="goBacktest"
          />
        </div>
        <el-empty
          v-else
          :description="t('strategy.noMatch')"
        />
      </el-tab-pane>

      <!-- ========== My strategies ========== -->
      <el-tab-pane
        :label="t('strategy.myStrategies')"
        name="my"
      >
        <el-table
          v-loading="loading"
          :data="strategies"
          stripe
          :empty-text="t('strategy.customEmpty')"
        >
          <el-table-column
            prop="name"
            :label="t('strategy.strategyName')"
            width="200"
          />
          <el-table-column
            prop="description"
            :label="t('strategy.paramDescription')"
            show-overflow-tooltip
          />
          <el-table-column
            prop="category"
            :label="$t('common.action')"
            width="120"
          >
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="getCategoryType(row.category)"
              >
                {{ getCategoryLabel(row.category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="created_at"
            :label="t('strategy.createdAt')"
            width="180"
          />
          <el-table-column
            :label="$t('common.action')"
            width="220"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                type="primary"
                link
                size="small"
                @click="viewStrategy(row)"
              >
                {{ t('strategy.actionView') }}
              </el-button>
              <el-button
                type="warning"
                link
                size="small"
                @click="editStrategy(row)"
              >
                {{ t('strategy.actionEdit') }}
              </el-button>
              <el-button
                type="danger"
                link
                size="small"
                @click="deleteStrategy(row.id)"
              >
                {{ t('strategy.actionDelete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ========== 策略详情弹窗 (模板) ========== -->
    <StrategyDetailDialog
      v-model:visible="detailVisible"
      v-model:detail-tab="detailTab"
      :template="detailTemplate"
      :param-table-data="paramTableData"
      :readme-loading="readmeLoading"
      :readme-content="readmeContent"
      :strip-meta="stripStrategyMeta"
      @use="useTemplate"
      @backtest="goBacktest"
    />

    <!-- ========== 创建/编辑弹窗 ========== -->
    <StrategyEditDialog
      v-model:visible="dialogVisible"
      :is-edit="isEdit"
      :saving="saving"
      :form="form"
      @update:form="updateStrategyForm"
      @save="saveStrategy"
    />

    <!-- ========== My strategy detail dialog ========== -->
    <el-dialog
      v-model="viewDialogVisible"
      :title="t('strategy.detailLabel')"
      width="800px"
    >
      <div
        v-if="currentStrategy"
        class="space-y-4"
      >
        <div class="flex justify-between items-center">
          <h2 class="text-xl font-bold">
            {{ currentStrategy.name }}
          </h2>
          <el-tag :type="getCategoryType(currentStrategy.category)">
            {{ getCategoryLabel(currentStrategy.category) }}
          </el-tag>
        </div>
        <p class="text-gray-500">
          {{ currentStrategy.description }}
        </p>
        <el-divider />
        <MonacoEditor
          v-model="currentStrategy.code"
          language="python"
          :height="400"
          :read-only="true"
          theme="vs"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Link, MagicStick, Plus, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '@/stores/strategy'
import { strategyApi } from '@/api/strategy'
import { getCategoryType, getCategoryLabel, stripStrategyMeta } from '@/constants/strategy'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
import StrategyEditDialog from './strategy-components/StrategyEditDialog.vue'
import StrategyDetailDialog from './strategy-components/StrategyDetailDialog.vue'
import StrategyTemplateCard from './strategy-components/StrategyTemplateCard.vue'
import type { ParamSpec, Strategy, StrategyTemplate } from '@/types'
import type {
  AIStrategyLiveReadinessItem,
  AIStrategyOutOfSampleValidation,
  AIStrategyPaperMonitoringRule,
  AIStrategyPaperTradingStart,
  AIStrategyPaperTradingReview,
  AIStrategyPipelineStep,
  AIStrategyQualityGateEvaluation,
  AIStrategyResearchRunRequest,
  AIStrategyResearchRunRecord,
  AIStrategyResearchRunResponse,
  AIStrategyResearchIteration,
  AIStrategyResearchTaskResponse,
} from '@/api/strategy'
import type { Workspace, StrategyUnit, TradingSnapshot, UnitStatusResponse } from '@/types/workspace'

const { t } = useI18n()
const router = useRouter()
const strategyStore = useStrategyStore()

// ---- State ----
const activeTab = ref('aiResearch')
const searchKeyword = ref('')
const categoryFilter = ref('')

const dialogVisible = ref(false)
const viewDialogVisible = ref(false)
const detailVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const editingId = ref('')
const currentStrategy = ref<Strategy | null>(null)

const detailTemplate = ref<StrategyTemplate | null>(null)
const detailTab = ref('readme')
const readmeContent = ref('')
const readmeLoading = ref(false)
const aiResearchRunning = ref(false)
const aiResearchResult = ref<AIStrategyResearchRunResponse | null>(null)
const aiResearchRunsLoading = ref(false)
const aiResearchRuns = ref<AIStrategyResearchRunRecord[]>([])
const aiResearchTaskId = ref('')
const aiResearchTaskStatus = ref('')
const aiResearchTaskStage = ref('')
const aiResearchTaskProgress = ref(0)
const aiResearchTaskIteration = ref<number | null>(null)
const aiResearchBacktestTaskId = ref('')
const aiResearchCancelledBacktestTaskId = ref('')
const aiResearchTaskError = ref('')
const aiResearchTaskMessage = ref('')
const aiResearchTaskLatestIteration = ref<Record<string, unknown> | null>(null)
const aiResearchCancelling = ref(false)
const aiResearchCancelRequested = ref(false)
const aiResearchPaperStartingRunId = ref('')
const aiResearchPaperReviewingRunId = ref('')
const aiResearchStrategyViewingRunId = ref('')
const aiResearchPaperReviews = reactive<Record<string, AIStrategyPaperTradingReview>>({})

const AI_RESEARCH_STAGE_LABELS: Record<string, string> = {
  queued: '排队中',
  starting: '启动中',
  running: '运行中',
  initializing: '初始化',
  workspace_ready: '工作区已就绪',
  drafting: '生成策略脚本',
  draft_generation_failed: '脚本生成失败',
  repairing_code: '修复策略脚本',
  backtesting: '运行回测',
  backtest_failed: '回测失败',
  backtest_submission_failed: '回测提交失败',
  backtest_timeout: '回测超时',
  improving: '改进策略',
  validating: '样本外验证',
  evaluating: '评估策略',
  quality_achieved: '质量达标',
  paper_trading: '模拟交易',
  paper_trading_failed: '模拟启动失败',
  paper_review: '模拟复核',
  live_candidate: '实盘候选',
  research_iteration: '投研迭代',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  timeout: '超时',
}

const AI_RESEARCH_RUN_STATUS_LABELS: Record<string, string> = {
  achieved: '已达标',
  completed: '已完成',
  failed: '未达标',
  cancelled: '已取消',
  timeout: '超时',
  backtest_submission_failed: '回测提交失败',
}

const AI_RESEARCH_PAPER_REVIEW_STATUS_LABELS: Record<string, string> = {
  ready_for_live_candidate: '实盘候选',
  live_readiness_expired: '实盘候选已过期',
  monitoring: '继续观察',
  needs_research_review: '需要重新投研',
}

const AI_RESEARCH_LIVE_READINESS_STATUS_LABELS: Record<string, string> = {
  passed: '已通过',
  pending: '待确认',
  pending_manual_confirmation: '待人工确认',
  expired: '已过期',
  failed: '未通过',
}

const AI_RESEARCH_PIPELINE_STEP_STATUS_LABELS: Record<string, string> = {
  pending: '待执行',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const form = reactive({
  name: '',
  description: '',
  code: '',
  category: 'custom',
})

const aiResearchForm = reactive({
  prompt: '',
  symbol: '000001.SZ',
  symbol_name: '',
  timeframe: '1d',
  timeframe_n: 1,
  start_date: '',
  end_date: '',
  knowledge_base_id: '',
  thinking_mode: false,
  target_sharpe: 1.0,
  min_total_trades: 1,
  use_max_drawdown_limit: false,
  max_drawdown_limit: 20,
  use_min_total_return: false,
  min_total_return: 0,
  use_min_annual_return: false,
  min_annual_return: 0,
  use_min_win_rate: false,
  min_win_rate: 50,
  max_iterations: 3,
  out_of_sample_validation: true,
  out_of_sample_ratio_pct: 25,
  use_min_out_of_sample_sharpe: false,
  min_out_of_sample_sharpe: 0.6,
  use_min_out_of_sample_trades: false,
  min_out_of_sample_trades: 1,
  initial_cash: 100000,
  use_manual_commission: false,
  commission: 0.001,
  backtest_timeout_seconds: 600,
  poll_interval_seconds: 2,
  research_workspace_id: '',
  seed_strategy_id: '',
  continue_from_run_id: '',
  continuation_source: '',
  start_paper_trading: true,
  paper_workspace_name: '',
  trading_workspace_id: '',
  gateway_config_json: '',
})

// ---- Computed ----
const strategies = computed(() => strategyStore.strategies)
const templates = computed(() => strategyStore.templates)
const loading = computed(() => strategyStore.loading)

const filteredTemplates = computed(() => {
  let list = templates.value
  if (categoryFilter.value) {
    list = list.filter(t => t.category === categoryFilter.value)
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(t =>
      t.name.toLowerCase().includes(kw) ||
      t.description.toLowerCase().includes(kw) ||
      t.id.toLowerCase().includes(kw)
    )
  }
  return list
})

const displayedTemplates = computed(() => filteredTemplates.value)

const aiBestSharpe = computed(() => {
  const metrics = aiResearchResult.value?.best_metrics
  const raw = metrics?.sharpe_ratio ?? metrics?.sharpe ?? null
  if (typeof raw === 'number') return raw
  if (typeof raw === 'string' && raw.trim()) return Number(raw)
  const bestIteration = aiResearchResult.value?.iterations.find(
    item => item.iteration === aiResearchResult.value?.best_iteration
  )
  return bestIteration?.sharpe_ratio ?? null
})

const aiResearchNextActions = computed(() => aiResearchResult.value?.next_actions ?? [])
const aiResearchPipelineSteps = computed<AIStrategyPipelineStep[]>(() => {
  const pipeline = aiResearchResult.value?.pipeline
  if (!pipeline) return []
  if (pipeline.steps?.length) return pipeline.steps
  if (!pipeline.current_stage) return []
  return [
    {
      key: pipeline.current_stage,
      label: aiResearchStageLabel(pipeline.current_stage),
      status: pipeline.ready_for_live ? 'completed' : 'running',
      error: pipeline.paper_trading_error,
    },
  ]
})
const aiResearchCurrentPaperFailed = computed(() => {
  const pipeline = aiResearchResult.value?.pipeline
  return Boolean(
    pipeline?.current_stage === 'paper_trading_failed'
    || pipeline?.paper_trading_error
  )
})
const aiResearchCurrentPaperTargetMissing = computed(() => {
  const record = aiResearchResult.value?.run_record
  return Boolean(record && isPaperTradingTargetMissing(record))
})
const aiResearchPaperStatusText = computed(() => {
  if (aiResearchCurrentPaperFailed.value) return '模拟启动失败'
  if (aiResearchCurrentPaperTargetMissing.value) return '模拟目标丢失'
  return aiResearchResult.value?.paper_trading?.started
    || aiResearchResult.value?.run_record?.paper_trading_started
    ? t('strategy.aiResearchPaperStarted')
    : t('strategy.aiResearchPaperNotStarted')
})
const aiResearchTaskStageLabel = computed(() =>
  aiResearchStageLabel(aiResearchTaskStage.value || aiResearchTaskStatus.value)
)
const aiResearchContinuationEnabled = computed(() =>
  Boolean(aiResearchForm.seed_strategy_id || aiResearchForm.continue_from_run_id)
)
const aiResearchContinuationLabel = computed(() => {
  if (aiResearchForm.continuation_source === 'paper_review') return '从模拟复核反馈继续'
  if (aiResearchForm.continuation_source === 'paper_trading_failed') return '从模拟启动失败继续'
  if (aiResearchForm.continuation_source === 'research_cancelled') return '从已取消任务继续'
  if (aiResearchForm.continuation_source === 'research_failure') return '从未达标结果继续'
  return '从历史最佳策略继续'
})
const canCancelAIResearchTask = computed(() =>
  aiResearchRunning.value
  && Boolean(aiResearchTaskId.value)
  && typeof (strategyApi as { cancelAIResearchTask?: unknown }).cancelAIResearchTask === 'function'
)
const canViewBestStrategyFromCurrentResult = computed(() =>
  Boolean(
    aiResearchResult.value?.best_strategy
    || (
      aiResearchResult.value?.run_record
      && bestStrategyIdForRecord(aiResearchResult.value.run_record)
    )
  )
)
const canStartPaperFromCurrentResult = computed(() => {
  const record = aiResearchResult.value?.run_record
  return Boolean(record && canStartPaperFromRecord(record))
})
const canOpenPaperFromCurrentResult = computed(() =>
  Boolean(
    !(
      aiResearchResult.value?.run_record
      && isPaperTradingTargetMissing(aiResearchResult.value.run_record)
    )
    && (
      aiResearchResult.value?.paper_trading?.started
      || (
        aiResearchResult.value?.run_record?.paper_trading_started
        && aiResearchResult.value?.run_record?.paper_workspace_id
      )
    )
  )
)
const canReviewPaperFromCurrentResult = computed(() => {
  const record = aiResearchResult.value?.run_record
  return Boolean(record && canReviewPaperFromRecord(record))
})
const canContinueResearchFromCurrentPaperReview = computed(() => {
  const record = aiResearchResult.value?.run_record
  return Boolean(record && canContinueResearchFromPaperReview(record))
})
const canContinueResearchFromCurrentPaperIssue = computed(() => {
  const record = aiResearchResult.value?.run_record
  return Boolean(record && canContinueResearchFromPaperIssue(record))
})
const canContinueResearchFromCurrentRunRecord = computed(() => {
  const record = aiResearchResult.value?.run_record
  return Boolean(record && canContinueResearchFromRunRecord(record))
})
const aiResearchCurrentPaperReview = computed(() => {
  const result = aiResearchResult.value
  const record = result?.run_record
  if (!result || !record) return null
  return paperReviewForRecord(record)
})
const aiResearchCurrentPaperEnvironment = computed(() => {
  const result = aiResearchResult.value
  if (!result) return []
  return paperEnvironmentItems(result.paper_trading?.handoff ?? result.run_record?.paper_handoff)
})
const aiResearchCurrentRuntimeEnvironment = computed(() => {
  const result = aiResearchResult.value
  if (!result) return []
  return researchRuntimeItems(result.run_record, result.paper_trading?.handoff)
})
const aiResearchBestGateEvaluations = computed(
  () => aiResearchResult.value?.best_quality_gate_evaluations ?? []
)
const aiResearchOutOfSampleValidation = computed(() => {
  const result = aiResearchResult.value
  if (!result) return null
  const handoffValidation = outOfSampleValidationFromHandoff(result.paper_trading?.handoff)
  if (handoffValidation) return handoffValidation
  const bestIteration = result.iterations.find(item => item.iteration === result.best_iteration)
    ?? result.iterations.find(item => item.passed)
    ?? result.iterations[result.iterations.length - 1]
  return bestIteration ? iterationOutOfSampleValidation(bestIteration) : null
})

const paramTableData = computed(() => {
  if (!detailTemplate.value) return []
  return Object.entries(detailTemplate.value.params).map(([name, spec]: [string, ParamSpec]) => ({
    name,
    default: spec.default ?? '-',
    type: spec.type ?? '-',
    description: spec.description ?? name,
  }))
})

// ---- Methods ----
async function openTemplateDetail(t: StrategyTemplate) {
  detailTemplate.value = t
  detailTab.value = 'readme'
  detailVisible.value = true
  readmeContent.value = ''
  readmeLoading.value = true
  try {
    const res = await strategyApi.getTemplateReadme(t.id)
    readmeContent.value = res.content ?? ''
  } catch {
    readmeContent.value = ''
  } finally {
    readmeLoading.value = false
  }
}

function goBacktest(t: StrategyTemplate) {
  detailVisible.value = false
  router.push({ path: '/backtest/legacy', query: { strategy: t.id } })
}

function formatMetric(value: unknown, digits = 2) {
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number)) return '-'
  return number.toFixed(digits)
}

function formatTaskProgress(value: unknown) {
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number) || number <= 0) return ''
  return `${Math.round(number)}%`
}

function taskLatestIterationLabel(iteration: Record<string, unknown>) {
  const number = taskLatestIterationMetric(iteration, 'iteration')
  return number === null ? '一轮' : `第 ${formatMetric(number, 0)} 轮`
}

function taskLatestIterationMetric(
  iteration: Record<string, unknown>,
  ...keys: string[]
) {
  for (const key of keys) {
    const value = optionalNumber(iteration[key])
    if (value !== null) return value
  }
  const metrics = iteration.metrics
  if (isRecord(metrics)) {
    for (const key of keys) {
      const value = optionalNumber(metrics[key])
      if (value !== null) return value
    }
  }
  return null
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function optionalNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const number = Number(value)
    return Number.isFinite(number) ? number : null
  }
  return null
}

function optionalBoolean(value: unknown, fallback = false) {
  if (typeof value === 'boolean') return value
  return fallback
}

function outOfSampleRatioPct(value: unknown) {
  const ratio = optionalNumber(value)
  if (ratio === null) return 25
  return ratio <= 1 ? Math.round(ratio * 100) : ratio
}

function outOfSampleRatioValue() {
  const ratio = Number(aiResearchForm.out_of_sample_ratio_pct || 25) / 100
  return Number(ratio.toFixed(4))
}

function validationWindowFromUnknown(value: unknown): Record<string, string> | null {
  if (!isRecord(value)) return null
  const entries = Object.entries(value)
    .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
  return entries.length ? Object.fromEntries(entries) : null
}

function outOfSampleValidationFromHandoff(
  handoff: Record<string, unknown> | null | undefined
): AIStrategyOutOfSampleValidation | null {
  if (!isRecord(handoff)) return null
  const payload = handoff.out_of_sample_validation
  if (!isRecord(payload)) return null
  return {
    status: typeof payload.status === 'string' ? payload.status : null,
    window: validationWindowFromUnknown(payload.window),
    metrics: isRecord(payload.metrics) ? payload.metrics : {},
    gate_evaluations: Array.isArray(payload.gate_evaluations)
      ? payload.gate_evaluations as AIStrategyQualityGateEvaluation[]
      : [],
    failures: Array.isArray(payload.failures)
      ? payload.failures.filter((item): item is string => typeof item === 'string')
      : [],
    failure_reason: typeof payload.failure_reason === 'string' ? payload.failure_reason : null,
  }
}

type PaperEnvironmentItem = {
  key: string
  label: string
  value: string
}

function hasResearchRuntimeEnvironment(record: AIStrategyResearchRunRecord) {
  return researchRuntimeItems(record).length > 0
}

function researchRuntimeItems(
  record: AIStrategyResearchRunRecord | null | undefined,
  handoff?: Record<string, unknown> | null
): PaperEnvironmentItem[] {
  const environment = runtimeEnvironmentPayload(record, handoff)
  const items = environmentItemsFromPayload(environment)
  const asset = firstRuntimeAssetSpec(record, handoff)
  if (!asset) return items

  const existing = new Set(items.map(item => item.key))
  if (!existing.has('asset_symbol')) {
    items.unshift({ key: 'asset_symbol', label: '资产', value: asset.symbol })
  }
  const appendSpecNumber = (key: string, label: string, digits = 2) => {
    if (existing.has(key)) return
    const value = asset.spec[key]
    if (value === undefined || value === null || value === '') return
    items.push({ key, label, value: formatMetric(value, digits) })
    existing.add(key)
  }
  const appendSpecText = (key: string, label: string) => {
    if (existing.has(key)) return
    const value = asset.spec[key]
    if (value === undefined || value === null || value === '') return
    items.push({ key, label, value: String(value) })
    existing.add(key)
  }
  appendSpecNumber('multiplier', '合约乘数', 2)
  appendSpecNumber('margin', '保证金', 4)
  appendSpecNumber('margin_rate', '保证金率', 4)
  appendSpecNumber('leverage', '杠杆', 2)
  appendSpecNumber('max_leverage', '最大杠杆', 2)
  appendSpecNumber('commission', '手续费', 6)
  appendSpecNumber('commission_rate', '手续费率', 6)
  if (!items.some(item => item.label === '资产来源')) appendSpecText('asset_spec_source', '资产来源')
  if (!items.some(item => item.label === '资产来源')) appendSpecText('source', '资产来源')
  if (!items.some(item => item.label === '费用来源')) appendSpecText('fee_source', '费用来源')
  return items.slice(0, 10)
}

function hasPaperEnvironment(handoff: Record<string, unknown> | null | undefined) {
  return paperEnvironmentItems(handoff).length > 0
}

function paperEnvironmentItems(
  handoff: Record<string, unknown> | null | undefined
): PaperEnvironmentItem[] {
  if (!isRecord(handoff) || !isRecord(handoff.backtest_environment)) return []
  return environmentItemsFromPayload(handoff.backtest_environment)
}

function environmentItemsFromPayload(environment: Record<string, unknown>): PaperEnvironmentItem[] {
  const items: PaperEnvironmentItem[] = []
  const appendNumber = (key: string, label: string, digits = 2) => {
    const value = environment[key]
    if (value === undefined || value === null || value === '') return
    items.push({ key, label, value: formatMetric(value, digits) })
  }
  const appendText = (key: string, label: string) => {
    const value = environment[key]
    if (value === undefined || value === null || value === '') return
    items.push({ key, label, value: String(value) })
  }
  const startDate = environment.start_date
  const endDate = environment.end_date
  if (startDate || endDate) {
    items.push({
      key: 'date_range',
      label: '区间',
      value: `${startDate || '-'} 至 ${endDate || '-'}`,
    })
  }
  appendNumber('initial_cash', '初始资金', 2)
  appendNumber('commission', '手续费', 6)
  appendNumber('multiplier', '合约乘数', 2)
  appendNumber('margin', '保证金', 4)
  appendNumber('annual_days', '年化天数', 0)
  appendText('calc_method', '收益')
  appendText('weight_mode', '权重')
  appendText('asset_spec_source', '资产来源')
  return items
}

function runtimeEnvironmentPayload(
  record: AIStrategyResearchRunRecord | null | undefined,
  handoff?: Record<string, unknown> | null
): Record<string, unknown> {
  if (isRecord(record?.backtest_environment)) return record.backtest_environment
  if (isRecord(handoff?.backtest_environment)) return handoff.backtest_environment
  if (isRecord(record?.paper_handoff) && isRecord(record.paper_handoff.backtest_environment)) {
    return record.paper_handoff.backtest_environment
  }
  return {}
}

function firstRuntimeAssetSpec(
  record: AIStrategyResearchRunRecord | null | undefined,
  handoff?: Record<string, unknown> | null
): { symbol: string; spec: Record<string, unknown> } | null {
  const sources = [
    record?.asset_specs,
    handoff?.asset_specs,
    isRecord(record?.paper_handoff) ? record.paper_handoff.asset_specs : null,
  ]
  for (const source of sources) {
    if (!isRecord(source)) continue
    for (const [symbol, spec] of Object.entries(source)) {
      if (!isRecord(spec)) continue
      return { symbol, spec }
    }
  }
  return null
}

function iterationOutOfSampleValidation(
  item: AIStrategyResearchRunResponse['iterations'][number]
): AIStrategyOutOfSampleValidation | null {
  const hasWindow = Boolean(item.validation_window)
  const hasMetrics = Boolean(Object.keys(item.validation_metrics || {}).length)
  const hasGates = Boolean((item.validation_gate_evaluations || []).length)
  const hasFailures = Boolean((item.validation_failures || []).length)
  if (!item.validation_status && !hasWindow && !hasMetrics && !hasGates && !hasFailures) {
    return null
  }
  return {
    status: item.validation_status ?? null,
    window: item.validation_window ?? null,
    metrics: item.validation_metrics ?? {},
    gate_evaluations: item.validation_gate_evaluations ?? [],
    failures: item.validation_failures ?? [],
    failure_reason: item.validation_failure_reason ?? null,
  }
}

function formatOutOfSampleWindow(window: Record<string, string> | null | undefined) {
  if (!window) return ''
  const trainStart = window.train_start
  const trainEnd = window.train_end
  const validationStart = window.validation_start
  const validationEnd = window.validation_end
  if (!trainStart || !trainEnd || !validationStart || !validationEnd) return ''
  return `训练 ${trainStart} - ${trainEnd}；样本外 ${validationStart} - ${validationEnd}`
}

function outOfSampleTagType(status: string | null | undefined) {
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'skipped') return 'info'
  return 'warning'
}

function recordOutOfSampleSummary(record: AIStrategyResearchRunRecord) {
  const handoffValidation = outOfSampleValidationFromHandoff(record.paper_handoff)
  if (handoffValidation?.status) return `样本外 ${handoffValidation.status}`
  const gates = record.quality_gates || {}
  if (optionalBoolean(gates.out_of_sample_validation, false)) {
    return `样本外 ${formatMetric(outOfSampleRatioPct(gates.out_of_sample_ratio), 0)}%`
  }
  return ''
}

function strategyIdFromIterationPayload(payload: Record<string, unknown>) {
  const strategySnapshot = isRecord(payload.strategy_snapshot) ? payload.strategy_snapshot : {}
  return stringFromUnknown(strategySnapshot.id ?? payload.strategy_id, '').trim()
}

function iterationPayloadHasStrategy(payload: Record<string, unknown>) {
  const strategySnapshot = isRecord(payload.strategy_snapshot) ? payload.strategy_snapshot : {}
  return Boolean(
    strategyIdFromIterationPayload(payload)
    || stringFromUnknown(strategySnapshot.code, '')
    || stringFromUnknown(payload.strategy_code, '')
    || stringFromUnknown(payload.code, '')
  )
}

function iterationPayloadRank(payload: Record<string, unknown>) {
  const metrics = isRecord(payload.metrics) ? payload.metrics : {}
  return [
    optionalBoolean(payload.passed, false) ? 1 : 0,
    optionalNumber(payload.quality_score) ?? 0,
    optionalNumber(payload.sharpe_ratio)
      ?? optionalNumber(metrics.sharpe_ratio)
      ?? optionalNumber(metrics.sharpe)
      ?? optionalNumber(metrics.sharpeRatio)
      ?? 0,
    optionalNumber(payload.total_trades)
      ?? optionalNumber(metrics.total_trades)
      ?? optionalNumber(metrics.totalTrades)
      ?? optionalNumber(metrics.trades)
      ?? 0,
    -(optionalNumber(payload.iteration) ?? 0),
  ]
}

function compareIterationPayloads(
  candidate: Record<string, unknown>,
  current: Record<string, unknown>
) {
  const candidateRank = iterationPayloadRank(candidate)
  const currentRank = iterationPayloadRank(current)
  for (let index = 0; index < candidateRank.length; index += 1) {
    const delta = candidateRank[index] - currentRank[index]
    if (delta !== 0) return delta
  }
  return 0
}

function bestIterationPayloadForRecord(record: AIStrategyResearchRunRecord) {
  const iterations = (record.iterations || []).filter(isRecord)
  if (!iterations.length) return null
  const bestIteration = optionalNumber(record.best_iteration)
  if (bestIteration !== null) {
    const matched = iterations.find(
      payload => optionalNumber(payload.iteration) === bestIteration
    )
    if (matched) return matched
  }
  const candidates = iterations.filter(iterationPayloadHasStrategy)
  const pool = candidates.length ? candidates : iterations
  return pool.reduce(
    (best, payload) => (compareIterationPayloads(payload, best) > 0 ? payload : best),
    pool[0]
  )
}

function bestStrategyIdForRecord(record: AIStrategyResearchRunRecord) {
  const direct = stringFromUnknown(record.best_strategy_id, '').trim()
  if (direct) return direct
  const payload = bestIterationPayloadForRecord(record)
  return payload ? strategyIdFromIterationPayload(payload) : ''
}

function bestStrategyFromRunRecord(record: AIStrategyResearchRunRecord): Strategy | null {
  const payload = bestIterationPayloadForRecord(record)
  if (!payload) return null
  const fallbackIteration = Math.max(
    Math.trunc(
      optionalNumber(payload.iteration)
      ?? optionalNumber(record.best_iteration)
      ?? record.iteration_count
      ?? 1
    ),
    1
  )
  return strategyFromIterationRecord(record, payload, fallbackIteration)
}

async function loadAIResearchRuns() {
  aiResearchRunsLoading.value = true
  try {
    const response = await strategyApi.listAIResearchRuns(undefined, 10)
    aiResearchRuns.value = response.items
  } finally {
    aiResearchRunsLoading.value = false
  }
}

function upsertAIResearchRunRecord(record: AIStrategyResearchRunRecord) {
  aiResearchRuns.value = [
    record,
    ...aiResearchRuns.value.filter(item => item.run_id !== record.run_id),
  ].slice(0, 10)
}

async function refreshAIResearchRunRecord(
  runId: string,
  researchWorkspaceId?: string | null
) {
  const response = await strategyApi.listAIResearchRuns(researchWorkspaceId || undefined, 20)
  const record = response.items.find(item => item.run_id === runId)
  if (!record) return null
  upsertAIResearchRunRecord(record)
  applyResearchRunRecordToCurrentResult(record)
  return record
}

function useAIResearchRecord(record: AIStrategyResearchRunRecord) {
  const gates = record.quality_gates || {}
  aiResearchForm.prompt = record.prompt
  aiResearchForm.symbol = record.symbol
  aiResearchForm.symbol_name = record.symbol_name || ''
  aiResearchForm.timeframe = record.timeframe || '1d'
  aiResearchForm.timeframe_n = record.timeframe_n || 1
  aiResearchForm.start_date = record.start_date || ''
  aiResearchForm.end_date = record.end_date || ''
  if (typeof record.initial_cash === 'number') {
    aiResearchForm.initial_cash = record.initial_cash
  }
  if (typeof record.commission === 'number') {
    aiResearchForm.commission = record.commission
    aiResearchForm.use_manual_commission = researchRecordUsesManualCommission(record)
  } else {
    aiResearchForm.use_manual_commission = false
  }
  aiResearchForm.knowledge_base_id = record.knowledge_base_id || ''
  aiResearchForm.thinking_mode = Boolean(record.thinking_mode)
  aiResearchForm.paper_workspace_name = record.paper_workspace_name || ''
  aiResearchForm.target_sharpe = record.target_sharpe
  aiResearchForm.min_total_trades = record.min_total_trades
  aiResearchForm.use_max_drawdown_limit = typeof gates.max_drawdown_limit === 'number'
  aiResearchForm.max_drawdown_limit = Number(gates.max_drawdown_limit ?? 20)
  aiResearchForm.use_min_total_return = typeof gates.min_total_return === 'number'
  aiResearchForm.min_total_return = Number(gates.min_total_return ?? 0)
  aiResearchForm.use_min_annual_return = typeof gates.min_annual_return === 'number'
  aiResearchForm.min_annual_return = Number(gates.min_annual_return ?? 0)
  aiResearchForm.use_min_win_rate = typeof gates.min_win_rate === 'number'
  aiResearchForm.min_win_rate = Number(gates.min_win_rate ?? 50)
  aiResearchForm.max_iterations = record.max_iterations || 3
  if (typeof record.backtest_timeout_seconds === 'number') {
    aiResearchForm.backtest_timeout_seconds = record.backtest_timeout_seconds
  }
  if (typeof record.poll_interval_seconds === 'number') {
    aiResearchForm.poll_interval_seconds = record.poll_interval_seconds
  }
  aiResearchForm.out_of_sample_validation = optionalBoolean(gates.out_of_sample_validation, true)
  aiResearchForm.out_of_sample_ratio_pct = outOfSampleRatioPct(gates.out_of_sample_ratio)
  aiResearchForm.use_min_out_of_sample_sharpe =
    optionalNumber(gates.min_out_of_sample_sharpe) !== null
  aiResearchForm.min_out_of_sample_sharpe = Number(gates.min_out_of_sample_sharpe ?? 0.6)
  aiResearchForm.use_min_out_of_sample_trades =
    optionalNumber(gates.min_out_of_sample_trades) !== null
  aiResearchForm.min_out_of_sample_trades = Number(gates.min_out_of_sample_trades ?? 1)
  aiResearchForm.research_workspace_id = record.research_workspace_id || ''
  const bestStrategyId = bestStrategyIdForRecord(record)
  aiResearchForm.seed_strategy_id = bestStrategyId
  aiResearchForm.continue_from_run_id = bestStrategyId ? record.run_id : ''
  aiResearchForm.continuation_source = continuationSourceForRecord(record)
}

function researchRecordUsesManualCommission(record: AIStrategyResearchRunRecord) {
  const environment = record.backtest_environment
  if (!isRecord(environment)) return false
  return String(environment.commission_source || '').trim() === 'user_override'
}

function enabledQualityGate(enabled: boolean, value: number) {
  return enabled ? value : null
}

function researchIterationNextActions(item: AIStrategyResearchRunResponse['iterations'][number]) {
  const nextActions = item.next_actions ?? []
  const improvementPlan = item.improvement_plan ?? item.diagnostics?.improvement_plan ?? []
  return [...new Set([...nextActions, ...improvementPlan])]
}

function canStartPaperFromRecord(record: AIStrategyResearchRunRecord) {
  return Boolean(
    record.achieved
    && bestStrategyIdForRecord(record)
    && (!record.paper_trading_started || isPaperTradingTargetMissing(record))
  )
}

function canReviewPaperFromRecord(record: AIStrategyResearchRunRecord) {
  return Boolean(
    record.paper_trading_started
    && record.paper_workspace_id
    && record.paper_unit_id
    && !isPaperTradingTargetMissing(record)
  )
}

function isPaperTradingTargetMissing(record: AIStrategyResearchRunRecord) {
  const status = String(record.paper_review_status || '').trim()
  return Boolean(
    ['paper_workspace_missing', 'paper_unit_missing'].includes(status)
    || (
      record.paper_trading_started
      && (!record.paper_workspace_id || !record.paper_unit_id)
    )
  )
}

function paperStartButtonLabel(record: AIStrategyResearchRunRecord) {
  if (isPaperTradingTargetMissing(record)) return '重启模拟'
  if (isPaperTradingStartFailure(record)) return '重试模拟'
  return '启动模拟'
}

function canContinueResearchFromPaperReview(record: AIStrategyResearchRunRecord) {
  return canContinueResearchFromPaperIssue(record)
}

function canContinueResearchFromPaperIssue(record: AIStrategyResearchRunRecord) {
  const source = continuationSourceForRecord(record)
  return Boolean(
    bestStrategyIdForRecord(record) &&
    (source === 'paper_review' || source === 'paper_trading_failed')
  )
}

function canContinueResearchFromRunRecord(record: AIStrategyResearchRunRecord) {
  return Boolean(
    bestStrategyIdForRecord(record)
    && !record.achieved
    && (
      record.iteration_count > 0
      || record.status === 'backtest_submission_failed'
      || record.status === 'cancelled'
      || record.pipeline?.current_stage === 'backtest_failed'
      || record.pipeline?.current_stage === 'cancelled'
    )
  )
}

function continuationSourceForRecord(record: AIStrategyResearchRunRecord) {
  if (
    ['needs_research_review', 'live_readiness_expired'].includes(
      String(record.paper_review_status || '')
    )
    && !record.paper_review_ready_for_live
  ) {
    return 'paper_review'
  }
  if (isPaperTradingStartFailure(record)) return 'paper_trading_failed'
  if (
    canContinueResearchFromRunRecord(record)
    && (record.status === 'cancelled' || record.pipeline?.current_stage === 'cancelled')
  ) {
    return 'research_cancelled'
  }
  if (canContinueResearchFromRunRecord(record)) return 'research_failure'
  return ''
}

function isPaperTradingStartFailure(record: AIStrategyResearchRunRecord) {
  return Boolean(
    record.pipeline?.current_stage === 'paper_trading_failed'
    || record.pipeline?.paper_trading_error
  )
}

function pipelineStage(record: AIStrategyResearchRunRecord) {
  if (record.paper_review_ready_for_live) return 'live_candidate'
  if (record.paper_review_status) return 'paper_review'
  if (record.paper_trading_started) return 'paper_trading'
  if (record.pipeline?.current_stage) return record.pipeline.current_stage
  if (record.achieved) return 'quality_achieved'
  if (record.status === 'timeout') return 'backtest_timeout'
  if (record.status === 'cancelled') return 'cancelled'
  return record.iteration_count > 0 ? 'research_iteration' : ''
}

function pipelineStageLabel(record: AIStrategyResearchRunRecord) {
  return aiResearchStageLabel(pipelineStage(record))
}

function aiResearchRunStatusLabel(status?: string | null) {
  const normalized = String(status || '').trim()
  if (!normalized) return ''
  return AI_RESEARCH_RUN_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
}

function paperReviewStatusLabel(status?: string | null) {
  const normalized = String(status || '').trim()
  if (!normalized) return ''
  return AI_RESEARCH_PAPER_REVIEW_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
}

function paperReviewDispositionLabel(review: AIStrategyPaperTradingReview | null | undefined) {
  const status = String(review?.status || '').trim()
  if (review?.ready_for_live) return '实盘候选'
  if (status === 'live_readiness_expired') return '重新复核'
  if (status === 'needs_research_review') return '需要重新投研'
  if (status === 'monitoring') return '继续观察'
  return '待处理'
}

function liveReadinessStatusLabel(status?: string | null) {
  const normalized = String(status || '').trim()
  if (!normalized) return ''
  return AI_RESEARCH_LIVE_READINESS_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
}

function pipelineStepStatusLabel(status?: string | null) {
  const normalized = String(status || '').trim()
  if (!normalized) return ''
  return AI_RESEARCH_PIPELINE_STEP_STATUS_LABELS[normalized] ?? aiResearchStageLabel(normalized)
}

function pipelineStepTagType(status?: string | null) {
  const normalized = String(status || '').trim()
  if (normalized === 'completed') return 'success'
  if (normalized === 'failed') return 'danger'
  if (normalized === 'running') return 'warning'
  return 'info'
}

function pipelineStepIterationText(step: AIStrategyPipelineStep) {
  const count = typeof step.iteration_count === 'number' ? step.iteration_count : null
  const max = typeof step.max_iterations === 'number' ? step.max_iterations : null
  if (count === null && max === null) return ''
  if (count !== null && max !== null) return `${count}/${max} 轮`
  if (count !== null) return `${count} 轮`
  return `最多 ${max} 轮`
}

function aiResearchStageLabel(stage?: string | null) {
  const normalized = String(stage || '').trim()
  if (!normalized) return ''
  return AI_RESEARCH_STAGE_LABELS[normalized] ?? normalized.replace(/_/g, ' ')
}

function liveReadinessChecklistForReview(
  review: AIStrategyPaperTradingReview | null | undefined
): AIStrategyLiveReadinessItem[] {
  if (!review) return []
  if (review.live_readiness_checklist?.length) return review.live_readiness_checklist
  return liveReadinessChecklistFromPayload(review.pipeline?.live_readiness_checklist)
}

function liveReadinessChecklistForRecord(
  record: AIStrategyResearchRunRecord
): AIStrategyLiveReadinessItem[] {
  if (record.live_readiness_checklist?.length) return record.live_readiness_checklist
  const pipelineChecklist = liveReadinessChecklistFromPayload(
    record.pipeline?.live_readiness_checklist
  )
  if (pipelineChecklist.length) return pipelineChecklist
  if (isRecord(record.paper_handoff)) {
    return liveReadinessChecklistFromPayload(record.paper_handoff.live_readiness_checklist)
  }
  return []
}

function liveReadinessExpiresAtForRecord(record: AIStrategyResearchRunRecord): string | null {
  if (record.live_readiness_expires_at) return record.live_readiness_expires_at
  if (typeof record.pipeline?.live_readiness_expires_at === 'string') {
    return record.pipeline.live_readiness_expires_at
  }
  if (isRecord(record.paper_handoff) && typeof record.paper_handoff.live_readiness_expires_at === 'string') {
    return record.paper_handoff.live_readiness_expires_at
  }
  return null
}

function liveReadinessChecklistFromPayload(payload: unknown): AIStrategyLiveReadinessItem[] {
  if (!Array.isArray(payload)) return []
  return payload.filter(isRecord).map((item, index) => ({
    key: String(item.key || `item-${index}`),
    label: String(item.label || item.key || `检查项 ${index + 1}`),
    status: String(item.status || 'pending'),
    evidence: String(item.evidence || ''),
    action: String(item.action || ''),
    details: isRecord(item.details) ? item.details : undefined,
  }))
}

function clearAIResearchContinuation() {
  aiResearchForm.research_workspace_id = ''
  aiResearchForm.seed_strategy_id = ''
  aiResearchForm.continue_from_run_id = ''
  aiResearchForm.continuation_source = ''
}

function paperStartedRunRecord(
  record: AIStrategyResearchRunRecord,
  paper: AIStrategyPaperTradingStart
): AIStrategyResearchRunRecord {
  return {
    ...record,
    paper_trading_started: paper.started,
    paper_workspace_id: paper.workspace.id,
    paper_workspace_name: paper.workspace.name,
    paper_unit_id: paper.unit.id,
    paper_handoff: paper.handoff ?? {},
    paper_monitoring_plan:
      paperMonitoringPlanFromHandoff(paper.handoff) ?? record.paper_monitoring_plan,
    paper_review_status: null,
    paper_review_ready_for_live: false,
    paper_reviewed_at: null,
    paper_review_evaluations: [],
    paper_review_next_actions: [],
    live_readiness_checklist: [],
    live_readiness_expires_at: null,
    pipeline: paperStartedPipeline(record),
    next_actions: [
      '模拟交易已启动，正在等待后端同步模拟复核状态。',
      '如果同步暂不可用，可稍后手动复核模拟交易监控指标。',
    ],
  }
}

function paperStartedPipeline(record: AIStrategyResearchRunRecord) {
  return {
    current_stage: 'paper_trading',
    status: record.status,
    progress: 80,
    ready_for_live: false,
    paper_trading_error: null,
    live_readiness_checklist: [],
    live_readiness_expires_at: null,
    steps: [
      { key: 'draft', label: '策略生成', status: 'completed' },
      {
        key: 'backtest_loop',
        label: '自动回测迭代',
        status: record.iteration_count > 0 ? 'completed' : 'pending',
        iteration_count: record.iteration_count,
        max_iterations: record.max_iterations,
      },
      {
        key: 'quality_gate',
        label: '质量门槛',
        status: record.achieved ? 'completed' : 'running',
      },
      {
        key: 'paper_trading',
        label: '模拟交易',
        status: 'completed',
        error: null,
      },
      {
        key: 'paper_review',
        label: '模拟复核',
        status: 'pending',
        review_status: null,
      },
    ],
  }
}

function paperTradingStartError(paper: AIStrategyPaperTradingStart) {
  const status = String(paper.run_result?.status || '').trim()
  if (status) return `Paper trading run finished with status ${status}`
  return 'Paper trading run did not return a runnable task'
}

function paperStartFailedRunRecord(
  record: AIStrategyResearchRunRecord,
  paper: AIStrategyPaperTradingStart
): AIStrategyResearchRunRecord {
  const error = paperTradingStartError(paper)
  const previousSteps = record.pipeline?.steps ?? []
  const steps = previousSteps.some(step => step.key === 'paper_trading')
    ? previousSteps.map(step =>
        step.key === 'paper_trading'
          ? { ...step, status: 'failed', error }
          : step
      )
    : [
        ...previousSteps,
        {
          key: 'paper_trading',
          label: '模拟交易',
          status: 'failed',
          error,
        },
      ]
  return {
    ...paperStartedRunRecord(record, paper),
    paper_trading_started: false,
    paper_review_status: null,
    paper_review_ready_for_live: false,
    paper_reviewed_at: null,
    paper_review_evaluations: [],
    paper_review_next_actions: [],
    live_readiness_checklist: [],
    live_readiness_expires_at: null,
    pipeline: {
      current_stage: 'paper_trading_failed',
      status: record.status,
      progress: record.pipeline?.progress ?? 92,
      ready_for_live: false,
      paper_trading_error: error,
      live_readiness_checklist: [],
      live_readiness_expires_at: null,
      steps,
    },
    next_actions: [
      `模拟交易启动错误：${error}`,
      '检查交易工作区、网关配置、策略脚本依赖和资产参数后可重试模拟。',
      '如果启动问题来自策略脚本或交易环境假设，可从该记录继续投研。',
    ],
  }
}

function applyPaperStartToCurrentResult(
  runId: string,
  paper: AIStrategyPaperTradingStart,
  runRecord: AIStrategyResearchRunRecord
) {
  const current = aiResearchResult.value
  if (!current || current.run_id !== runId) return
  aiResearchResult.value = {
    ...current,
    paper_trading: paper,
    paper_monitoring_plan:
      paperMonitoringPlanFromHandoff(paper.handoff) ?? current.paper_monitoring_plan,
    pipeline: runRecord.pipeline ?? current.pipeline,
    next_actions: runRecord.next_actions ?? current.next_actions,
    run_record: runRecord,
  }
}

function applyResearchRunRecordToCurrentResult(runRecord: AIStrategyResearchRunRecord) {
  const current = aiResearchResult.value
  if (!current || current.run_id !== runRecord.run_id) return
  aiResearchResult.value = {
    ...current,
    run_record: runRecord,
    pipeline: runRecord.pipeline ?? current.pipeline,
    next_actions: runRecord.next_actions ?? current.next_actions,
    paper_monitoring_plan: runRecord.paper_monitoring_plan ?? current.paper_monitoring_plan,
  }
}

function workspaceFromResearchRunRecord(record: AIStrategyResearchRunRecord): Workspace {
  return {
    id: record.research_workspace_id,
    user_id: '',
    name: `AI投研 - ${record.symbol}`,
    description: null,
    workspace_type: 'research',
    settings: { ai_research: { runs: [record] } },
    trading_config: {},
    unit_count: 0,
    completed_count: record.iteration_count,
    status: 'completed',
    created_at: record.started_at,
    updated_at: record.completed_at,
  }
}

function researchResultFromRunRecord(
  record: AIStrategyResearchRunRecord
): AIStrategyResearchRunResponse {
  const iterations = researchIterationsFromRunRecord(record)
  return {
    run_id: record.run_id,
    status: record.status,
    achieved: record.achieved,
    target_sharpe: record.target_sharpe,
    started_at: record.started_at,
    completed_at: record.completed_at,
    best_iteration: record.best_iteration,
    best_quality_score: record.best_quality_score,
    best_quality_gate_evaluations: record.best_quality_gate_evaluations ?? [],
    best_diagnostics: record.best_diagnostics ?? {},
    best_metrics: record.best_metrics ?? {},
    research_workspace: workspaceFromResearchRunRecord(record),
    iterations,
    best_strategy: null,
    paper_trading: null,
    paper_monitoring_plan: record.paper_monitoring_plan ?? [],
    pipeline: record.pipeline,
    run_record: record,
    next_actions: record.next_actions ?? [],
    message: 'AI research result restored from run history',
  }
}

function researchIterationsFromRunRecord(
  record: AIStrategyResearchRunRecord
): AIStrategyResearchIteration[] {
  return (record.iterations || [])
    .filter(isRecord)
    .map((payload, index) => researchIterationFromRunRecord(record, payload, index + 1))
}

function researchIterationFromRunRecord(
  record: AIStrategyResearchRunRecord,
  payload: Record<string, unknown>,
  fallbackIteration: number
): AIStrategyResearchIteration {
  const iteration = Math.max(Math.trunc(optionalNumber(payload.iteration) ?? fallbackIteration), 1)
  const metrics = isRecord(payload.metrics) ? payload.metrics : {}
  const strategy = strategyFromIterationRecord(record, payload, iteration)
  const unit = unitFromIterationRecord(record, payload, strategy, metrics)
  const runStatus = stringFromUnknown(payload.run_status, 'completed')
  const taskId = nullableString(payload.task_id)
  return {
    iteration,
    strategy,
    unit,
    run_result: {
      unit_id: unit.id,
      task_id: taskId,
      status: runStatus,
    },
    unit_status: unitStatusFromIterationRecord(unit, runStatus, taskId, metrics),
    metrics,
    sharpe_ratio: optionalNumber(payload.sharpe_ratio) ?? metricFromPayload(metrics, 'sharpe_ratio', 'sharpe') ?? 0,
    total_trades: optionalNumber(payload.total_trades) ?? metricFromPayload(metrics, 'total_trades', 'trades') ?? 0,
    validation_status: nullableString(payload.validation_status),
    validation_window: validationWindowFromUnknown(payload.validation_window),
    validation_metrics: isRecord(payload.validation_metrics) ? payload.validation_metrics : {},
    validation_gate_evaluations: arrayFromUnknown<AIStrategyQualityGateEvaluation>(
      payload.validation_gate_evaluations
    ),
    validation_failures: stringArrayFromUnknown(payload.validation_failures),
    validation_failure_reason: nullableString(payload.validation_failure_reason),
    quality_score: optionalNumber(payload.quality_score) ?? record.best_quality_score ?? 0,
    quality_gate_evaluations: arrayFromUnknown<AIStrategyQualityGateEvaluation>(
      payload.quality_gate_evaluations
    ),
    passed: Boolean(payload.passed),
    failure_reason: nullableString(payload.failure_reason),
    quality_gate_failures: stringArrayFromUnknown(payload.quality_gate_failures),
    diagnostics: isRecord(payload.diagnostics)
      ? payload.diagnostics as AIStrategyResearchIteration['diagnostics']
      : {},
    improvement_plan: stringArrayFromUnknown(payload.improvement_plan),
    improvement_notes: stringArrayFromUnknown(payload.improvement_notes),
    next_actions: stringArrayFromUnknown(payload.next_actions),
  }
}

function strategyFromIterationRecord(
  record: AIStrategyResearchRunRecord,
  payload: Record<string, unknown>,
  iteration: number
): Strategy {
  const snapshot = isRecord(payload.unit_snapshot) ? payload.unit_snapshot : {}
  const strategySnapshot = isRecord(payload.strategy_snapshot) ? payload.strategy_snapshot : {}
  const strategyId = stringFromUnknown(
    strategySnapshot.id ?? payload.strategy_id,
    record.best_strategy_id || `${record.run_id}-iteration-${iteration}`
  )
  const strategyName = stringFromUnknown(
    strategySnapshot.name ?? payload.strategy_name,
    record.best_strategy_name || `AI策略 第${iteration}轮`
  )
  const diagnostics = isRecord(payload.diagnostics) ? payload.diagnostics : {}
  return {
    id: strategyId,
    user_id: '',
    name: strategyName,
    description: stringFromUnknown(strategySnapshot.description, stringFromUnknown(diagnostics.summary, record.prompt)),
    code: stringFromUnknown(strategySnapshot.code, stringFromUnknown(payload.strategy_code, stringFromUnknown(payload.code, ''))),
    params: isRecord(strategySnapshot.params)
      ? strategySnapshot.params as Strategy['params']
      : isRecord(snapshot.params) ? snapshot.params as Strategy['params'] : {},
    category: stringFromUnknown(strategySnapshot.category, stringFromUnknown(snapshot.category, 'custom')),
    created_at: stringFromUnknown(strategySnapshot.created_at, record.started_at),
    updated_at: stringFromUnknown(strategySnapshot.updated_at, record.completed_at),
  }
}

function unitFromIterationRecord(
  record: AIStrategyResearchRunRecord,
  payload: Record<string, unknown>,
  strategy: Strategy,
  metrics: Record<string, unknown>
): StrategyUnit {
  const snapshot = isRecord(payload.unit_snapshot) ? payload.unit_snapshot : {}
  return {
    id: stringFromUnknown(payload.unit_id, stringFromUnknown(snapshot.id, `${record.run_id}-unit`)),
    workspace_id: stringFromUnknown(snapshot.workspace_id, record.research_workspace_id),
    group_name: stringFromUnknown(snapshot.group_name, strategy.name),
    strategy_id: strategy.id,
    strategy_name: strategy.name,
    symbol: stringFromUnknown(snapshot.symbol, record.symbol),
    symbol_name: stringFromUnknown(snapshot.symbol_name, record.symbol_name || record.symbol),
    timeframe: stringFromUnknown(snapshot.timeframe, record.timeframe),
    timeframe_n: optionalNumber(snapshot.timeframe_n) ?? record.timeframe_n,
    category: stringFromUnknown(snapshot.category, strategy.category),
    sort_order: 0,
    data_config: isRecord(snapshot.data_config) ? snapshot.data_config : {},
    unit_settings: isRecord(snapshot.unit_settings) ? snapshot.unit_settings : {},
    params: isRecord(snapshot.params) ? snapshot.params : {},
    optimization_config: isRecord(snapshot.optimization_config) ? snapshot.optimization_config : {},
    trading_mode: unitTradingMode(snapshot),
    gateway_config: isRecord(snapshot.gateway_config)
      ? snapshot.gateway_config as StrategyUnit['gateway_config']
      : {},
    lock_trading: Boolean(snapshot.lock_trading),
    lock_running: Boolean(snapshot.lock_running),
    trading_instance_id: nullableString(snapshot.trading_instance_id),
    trading_snapshot: emptyTradingSnapshot(unitTradingMode(snapshot)),
    run_status: stringFromUnknown(payload.run_status, 'completed') as StrategyUnit['run_status'],
    run_count: optionalNumber(snapshot.run_count) ?? 1,
    last_run_time: optionalNumber(snapshot.last_run_time),
    last_task_id: nullableString(payload.task_id),
    last_optimization_task_id: nullableString(snapshot.last_optimization_task_id),
    bar_count: optionalNumber(snapshot.bar_count),
    metrics_snapshot: metrics,
    created_at: record.started_at,
    updated_at: record.completed_at,
  }
}

function unitStatusFromIterationRecord(
  unit: StrategyUnit,
  runStatus: string,
  taskId: string | null,
  metrics: Record<string, unknown>
): UnitStatusResponse {
  return {
    id: unit.id,
    run_status: runStatus as UnitStatusResponse['run_status'],
    last_task_id: taskId,
    metrics_snapshot: metrics,
    run_count: unit.run_count,
    last_run_time: unit.last_run_time,
    bar_count: unit.bar_count,
    trading_instance_id: unit.trading_instance_id,
    trading_snapshot: emptyTradingSnapshot(unit.trading_mode),
    trading_mode: unit.trading_mode,
    lock_trading: unit.lock_trading,
    lock_running: unit.lock_running,
    opt_status: null,
    opt_total: null,
    opt_completed: null,
    opt_progress: null,
    opt_elapsed_time: null,
    opt_remaining_time: null,
  }
}

function metricFromPayload(payload: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = optionalNumber(payload[key])
    if (value !== null) return value
  }
  return null
}

function unitTradingMode(snapshot: Record<string, unknown>) {
  return stringFromUnknown(snapshot.trading_mode, 'paper') as StrategyUnit['trading_mode']
}

function emptyTradingSnapshot(mode: StrategyUnit['trading_mode']): TradingSnapshot {
  return {
    instance_id: null,
    instance_status: 'idle',
    mode,
    error: null,
    started_at: null,
    stopped_at: null,
    gateway_summary: null,
    long_position: 0,
    short_position: 0,
    today_pnl: null,
    position_pnl: null,
    latest_price: null,
    change_pct: null,
    long_market_value: null,
    short_market_value: null,
    leverage: null,
    cumulative_pnl: null,
    max_drawdown_rate: null,
    trading_day: null,
    updated_at: null,
    detail_route: null,
    positions: [],
    trades: [],
  }
}

function stringFromUnknown(value: unknown, fallback = '') {
  const text = typeof value === 'string' ? value.trim() : ''
  return text || fallback
}

function nullableString(value: unknown) {
  const text = typeof value === 'string' ? value.trim() : ''
  return text || null
}

function stringArrayFromUnknown(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
}

function arrayFromUnknown<T>(value: unknown): T[] {
  return Array.isArray(value) ? value.filter(isRecord) as T[] : []
}

async function restoreAIResearchResultFromTask(
  task: AIStrategyResearchTaskResponse
): Promise<AIStrategyResearchRunResponse | null> {
  if (!task.run_id) return null
  try {
    const response = await strategyApi.listAIResearchRuns(
      task.research_workspace_id || undefined,
      100
    )
    const record = response.items.find(item => item.run_id === task.run_id)
    if (!record) return null
    upsertAIResearchRunRecord(record)
    return researchResultFromRunRecord(record)
  } catch {
    return null
  }
}

function reviewedRunRecord(
  record: AIStrategyResearchRunRecord,
  review: AIStrategyPaperTradingReview
): AIStrategyResearchRunRecord {
  const liveReadinessChecklist = liveReadinessChecklistForReview(review)
  const paperHandoff: Record<string, unknown> = { ...(record.paper_handoff ?? {}) }
  if (liveReadinessChecklist.length) {
    paperHandoff.live_readiness_checklist = liveReadinessChecklist
  } else {
    delete paperHandoff.live_readiness_checklist
  }
  if (review.live_readiness_expires_at) {
    paperHandoff.live_readiness_expires_at = review.live_readiness_expires_at
  } else {
    delete paperHandoff.live_readiness_expires_at
  }
  return {
    ...record,
    paper_review_status: review.status,
    paper_review_ready_for_live: review.ready_for_live,
    paper_reviewed_at: review.reviewed_at ?? record.paper_reviewed_at,
    paper_review_evaluations: review.evaluations,
    paper_review_next_actions: review.next_actions,
    live_readiness_checklist: liveReadinessChecklist,
    live_readiness_expires_at: review.live_readiness_expires_at ?? null,
    paper_handoff: paperHandoff,
    pipeline: review.pipeline ?? record.pipeline,
    next_actions: review.next_actions,
  }
}

function paperReviewForRecord(
  record: AIStrategyResearchRunRecord
): AIStrategyPaperTradingReview | null {
  const review = aiResearchPaperReviews[record.run_id]
  if (review) return review
  if (!record.paper_review_status || !record.paper_review_evaluations?.length) return null
  return {
    run_id: record.run_id,
    research_workspace_id: record.research_workspace_id,
    paper_workspace_id: record.paper_workspace_id,
    paper_unit_id: record.paper_unit_id,
    paper_trading_started: record.paper_trading_started,
    monitoring_plan: record.paper_monitoring_plan ?? [],
    evaluations: record.paper_review_evaluations,
    ready_for_live: Boolean(record.paper_review_ready_for_live),
    status: record.paper_review_status,
    reviewed_at: record.paper_reviewed_at,
    live_readiness_checklist: liveReadinessChecklistForRecord(record),
    live_readiness_expires_at: liveReadinessExpiresAtForRecord(record),
    pipeline: record.pipeline,
    next_actions: record.paper_review_next_actions ?? [],
  } satisfies AIStrategyPaperTradingReview
}

function applyPaperReviewToCurrentResult(
  runId: string,
  runRecord: AIStrategyResearchRunRecord
) {
  const current = aiResearchResult.value
  if (!current || current.run_id !== runId) return
  aiResearchResult.value = {
    ...current,
    run_record: runRecord,
    pipeline: runRecord.pipeline ?? current.pipeline,
    next_actions: runRecord.next_actions ?? current.next_actions,
  }
}

async function startPaperFromResearchRecord(record: AIStrategyResearchRunRecord) {
  aiResearchPaperStartingRunId.value = record.run_id
  try {
    const paper = await strategyApi.startAIResearchPaperTrading(
      record.run_id,
      aiResearchPaperStartRequest(record)
    )
    if (!paper.started) {
      const failedRecord = paperStartFailedRunRecord(record, paper)
      upsertAIResearchRunRecord(failedRecord)
      applyPaperStartToCurrentResult(record.run_id, paper, failedRecord)
      try {
        await refreshAIResearchRunRecord(record.run_id, record.research_workspace_id)
      } catch {
        // Keep the local failed start state visible even if history refresh fails.
      }
      ElMessage.error('模拟交易启动失败')
      return
    }
    const updatedRecord = paperStartedRunRecord(record, paper)
    upsertAIResearchRunRecord(updatedRecord)
    applyPaperStartToCurrentResult(record.run_id, paper, updatedRecord)
    try {
      await refreshAIResearchRunRecord(record.run_id, record.research_workspace_id)
    } catch {
      // Keep the local started state visible even if history refresh fails.
    }
    ElMessage.success('模拟交易已启动')
  } catch {
    try {
      await refreshAIResearchRunRecord(record.run_id, record.research_workspace_id)
    } catch {
      // Keep the original start failure visible even if history refresh fails.
    }
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchPaperStartingRunId.value = ''
  }
}

async function startPaperFromCurrentResult() {
  const record = aiResearchResult.value?.run_record
  if (!record) return
  await startPaperFromResearchRecord(record)
}

async function viewBestStrategyFromCurrentResult() {
  const result = aiResearchResult.value
  if (!result) return
  if (result.best_strategy) {
    viewStrategy(result.best_strategy)
    return
  }
  const record = result.run_record
  if (!record) return
  await viewStrategyFromResearchRecord(record)
}

async function viewResearchIterationStrategy(item: AIStrategyResearchIteration) {
  if (item.strategy.code.trim()) {
    viewStrategy(item.strategy)
    return
  }
  if (!item.strategy.id) return
  aiResearchStrategyViewingRunId.value = aiResearchResult.value?.run_id || item.strategy.id
  try {
    const strategy = await strategyApi.get(item.strategy.id)
    viewStrategy(strategy)
  } catch {
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchStrategyViewingRunId.value = ''
  }
}

async function viewStrategyFromResearchRecord(record: AIStrategyResearchRunRecord) {
  const snapshotStrategy = bestStrategyFromRunRecord(record)
  if (snapshotStrategy?.code?.trim()) {
    viewStrategy(snapshotStrategy)
    return
  }
  const strategyId = bestStrategyIdForRecord(record)
  if (!strategyId) return
  aiResearchStrategyViewingRunId.value = record.run_id
  try {
    const strategy = await strategyApi.get(strategyId)
    viewStrategy(strategy)
  } catch {
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchStrategyViewingRunId.value = ''
  }
}

function paperMonitoringPlanFromHandoff(
  handoff: Record<string, unknown> | null | undefined
): AIStrategyPaperMonitoringRule[] | undefined {
  const plan = handoff?.paper_monitoring_plan
  return Array.isArray(plan) ? (plan as AIStrategyPaperMonitoringRule[]) : undefined
}

async function reviewPaperFromResearchRecord(record: AIStrategyResearchRunRecord) {
  aiResearchPaperReviewingRunId.value = record.run_id
  try {
    const review = await strategyApi.reviewAIResearchPaperTrading(
      record.run_id,
      record.research_workspace_id
    )
    aiResearchPaperReviews[record.run_id] = review
    const updatedRecord = reviewedRunRecord(record, review)
    upsertAIResearchRunRecord(updatedRecord)
    applyPaperReviewToCurrentResult(record.run_id, updatedRecord)
    ElMessage.success(review.ready_for_live ? '模拟交易已满足实盘候选条件' : '模拟交易复核已更新')
  } catch {
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchPaperReviewingRunId.value = ''
  }
}

async function reviewPaperFromCurrentResult() {
  const record = aiResearchResult.value?.run_record
  if (!record) return
  await reviewPaperFromResearchRecord(record)
}

async function continueResearchFromCurrentPaperReview() {
  const record = aiResearchResult.value?.run_record
  if (!record) return
  await continueResearchFromRecord(record)
}

async function continueResearchFromCurrentRunRecord() {
  const record = aiResearchResult.value?.run_record
  if (!record) return
  await continueResearchFromRecord(record)
}

async function continueResearchFromPaperReview(record: AIStrategyResearchRunRecord) {
  await continueResearchFromRecord(record)
}

async function continueResearchFromRecord(record: AIStrategyResearchRunRecord) {
  useAIResearchRecord(record)
  await runAIResearchLoop()
}

function buildAIResearchRequest(prompt: string, symbol: string): AIStrategyResearchRunRequest {
  const paperWorkspaceName = aiResearchPaperWorkspaceName()
  const gatewayConfig = parseAIResearchGatewayConfig()
  const request: AIStrategyResearchRunRequest = {
    prompt,
    symbol,
    symbol_name: aiResearchForm.symbol_name.trim(),
    timeframe: aiResearchForm.timeframe,
    timeframe_n: aiResearchForm.timeframe_n,
    start_date: aiResearchForm.start_date || null,
    end_date: aiResearchForm.end_date || null,
    target_sharpe: aiResearchForm.target_sharpe,
    min_total_trades: aiResearchForm.min_total_trades,
    max_drawdown_limit: enabledQualityGate(
      aiResearchForm.use_max_drawdown_limit,
      aiResearchForm.max_drawdown_limit
    ),
    min_total_return: enabledQualityGate(
      aiResearchForm.use_min_total_return,
      aiResearchForm.min_total_return
    ),
    min_annual_return: enabledQualityGate(
      aiResearchForm.use_min_annual_return,
      aiResearchForm.min_annual_return
    ),
    min_win_rate: enabledQualityGate(
      aiResearchForm.use_min_win_rate,
      aiResearchForm.min_win_rate
    ),
    max_iterations: aiResearchForm.max_iterations,
    out_of_sample_validation: aiResearchForm.out_of_sample_validation,
    out_of_sample_ratio: outOfSampleRatioValue(),
    min_out_of_sample_sharpe: aiResearchForm.out_of_sample_validation
      ? enabledQualityGate(
          aiResearchForm.use_min_out_of_sample_sharpe,
          aiResearchForm.min_out_of_sample_sharpe
        )
      : null,
    min_out_of_sample_trades: aiResearchForm.out_of_sample_validation
      ? enabledQualityGate(
          aiResearchForm.use_min_out_of_sample_trades,
          aiResearchForm.min_out_of_sample_trades
        )
      : null,
    initial_cash: aiResearchForm.initial_cash,
    research_workspace_id: aiResearchForm.research_workspace_id || null,
    seed_strategy_id: aiResearchForm.seed_strategy_id || null,
    continue_from_run_id: aiResearchForm.continue_from_run_id || null,
    start_paper_trading: aiResearchForm.start_paper_trading,
    trading_workspace_id: aiResearchForm.trading_workspace_id.trim() || null,
    paper_workspace_name: aiResearchForm.start_paper_trading
      ? paperWorkspaceName
      : null,
    backtest_timeout_seconds: aiResearchForm.backtest_timeout_seconds,
    poll_interval_seconds: aiResearchForm.poll_interval_seconds,
    knowledge_base_id: aiResearchForm.knowledge_base_id.trim() || null,
    thinking_mode: aiResearchForm.thinking_mode,
  }
  if (aiResearchForm.use_manual_commission) {
    request.commission = aiResearchForm.commission
  }
  if (gatewayConfig) {
    request.gateway_config = gatewayConfig
  }
  return request
}

function aiResearchPaperWorkspaceName() {
  return aiResearchForm.paper_workspace_name.trim() || null
}

function parseAIResearchGatewayConfig() {
  const raw = aiResearchForm.gateway_config_json.trim()
  if (!raw) return undefined
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error('模拟网关配置必须是合法 JSON')
  }
  if (!isRecord(parsed) || Array.isArray(parsed)) {
    throw new Error('模拟网关配置必须是 JSON 对象')
  }
  return parsed
}

function aiResearchPaperStartRequest(record: AIStrategyResearchRunRecord) {
  const gatewayConfig = parseAIResearchGatewayConfig()
  const request = {
    research_workspace_id: record.research_workspace_id,
  } as {
    research_workspace_id: string
    trading_workspace_id?: string
    paper_workspace_name?: string
    gateway_config?: Record<string, unknown>
  }
  const tradingWorkspaceId = aiResearchForm.trading_workspace_id.trim()
  if (tradingWorkspaceId) {
    request.trading_workspace_id = tradingWorkspaceId
  }
  const paperWorkspaceName = aiResearchPaperWorkspaceName()
    || record.paper_workspace_name?.trim()
    || null
  if (paperWorkspaceName) {
    request.paper_workspace_name = paperWorkspaceName
  }
  if (gatewayConfig) {
    request.gateway_config = gatewayConfig
  }
  return request
}

function isAIResearchTaskTerminal(task: AIStrategyResearchTaskResponse) {
  return ['completed', 'failed', 'cancelled'].includes(String(task.status || '').toLowerCase())
}

function isAIResearchTaskCancelled(task: AIStrategyResearchTaskResponse) {
  return String(task.status || '').toLowerCase() === 'cancelled'
}

function sleep(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

const AI_RESEARCH_TASK_POLL_INTERVAL_MS = 1500
const AI_RESEARCH_TASK_MIN_TIMEOUT_MS = 10 * 60 * 1000
const AI_RESEARCH_TASK_MAX_TIMEOUT_MS = 8 * 60 * 60 * 1000

function boundedNumber(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(Math.max(parsed, min), max)
}

function aiResearchTaskPollTimeoutMs(
  payload?: AIStrategyResearchRunRequest,
  task?: AIStrategyResearchTaskResponse
) {
  const maxIterations = boundedNumber(
    payload?.max_iterations ?? task?.max_iterations ?? aiResearchForm.max_iterations,
    3,
    1,
    8
  )
  const backtestTimeoutSeconds = boundedNumber(payload?.backtest_timeout_seconds, 600, 1, 3600)
  const validationFactor = payload?.out_of_sample_validation === false ? 1 : 2
  const estimatedSeconds = maxIterations * validationFactor * backtestTimeoutSeconds + 240
  return boundedNumber(
    estimatedSeconds * 1000,
    AI_RESEARCH_TASK_MIN_TIMEOUT_MS,
    AI_RESEARCH_TASK_MIN_TIMEOUT_MS,
    AI_RESEARCH_TASK_MAX_TIMEOUT_MS
  )
}

function applyAIResearchTaskStatus(task: AIStrategyResearchTaskResponse) {
  aiResearchTaskId.value = task.task_id
  aiResearchTaskStatus.value = task.status
  aiResearchTaskStage.value = task.current_stage || task.status
  aiResearchTaskProgress.value = Number(task.progress || 0)
  aiResearchTaskIteration.value = task.current_iteration ?? task.iteration_count ?? null
  aiResearchBacktestTaskId.value = task.current_backtest_task_id || ''
  aiResearchCancelledBacktestTaskId.value = task.cancelled_backtest_task_id || ''
  aiResearchTaskError.value = aiResearchTaskFailureMessage(task)
  aiResearchTaskMessage.value = String(task.message || '').trim()
  aiResearchTaskLatestIteration.value = task.latest_iteration ?? null
}

function aiResearchTaskFailureMessage(task: AIStrategyResearchTaskResponse) {
  if (isAIResearchTaskCancelled(task)) return ''
  if (String(task.status || '').toLowerCase() !== 'failed') return ''
  return String(task.error || task.message || 'AI research task failed').trim()
}

function aiResearchErrorMessage(error: unknown) {
  if (error instanceof Error && error.message.trim()) return error.message.trim()
  const message = String(error || '').trim()
  return message || t('strategy.aiResearchRunFailed')
}

async function runAIResearchRequest(
  payload: AIStrategyResearchRunRequest
): Promise<AIStrategyResearchRunResponse> {
  const apiWithTasks = strategyApi as typeof strategyApi & {
    submitAIResearchTask?: typeof strategyApi.submitAIResearchTask
    getAIResearchTask?: typeof strategyApi.getAIResearchTask
  }
  if (
    typeof apiWithTasks.submitAIResearchTask !== 'function'
    || typeof apiWithTasks.getAIResearchTask !== 'function'
  ) {
    return strategyApi.runAIResearchLoop(payload)
  }

  const task = await apiWithTasks.submitAIResearchTask(payload)
  return pollAIResearchTask(task, aiResearchTaskPollTimeoutMs(payload, task))
}

async function pollAIResearchTask(
  task: AIStrategyResearchTaskResponse,
  timeoutMs = aiResearchTaskPollTimeoutMs(undefined, task)
): Promise<AIStrategyResearchRunResponse> {
  const apiWithTasks = strategyApi as typeof strategyApi & {
    getAIResearchTask?: typeof strategyApi.getAIResearchTask
  }
  if (typeof apiWithTasks.getAIResearchTask !== 'function') {
    throw new Error('AI research task polling is unavailable')
  }
  applyAIResearchTaskStatus(task)
  const deadline = Date.now() + timeoutMs
  const maxPolls = Math.max(
    240,
    Math.ceil(timeoutMs / AI_RESEARCH_TASK_POLL_INTERVAL_MS) + 2
  )
  for (let attempt = 0; attempt < maxPolls; attempt += 1) {
    if (task.status === 'completed') {
      if (task.result) return task.result
      const restoredResult = await restoreAIResearchResultFromTask(task)
      if (restoredResult) return restoredResult
      throw new Error('AI research task completed without a result')
    }
    if (isAIResearchTaskCancelled(task)) {
      const restoredResult = await restoreAIResearchResultFromTask(task)
      if (restoredResult) return restoredResult
      throw new Error('AI_RESEARCH_CANCELLED')
    }
    if (isAIResearchTaskTerminal(task)) {
      throw new Error(task.error || task.message || 'AI research task failed')
    }
    if (Date.now() > deadline) {
      break
    }
    task = await apiWithTasks.getAIResearchTask(task.task_id)
    applyAIResearchTaskStatus(task)
    if (!isAIResearchTaskTerminal(task)) {
      await sleep(AI_RESEARCH_TASK_POLL_INTERVAL_MS)
    }
  }
  throw new Error(`AI research task polling timed out after ${Math.round(timeoutMs / 1000)}s`)
}

async function restoreActiveAIResearchTask() {
  const apiWithTasks = strategyApi as typeof strategyApi & {
    listAIResearchTasks?: typeof strategyApi.listAIResearchTasks
  }
  if (aiResearchRunning.value || typeof apiWithTasks.listAIResearchTasks !== 'function') return
  try {
    const response = await apiWithTasks.listAIResearchTasks(true, 5)
    const task = response.items.find(item => !isAIResearchTaskTerminal(item))
    if (!task) return
    aiResearchRunning.value = true
    aiResearchResult.value = await pollAIResearchTask(task)
    if (aiResearchResult.value.run_record) {
      upsertAIResearchRunRecord(aiResearchResult.value.run_record)
    } else {
      await loadAIResearchRuns()
    }
    if (String(aiResearchResult.value.status || '').toLowerCase() === 'cancelled') {
      if (!aiResearchCancelRequested.value) {
        ElMessage.success('AI投研任务已取消')
      }
    } else {
      ElMessage.success(t('strategy.aiResearchRunSuccess'))
    }
  } catch (error) {
    aiResearchTaskError.value = aiResearchErrorMessage(error)
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchRunning.value = false
  }
}

async function cancelAIResearchTask() {
  const taskId = aiResearchTaskId.value
  const cancelTask = (strategyApi as { cancelAIResearchTask?: (taskId: string) => Promise<AIStrategyResearchTaskResponse> }).cancelAIResearchTask
  if (!taskId || typeof cancelTask !== 'function') return
  aiResearchCancelling.value = true
  aiResearchCancelRequested.value = true
  try {
    const task = await cancelTask(taskId)
    applyAIResearchTaskStatus(task)
    aiResearchTaskError.value = ''
    aiResearchRunning.value = false
    if (task.run_id) {
      try {
        const record = await refreshAIResearchRunRecord(task.run_id, task.research_workspace_id)
        if (record) {
          aiResearchResult.value = researchResultFromRunRecord(record)
        }
      } catch {
        await loadAIResearchRuns()
      }
    }
    ElMessage.success(
      task.child_cancelled && task.cancelled_backtest_task_id
        ? 'AI投研任务已取消，当前回测任务已同步取消'
        : 'AI投研任务已取消'
    )
  } catch {
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchCancelling.value = false
  }
}

async function runAIResearchLoop() {
  const prompt = aiResearchForm.prompt.trim()
  const symbol = aiResearchForm.symbol.trim()
  if (!prompt) {
    ElMessage.warning(t('strategy.aiResearchPromptRequired'))
    return
  }
  if (!symbol) {
    ElMessage.warning(t('strategy.aiResearchSymbolRequired'))
    return
  }

  aiResearchRunning.value = true
  aiResearchTaskId.value = ''
  aiResearchTaskStatus.value = ''
  aiResearchTaskStage.value = ''
  aiResearchTaskProgress.value = 0
  aiResearchTaskIteration.value = null
  aiResearchBacktestTaskId.value = ''
  aiResearchCancelledBacktestTaskId.value = ''
  aiResearchTaskError.value = ''
  aiResearchTaskMessage.value = ''
  aiResearchTaskLatestIteration.value = null
  aiResearchCancelRequested.value = false
  try {
    aiResearchResult.value = await runAIResearchRequest(buildAIResearchRequest(prompt, symbol))
    if (aiResearchResult.value.run_record) {
      upsertAIResearchRunRecord(aiResearchResult.value.run_record)
    } else {
      await loadAIResearchRuns()
    }
    if (String(aiResearchResult.value.status || '').toLowerCase() === 'cancelled') {
      if (!aiResearchCancelRequested.value) {
        ElMessage.success('AI投研任务已取消')
      }
    } else {
      ElMessage.success(t('strategy.aiResearchRunSuccess'))
    }
  } catch (error) {
    if (
      error instanceof Error
      && error.message === 'AI_RESEARCH_CANCELLED'
      && aiResearchCancelRequested.value
    ) {
      aiResearchTaskError.value = ''
      return
    }
    aiResearchTaskError.value = aiResearchErrorMessage(error)
    ElMessage.error(t('strategy.aiResearchRunFailed'))
  } finally {
    aiResearchRunning.value = false
  }
}

function openResearchWorkspace() {
  const workspaceId = aiResearchResult.value?.research_workspace.id
  if (!workspaceId) return
  router.push({ name: 'ResearchWorkspaceDetail', params: { id: workspaceId } })
}

function openPaperWorkspace() {
  const workspaceId = aiResearchResult.value?.paper_trading?.workspace.id
    || aiResearchResult.value?.run_record?.paper_workspace_id
  if (!workspaceId) return
  router.push({ name: 'TradingWorkspaceDetail', params: { id: workspaceId } })
}

function showCreateDialog() {
  isEdit.value = false
  editingId.value = ''
  Object.assign(form, { name: '', description: '', code: '', category: 'custom' })
  dialogVisible.value = true
}

function editStrategy(strategy: Strategy) {
  isEdit.value = true
  editingId.value = strategy.id
  Object.assign(form, {
    name: strategy.name,
    description: strategy.description || '',
    code: strategy.code,
    category: strategy.category,
  })
  dialogVisible.value = true
}

function viewStrategy(strategy: Strategy) {
  currentStrategy.value = strategy
  viewDialogVisible.value = true
}

function useTemplate(template: StrategyTemplate) {
  detailVisible.value = false
  isEdit.value = false
  editingId.value = ''
  Object.assign(form, {
    name: template.name + ` (${t('strategy.typeCopy')})`,
    description: stripStrategyMeta(template.description),
    code: template.code,
    category: template.category,
  })
  activeTab.value = 'my'
  dialogVisible.value = true
}

function updateStrategyForm(nextForm: typeof form) {
  Object.assign(form, nextForm)
}

async function saveStrategy() {
  if (!form.name || !form.code) {
    ElMessage.warning(t('strategy.warnNameOrCodeEmpty'))
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await strategyStore.updateStrategy(editingId.value, form)
      ElMessage.success(t('strategy.updated'))
    } else {
      await strategyStore.createStrategy(form)
      ElMessage.success(t('strategy.created'))
    }
    dialogVisible.value = false
  } finally {
    saving.value = false
  }
}

async function deleteStrategy(id: string) {
  await ElMessageBox.confirm(t('strategy.confirmDeleteText'), t('strategy.confirmDeleteTitle'), { type: 'warning' })
  await strategyStore.deleteStrategy(id)
  ElMessage.success(t('strategy.deleted'))
}

onMounted(async () => {
  try {
    await Promise.all([
      strategyStore.fetchStrategies(),
      strategyStore.fetchTemplates(),
      loadAIResearchRuns(),
    ])
    void restoreActiveAIResearchTask()
  } catch {
    ElMessage.error(t('strategy.loadFailed'))
  }
})
</script>

<style scoped>
.ai-research-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.95fr) minmax(360px, 1.05fr);
  gap: 20px;
  align-items: start;
}

.ai-research-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 20px;
  background: var(--el-bg-color);
}

.ai-research-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.ai-research-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 8px;
}

.ai-research-action-options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ai-research-task-progress {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.ai-research-task-progress strong {
  color: var(--el-text-color-primary);
  font-size: 12px;
  line-height: 1.4;
}

.ai-research-gate-control {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.ai-research-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.ai-research-kicker {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.2;
  margin-bottom: 4px;
}

.ai-research-title {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.3;
  margin: 0;
  color: var(--el-text-color-primary);
}

.ai-research-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.ai-research-metrics > div {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px;
  min-width: 0;
}

.ai-research-metrics span {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 6px;
}

.ai-research-metrics strong {
  display: block;
  color: var(--el-text-color-primary);
  font-size: 18px;
  line-height: 1.2;
}

.ai-research-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.ai-research-pipeline {
  border-top: 1px solid var(--el-border-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 10px 0;
  margin-bottom: 16px;
}

.ai-research-pipeline > strong {
  display: block;
  color: var(--el-text-color-primary);
  font-size: 13px;
  margin-bottom: 8px;
}

.ai-research-pipeline-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-research-pipeline-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  color: var(--el-text-color-regular);
  font-size: 12px;
}

.ai-research-pipeline-step small {
  color: var(--el-text-color-secondary);
}

.ai-research-action-plan {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
  background: var(--el-fill-color-light);
}

.ai-research-action-plan strong {
  display: block;
  color: var(--el-text-color-primary);
  font-size: 13px;
  margin-bottom: 8px;
}

.ai-research-action-plan ul,
.ai-research-next-actions {
  margin: 0;
  padding-left: 18px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.ai-research-gate-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.ai-research-gate-summary-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.ai-research-oos-summary {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 16px;
  background: var(--el-fill-color-lighter);
}

.ai-research-oos-summary-compact {
  margin: 10px 0 0;
}

.ai-research-oos-head,
.ai-research-oos-details {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.ai-research-oos-head {
  justify-content: space-between;
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.ai-research-oos-details {
  color: var(--el-text-color-regular);
  font-size: 12px;
}

.ai-research-warning-text {
  color: var(--el-color-warning);
}

.ai-research-iterations {
  display: grid;
  gap: 10px;
}

.ai-research-iteration {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
}

.ai-research-iteration-head,
.ai-research-iteration-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.ai-research-iteration-head {
  justify-content: space-between;
  margin-bottom: 8px;
}

.ai-research-iteration-actions {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.ai-research-iteration-metrics {
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.ai-research-warning {
  margin: 8px 0 0;
  color: var(--el-color-warning);
  font-size: 13px;
}

.ai-research-notes {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.ai-research-next-actions {
  margin-top: 8px;
  color: var(--el-color-primary);
}

.ai-research-history {
  margin-top: 18px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 16px;
}

.ai-research-history-head {
  margin-bottom: 10px;
}

.ai-research-history-title {
  margin: 0;
  font-size: 16px;
  line-height: 1.3;
  color: var(--el-text-color-primary);
}

.ai-research-history-list {
  display: grid;
  gap: 8px;
}

.ai-research-history-item {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-bg-color);
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.ai-research-history-select {
  border: 0;
  padding: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  flex: 1;
  min-width: 0;
}

.ai-research-history-select:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.ai-research-history-main,
.ai-research-history-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.ai-research-history-main {
  justify-content: space-between;
  margin-bottom: 6px;
}

.ai-research-history-main strong {
  min-width: 0;
  color: var(--el-text-color-primary);
  font-size: 13px;
  line-height: 1.35;
}

.ai-research-history-meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.ai-research-paper-review {
  flex-basis: 100%;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
}

.ai-research-current-paper-review {
  margin-bottom: 16px;
}

.ai-research-current-paper-review-action {
  margin-top: 8px;
}

.ai-research-paper-env {
  flex-basis: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.ai-research-paper-env strong {
  color: var(--el-text-color-primary);
  font-size: 12px;
}

.ai-research-paper-review-head,
.ai-research-paper-review-rules {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.ai-research-paper-review-head {
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
}

.ai-research-paper-review-rules {
  color: var(--el-text-color-secondary);
}

.ai-research-live-readiness {
  display: grid;
  gap: 4px;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.ai-research-live-readiness strong {
  color: var(--el-text-color-primary);
  font-size: 12px;
}

.ai-research-history-empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 8px 0;
}

@media (max-width: 1024px) {
  .ai-research-grid,
  .ai-research-form-grid,
  .ai-research-metrics {
    grid-template-columns: 1fr;
  }
}

.strategy-card {
  transition: transform 0.15s, box-shadow 0.15s;
}
.strategy-card:hover {
  transform: translateY(-2px);
}
.strategy-card:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 2px;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.readme-content h1, .readme-content h2, .readme-content h3 {
  border-bottom: 1px solid var(--border-color-light);
  padding-bottom: 4px;
}
</style>
