<template>
  <div
    class="strategy-page"
    :class="{
      'strategy-page--ai-research': showAIResearchTab,
      'strategy-page--management': showStrategyManagementTabs,
    }"
  >
    <section
      v-if="showStrategyManagementTabs"
      class="strategy-management-hero"
      data-test="strategy-management-hero"
      aria-labelledby="strategy-management-title"
    >
      <div class="strategy-management-copy">
        <span class="strategy-management-kicker">{{ t('strategy.managementHeroKicker') }}</span>
        <h1 id="strategy-management-title">
          {{ t('strategy.managementHeroTitle') }}
        </h1>
        <p>{{ t('strategy.managementHeroSubtitle') }}</p>
      </div>

      <div class="strategy-management-actions">
        <el-button
          type="primary"
          size="large"
          :aria-label="t('strategy.createStrategy')"
          @click="showCreateDialog"
        >
          <el-icon aria-hidden="true">
            <Plus />
          </el-icon>
          {{ t('strategy.createStrategy') }}
        </el-button>
      </div>

      <div class="strategy-management-metrics">
        <div
          v-for="item in strategyManagementStats"
          :key="item.key"
          class="strategy-management-metric"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </section>

    <section
      v-if="showAIResearchTab"
      class="ai-research-hero"
      data-test="ai-research-hero"
      aria-labelledby="ai-research-hero-title"
    >
      <div class="ai-research-hero-copy">
        <span class="ai-research-hero-kicker">{{ t('strategy.aiResearchHeroKicker') }}</span>
        <h1 id="ai-research-hero-title">
          {{ t('strategy.aiResearchHeroTitle') }}
        </h1>
        <p>{{ t('strategy.aiResearchHeroSubtitle') }}</p>
      </div>

      <div class="ai-research-hero-steps">
        <span
          v-for="step in aiResearchHeroSteps"
          :key="step.key"
          class="ai-research-hero-step"
        >
          <span class="ai-research-hero-step-index">{{ step.index }}</span>
          <span>{{ step.label }}</span>
        </span>
      </div>

      <div class="ai-research-hero-metrics">
        <div
          v-for="item in aiResearchHeroMetrics"
          :key="item.key"
          class="ai-research-hero-metric"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </section>

    <!-- Main tabs: Gallery / My strategies -->
    <el-tabs
      v-model="activeTab"
      type="border-card"
      class="strategy-tabs"
    >
      <!-- ========== AI Research Loop ========== -->
      <el-tab-pane
        v-if="showAIResearchTab"
        :label="t('strategy.aiResearch')"
        name="aiResearch"
      >
        <div class="ai-research-grid">
          <section class="ai-research-panel ai-research-control-panel">
            <div class="ai-research-panel-head">
              <span class="ai-research-kicker">{{ t('strategy.aiResearchControlKicker') }}</span>
              <h2>{{ t('strategy.aiResearchControlTitle') }}</h2>
              <p>{{ t('strategy.aiResearchControlSubtitle') }}</p>
            </div>

            <div
              class="ai-research-plan-bar"
              data-test="ai-research-plan-bar"
            >
              <div class="ai-research-plan-select">
                <span>投研方案</span>
                <el-select
                  v-model="aiResearchSelectedConfigProfileId"
                  class="w-full"
                  filterable
                  :loading="aiResearchConfigProfilesLoading"
                  placeholder="选择配置方案"
                  data-test="ai-research-profile-select"
                  @change="selectAIResearchConfigProfile"
                >
                  <el-option
                    v-for="profile in aiResearchConfigProfiles"
                    :key="profile.id"
                    :label="profile.name"
                    :value="profile.id"
                  >
                    <span>{{ profile.name }}</span>
                    <span class="ai-research-plan-option">
                      {{ aiResearchConfigProfileValue(profile, 'symbol') }}
                      · {{ aiResearchConfigProfileValue(profile, 'timeframe') }}
                    </span>
                  </el-option>
                </el-select>
              </div>
              <div class="ai-research-plan-summary">
                <strong>{{ aiResearchSelectedProfileSummary }}</strong>
                <span>
                  {{ aiResearchSelectedConfigProfile?.description || '方案控制标的、周期、质量门槛、回测口径和晋级设置。' }}
                </span>
              </div>
              <el-button
                type="primary"
                plain
                data-test="ai-research-config-open"
                @click="openAIResearchConfigDialog"
              >
                <el-icon aria-hidden="true">
                  <EditPen />
                </el-icon>
                配置方案
              </el-button>
            </div>

            <el-dialog
              v-model="aiResearchConfigDialogVisible"
              title="配置投研方案"
              width="1100px"
              class="ai-research-config-dialog"
              destroy-on-close
            >
              <div
                class="ai-research-config-sheet"
                data-test="ai-research-config-profiles"
              >
                <div class="ai-research-config-head">
                  <div>
                    <strong>配置表</strong>
                    <span v-if="aiResearchConfigProfileFilePath">
                      {{ aiResearchConfigProfileFilePath }}
                    </span>
                  </div>
                  <div class="ai-research-config-head-actions">
                    <el-button
                      size="small"
                      :loading="aiResearchConfigProfileImporting"
                      data-test="ai-research-config-import"
                      @click="triggerAIResearchConfigProfileImport"
                    >
                      <el-icon aria-hidden="true">
                        <Upload />
                      </el-icon>
                      导入 YAML
                    </el-button>
                    <el-button
                      size="small"
                      :loading="aiResearchConfigProfilesLoading"
                      data-test="ai-research-config-refresh"
                      @click="loadAIResearchConfigProfiles({ showError: true })"
                    >
                      <el-icon aria-hidden="true">
                        <RefreshRight />
                      </el-icon>
                      刷新
                    </el-button>
                  </div>
                </div>

                <input
                  ref="aiResearchConfigProfileFileInput"
                  class="ai-research-config-file-input"
                  type="file"
                  accept=".yaml,.yml,text/yaml,application/x-yaml"
                  @change="importAIResearchConfigProfileFile"
                >

                <el-table
                  v-loading="aiResearchConfigProfilesLoading"
                  class="ai-research-config-table"
                  :data="aiResearchConfigProfiles"
                  size="small"
                  row-key="id"
                  highlight-current-row
                  :empty-text="'暂无配置，可从当前表单新建或导入 YAML'"
                  @row-click="handleAIResearchConfigProfileRowClick"
                >
                  <el-table-column
                    label="名称"
                    min-width="150"
                  >
                    <template #default="{ row }">
                      <div class="ai-research-config-name">
                        <strong>{{ row.name }}</strong>
                        <span>{{ row.id }}</span>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="标的"
                    min-width="110"
                  >
                    <template #default="{ row }">
                      {{ aiResearchConfigProfileValue(row, 'symbol') }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="周期"
                    width="76"
                  >
                    <template #default="{ row }">
                      {{ aiResearchConfigProfileValue(row, 'timeframe') }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="Sharpe"
                    width="86"
                  >
                    <template #default="{ row }">
                      {{ aiResearchConfigProfileMetric(row, 'target_sharpe') }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="轮数"
                    width="72"
                  >
                    <template #default="{ row }">
                      {{ aiResearchConfigProfileMetric(row, 'max_iterations', 0) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="样本外"
                    width="86"
                  >
                    <template #default="{ row }">
                      {{ aiResearchConfigProfileOos(row) }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="操作"
                    width="174"
                    fixed="right"
                  >
                    <template #default="{ row }">
                      <el-button
                        link
                        size="small"
                        type="primary"
                        @click.stop="applyAIResearchConfigProfile(row)"
                      >
                        加载
                      </el-button>
                      <el-button
                        link
                        size="small"
                        type="warning"
                        :loading="aiResearchConfigProfileSaving && aiResearchSelectedConfigProfileId === row.id"
                        @click.stop="saveAIResearchConfigProfile(row.id)"
                      >
                        保存
                      </el-button>
                      <el-button
                        link
                        size="small"
                        type="danger"
                        :loading="aiResearchConfigProfileDeletingId === row.id"
                        @click.stop="deleteAIResearchConfigProfile(row)"
                      >
                        删除
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>

                <div
                  v-if="aiResearchSelectedConfigProfile"
                  class="ai-research-config-detail"
                  data-test="ai-research-config-detail"
                >
                  <div class="ai-research-config-detail-head">
                    <strong>{{ aiResearchSelectedConfigProfile.name }}</strong>
                    <span>
                      {{ aiResearchSelectedConfigProfile.description || '当前配置没有填写说明。' }}
                    </span>
                  </div>
                  <div class="ai-research-config-detail-grid">
                    <div
                      v-for="item in aiResearchSelectedConfigDetails"
                      :key="item.label"
                      class="ai-research-config-detail-item"
                    >
                      <span>{{ item.label }}</span>
                      <strong>{{ item.value }}</strong>
                    </div>
                  </div>
                  <pre
                    v-if="aiResearchSelectedConfigPromptPreview"
                    class="ai-research-config-prompt-preview"
                  >{{ aiResearchSelectedConfigPromptPreview }}</pre>
                </div>

                <div class="ai-research-config-editor">
                  <el-input
                    v-model="aiResearchConfigProfileName"
                    placeholder="配置名称"
                    data-test="ai-research-config-name"
                  />
                  <el-input
                    v-model="aiResearchConfigProfileDescription"
                    placeholder="配置说明"
                    data-test="ai-research-config-description"
                  />
                  <el-button
                    type="primary"
                    plain
                    :disabled="!aiResearchSelectedConfigProfile"
                    :loading="aiResearchConfigProfileSaving"
                    data-test="ai-research-config-save"
                    @click="saveAIResearchConfigProfile()"
                  >
                    <el-icon aria-hidden="true">
                      <EditPen />
                    </el-icon>
                    保存修改
                  </el-button>
                  <el-button
                    type="success"
                    plain
                    :loading="aiResearchConfigProfileSaving"
                    data-test="ai-research-config-create"
                    @click="createAIResearchConfigProfile"
                  >
                    <el-icon aria-hidden="true">
                      <Plus />
                    </el-icon>
                    新建配置
                  </el-button>
                  <el-button
                    type="danger"
                    plain
                    :disabled="!aiResearchSelectedConfigProfile"
                    :loading="aiResearchConfigProfileDeletingId === aiResearchSelectedConfigProfileId"
                    data-test="ai-research-config-delete"
                    @click="aiResearchSelectedConfigProfile && deleteAIResearchConfigProfile(aiResearchSelectedConfigProfile)"
                  >
                    <el-icon aria-hidden="true">
                      <Delete />
                    </el-icon>
                    删除配置
                  </el-button>
                </div>
              </div>

              <el-form
                label-position="top"
                :model="aiResearchForm"
              >
                <el-form-item label="投研方式">
                  <el-radio-group
                    v-model="aiResearchForm.workflow_mode"
                    data-test="ai-research-workflow-mode"
                  >
                    <el-radio-button value="auto">
                      自动规划
                    </el-radio-button>
                    <el-radio-button value="prompt">
                      按提示执行
                    </el-radio-button>
                  </el-radio-group>
                </el-form-item>

                <el-form-item :label="t('strategy.aiResearchPrompt')">
                  <el-input
                    v-model="aiResearchForm.prompt"
                    type="textarea"
                    :rows="5"
                    :placeholder="t('strategy.aiResearchPromptPlaceholder')"
                    data-test="ai-research-prompt-config"
                  />
                  <div class="ai-research-prompt-tools">
                    <el-button
                      size="small"
                      type="primary"
                      data-test="ai-research-generate-prompt-config"
                      @click="generateAIResearchPrompt"
                    >
                      <el-icon
                        class="mr-1"
                        aria-hidden="true"
                      >
                        <MagicStick />
                      </el-icon>
                      {{ t('strategy.aiResearchGeneratePrompt') }}
                    </el-button>
                  </div>
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
                  <el-form-item :label="t('strategy.aiResearchAnnualDays')">
                    <el-input-number
                      v-model="aiResearchForm.annual_days"
                      :min="1"
                      :max="366"
                      :step="1"
                      class="w-full"
                      data-test="ai-research-annual-days"
                    />
                  </el-form-item>
                  <el-form-item :label="t('strategy.aiResearchCalcMethod')">
                    <el-select
                      v-model="aiResearchForm.calc_method"
                      class="w-full"
                      data-test="ai-research-calc-method"
                    >
                      <el-option
                        label="simple"
                        value="simple"
                      />
                      <el-option
                        label="log"
                        value="log"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item :label="t('strategy.aiResearchWeightMode')">
                    <el-select
                      v-model="aiResearchForm.weight_mode"
                      class="w-full"
                      data-test="ai-research-weight-mode"
                    >
                      <el-option
                        label="equal"
                        value="equal"
                      />
                      <el-option
                        label="value"
                        value="value"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item :label="t('strategy.aiResearchGroupName')">
                    <el-input
                      v-model="aiResearchForm.group_name"
                      data-test="ai-research-group-name"
                    />
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
                      :placeholder="PAPER_GATEWAY_CONFIG_PLACEHOLDER"
                      data-test="ai-research-gateway-config"
                    />
                  </el-form-item>
                  <el-form-item label="实盘工作区名称">
                    <el-input
                      v-model="aiResearchForm.live_workspace_name"
                      clearable
                      placeholder="自动命名"
                      data-test="ai-research-live-workspace-name"
                    />
                  </el-form-item>
                  <el-form-item label="实盘工作区 ID">
                    <el-input
                      v-model="aiResearchForm.live_trading_workspace_id"
                      clearable
                      placeholder="可选，复用已有实盘工作区"
                      data-test="ai-research-live-workspace-id"
                    />
                  </el-form-item>
                  <el-form-item label="实盘网关配置 JSON">
                    <el-input
                      v-model="aiResearchForm.live_gateway_config_json"
                      type="textarea"
                      :rows="3"
                      :placeholder="LIVE_GATEWAY_CONFIG_PLACEHOLDER"
                      data-test="ai-research-live-gateway-config"
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
                  <el-form-item label="晋级必须通过样本外">
                    <el-checkbox
                      v-model="aiResearchForm.require_out_of_sample_validation"
                      :disabled="!aiResearchForm.out_of_sample_validation"
                      data-test="ai-research-oos-required"
                    >
                      达标后先完成样本外验证
                    </el-checkbox>
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
                  <el-form-item label="数据预检">
                    <div class="ai-research-precheck-control">
                      <el-button
                        size="small"
                        :loading="aiResearchPrecheckLoading"
                        data-test="ai-research-data-precheck"
                        @click="runAIResearchDataPrecheck"
                      >
                        <el-icon aria-hidden="true">
                          <RefreshRight />
                        </el-icon>
                        运行预检
                      </el-button>
                      <el-tag
                        v-if="aiResearchPrecheckResult || aiResearchPrecheckError"
                        size="small"
                        :type="aiResearchPrecheckTagType"
                      >
                        {{ aiResearchPrecheckSummary }}
                      </el-tag>
                    </div>
                  </el-form-item>
                  <el-form-item label="稳健性验证">
                    <div class="ai-research-gate-control">
                      <el-checkbox
                        v-model="aiResearchForm.robustness_validation"
                        data-test="ai-research-robustness-enabled"
                      />
                      <el-input-number
                        v-model="aiResearchForm.min_robustness_score"
                        :disabled="!aiResearchForm.robustness_validation"
                        :min="0"
                        :max="100"
                        :step="5"
                        class="w-full"
                        data-test="ai-research-robustness-score"
                      />
                    </div>
                  </el-form-item>
                  <el-form-item label="晋级必须通过稳健性">
                    <el-checkbox
                      v-model="aiResearchForm.require_robustness_validation"
                      :disabled="!aiResearchForm.robustness_validation"
                      data-test="ai-research-robustness-required"
                    >
                      达标后先完成稳健性验证
                    </el-checkbox>
                  </el-form-item>
                  <el-form-item label="稳健性方法">
                    <el-checkbox-group
                      v-model="aiResearchForm.robustness_methods"
                      :disabled="!aiResearchForm.robustness_validation"
                    >
                      <el-checkbox label="monte_carlo">
                        Monte Carlo
                      </el-checkbox>
                      <el-checkbox label="parameter_sensitivity">
                        参数扰动
                      </el-checkbox>
                      <el-checkbox label="walk_forward">
                        Walk Forward
                      </el-checkbox>
                    </el-checkbox-group>
                  </el-form-item>
                  <el-form-item label="Monte Carlo 次数">
                    <el-input-number
                      v-model="aiResearchForm.robustness_monte_carlo_iterations"
                      :disabled="!aiResearchForm.robustness_validation"
                      :min="50"
                      :max="5000"
                      :step="50"
                      class="w-full"
                    />
                  </el-form-item>
                  <el-form-item label="最少模拟观察天数">
                    <el-input-number
                      v-model="aiResearchForm.min_paper_trading_days"
                      :min="0"
                      :max="365"
                      :step="1"
                      class="w-full"
                      data-test="ai-research-min-paper-days"
                    />
                  </el-form-item>
                </div>
              </el-form>
            </el-dialog>

            <el-form
              label-position="top"
              :model="aiResearchForm"
              class="ai-research-main-form"
            >
              <el-form-item :label="t('strategy.aiResearchPrompt')">
                <el-input
                  v-model="aiResearchForm.prompt"
                  type="textarea"
                  :rows="7"
                  :placeholder="t('strategy.aiResearchPromptPlaceholder')"
                  data-test="ai-research-prompt"
                />
                <div class="ai-research-prompt-tools">
                  <el-button
                    size="small"
                    type="primary"
                    data-test="ai-research-generate-prompt"
                    @click="generateAIResearchPrompt"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <MagicStick />
                    </el-icon>
                    {{ t('strategy.aiResearchGeneratePrompt') }}
                  </el-button>
                </div>
              </el-form-item>
            </el-form>

            <div
              class="ai-research-mandate"
              data-test="ai-research-mandate"
            >
              <div class="ai-research-mandate-head">
                <div>
                  <span class="ai-research-kicker">投资需求</span>
                  <strong>{{ aiResearchMandate?.objective || '待确认' }}</strong>
                </div>
                <el-tag
                  size="small"
                  :type="aiResearchMandateConfirmed ? 'success' : 'warning'"
                >
                  {{ aiResearchMandateConfirmed ? '已确认' : '待确认' }}
                </el-tag>
              </div>
              <div class="ai-research-mandate-actions">
                <el-button
                  size="small"
                  plain
                  :loading="aiResearchMandateLoading"
                  data-test="ai-research-parse-mandate"
                  @click="parseAIResearchMandate()"
                >
                  解析需求
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  :disabled="!aiResearchMandate"
                  data-test="ai-research-confirm-mandate"
                  @click="confirmAIResearchMandate"
                >
                  确认需求
                </el-button>
              </div>
              <div
                v-if="aiResearchMandate"
                class="ai-research-mandate-grid"
              >
                <span
                  v-for="item in aiResearchMandateDetails"
                  :key="item.key"
                >
                  <small>{{ item.label }}</small>
                  <strong>{{ item.value }}</strong>
                </span>
              </div>
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
              <el-button
                v-if="canContinueAIResearchTask"
                type="warning"
                plain
                data-test="ai-research-continue-task"
                :loading="aiResearchRunning"
                @click="continueAIResearchFromTaskSnapshot"
              >
                从任务继续
              </el-button>
              <el-button
                v-if="canRetryAIResearchTask"
                type="warning"
                plain
                data-test="ai-research-retry-task"
                :loading="aiResearchRunning"
                @click="retryAIResearchFromTaskSnapshot"
              >
                重新启动任务
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
                <template v-else-if="aiResearchCancelledBacktestTaskId">
                  已取消回测 {{ aiResearchCancelledBacktestTaskId }}
                </template>
              </el-tag>
            </div>
            <div
              v-if="aiResearchTaskId"
              class="ai-research-task-progress"
              data-test="ai-research-task-progress"
            >
              <strong>任务进度</strong>
              <span
                v-if="aiResearchTaskContinuationSummary"
                data-test="ai-research-task-continuation"
              >
                继续来源 {{ aiResearchTaskContinuationSummary }}
              </span>
              <span>阶段 {{ aiResearchTaskStageLabel }}</span>
              <span>{{ formatTaskProgress(aiResearchTaskProgress) }}</span>
              <span v-if="aiResearchTaskIteration">第 {{ aiResearchTaskIteration }} 轮</span>
              <span v-if="aiResearchBacktestTaskId">回测 {{ aiResearchBacktestTaskId }}</span>
              <span v-else-if="aiResearchCancelledBacktestTaskId">
                已取消回测 {{ aiResearchCancelledBacktestTaskId }}
              </span>
              <span v-if="aiResearchTaskPaperStatusText">{{ aiResearchTaskPaperStatusText }}</span>
              <span v-if="aiResearchTaskPaperUnitId">模拟单元 {{ aiResearchTaskPaperUnitId }}</span>
              <span v-if="aiResearchTaskLiveStatusText">{{ aiResearchTaskLiveStatusText }}</span>
              <span v-if="aiResearchTaskLiveUnitId">实盘单元 {{ aiResearchTaskLiveUnitId }}</span>
              <span v-if="aiResearchTaskMessage">{{ aiResearchTaskMessage }}</span>
              <span v-if="aiResearchTaskLatestIteration">
                最近{{ taskLatestIterationLabel(aiResearchTaskLatestIteration) }}
                Sharpe {{ formatMetric(taskLatestIterationMetric(aiResearchTaskLatestIteration, 'sharpe_ratio', 'sharpe')) }}
                交易 {{ formatMetric(taskLatestIterationMetric(aiResearchTaskLatestIteration, 'total_trades', 'trades')) }}
              </span>
              <span
                v-if="aiResearchTaskBestIterationDisplay"
                data-test="ai-research-task-best-iteration"
              >
                当前最佳{{ taskLatestIterationLabel(aiResearchTaskBestIterationDisplay) }}
                Sharpe {{ formatMetric(taskLatestIterationMetric(aiResearchTaskBestIterationDisplay, 'sharpe_ratio', 'sharpe')) }}
                交易 {{ formatMetric(taskLatestIterationMetric(aiResearchTaskBestIterationDisplay, 'total_trades', 'trades')) }}
              </span>
              <span
                v-if="taskLatestIterationProgress(aiResearchTaskLatestIteration)"
                class="ai-research-task-iteration-progress"
                data-test="ai-research-task-iteration-progress"
              >
                <el-tag
                  size="small"
                  :type="iterationProgressTagType(taskLatestIterationProgress(aiResearchTaskLatestIteration)?.status)"
                >
                  {{ iterationProgressLabel(taskLatestIterationProgress(aiResearchTaskLatestIteration)?.status) }}
                </el-tag>
                <template v-if="taskLatestIterationProgress(aiResearchTaskLatestIteration)?.previous_iteration">
                  对比第 {{ taskLatestIterationProgress(aiResearchTaskLatestIteration)?.previous_iteration }} 轮
                </template>
                <template v-if="iterationProgressDeltaText(taskLatestIterationProgress(aiResearchTaskLatestIteration), 'sharpe_delta')">
                  Sharpe {{ iterationProgressDeltaText(taskLatestIterationProgress(aiResearchTaskLatestIteration), 'sharpe_delta') }}
                </template>
              </span>
              <span
                v-if="aiResearchTaskLatestDiagnostics"
                class="ai-research-task-diagnostics"
                data-test="ai-research-task-latest-diagnostics"
              >
                <strong>最近诊断</strong>
                <span v-if="aiResearchTaskLatestDiagnostics.summary">
                  {{ aiResearchTaskLatestDiagnostics.summary }}
                </span>
                <span v-if="aiResearchTaskLatestDiagnostics.generationText">
                  {{ aiResearchTaskLatestDiagnostics.generationText }}
                </span>
                <span
                  v-for="gap in aiResearchTaskLatestDiagnostics.gateGaps"
                  :key="`task-gap-${gap.key || gap.label}`"
                  class="ai-research-warning-text"
                >
                  差距 {{ gateGapText(gap) }}
                </span>
                <span
                  v-for="failure in aiResearchTaskLatestDiagnostics.failures"
                  :key="`task-failure-${failure}`"
                  class="ai-research-warning-text"
                >
                  {{ failure }}
                </span>
                <span
                  v-for="plan in aiResearchTaskLatestDiagnostics.improvementPlan"
                  :key="`task-plan-${plan}`"
                >
                  改稿 {{ plan }}
                </span>
                <span
                  v-for="action in aiResearchTaskLatestDiagnostics.nextActions"
                  :key="`task-action-${action}`"
                >
                  下一步 {{ action }}
                </span>
              </span>
              <span
                v-if="aiResearchTaskPipelineSteps.length"
                class="ai-research-task-pipeline"
                data-test="ai-research-task-pipeline"
              >
                <span
                  v-for="step in aiResearchTaskPipelineSteps"
                  :key="step.key"
                >
                  {{ step.label || aiResearchStageLabel(step.key) }}
                  {{ pipelineStepStatusLabel(step.status) }}
                  <template v-if="pipelineStepDetailText(step, aiResearchTaskPipeline)">
                    {{ pipelineStepDetailText(step, aiResearchTaskPipeline) }}
                  </template>
                </span>
              </span>
              <span
                v-if="aiResearchTaskPromotionAudit.length"
                class="ai-research-task-promotion-audit"
                data-test="ai-research-task-promotion-audit"
              >
                <strong>晋级审计</strong>
                <span
                  v-for="item in aiResearchTaskPromotionAudit"
                  :key="item.key"
                >
                  {{ item.label }} {{ pipelineStepStatusLabel(item.status) }}
                  <template v-if="item.evidence">
                    {{ item.evidence }}
                  </template>
                </span>
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
          </section>

          <section class="ai-research-panel ai-research-result">
            <div class="ai-research-panel-head">
              <span class="ai-research-kicker">{{ t('strategy.aiResearchResultKicker') }}</span>
              <h2>{{ t('strategy.aiResearchResultTitle') }}</h2>
              <p>{{ t('strategy.aiResearchResultSubtitle') }}</p>
            </div>
            <div
              v-if="aiResearchSelectedConfigProfile"
              class="ai-research-result-context"
              data-test="ai-research-result-context"
            >
              <strong>当前方案 {{ aiResearchSelectedConfigProfile.name }}</strong>
              <span>{{ aiResearchSelectedProfileSummary }}</span>
            </div>
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
                <div
                  v-if="aiResearchCurrentContinuationSummary"
                  data-test="ai-research-current-continuation"
                >
                  <span>继续来源</span>
                  <strong>{{ aiResearchCurrentContinuationSummary }}</strong>
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
                  v-if="canBuildLiveHandoffFromCurrentResult"
                  size="small"
                  type="success"
                  plain
                  :loading="aiResearchLiveHandoffLoadingRunId === aiResearchResult.run_id"
                  data-test="ai-research-current-live-handoff-button"
                  @click="buildLiveHandoffFromCurrentResult"
                >
                  <el-icon
                    class="mr-1"
                    aria-hidden="true"
                  >
                    <Link />
                  </el-icon>
                  实盘交接包
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
                v-if="aiResearchCurrentLiveHandoff"
                class="ai-research-paper-review ai-research-live-handoff"
                data-test="ai-research-current-live-handoff"
              >
                <div class="ai-research-paper-review-head">
                  <el-tag
                    size="small"
                    :type="aiResearchCurrentLiveHandoff.ready_for_live ? 'success' : 'danger'"
                  >
                    {{ liveHandoffStatusLabel(aiResearchCurrentLiveHandoff.status) }}
                  </el-tag>
                  <span>
                    {{ aiResearchCurrentLiveHandoff.approval_required ? '需要人工审批' : '无需额外审批' }}
                  </span>
                </div>
                <div class="ai-research-paper-review-rules">
                  <span>标的 {{ aiResearchCurrentLiveHandoff.symbol }}</span>
                  <span>Sharpe {{ formatMetric(aiResearchCurrentLiveHandoff.best_sharpe) }}</span>
                  <span v-if="aiResearchCurrentLiveHandoff.expires_at">
                    候选有效期 {{ formatDateTime(aiResearchCurrentLiveHandoff.expires_at) }}
                  </span>
                  <span v-if="Object.keys(aiResearchCurrentLiveHandoff.asset_specs || {}).length">
                    资产规格已随交接包固化
                  </span>
                </div>
                <div
                  v-if="aiResearchCurrentLiveHandoff.approvals_required.length"
                  class="ai-research-live-readiness"
                  data-test="ai-research-current-live-handoff-approvals"
                >
                  <strong>审批项</strong>
                  <span
                    v-for="item in aiResearchCurrentLiveHandoff.approvals_required"
                    :key="item.key"
                  >
                    {{ item.label }} {{ liveReadinessStatusLabel(item.status) }}：{{ item.action || item.evidence }}
                  </span>
                </div>
                <div
                  v-if="aiResearchCurrentLiveHandoff.deployment_blockers.length"
                  class="ai-research-paper-review-actions"
                  data-test="ai-research-current-live-handoff-blockers"
                >
                  <span
                    v-for="blocker in aiResearchCurrentLiveHandoff.deployment_blockers"
                    :key="blocker"
                  >
                    {{ blocker }}
                  </span>
                </div>
                <div
                  v-if="aiResearchCurrentLiveHandoff.approval"
                  class="ai-research-live-readiness"
                  data-test="ai-research-current-live-handoff-approval"
                >
                  <strong>审批结果</strong>
                  <span>
                    {{ liveHandoffApprovalLabel(aiResearchCurrentLiveHandoff) }}
                    {{ aiResearchCurrentLiveHandoff.approval.decided_by }}
                    {{ formatDateTime(aiResearchCurrentLiveHandoff.approval.decided_at) }}
                  </span>
                  <span v-if="aiResearchCurrentLiveHandoff.approval.comment">
                    {{ aiResearchCurrentLiveHandoff.approval.comment }}
                  </span>
                </div>
                <div
                  v-if="canApproveLiveHandoff(aiResearchCurrentLiveHandoff)"
                  class="ai-research-paper-review-actions"
                  data-test="ai-research-current-live-handoff-actions"
                >
                  <el-button
                    size="small"
                    type="success"
                    plain
                    :loading="aiResearchLiveHandoffApprovingRunId === `${aiResearchCurrentLiveHandoff.run_id}:approved`"
                    data-test="ai-research-current-live-handoff-approve"
                    @click="approveCurrentLiveHandoff('approved')"
                  >
                    批准交接
                  </el-button>
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    :loading="aiResearchLiveHandoffApprovingRunId === `${aiResearchCurrentLiveHandoff.run_id}:rejected`"
                    data-test="ai-research-current-live-handoff-reject"
                    @click="approveCurrentLiveHandoff('rejected')"
                  >
                    驳回
                  </el-button>
                </div>
                <div
                  v-if="isLiveTradingPreparedForRecord(aiResearchResult.run_record)"
                  class="ai-research-live-readiness"
                  data-test="ai-research-current-live-prepare-status"
                >
                  <strong>实盘单元</strong>
                  <span>{{ liveTradingPrepareSummary(aiResearchResult.run_record) }}</span>
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    data-test="ai-research-current-open-live"
                    @click="openLiveWorkspaceFromCurrentResult"
                  >
                    打开实盘工作区
                  </el-button>
                </div>
                <div
                  v-else-if="aiResearchResult.run_record && canPrepareLiveTradingFromRecord(aiResearchResult.run_record)"
                  class="ai-research-paper-review-actions"
                  data-test="ai-research-current-live-prepare-actions"
                >
                  <el-button
                    size="small"
                    type="success"
                    plain
                    :loading="aiResearchLiveTradingPreparingRunId === aiResearchResult.run_id"
                    data-test="ai-research-current-live-prepare"
                    @click="prepareLiveTradingFromCurrentResult"
                  >
                    准备实盘单元
                  </el-button>
                </div>
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
                    {{ rule.label }} {{ paperReviewRuleStatusLabel(rule.status) }}
                    {{ formatMetric(rule.actual) }} / {{ formatMetric(rule.threshold) }}
                    {{ paperReviewRuleGapText(rule) }}
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
                  v-if="aiResearchCurrentPaperReviewLock"
                  class="ai-research-live-readiness"
                  data-test="ai-research-current-paper-review-lock"
                >
                  <strong>模拟单元保护</strong>
                  <span>{{ paperReviewLockSummary(aiResearchCurrentPaperReviewLock) }}</span>
                  <span v-if="aiResearchCurrentPaperReviewLock.reviewed_at">
                    复核时间 {{ formatDateTime(aiResearchCurrentPaperReviewLock.reviewed_at) }}
                  </span>
                  <span v-if="paperReviewLockStopResultText(aiResearchCurrentPaperReviewLock)">
                    停止结果 {{ paperReviewLockStopResultText(aiResearchCurrentPaperReviewLock) }}
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
                    <small v-if="pipelineStepDetailText(step, aiResearchResult.pipeline)">
                      {{ pipelineStepDetailText(step, aiResearchResult.pipeline) }}
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
                class="ai-research-timeline"
                data-test="ai-research-timeline"
              >
                <div class="ai-research-section-head">
                  <strong>投研时间线</strong>
                  <el-tag
                    size="small"
                    type="info"
                  >
                    {{ aiResearchTimeline.length }}
                  </el-tag>
                </div>
                <div
                  v-if="aiResearchTimelineLoading"
                  class="ai-research-history-empty"
                >
                  {{ t('common.loading') }}
                </div>
                <el-timeline v-else-if="aiResearchTimeline.length">
                  <el-timeline-item
                    v-for="event in aiResearchTimeline"
                    :key="event.id"
                    :timestamp="formatDateTime(event.created_at)"
                    placement="top"
                  >
                    <div class="ai-research-timeline-item">
                      <div>
                        <strong>{{ aiResearchStageLabel(event.stage) }}</strong>
                        <el-tag
                          size="small"
                          :type="aiResearchEventTagType(event.status)"
                        >
                          {{ pipelineStepStatusLabel(event.status) || event.status }}
                        </el-tag>
                        <span v-if="event.iteration">第 {{ event.iteration }} 轮</span>
                      </div>
                      <p v-if="event.summary">
                        {{ event.summary }}
                      </p>
                      <span
                        v-if="event.error"
                        class="ai-research-warning-text"
                      >
                        {{ event.error }}
                      </span>
                    </div>
                  </el-timeline-item>
                </el-timeline>
                <div
                  v-else
                  class="ai-research-history-empty"
                >
                  暂无时间线记录
                </div>
              </div>

              <div
                class="ai-research-versions"
                data-test="ai-research-versions"
              >
                <div class="ai-research-section-head">
                  <strong>策略版本</strong>
                  <div class="ai-research-version-compare-tools">
                    <el-select
                      v-model="aiResearchSelectedVersionIds"
                      multiple
                      collapse-tags
                      collapse-tags-tooltip
                      :multiple-limit="2"
                      size="small"
                      placeholder="选择两个版本"
                    >
                      <el-option
                        v-for="version in aiResearchVersions"
                        :key="version.id"
                        :label="`${version.version_name} · ${version.strategy_name || '策略'}`"
                        :value="version.id"
                      />
                    </el-select>
                    <el-button
                      size="small"
                      plain
                      :disabled="!aiResearchCanCompareVersions"
                      :loading="aiResearchVersionCompareLoading"
                      data-test="ai-research-compare-versions"
                      @click="compareSelectedAIResearchVersions"
                    >
                      对比版本
                    </el-button>
                  </div>
                </div>
                <el-table
                  v-loading="aiResearchVersionsLoading"
                  :data="aiResearchVersions"
                  size="small"
                  class="ai-research-version-table"
                  :empty-text="'暂无版本记录'"
                >
                  <el-table-column
                    prop="version_name"
                    label="版本"
                    width="90"
                  />
                  <el-table-column
                    label="修改原因"
                    min-width="240"
                  >
                    <template #default="{ row }">
                      <span>{{ row.ai_rationale || row.change_summary || '-' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="质量"
                    width="100"
                  >
                    <template #default="{ row }">
                      <el-tag
                        size="small"
                        :type="aiResearchVersionStatusTagType(row.quality_gate_status)"
                      >
                        {{ row.quality_gate_status }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="指标"
                    min-width="240"
                  >
                    <template #default="{ row }">
                      <span class="ai-research-version-metrics">
                        <span
                          v-for="key in aiResearchVersionMetricKeys"
                          :key="key"
                        >
                          {{ aiResearchVersionMetricLabel(key) }}
                          {{ aiResearchVersionMetric(row, key) }}
                        </span>
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="操作"
                    width="110"
                  >
                    <template #default="{ row }">
                      <el-button
                        size="small"
                        link
                        data-test="ai-research-view-version-code"
                        @click="viewAIResearchVersionCode(row)"
                      >
                        查看代码
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div
                  v-if="aiResearchVersionCompare"
                  class="ai-research-version-compare"
                  data-test="ai-research-version-compare"
                >
                  <strong>{{ aiResearchVersionCompare.summary }}</strong>
                  <pre v-if="aiResearchVersionCompare.code_diff">{{ aiResearchVersionCompare.code_diff }}</pre>
                </div>
              </div>

              <div
                v-if="aiResearchPromotionAudit.length"
                class="ai-research-promotion-audit"
                data-test="ai-research-promotion-audit"
              >
                <strong>晋级审计</strong>
                <div class="ai-research-promotion-audit-items">
                  <span
                    v-for="item in aiResearchPromotionAudit"
                    :key="item.key"
                    class="ai-research-promotion-audit-item"
                  >
                    <span>{{ item.label }}</span>
                    <el-tag
                      size="small"
                      :type="pipelineStepTagType(item.status)"
                    >
                      {{ pipelineStepStatusLabel(item.status) }}
                    </el-tag>
                    <small>{{ item.evidence }}</small>
                    <small
                      v-if="item.action"
                      class="ai-research-muted-text"
                    >
                      {{ item.action }}
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
                v-if="aiResearchBestDiagnostics"
                class="ai-research-diagnostics"
                data-test="ai-research-best-diagnostics"
              >
                <div class="ai-research-diagnostics-head">
                  <strong>投研诊断</strong>
                  <el-tag
                    v-if="aiResearchBestDiagnostics.promotionReady !== null"
                    size="small"
                    :type="aiResearchBestDiagnostics.promotionReady ? 'success' : 'warning'"
                  >
                    {{ aiResearchBestDiagnostics.promotionReady ? '可晋级' : '需改进' }}
                  </el-tag>
                </div>
                <p v-if="aiResearchBestDiagnostics.summary">
                  {{ aiResearchBestDiagnostics.summary }}
                </p>
                <div class="ai-research-diagnostics-items">
                  <span v-if="aiResearchBestDiagnostics.generationText">
                    {{ aiResearchBestDiagnostics.generationText }}
                  </span>
                  <span
                    v-for="category in aiResearchBestDiagnostics.failureCategories"
                    :key="`category-${category}`"
                  >
                    问题 {{ category }}
                  </span>
                  <span
                    v-for="weakness in aiResearchBestDiagnostics.weaknesses"
                    :key="`weakness-${weakness}`"
                    class="ai-research-warning-text"
                  >
                    {{ weakness }}
                  </span>
                  <span
                    v-for="gap in aiResearchBestDiagnostics.gateGaps"
                    :key="`best-gap-${gap.key || gap.label}`"
                    class="ai-research-warning-text"
                  >
                    差距 {{ gateGapText(gap) }}
                  </span>
                  <span
                    v-for="strength in aiResearchBestDiagnostics.strengths"
                    :key="`strength-${strength}`"
                  >
                    {{ strength }}
                  </span>
                  <span
                    v-for="plan in aiResearchBestDiagnostics.improvementPlan"
                    :key="`plan-${plan}`"
                  >
                    {{ plan }}
                  </span>
                </div>
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
                    {{ outOfSampleStatusLabel(aiResearchOutOfSampleValidation.status) }}
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
                  <div
                    v-if="researchIterationBacktestSummary(item).length"
                    class="ai-research-backtest-summary"
                    data-test="ai-research-iteration-backtest-summary"
                  >
                    <strong>回测结果</strong>
                    <span
                      v-for="metric in researchIterationBacktestSummary(item)"
                      :key="metric.key"
                    >
                      {{ metric.label }} {{ metric.value }}
                    </span>
                  </div>
                  <div
                    v-if="iterationProgress(item)"
                    class="ai-research-iteration-progress"
                    data-test="ai-research-iteration-progress"
                  >
                    <el-tag
                      size="small"
                      :type="iterationProgressTagType(iterationProgress(item)?.status)"
                    >
                      {{ iterationProgressLabel(iterationProgress(item)?.status) }}
                    </el-tag>
                    <span v-if="iterationProgress(item)?.previous_iteration">
                      对比第 {{ iterationProgress(item)?.previous_iteration }} 轮
                    </span>
                    <span v-if="iterationProgressDeltaText(iterationProgress(item), 'sharpe_delta')">
                      Sharpe {{ iterationProgressDeltaText(iterationProgress(item), 'sharpe_delta') }}
                    </span>
                    <span v-if="iterationProgressDeltaText(iterationProgress(item), 'quality_score_delta')">
                      质量分 {{ iterationProgressDeltaText(iterationProgress(item), 'quality_score_delta') }}
                    </span>
                    <span v-if="iterationProgress(item)?.summary">
                      {{ iterationProgress(item)?.summary }}
                    </span>
                  </div>
                  <p
                    v-if="item.failure_reason"
                    class="ai-research-warning"
                  >
                    {{ item.failure_reason }}
                  </p>
                  <ul
                    v-if="item.quality_gate_failures?.length"
                    class="ai-research-notes ai-research-warning-list"
                    data-test="ai-research-iteration-failures"
                  >
                    <li
                      v-for="failure in item.quality_gate_failures"
                      :key="failure"
                    >
                      {{ failure }}
                    </li>
                  </ul>
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
                        {{ outOfSampleStatusLabel(iterationOutOfSampleValidation(item)?.status) }}
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
              :description="aiResearchNoResultDescription"
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
                  {{ aiResearchVisibleRuns.length }}
                </el-tag>
              </div>

              <div
                v-if="aiResearchRunsLoading"
                class="ai-research-history-empty"
              >
                {{ t('common.loading') }}
              </div>
              <div
                v-else-if="aiResearchVisibleRuns.length"
                class="ai-research-history-list"
              >
                <div
                  v-for="record in aiResearchVisibleRuns"
                  :key="record.run_id"
                  class="ai-research-history-item"
                >
                  <button
                    type="button"
                    class="ai-research-history-select"
                    @click="selectAIResearchRunRecord(record)"
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
                      <span
                        v-if="continuationSummaryForRecord(record)"
                        data-test="ai-research-history-continuation"
                      >
                        继续来源 {{ continuationSummaryForRecord(record) }}
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
                    v-if="canBuildLiveHandoffFromRecord(record)"
                    size="small"
                    type="success"
                    plain
                    :loading="aiResearchLiveHandoffLoadingRunId === record.run_id"
                    data-test="ai-research-history-live-handoff"
                    @click="buildLiveHandoffFromResearchRecord(record)"
                  >
                    <el-icon
                      class="mr-1"
                      aria-hidden="true"
                    >
                      <Link />
                    </el-icon>
                    实盘交接包
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
                        {{ rule.label }} {{ paperReviewRuleStatusLabel(rule.status) }}
                        {{ formatMetric(rule.actual) }} / {{ formatMetric(rule.threshold) }}
                        {{ paperReviewRuleGapText(rule) }}
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
                      v-if="paperReviewLockForRecord(record)"
                      class="ai-research-live-readiness"
                      data-test="ai-research-paper-review-lock"
                    >
                      <strong>模拟单元保护</strong>
                      <span>{{ paperReviewLockSummary(paperReviewLockForRecord(record)) }}</span>
                      <span v-if="paperReviewLockForRecord(record)?.reviewed_at">
                        复核时间 {{ formatDateTime(paperReviewLockForRecord(record)?.reviewed_at) }}
                      </span>
                      <span v-if="paperReviewLockStopResultText(paperReviewLockForRecord(record))">
                        停止结果 {{ paperReviewLockStopResultText(paperReviewLockForRecord(record)) }}
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
                  <div
                    v-if="liveHandoffForRecord(record)"
                    class="ai-research-paper-review ai-research-live-handoff"
                    data-test="ai-research-history-live-handoff-panel"
                  >
                    <div class="ai-research-paper-review-head">
                      <el-tag
                        size="small"
                        :type="liveHandoffForRecord(record)?.ready_for_live ? 'success' : 'danger'"
                      >
                        {{ liveHandoffStatusLabel(liveHandoffForRecord(record)?.status) }}
                      </el-tag>
                      <span>
                        {{ liveHandoffForRecord(record)?.approval_required ? '需要人工审批' : '无需额外审批' }}
                      </span>
                    </div>
                    <div class="ai-research-paper-review-rules">
                      <span>标的 {{ liveHandoffForRecord(record)?.symbol }}</span>
                      <span>Sharpe {{ formatMetric(liveHandoffForRecord(record)?.best_sharpe) }}</span>
                      <span v-if="liveHandoffForRecord(record)?.expires_at">
                        候选有效期 {{ formatDateTime(liveHandoffForRecord(record)?.expires_at) }}
                      </span>
                      <span v-if="Object.keys(liveHandoffForRecord(record)?.asset_specs || {}).length">
                        资产规格已随交接包固化
                      </span>
                    </div>
                    <div
                      v-if="liveHandoffForRecord(record)?.approvals_required.length"
                      class="ai-research-live-readiness"
                      data-test="ai-research-history-live-handoff-approvals"
                    >
                      <strong>审批项</strong>
                      <span
                        v-for="item in liveHandoffForRecord(record)?.approvals_required ?? []"
                        :key="item.key"
                      >
                        {{ item.label }} {{ liveReadinessStatusLabel(item.status) }}：{{ item.action || item.evidence }}
                      </span>
                    </div>
                    <div
                      v-if="liveHandoffForRecord(record)?.deployment_blockers.length"
                      class="ai-research-paper-review-actions"
                      data-test="ai-research-history-live-handoff-blockers"
                    >
                      <span
                        v-for="blocker in liveHandoffForRecord(record)?.deployment_blockers ?? []"
                        :key="blocker"
                      >
                        {{ blocker }}
                      </span>
                    </div>
                    <div
                      v-if="liveHandoffForRecord(record)?.approval"
                      class="ai-research-live-readiness"
                      data-test="ai-research-history-live-handoff-approval"
                    >
                      <strong>审批结果</strong>
                      <span>
                        {{ liveHandoffApprovalLabel(liveHandoffForRecord(record)) }}
                        {{ liveHandoffForRecord(record)?.approval?.decided_by }}
                        {{ formatDateTime(liveHandoffForRecord(record)?.approval?.decided_at) }}
                      </span>
                      <span v-if="liveHandoffForRecord(record)?.approval?.comment">
                        {{ liveHandoffForRecord(record)?.approval?.comment }}
                      </span>
                    </div>
                    <div
                      v-if="canApproveLiveHandoff(liveHandoffForRecord(record))"
                      class="ai-research-paper-review-actions"
                      data-test="ai-research-history-live-handoff-actions"
                    >
                      <el-button
                        size="small"
                        type="success"
                        plain
                        :loading="aiResearchLiveHandoffApprovingRunId === `${record.run_id}:approved`"
                        data-test="ai-research-history-live-handoff-approve"
                        @click="approveLiveHandoffFromResearchRecord(record, 'approved')"
                      >
                        批准交接
                      </el-button>
                      <el-button
                        size="small"
                        type="danger"
                        plain
                        :loading="aiResearchLiveHandoffApprovingRunId === `${record.run_id}:rejected`"
                        data-test="ai-research-history-live-handoff-reject"
                        @click="approveLiveHandoffFromResearchRecord(record, 'rejected')"
                      >
                        驳回
                      </el-button>
                    </div>
                    <div
                      v-if="isLiveTradingPreparedForRecord(record)"
                      class="ai-research-live-readiness"
                      data-test="ai-research-history-live-prepare-status"
                    >
                      <strong>实盘单元</strong>
                      <span>{{ liveTradingPrepareSummary(record) }}</span>
                      <el-button
                        size="small"
                        type="primary"
                        plain
                        data-test="ai-research-history-open-live"
                        @click="openLiveWorkspaceFromRecord(record)"
                      >
                        打开实盘工作区
                      </el-button>
                    </div>
                    <div
                      v-else-if="canPrepareLiveTradingFromRecord(record)"
                      class="ai-research-paper-review-actions"
                      data-test="ai-research-history-live-prepare-actions"
                    >
                      <el-button
                        size="small"
                        type="success"
                        plain
                        :loading="aiResearchLiveTradingPreparingRunId === record.run_id"
                        data-test="ai-research-history-live-prepare"
                        @click="prepareLiveTradingFromResearchRecord(record)"
                      >
                        准备实盘单元
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
              <div
                v-else
                class="ai-research-history-empty"
              >
                {{ aiResearchNoResultDescription }}
              </div>
            </div>
          </section>
        </div>
      </el-tab-pane>

      <!-- ========== Gallery ========== -->
      <el-tab-pane
        v-if="showStrategyManagementTabs"
        :label="t('strategy.gallery')"
        name="gallery"
      >
        <section class="strategy-library-panel">
          <div class="strategy-panel-head">
            <div>
              <span>{{ t('strategy.searchAndFilter') }}</span>
              <h2>{{ t('strategy.gallery') }}</h2>
            </div>
            <el-tag
              effect="plain"
              round
            >
              {{ t('strategy.customCount', { count: filteredTemplates.length }) }}
            </el-tag>
          </div>

          <div class="strategy-filter-bar">
            <el-input
              v-model="searchKeyword"
              :placeholder="t('strategy.searchPlaceholder')"
              :aria-label="t('strategy.searchAriaLabel')"
              clearable
              class="strategy-search-input"
              prefix-icon="Search"
            />
            <el-radio-group
              v-model="categoryFilter"
              class="strategy-category-filter"
              size="default"
              :aria-label="t('strategy.filterAriaLabel')"
            >
              <el-radio-button value="">
                {{ t('strategy.categoryAll') }}
              </el-radio-button>
              <el-radio-button value="trend">
                {{ t('strategy.categoryTrend') }}
              </el-radio-button>
              <el-radio-button value="mean_reversion">
                {{ t('strategy.categoryMeanReversion') }}
              </el-radio-button>
              <el-radio-button value="volatility">
                {{ t('strategy.categoryVolatility') }}
              </el-radio-button>
              <el-radio-button value="indicator">
                {{ t('strategy.categoryIndicator') }}
              </el-radio-button>
              <el-radio-button value="arbitrage">
                {{ t('strategy.categoryArbitrage') }}
              </el-radio-button>
              <el-radio-button value="custom">
                {{ t('strategy.categoryOther') }}
              </el-radio-button>
            </el-radio-group>
          </div>

          <div
            v-if="filteredTemplates.length"
            class="strategy-template-grid"
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
            class="strategy-empty-state"
            :description="t('strategy.noMatch')"
          />
        </section>
      </el-tab-pane>

      <!-- ========== My strategies ========== -->
      <el-tab-pane
        v-if="showStrategyManagementTabs"
        :label="t('strategy.myStrategies')"
        name="my"
      >
        <section class="strategy-table-panel">
          <div class="strategy-panel-head">
            <div>
              <span>{{ t('strategy.listDialog') }}</span>
              <h2>{{ t('strategy.myStrategies') }}</h2>
            </div>
            <el-button
              type="primary"
              plain
              @click="showCreateDialog"
            >
              <el-icon aria-hidden="true">
                <Plus />
              </el-icon>
              {{ t('strategy.createStrategy') }}
            </el-button>
          </div>

          <el-table
            v-loading="loading"
            class="strategy-owned-table"
            :data="strategies"
            stripe
            :empty-text="t('strategy.customEmpty')"
          >
            <el-table-column
              prop="name"
              :label="t('strategy.strategyName')"
              min-width="180"
            />
            <el-table-column
              prop="description"
              :label="t('strategy.paramDescription')"
              min-width="260"
              show-overflow-tooltip
            />
            <el-table-column
              prop="category"
              :label="t('strategy.strategyType')"
              width="140"
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
        </section>
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
import { Delete, EditPen, Link, MagicStick, Plus, RefreshRight, Upload, VideoPlay } from '@element-plus/icons-vue'
import { getCategoryType, getCategoryLabel, stripStrategyMeta } from '@/constants/strategy'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
import StrategyEditDialog from './strategy-components/StrategyEditDialog.vue'
import StrategyDetailDialog from './strategy-components/StrategyDetailDialog.vue'
import StrategyTemplateCard from './strategy-components/StrategyTemplateCard.vue'
import { useStrategyPage } from './strategy/useStrategyPage'
import type { AIStrategyResearchConfigProfile } from '@/api/strategy'

const strategyPage = useStrategyPage()

const {
  t,
  showAIResearchTab,
  showStrategyManagementTabs,
  activeTab,
  searchKeyword,
  categoryFilter,
  dialogVisible,
  viewDialogVisible,
  detailVisible,
  isEdit,
  saving,
  currentStrategy,
  detailTemplate,
  detailTab,
  readmeContent,
  readmeLoading,
  aiResearchRunning,
  aiResearchResult,
  aiResearchRunsLoading,
  aiResearchTaskId,
  aiResearchTaskProgress,
  aiResearchTaskIteration,
  aiResearchBacktestTaskId,
  aiResearchCancelledBacktestTaskId,
  aiResearchTaskPaperUnitId,
  aiResearchTaskLiveUnitId,
  aiResearchTaskPipeline,
  aiResearchTaskError,
  aiResearchTaskMessage,
  aiResearchTaskLatestIteration,
  aiResearchTaskPromotionAudit,
  aiResearchCancelling,
  aiResearchPaperStartingRunId,
  aiResearchPaperReviewingRunId,
  aiResearchLiveHandoffLoadingRunId,
  aiResearchStrategyViewingRunId,
  aiResearchLiveHandoffApprovingRunId,
  aiResearchLiveTradingPreparingRunId,
  aiResearchConfigDialogVisible,
  aiResearchConfigProfiles,
  aiResearchConfigProfilesLoading,
  aiResearchConfigProfileSaving,
  aiResearchConfigProfileImporting,
  aiResearchConfigProfileDeletingId,
  aiResearchSelectedConfigProfileId,
  aiResearchConfigProfileName,
  aiResearchConfigProfileDescription,
  aiResearchConfigProfileFilePath,
  aiResearchConfigProfileFileInput,
  aiResearchMandate,
  aiResearchMandateConfirmed,
  aiResearchMandateLoading,
  aiResearchTimeline,
  aiResearchTimelineLoading,
  aiResearchVersions,
  aiResearchVersionsLoading,
  aiResearchVersionCompare,
  aiResearchVersionCompareLoading,
  aiResearchSelectedVersionIds,
  aiResearchPrecheckLoading,
  aiResearchPrecheckResult,
  aiResearchPrecheckError,
  PAPER_GATEWAY_CONFIG_PLACEHOLDER,
  LIVE_GATEWAY_CONFIG_PLACEHOLDER,
  form,
  aiResearchForm,
  aiResearchHeroSteps,
  aiResearchHeroMetrics,
  aiResearchPrecheckTagType,
  aiResearchPrecheckSummary,
  strategies,
  loading,
  filteredTemplates,
  displayedTemplates,
  aiResearchSelectedConfigProfile,
  aiResearchSelectedProfileSummary,
  aiResearchSelectedConfigDetails,
  aiResearchSelectedConfigPromptPreview,
  aiResearchVisibleRuns,
  aiResearchNoResultDescription,
  aiResearchMandateDetails,
  aiResearchCanCompareVersions,
  aiResearchVersionMetricKeys,
  strategyManagementStats,
  aiBestSharpe,
  aiResearchNextActions,
  aiResearchBestDiagnostics,
  aiResearchPipelineSteps,
  aiResearchPromotionAudit,
  aiResearchCurrentPaperFailed,
  aiResearchCurrentPaperTargetMissing,
  aiResearchPaperStatusText,
  aiResearchTaskStageLabel,
  aiResearchTaskContinuationSummary,
  aiResearchTaskPaperStatusText,
  aiResearchTaskLiveStatusText,
  aiResearchTaskPipelineSteps,
  aiResearchTaskLatestDiagnostics,
  aiResearchTaskBestIterationDisplay,
  aiResearchContinuationEnabled,
  aiResearchContinuationLabel,
  aiResearchCurrentContinuationSummary,
  canCancelAIResearchTask,
  canContinueAIResearchTask,
  canRetryAIResearchTask,
  canViewBestStrategyFromCurrentResult,
  canStartPaperFromCurrentResult,
  canOpenPaperFromCurrentResult,
  canReviewPaperFromCurrentResult,
  canContinueResearchFromCurrentPaperReview,
  canContinueResearchFromCurrentPaperIssue,
  canContinueResearchFromCurrentRunRecord,
  aiResearchCurrentPaperReview,
  aiResearchCurrentPaperReviewLock,
  canBuildLiveHandoffFromCurrentResult,
  aiResearchCurrentLiveHandoff,
  aiResearchCurrentPaperEnvironment,
  aiResearchCurrentRuntimeEnvironment,
  aiResearchBestGateEvaluations,
  aiResearchOutOfSampleValidation,
  paramTableData,
  openTemplateDetail,
  goBacktest,
  formatMetric,
  gateGapText,
  formatTaskProgress,
  taskLatestIterationLabel,
  taskLatestIterationMetric,
  taskLatestIterationProgress,
  formatDateTime,
  runAIResearchDataPrecheck,
  generateAIResearchPrompt,
  parseAIResearchMandate,
  confirmAIResearchMandate,
  applyAIResearchConfigProfile,
  openAIResearchConfigDialog,
  selectAIResearchConfigProfile,
  aiResearchConfigProfileValue,
  aiResearchConfigProfileMetric,
  aiResearchConfigProfileOos,
  loadAIResearchConfigProfiles,
  createAIResearchConfigProfile,
  saveAIResearchConfigProfile,
  deleteAIResearchConfigProfile,
  triggerAIResearchConfigProfileImport,
  importAIResearchConfigProfileFile,
  hasResearchRuntimeEnvironment,
  researchRuntimeItems,
  hasPaperEnvironment,
  paperEnvironmentItems,
  iterationOutOfSampleValidation,
  researchIterationBacktestSummary,
  formatOutOfSampleWindow,
  outOfSampleTagType,
  outOfSampleStatusLabel,
  recordOutOfSampleSummary,
  bestStrategyIdForRecord,
  compareSelectedAIResearchVersions,
  aiResearchEventTagType,
  aiResearchVersionStatusTagType,
  aiResearchVersionMetric,
  aiResearchVersionMetricLabel,
  selectAIResearchRunRecord,
  researchIterationNextActions,
  iterationProgress,
  iterationProgressLabel,
  iterationProgressTagType,
  iterationProgressDeltaText,
  canStartPaperFromRecord,
  canReviewPaperFromRecord,
  canBuildLiveHandoffFromRecord,
  liveHandoffForRecord,
  canApproveLiveHandoff,
  canPrepareLiveTradingFromRecord,
  liveHandoffApprovalLabel,
  liveTradingPrepareSummary,
  isLiveTradingPreparedForRecord,
  paperStartButtonLabel,
  canContinueResearchFromPaperReview,
  canContinueResearchFromRunRecord,
  continuationSummaryForRecord,
  pipelineStage,
  pipelineStageLabel,
  aiResearchRunStatusLabel,
  paperReviewStatusLabel,
  paperReviewRuleStatusLabel,
  paperReviewRuleGapText,
  paperReviewDispositionLabel,
  liveReadinessStatusLabel,
  liveHandoffStatusLabel,
  pipelineStepStatusLabel,
  pipelineStepTagType,
  pipelineStepDetailText,
  aiResearchStageLabel,
  liveReadinessChecklistForReview,
  paperReviewLockForRecord,
  paperReviewLockSummary,
  paperReviewLockStopResultText,
  clearAIResearchContinuation,
  paperReviewForRecord,
  startPaperFromResearchRecord,
  startPaperFromCurrentResult,
  viewBestStrategyFromCurrentResult,
  viewResearchIterationStrategy,
  viewStrategyFromResearchRecord,
  viewAIResearchVersionCode,
  reviewPaperFromResearchRecord,
  reviewPaperFromCurrentResult,
  buildLiveHandoffFromCurrentResult,
  approveCurrentLiveHandoff,
  prepareLiveTradingFromCurrentResult,
  buildLiveHandoffFromResearchRecord,
  approveLiveHandoffFromResearchRecord,
  prepareLiveTradingFromResearchRecord,
  continueResearchFromCurrentPaperReview,
  continueResearchFromCurrentRunRecord,
  continueResearchFromPaperReview,
  continueResearchFromRecord,
  cancelAIResearchTask,
  continueAIResearchFromTaskSnapshot,
  retryAIResearchFromTaskSnapshot,
  runAIResearchLoop,
  openResearchWorkspace,
  openPaperWorkspace,
  openLiveWorkspaceFromCurrentResult,
  openLiveWorkspaceFromRecord,
  showCreateDialog,
  editStrategy,
  viewStrategy,
  useTemplate,
  updateStrategyForm,
  saveStrategy,
  deleteStrategy,
} = strategyPage

function handleAIResearchConfigProfileRowClick(profile: AIStrategyResearchConfigProfile) {
  applyAIResearchConfigProfile(profile)
}

defineExpose(strategyPage)
</script>
<style scoped src="./StrategyPage.css" />
