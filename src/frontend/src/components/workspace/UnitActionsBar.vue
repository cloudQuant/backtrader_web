<template>
  <div
    class="trading-toolbar"
    :class="toolbarInHeader && active ? 'mb-0' : 'mb-4'"
  >
    <div class="trading-toolbar__groups">
      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.selectAll') + ' / ' + t('workspaceDialogs.deselectAll')"
          placement="top"
        >
          <el-button
            size="small"
            @click="emit('selectAll')"
          >
            <el-icon><Select /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.autoTradingEnable')"
          placement="top"
        >
          <el-button
            size="small"
            type="success"
            plain
            :loading="autoTradingLoading"
            :disabled="autoTradingEnabled"
            @click="emit('enableAutoTrading')"
          >
            <el-icon><Timer /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.autoTradingDisable')"
          placement="top"
        >
          <el-button
            size="small"
            type="warning"
            plain
            :loading="autoTradingLoading"
            :disabled="!autoTradingEnabled"
            @click="emit('disableAutoTrading')"
          >
            <el-icon><SwitchButton /></el-icon>
          </el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.lockTrading')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('lockTrading')"
          >
            <el-icon><Lock /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.lockRunning')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('lockRunning')"
          >
            <el-icon><Files /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.unlock')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('unlock')"
          >
            <el-icon><Unlock /></el-icon>
          </el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.startUnits')"
          placement="top"
        >
          <el-button
            size="small"
            type="success"
            :disabled="!hasSelection || running"
            @click="emit('startSelected')"
          >
            <el-icon><VideoPlay /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.stopUnits')"
          placement="top"
        >
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!hasSelection"
            @click="emit('stopSelected')"
          >
            <el-icon><CircleCloseFilled /></el-icon>
          </el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.newUnit')"
          placement="top"
        >
          <el-button
            size="small"
            type="primary"
            @click="emit('createUnit')"
          >
            <el-icon><Plus /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.deleteUnits')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('bulkDelete')"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.importTitle')"
          placement="top"
        >
          <el-button
            size="small"
            @click="emit('importUnits')"
          >
            <el-icon><FolderOpened /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.exportTitle')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('exportUnits')"
          >
            <el-icon><Download /></el-icon>
          </el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.dataSourceTitle')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSingleSelection"
            @click="emit('openDataSource')"
          >
            <el-icon><DataLine /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.unitSettingsTitle')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSingleSelection"
            @click="emit('openUnitSettings')"
          >
            <el-icon><Setting /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.formulaApply')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSingleSelection"
            @click="emit('openStrategyParams')"
          >
            <el-icon><Document /></el-icon>
          </el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.positionManager')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="unitCount === 0"
            @click="emit('openPositionManager')"
          >
            <el-icon><Wallet /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.open') + ' K'"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSingleSelection"
            @click="emit('openKline')"
          >
            <el-icon><TrendCharts /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.openPortfolioReport')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('openReport')"
          >
            <el-icon><PieChart /></el-icon>
          </el-button>
        </el-tooltip>
      </el-button-group>

      <el-button-group class="toolbar-group">
        <el-tooltip
          :content="t('workspaceDialogs.autoTradingConfig')"
          placement="top"
        >
          <el-button
            size="small"
            @click="emit('openAutoTradingConfig')"
          >
            <el-icon><Tools /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.newOptTask')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('createOptimizationTask')"
          >
            <el-icon><Promotion /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.openOptResults')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSingleSelection"
            @click="emit('openOptimization')"
          >
            <el-icon><DataAnalysis /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.scheduledOptTitle')"
          placement="top"
        >
          <el-button
            size="small"
            @click="emit('openScheduledOptimization')"
          >
            <el-icon><Calendar /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.tradingDayStat')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="unitCount === 0"
            @click="emit('openTradingDayStats')"
          >
            <el-icon><Histogram /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="t('workspaceDialogs.groupLink')"
          placement="top"
        >
          <el-button
            size="small"
            :disabled="!hasSelection"
            @click="emit('openGroupLink')"
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
        {{ t('workspaceDialogs.autoTradingTitleAlt') }}{{ autoTradingEnabled ? t('workspaceDialogs.enabledStatus') : t('workspaceDialogs.disabledStatus') }}
      </el-tag>
      <span
        v-if="autoTradingScheduleSummary"
        class="text-slate-500"
      >
        {{ autoTradingScheduleSummary }}
      </span>
      <span class="text-slate-500">{{ t('workspaceDialogs.selectedSuffix') }} {{ selectedCount }} / {{ unitCount }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Calendar,
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
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  active?: boolean
  toolbarInHeader?: boolean
  hasSelection: boolean
  hasSingleSelection: boolean
  running: boolean
  autoTradingEnabled: boolean
  autoTradingLoading: boolean
  autoTradingScheduleSummary: string
  selectedCount: number
  unitCount: number
}>()

const emit = defineEmits<{
  selectAll: []
  enableAutoTrading: []
  disableAutoTrading: []
  lockTrading: []
  lockRunning: []
  unlock: []
  startSelected: []
  stopSelected: []
  createUnit: []
  bulkDelete: []
  importUnits: []
  exportUnits: []
  openDataSource: []
  openUnitSettings: []
  openStrategyParams: []
  openPositionManager: []
  openKline: []
  openReport: []
  openAutoTradingConfig: []
  createOptimizationTask: []
  openOptimization: []
  openScheduledOptimization: []
  openTradingDayStats: []
  openGroupLink: []
}>()
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
</style>
