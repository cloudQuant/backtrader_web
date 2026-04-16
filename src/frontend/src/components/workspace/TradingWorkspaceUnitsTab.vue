<template>
  <div class="workspace-units-tab trading-workspace-tab">
    <teleport
      to="#page-header-actions"
      :disabled="!props.toolbarInHeader || !props.active"
    >
      <div
        class="trading-toolbar"
        :class="props.toolbarInHeader && props.active ? 'mb-0' : 'mb-4'"
      >
        <div class="trading-toolbar__groups">
          <el-button-group class="toolbar-group">
            <el-tooltip
              content="全选 / 取消全选"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleSelectAll"
              >
                <el-icon><Select /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="启动自动交易"
              placement="top"
            >
              <el-button
                size="small"
                type="success"
                plain
                :loading="autoTradingLoading"
                :disabled="autoTradingEnabled"
                @click="handleEnableAutoTrading"
              >
                <el-icon><Timer /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="关闭自动交易"
              placement="top"
            >
              <el-button
                size="small"
                type="warning"
                plain
                :loading="autoTradingLoading"
                :disabled="!autoTradingEnabled"
                @click="handleDisableAutoTrading"
              >
                <el-icon><SwitchButton /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group class="toolbar-group">
            <el-tooltip
              content="锁定交易"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="handleLockTrading"
              >
                <el-icon><Lock /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="锁定运行"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="handleLockRunning"
              >
                <el-icon><Files /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="解锁"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="handleUnlock"
              >
                <el-icon><Unlock /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group class="toolbar-group">
            <el-tooltip
              content="启动策略单元"
              placement="top"
            >
              <el-button
                size="small"
                type="success"
                :disabled="!hasSelection || store.running"
                @click="handleStartSelected"
              >
                <el-icon><VideoPlay /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="停止策略单元"
              placement="top"
            >
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="!hasSelection"
                @click="handleStopSelected"
              >
                <el-icon><CircleCloseFilled /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group class="toolbar-group">
            <el-tooltip
              content="新建策略单元"
              placement="top"
            >
              <el-button
                size="small"
                type="primary"
                @click="showCreateUnit = true"
              >
                <el-icon><Plus /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="删除策略单元"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="handleBulkDelete"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="导入策略单元"
              placement="top"
            >
              <el-button
                size="small"
                @click="handleImportUnits"
              >
                <el-icon><FolderOpened /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="导出策略单元"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="handleExportUnits"
              >
                <el-icon><Download /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group class="toolbar-group">
            <el-tooltip
              content="数据源设置"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSingleSelection"
                @click="showDataSource = true"
              >
                <el-icon><DataLine /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="策略单元设置"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSingleSelection"
                @click="showUnitSettings = true"
              >
                <el-icon><Setting /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="公式应用设置"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSingleSelection"
                @click="showStrategyParams = true"
              >
                <el-icon><Document /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group class="toolbar-group">
            <el-tooltip
              content="头寸管理器"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="store.units.length === 0"
                @click="showPositionManager = true"
              >
                <el-icon><Wallet /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="打开K线"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSingleSelection"
                @click="handleOpenKline"
              >
                <el-icon><TrendCharts /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="打开组合报告"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="emit('switch-tab', 'report', store.selectedUnitIds[0], [...store.selectedUnitIds])"
              >
                <el-icon><PieChart /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>

          <el-button-group class="toolbar-group">
            <el-tooltip
              content="自动交易配置"
              placement="top"
            >
              <el-button
                size="small"
                @click="showAutoTradingConfig = true"
              >
                <el-icon><Tools /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="新建优化任务"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="handleCreateOptimizationTask"
              >
                <el-icon><Promotion /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="打开优化结果"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSingleSelection"
                @click="emit('switch-tab', 'optimization', store.selectedUnitIds[0])"
              >
                <el-icon><DataAnalysis /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="定时优化设置"
              placement="top"
            >
              <el-button
                size="small"
                @click="showScheduledOptimization = true"
              >
                <el-icon><Calendar /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="交易日统计选项"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="store.units.length === 0"
                @click="showTradingDayStats = true"
              >
                <el-icon><Histogram /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip
              content="联动分组"
              placement="top"
            >
              <el-button
                size="small"
                :disabled="!hasSelection"
                @click="showGroupLink = true"
              >
                <el-icon><Share /></el-icon>
              </el-button>
            </el-tooltip>
          </el-button-group>
        </div>

        <div class="trading-toolbar__meta">
          <el-tag
            size="small"
            effect="dark"
            :type="autoTradingEnabled ? 'success' : 'info'"
          >
            自动交易{{ autoTradingEnabled ? '已启用' : '已关闭' }}
          </el-tag>
          <span
            v-if="autoTradingScheduleSummary"
            class="text-slate-500"
          >
            {{ autoTradingScheduleSummary }}
          </span>
          <span class="text-slate-500">已选 {{ store.selectedUnitIds.length }} / {{ store.units.length }}</span>
        </div>
      </div>
    </teleport>

    <div class="trading-overview-grid">
      <div class="overview-card">
        <span class="overview-card__label">策略单元</span>
        <strong class="overview-card__value">{{ store.units.length }}</strong>
        <span class="overview-card__meta">当前工作区总量</span>
      </div>
      <div class="overview-card is-success">
        <span class="overview-card__label">运行中</span>
        <strong class="overview-card__value">{{ runningUnitCount }}</strong>
        <span class="overview-card__meta">含运行与排队状态</span>
      </div>
      <div class="overview-card is-warning">
        <span class="overview-card__label">实盘 / 模拟</span>
        <strong class="overview-card__value">{{ liveUnitCount }} / {{ paperUnitCount }}</strong>
        <span class="overview-card__meta">交易模式分布</span>
      </div>
      <div class="overview-card is-danger">
        <span class="overview-card__label">锁定单元</span>
        <strong class="overview-card__value">{{ lockedUnitCount }}</strong>
        <span class="overview-card__meta">交易或运行锁定</span>
      </div>
    </div>

    <div class="trading-schedule-bar">
      <div class="trading-schedule-bar__item">
        <span class="label">自动交易</span>
        <span class="value">{{ autoTradingScheduleSummary || '未配置交易时段' }}</span>
      </div>
      <div class="trading-schedule-bar__item">
        <span class="label">当日盈利单元</span>
        <span class="value">{{ profitableUnitCount }}</span>
      </div>
      <div class="trading-schedule-bar__item">
        <span class="label">最近更新</span>
        <span class="value">{{ lastUpdatedLabel }}</span>
      </div>
    </div>

    <el-table
      ref="tableRef"
      :data="store.units"
      row-key="id"
      stripe
      border
      size="small"
      class="trading-units-table"
      empty-text="暂无策略单元，点击「新建策略单元」开始"
      @selection-change="onSelectionChange"
      @row-dblclick="openDetail"
    >
      <el-table-column
        type="selection"
        width="42"
      />
      <el-table-column
        label="序号"
        width="60"
        align="center"
      >
        <template #default="{ row }">
          {{ row.sort_order + 1 }}
        </template>
      </el-table-column>
      <el-table-column
        label="状态"
        width="156"
        fixed="left"
      >
        <template #default="{ row }">
          <div class="status-cell">
            <div class="status-cell__main">
              <span
                class="status-dot"
                :class="statusDotClass(row)"
              />
              <span class="status-text">{{ statusLabel(row) }}</span>
            </div>
            <div class="status-cell__meta">
              <el-tag
                size="small"
                effect="plain"
                :type="row.trading_mode === 'live' ? 'danger' : 'info'"
              >
                {{ row.trading_mode === 'live' ? '实盘' : '模拟' }}
              </el-tag>
              <span
                v-if="row.lock_trading"
                class="status-flag"
              >锁交</span>
              <span
                v-if="row.lock_running"
                class="status-flag"
              >锁运</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="group_name"
        label="组名"
        min-width="120"
        show-overflow-tooltip
      />
      <el-table-column
        prop="strategy_name"
        label="单元名"
        min-width="150"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span class="font-medium text-slate-700">{{ row.strategy_name || row.strategy_id }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="strategy_id"
        label="公式"
        min-width="160"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span class="font-mono text-xs text-slate-600">{{ row.strategy_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="symbol"
        label="商品代码"
        width="110"
      />
      <el-table-column
        prop="symbol_name"
        label="商品简称"
        width="120"
        show-overflow-tooltip
      />
      <el-table-column
        prop="timeframe"
        label="周期"
        width="90"
        align="center"
      />
      <el-table-column
        prop="category"
        label="分类"
        width="90"
      />
      <el-table-column
        label="起始日期"
        width="120"
      >
        <template #default="{ row }">
          {{ formatDate(row.data_config?.start_date) }}
        </template>
      </el-table-column>
      <el-table-column
        label="结束日期"
        width="120"
      >
        <template #default="{ row }">
          {{ row.data_config?.use_end_date ? formatDate(row.data_config?.end_date) : '-' }}
        </template>
      </el-table-column>
      <el-table-column
        label="更新时间"
        width="160"
      >
        <template #default="{ row }">
          {{ row.trading_snapshot?.updated_at || formatTime(row.updated_at) }}
        </template>
      </el-table-column>
      <el-table-column
        label="bar数"
        width="80"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.bar_count, 0, false) }}
        </template>
      </el-table-column>
      <el-table-column
        label="多仓"
        width="90"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.trading_snapshot?.long_position, 0, false) }}
        </template>
      </el-table-column>
      <el-table-column
        label="空仓"
        width="90"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.trading_snapshot?.short_position, 0, false) }}
        </template>
      </el-table-column>
      <el-table-column
        label="当日盈亏"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          <span :class="numberClass(row.trading_snapshot?.today_pnl)">
            {{ formatSignedNumber(row.trading_snapshot?.today_pnl, 2, false) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="持仓盈亏"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          <span :class="numberClass(row.trading_snapshot?.position_pnl)">
            {{ formatSignedNumber(row.trading_snapshot?.position_pnl, 2, false) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="最新价"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          {{ formatPrice(row.trading_snapshot?.latest_price) }}
        </template>
      </el-table-column>
      <el-table-column
        label="涨幅(%)"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          <span :class="numberClass(row.trading_snapshot?.change_pct)">
            {{ formatSignedNumber(row.trading_snapshot?.change_pct, 2, false, '%') }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="多头市值"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatAmountCompact(row.trading_snapshot?.long_market_value) }}
        </template>
      </el-table-column>
      <el-table-column
        label="空头市值"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatAmountCompact(row.trading_snapshot?.short_market_value) }}
        </template>
      </el-table-column>
      <el-table-column
        label="杠杆"
        width="90"
        align="right"
      >
        <template #default="{ row }">
          {{ formatNumber(row.trading_snapshot?.leverage, 2, false) }}
        </template>
      </el-table-column>
      <el-table-column
        label="累计盈亏"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          <span :class="numberClass(row.trading_snapshot?.cumulative_pnl)">
            {{ formatSignedNumber(row.trading_snapshot?.cumulative_pnl, 2, false) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="最大回撤率"
        width="110"
        align="right"
      >
        <template #default="{ row }">
          {{ formatSignedNumber(row.trading_snapshot?.max_drawdown_rate, 2, false, '%') }}
        </template>
      </el-table-column>
      <el-table-column
        label="详情"
        width="90"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            @click="openDetail(row)"
          >
            详情
          </el-button>
        </template>
      </el-table-column>
      <el-table-column
        label="交易日"
        width="110"
        fixed="right"
      >
        <template #default="{ row }">
          {{ row.trading_snapshot?.trading_day || '-' }}
        </template>
      </el-table-column>
    </el-table>

    <CreateUnitDialog
      v-model="showCreateUnit"
      :workspace-id="props.workspaceId"
      workspace-type="trading"
      @created="onUnitCreated"
    />

    <DataSourceDialog
      v-model="showDataSource"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="trading"
      @saved="onUnitUpdated"
    />

    <UnitSettingsDialog
      v-model="showUnitSettings"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="trading"
      @saved="onUnitUpdated"
    />

    <StrategyParamsDialog
      v-model="showStrategyParams"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      workspace-type="trading"
      @saved="onUnitUpdated"
    />

    <AutoTradingConfigDialog
      v-model="showAutoTradingConfig"
      :workspace-id="props.workspaceId"
      @saved="handleAutoTradingSaved"
    />

    <OptimizationConfigDialog
      v-model="showOptConfig"
      :workspace-id="props.workspaceId"
      :unit="selectedUnit"
      @saved="onUnitUpdated"
    />

    <BatchOptimizationConfigDialog
      v-model="showBatchOptConfig"
      :workspace-id="props.workspaceId"
      :unit-ids="store.selectedUnitIds"
      :units="store.units"
      @saved="onUnitUpdated"
    />

    <PositionManagerDialog
      v-model="showPositionManager"
      :workspace-id="props.workspaceId"
      :unit-ids="store.selectedUnitIds.length ? [...store.selectedUnitIds] : undefined"
    />

    <TradingDayStatsDialog
      v-model="showTradingDayStats"
      :workspace-id="props.workspaceId"
    />

    <ScheduledOptimizationDialog
      v-model="showScheduledOptimization"
      :workspace-id="props.workspaceId"
    />

    <GroupLinkDialog
      v-model="showGroupLink"
      :workspace-id="props.workspaceId"
      :unit-ids="[...store.selectedUnitIds]"
    />

    <ImportTradingUnitsDialog
      v-model="showImportDialog"
      :workspace-id="props.workspaceId"
      @imported="handleUnitsImported"
    />

    <ExportTradingUnitsDialog
      v-model="showExportDialog"
      :units="selectedUnits"
      @exported="handleUnitsExported"
    />

    <el-dialog
      v-model="showDetailDialog"
      title="策略单元详情"
      width="980px"
    >
      <div
        v-if="detailUnit"
        class="space-y-4 text-sm"
      >
        <div class="flex flex-wrap items-center justify-end gap-2">
          <el-button
            size="small"
            @click="handleOpenRuntimeDialog(detailUnit)"
          >
            查看运行文件
          </el-button>
          <el-button
            type="primary"
            size="small"
            @click="handleOpenRuntimeDirectory(detailUnit)"
          >
            打开策略单元
          </el-button>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              单元
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.strategy_name || detailUnit.strategy_id }}
            </div>
            <div class="text-xs text-slate-400">
              {{ detailUnit.symbol }} / {{ detailUnit.timeframe }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              交易模式
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_mode === 'live' ? '实盘交易' : '模拟交易' }}
            </div>
            <div class="text-xs text-slate-400">
              {{ statusLabel(detailUnit) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              网关
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_snapshot?.gateway_summary || '-' }}
            </div>
            <div class="text-xs text-slate-400">
              实例 {{ detailUnit.trading_instance_id || '-' }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div class="text-xs text-slate-500">
              最近更新
            </div>
            <div class="mt-1 font-semibold text-slate-700">
              {{ detailUnit.trading_snapshot?.updated_at || formatTime(detailUnit.updated_at) }}
            </div>
            <div class="text-xs text-slate-400">
              交易日 {{ detailUnit.trading_snapshot?.trading_day || '-' }}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              多仓 / 空仓
            </div>
            <div class="mt-1 text-lg font-semibold text-slate-700">
              {{ formatNumber(detailUnit.trading_snapshot?.long_position, 0, false) }}
              /
              {{ formatNumber(detailUnit.trading_snapshot?.short_position, 0, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              当日盈亏
            </div>
            <div
              class="mt-1 text-lg font-semibold"
              :class="numberClass(detailUnit.trading_snapshot?.today_pnl)"
            >
              {{ formatSignedNumber(detailUnit.trading_snapshot?.today_pnl, 2, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              累计盈亏
            </div>
            <div
              class="mt-1 text-lg font-semibold"
              :class="numberClass(detailUnit.trading_snapshot?.cumulative_pnl)"
            >
              {{ formatSignedNumber(detailUnit.trading_snapshot?.cumulative_pnl, 2, false) }}
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div class="text-xs text-slate-500">
              杠杆 / 最新价
            </div>
            <div class="mt-1 text-lg font-semibold text-slate-700">
              {{ formatNumber(detailUnit.trading_snapshot?.leverage, 2, false) }}
              /
              {{ formatPrice(detailUnit.trading_snapshot?.latest_price) }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-3 text-sm font-medium text-slate-700">
            运行信息
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div><span class="text-gray-500">启动时间：</span>{{ detailUnit.trading_snapshot?.started_at || '-' }}</div>
            <div><span class="text-gray-500">停止时间：</span>{{ detailUnit.trading_snapshot?.stopped_at || '-' }}</div>
            <div class="md:col-span-2">
              <span class="text-gray-500">错误信息：</span>{{ detailUnit.trading_snapshot?.error || '-' }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-3 text-sm font-medium text-slate-700">
            头寸明细
          </div>
          <el-table
            :data="detailUnit.trading_snapshot?.positions || []"
            size="small"
            border
            class="detail-positions-table"
            empty-text="暂无持仓明细"
          >
            <el-table-column
              prop="data_name"
              label="合约"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column
              label="方向"
              width="90"
              align="center"
            >
              <template #default="{ row }">
                {{ directionLabel(row.direction) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="size"
              label="数量"
              width="90"
              align="right"
            />
            <el-table-column
              label="开仓价"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                {{ formatPrice(row.price) }}
              </template>
            </el-table-column>
            <el-table-column
              label="现价"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                {{ formatPrice(row.current_price) }}
              </template>
            </el-table-column>
            <el-table-column
              label="市值"
              width="120"
              align="right"
            >
              <template #default="{ row }">
                {{ formatAmountCompact(row.market_value) }}
              </template>
            </el-table-column>
            <el-table-column
              label="盈亏"
              width="110"
              align="right"
            >
              <template #default="{ row }">
                <span :class="numberClass(row.pnl)">
                  {{ formatSignedNumber(row.pnl, 2, false) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-dialog>
    <UnitRuntimeDialog
      v-model="showRuntimeDialog"
      :workspace-id="workspaceId"
      :unit="runtimeUnit"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CircleCloseFilled,
  DataAnalysis,
  DataLine,
  Delete,
  Document,
  Download,
  Files,
  FolderOpened,
  Histogram,
  Lock,
  PieChart,
  Plus,
  Promotion,
  Select,
  Setting,
  Share,
  SwitchButton,
  Timer,
  Tools,
  TrendCharts,
  Unlock,
  VideoPlay,
  Wallet,
} from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import { useWorkspaceStore } from '@/stores/workspace'
import type {
  StrategyUnit,
  TradingAutoConfig,
  TradingAutoScheduleItem,
} from '@/types/workspace'
import AutoTradingConfigDialog from './AutoTradingConfigDialog.vue'
import BatchOptimizationConfigDialog from './BatchOptimizationConfigDialog.vue'
import CreateUnitDialog from './CreateUnitDialog.vue'
import DataSourceDialog from './DataSourceDialog.vue'
import ExportTradingUnitsDialog from './ExportTradingUnitsDialog.vue'
import GroupLinkDialog from './GroupLinkDialog.vue'
import ImportTradingUnitsDialog from './ImportTradingUnitsDialog.vue'
import OptimizationConfigDialog from './OptimizationConfigDialog.vue'
import PositionManagerDialog from './PositionManagerDialog.vue'
import ScheduledOptimizationDialog from './ScheduledOptimizationDialog.vue'
import StrategyParamsDialog from './StrategyParamsDialog.vue'
import TradingDayStatsDialog from './TradingDayStatsDialog.vue'
import UnitRuntimeDialog from './UnitRuntimeDialog.vue'
import UnitSettingsDialog from './UnitSettingsDialog.vue'

const props = defineProps<{
  workspaceId: string
  active?: boolean
  toolbarInHeader?: boolean
}>()

const emit = defineEmits<{
  'switch-tab': [tab: string, unitId?: string, unitIds?: string[]]
}>()

const store = useWorkspaceStore()
const tableRef = ref<{
  clearSelection: () => void
  toggleRowSelection: (row: StrategyUnit, selected?: boolean) => void
} | null>(null)

const showCreateUnit = ref(false)
const showDataSource = ref(false)
const showUnitSettings = ref(false)
const showStrategyParams = ref(false)
const showAutoTradingConfig = ref(false)
const showOptConfig = ref(false)
const showBatchOptConfig = ref(false)
const showPositionManager = ref(false)
const showTradingDayStats = ref(false)
const showScheduledOptimization = ref(false)
const showGroupLink = ref(false)
const showImportDialog = ref(false)
const showExportDialog = ref(false)
const showDetailDialog = ref(false)
const showRuntimeDialog = ref(false)
const detailUnit = ref<StrategyUnit | null>(null)
const runtimeUnit = ref<StrategyUnit | null>(null)
const autoTradingEnabled = ref(false)
const autoTradingLoading = ref(false)
const autoTradingSchedule = ref<TradingAutoScheduleItem[]>([])

const hasSelection = computed(() => store.selectedUnitIds.length > 0)
const hasSingleSelection = computed(() => store.selectedUnitIds.length === 1)
const selectedUnits = computed(() =>
  store.units.filter(unit => store.selectedUnitIds.includes(unit.id))
)
const selectedUnit = computed<StrategyUnit | null>(() => {
  if (!hasSingleSelection.value) return null
  return store.units.find(unit => unit.id === store.selectedUnitIds[0]) ?? null
})
const runningUnitCount = computed(() =>
  store.units.filter(unit => ['running', 'queued'].includes(unit.trading_snapshot?.instance_status || unit.run_status)).length
)
const lockedUnitCount = computed(() =>
  store.units.filter(unit => unit.lock_trading || unit.lock_running).length
)
const liveUnitCount = computed(() =>
  store.units.filter(unit => unit.trading_mode === 'live').length
)
const paperUnitCount = computed(() =>
  store.units.filter(unit => unit.trading_mode !== 'live').length
)
const profitableUnitCount = computed(() =>
  store.units.filter(unit => Number(unit.trading_snapshot?.today_pnl || 0) > 0).length
)
const autoTradingScheduleSummary = computed(() => {
  if (!autoTradingSchedule.value.length) {
    return ''
  }
  return autoTradingSchedule.value
    .map(item => `${item.session} ${item.start}-${item.stop}`)
    .join(' / ')
})
const lastUpdatedLabel = computed(() => {
  const timestamps = store.units
    .map(unit => unit.trading_snapshot?.updated_at || unit.updated_at)
    .filter(Boolean)
    .map(value => new Date(String(value)).getTime())
    .filter(value => !Number.isNaN(value))
  if (!timestamps.length) {
    return '-'
  }
  return new Date(Math.max(...timestamps)).toLocaleString('zh-CN')
})

onMounted(() => {
  store.clearSelection()
  store.startPolling(props.workspaceId)
  void loadAutoTradingState()
})

onUnmounted(() => {
  store.stopPolling()
})

function onSelectionChange(rows: StrategyUnit[]) {
  store.setSelectedUnitIds(rows.map(row => row.id))
}

function handleSelectAll() {
  if (!tableRef.value) return
  if (store.selectedUnitIds.length === store.units.length) {
    tableRef.value.clearSelection()
    store.clearSelection()
    return
  }
  tableRef.value.clearSelection()
  for (const unit of store.units) {
    tableRef.value.toggleRowSelection(unit, true)
  }
}

function onUnitCreated() {
  void store.fetchUnits(props.workspaceId)
}

async function onUnitUpdated() {
  await store.fetchUnits(props.workspaceId)
  await store.pollStatus(props.workspaceId)
}

async function loadAutoTradingState() {
  try {
    const [config, scheduleResponse] = await Promise.all([
      workspaceApi.getTradingAutoConfig(props.workspaceId),
      workspaceApi.getTradingAutoSchedule(props.workspaceId),
    ])
    autoTradingEnabled.value = config.enabled
    autoTradingSchedule.value = scheduleResponse
  } catch {
    autoTradingEnabled.value = false
    autoTradingSchedule.value = []
  }
}

async function updateAutoTradingEnabled(enabled: boolean) {
  autoTradingLoading.value = true
  try {
    const updated = await workspaceApi.updateTradingAutoConfig(props.workspaceId, { enabled })
    const scheduleResponse = await workspaceApi.getTradingAutoSchedule(props.workspaceId)
    autoTradingEnabled.value = updated.enabled
    autoTradingSchedule.value = scheduleResponse
    ElMessage.success(updated.enabled ? '自动交易已启用' : '自动交易已关闭')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '更新自动交易配置失败'))
  } finally {
    autoTradingLoading.value = false
  }
}

function handleEnableAutoTrading() {
  void updateAutoTradingEnabled(true)
}

function handleDisableAutoTrading() {
  void updateAutoTradingEnabled(false)
}

function handleAutoTradingSaved(payload: { config: TradingAutoConfig; schedule: TradingAutoScheduleItem[] }) {
  autoTradingEnabled.value = payload.config.enabled
  autoTradingSchedule.value = payload.schedule
}

function handleCreateOptimizationTask() {
  if (!store.selectedUnitIds.length) {
    ElMessage.warning('请先选择要创建优化任务的策略单元')
    return
  }
  if (hasSingleSelection.value) {
    showOptConfig.value = true
    return
  }
  showBatchOptConfig.value = true
}

async function handleStartSelected() {
  if (!store.selectedUnitIds.length) return
  const liveUnits = store.units.filter(unit =>
    store.selectedUnitIds.includes(unit.id) && unit.trading_mode === 'live'
  )
  try {
    if (liveUnits.length > 0) {
      await ElMessageBox.confirm(
        `将启动 ${liveUnits.length} 个实盘策略单元。请确认网关状态和交易参数无误。`,
        '实盘启动确认',
        {
          type: 'warning',
          confirmButtonText: '确认启动',
          cancelButtonText: '取消',
        }
      )
    }
    const results = await store.runSelectedUnits(props.workspaceId, false)
    const failed = (results ?? []).filter(result => result.status === 'failed')
    if (failed.length > 0) {
      ElMessage.warning(`已提交启动请求，${failed.length} 个单元启动失败`)
    } else {
      ElMessage.success('启动请求已提交')
    }
    await onUnitUpdated()
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '启动失败'))
    }
  }
}

async function handleStopSelected() {
  if (!store.selectedUnitIds.length) return
  try {
    await store.stopSelectedUnits(props.workspaceId)
    ElMessage.success('停止指令已发送')
    await onUnitUpdated()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '停止失败'))
  }
}

async function applyLockPatch(
  patch: Partial<Pick<StrategyUnit, 'lock_trading' | 'lock_running'>>,
  successMessage: string,
) {
  if (!store.selectedUnitIds.length) return
  try {
    await store.patchUnits(props.workspaceId, [...store.selectedUnitIds], patch)
    ElMessage.success(successMessage)
    await onUnitUpdated()
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '更新锁定状态失败'))
  }
}

function handleLockTrading() {
  void applyLockPatch({ lock_trading: true }, '已锁定交易')
}

function handleLockRunning() {
  void applyLockPatch({ lock_running: true }, '已锁定运行')
}

function handleUnlock() {
  void applyLockPatch({ lock_trading: false, lock_running: false }, '已解除锁定')
}

async function handleBulkDelete() {
  if (!store.selectedUnitIds.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${store.selectedUnitIds.length} 个策略单元？`, '删除确认', {
      type: 'warning',
    })
    await store.bulkDeleteUnits(props.workspaceId, [...store.selectedUnitIds])
    ElMessage.success('策略单元已删除')
  } catch (error: unknown) {
    if (error !== 'cancel' && (error as { message?: string })?.message !== 'cancel') {
      ElMessage.error(getErrorMessage(error, '删除失败'))
    }
  }
}

function handleImportUnits() {
  showImportDialog.value = true
}

function handleExportUnits() {
  if (!selectedUnits.value.length) {
    ElMessage.warning('请先选择要导出的策略单元')
    return
  }
  showExportDialog.value = true
}

async function handleUnitsImported() {
  await onUnitUpdated()
}

function handleUnitsExported() {
  ElMessage.success('导出操作已完成')
}

function handleOpenKline() {
  if (!selectedUnit.value) return
  const query = new URLSearchParams({
    symbol: selectedUnit.value.symbol,
    timeframe: selectedUnit.value.timeframe,
  })
  window.open(`/backtest/legacy?${query.toString()}`, '_blank')
}

function openDetail(unit: StrategyUnit) {
  detailUnit.value = unit
  showDetailDialog.value = true
}

async function handleOpenRuntimeDirectory(unit: StrategyUnit) {
  try {
    const result = await workspaceApi.openUnitRuntimeDir(props.workspaceId, unit.id)
    ElMessage.success(result.message || '策略单元目录已打开')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '打开策略单元失败'))
  }
}

function handleOpenRuntimeDialog(unit: StrategyUnit) {
  runtimeUnit.value = unit
  showRuntimeDialog.value = true
}

function statusDotClass(row: StrategyUnit) {
  const status = row.trading_snapshot?.instance_status || row.run_status
  if (status === 'running') return 'is-running'
  if (status === 'queued') return 'is-queued'
  if (status === 'error' || row.trading_snapshot?.error || row.run_status === 'failed') return 'is-error'
  return 'is-idle'
}

function statusLabel(row: StrategyUnit) {
  const status = row.trading_snapshot?.instance_status || row.run_status
  const map: Record<string, string> = {
    idle: '空闲',
    queued: '排队中',
    running: '运行中',
    stopped: '已停止',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    cancelled: '已取消',
  }
  return map[status] || status
}

function formatDate(value: unknown) {
  const text = String(value ?? '').trim()
  return text ? text.slice(0, 10) : '-'
}

function formatTime(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function formatNumber(value: number | null | undefined, digits = 2, trimTrailingZeros = true) {
  if (value == null || Number.isNaN(value)) return '-'
  const formatted = Number(value).toFixed(digits)
  return trimTrailingZeros && digits > 0
    ? formatted.replace(/\.?0+$/, '')
    : formatted
}

function formatPrice(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  if (Number.isInteger(number)) {
    return String(number)
  }
  return Math.abs(number) >= 100 ? number.toFixed(2) : number.toFixed(4)
}

function formatSignedNumber(
  value: number | null | undefined,
  digits = 2,
  showSign = true,
  suffix = '',
) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  const prefix = showSign && number >= 0 ? '+' : ''
  return `${prefix}${number.toFixed(digits)}${suffix}`
}

function formatAmountCompact(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '-'
  const number = Number(value)
  const abs = Math.abs(number)
  if (abs >= 100000000) {
    return `${(number / 100000000).toFixed(digits)}亿`
  }
  if (abs >= 10000) {
    return `${(number / 10000).toFixed(digits)}万`
  }
  return number.toFixed(digits)
}

function numberClass(value: number | null | undefined) {
  if (value == null || Number.isNaN(value) || value === 0) return 'text-gray-500'
  return value > 0 ? 'text-red-500' : 'text-green-600'
}

function directionLabel(value: string | null | undefined) {
  const text = String(value || '').toLowerCase()
  if (text.includes('long')) return '多头'
  if (text.includes('short')) return '空头'
  return value || '-'
}
</script>

<style scoped>
.trading-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.trading-toolbar__groups {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-group {
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
}

.trading-toolbar__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
}

.trading-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.overview-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
}

.overview-card.is-success {
  border-color: #bbf7d0;
  background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
}

.overview-card.is-warning {
  border-color: #fde68a;
  background: linear-gradient(135deg, #ffffff 0%, #fffbeb 100%);
}

.overview-card.is-danger {
  border-color: #fecaca;
  background: linear-gradient(135deg, #ffffff 0%, #fef2f2 100%);
}

.overview-card__label {
  font-size: 12px;
  color: #64748b;
}

.overview-card__value {
  font-size: 24px;
  line-height: 1.1;
  color: #0f172a;
}

.overview-card__meta {
  font-size: 12px;
  color: #94a3b8;
}

.trading-schedule-bar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
}

.trading-schedule-bar__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.trading-schedule-bar__item .label {
  font-size: 12px;
  color: #94a3b8;
}

.trading-schedule-bar__item .value {
  font-size: 13px;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.trading-units-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}

.trading-units-table :deep(.el-table__row:hover > td) {
  background: #f8fbff !important;
}

.detail-positions-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}

.status-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.status-cell__main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-text {
  font-weight: 500;
  color: #334155;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  flex: 0 0 auto;
  background: #94a3b8;
}

.status-dot.is-running {
  background: #22c55e;
  box-shadow: 0 0 0 3px rgb(34 197 94 / 0.14);
}

.status-dot.is-queued {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgb(245 158 11 / 0.14);
}

.status-dot.is-error {
  background: #ef4444;
  box-shadow: 0 0 0 3px rgb(239 68 68 / 0.14);
}

.status-dot.is-idle {
  background: #94a3b8;
}

.status-cell__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.status-flag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  padding: 0 6px;
  height: 20px;
  border-radius: 999px;
  font-size: 11px;
  color: #92400e;
  background: #fef3c7;
}

@media (max-width: 1200px) {
  .trading-overview-grid,
  .trading-schedule-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .trading-overview-grid,
  .trading-schedule-bar {
    grid-template-columns: 1fr;
  }
}
</style>
