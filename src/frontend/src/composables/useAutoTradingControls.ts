/**
 * Auto-trading enable/disable + schedule state for a trading workspace.
 *
 * Extracted from ``TradingWorkspaceUnitsTab.vue`` (REFACTORING_BACKLOG.md §G)
 * so the SFC stays focused on layout/orchestration. Owns the three reactive
 * pieces of auto-trading state and the API calls that mutate them.
 */
import { computed, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'

import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import { getErrorMessage } from '@/api/index'
import { workspaceApi } from '@/api/workspace'
import type { TradingAutoConfig, TradingAutoScheduleItem } from '@/types/workspace'

export interface AutoTradingControls {
  autoTradingEnabled: Ref<boolean>
  autoTradingLoading: Ref<boolean>
  autoTradingSchedule: Ref<TradingAutoScheduleItem[]>
  autoTradingScheduleSummary: ComputedRef<string>
  loadAutoTradingState: () => Promise<void>
  updateAutoTradingEnabled: (enabled: boolean) => Promise<void>
  handleEnableAutoTrading: () => void
  handleDisableAutoTrading: () => void
  handleAutoTradingSaved: (payload: {
    config: TradingAutoConfig
    schedule: TradingAutoScheduleItem[]
  }) => void
}

export function useAutoTradingControls(workspaceId: () => string): AutoTradingControls {
  const { t } = useI18n()

  const autoTradingEnabled = ref(false)
  const autoTradingLoading = ref(false)
  const autoTradingSchedule = ref<TradingAutoScheduleItem[]>([])

  const autoTradingScheduleSummary = computed(() => {
    if (!autoTradingSchedule.value.length) {
      return ''
    }
    return autoTradingSchedule.value
      .map(item => `${item.session} ${item.start}-${item.stop}`)
      .join(' / ')
  })

  async function loadAutoTradingState(): Promise<void> {
    try {
      const [config, scheduleResponse] = await Promise.all([
        workspaceApi.getTradingAutoConfig(workspaceId()),
        workspaceApi.getTradingAutoSchedule(workspaceId()),
      ])
      autoTradingEnabled.value = config.enabled
      autoTradingSchedule.value = scheduleResponse
    } catch {
      autoTradingEnabled.value = false
      autoTradingSchedule.value = []
    }
  }

  async function updateAutoTradingEnabled(enabled: boolean): Promise<void> {
    autoTradingLoading.value = true
    try {
      const updated = await workspaceApi.updateTradingAutoConfig(workspaceId(), { enabled })
      const scheduleResponse = await workspaceApi.getTradingAutoSchedule(workspaceId())
      autoTradingEnabled.value = updated.enabled
      autoTradingSchedule.value = scheduleResponse
      ElMessage.success(
        updated.enabled
          ? t('tradingUnits.autoTradingEnabled')
          : t('tradingUnits.autoTradingDisabled'),
      )
    } catch (error: unknown) {
      ElMessage.error(getErrorMessage(error, t('tradingUnits.updateAutoTradingFailed')))
    } finally {
      autoTradingLoading.value = false
    }
  }

  function handleEnableAutoTrading(): void {
    void updateAutoTradingEnabled(true)
  }

  function handleDisableAutoTrading(): void {
    void updateAutoTradingEnabled(false)
  }

  function handleAutoTradingSaved(payload: {
    config: TradingAutoConfig
    schedule: TradingAutoScheduleItem[]
  }): void {
    autoTradingEnabled.value = payload.config.enabled
    autoTradingSchedule.value = payload.schedule
  }

  return {
    autoTradingEnabled,
    autoTradingLoading,
    autoTradingSchedule,
    autoTradingScheduleSummary,
    loadAutoTradingState,
    updateAutoTradingEnabled,
    handleEnableAutoTrading,
    handleDisableAutoTrading,
    handleAutoTradingSaved,
  }
}
