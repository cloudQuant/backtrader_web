<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="860px"
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('unitDialog.workspaceType') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ isTradingWorkspace ? t('unitDialog.tradingTrading') : t('unitDialog.tradingResearch') }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('unitDialog.currentContext') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('unitDialog.creationMode') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ form.create_mode === 'batch' ? t('unitDialog.batch') : t('unitDialog.overlay') }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('unitDialog.supportMulti') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('unitDialog.symbolCount') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ validSymbolCount }}
          </div>
          <div class="text-xs text-slate-400">
            {{ t('unitDialog.validCodeLines') }}
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            {{ t('unitDialog.tradingMode') }}
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ isTradingWorkspace ? tradingModeLabel : t('unitDialog.researchMode') }}
          </div>
          <div class="text-xs text-slate-400">
            {{ selectedStrategyName || t('unitDialog.notSelected') }}
          </div>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">
            {{ t('unitDialog.single') }}
          </div>
          <el-row :gutter="20">
            <el-col :span="24">
              <el-form-item :label="t('unitDialog.creationMode')">
                <el-radio-group v-model="form.create_mode">
                  <el-radio value="batch">
                    {{ t('unitDialog.batch') }}
                  </el-radio>
                  <el-radio
                    value="overlay"
                    disabled
                  >
                    {{ t('unitDialog.overlay') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item
                :label="t('unitDialog.groupName')"
                prop="group_name"
              >
                <el-input
                  v-model="form.group_name"
                  :placeholder="t('unitDialog.egPrefix') + ': ' + t('unitDialog.sampleGroup')"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('unitDialog.category')">
                <el-select
                  v-model="form.category"
                  :placeholder="t('unitDialog.selectCategory')"
                  style="width: 100%"
                >
                  <el-option
                    v-for="category in UNIT_CATEGORY_OPTIONS"
                    :key="category"
                    :label="category"
                    :value="category"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item
            :label="t('unitDialog.selectStrategy')"
            prop="strategy_id"
          >
            <el-select
              v-model="form.strategy_id"
              filterable
              :placeholder="t('unitDialog.selectTemplate')"
              style="width: 100%"
              @change="onStrategyChange"
            >
              <el-option
                v-for="template in strategyStore.templates"
                :key="template.id"
                :label="template.name"
                :value="template.id"
              />
            </el-select>
          </el-form-item>
        </div>

        <div
          v-if="isTradingWorkspace"
          class="rounded-xl border border-slate-200 bg-white px-4 py-4"
        >
          <div class="mb-4 text-sm font-medium text-slate-700">
            {{ t('unitDialog.tradingSettings') }}
          </div>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('unitDialog.tradingMode')">
                <el-radio-group v-model="form.trading_mode">
                  <el-radio value="paper">
                    {{ t('unitDialog.paperTrading') }}
                  </el-radio>
                  <el-radio value="live">
                    {{ t('unitDialog.liveTrading') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item
            v-if="form.trading_mode === 'live'"
            :label="t('unitDialog.gatewayConfig')"
          >
            <TradingGatewaySelect v-model="form.gateway_config" />
          </el-form-item>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">
            {{ t('unitDialog.symbolListLabel') }}
          </div>
          <el-form-item
            :label="t('unitDialog.symbolCode')"
            prop="symbols"
          >
            <div class="w-full">
              <div
                v-for="(symbol, index) in form.symbols"
                :key="index"
                class="mb-2 flex items-center gap-2"
              >
                <el-input
                  v-model="symbol.code"
                  :placeholder="t('unitDialog.codeLabel') + ' (' + t('unitDialog.likePrefix') + ' au000)'"
                  style="width: 180px"
                />
                <el-input
                  v-model="symbol.name"
                  :placeholder="t('unitDialog.nameLabel') + ' (' + t('unitDialog.likePrefix') + ' ' + t('unitDialog.sampleSymbol') + '0)'"
                  style="width: 220px"
                />
                <el-button
                  link
                  type="danger"
                  :disabled="form.symbols.length <= 1"
                  @click="form.symbols.splice(index, 1)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
              <el-button
                size="small"
                @click="form.symbols.push({ code: '', name: '' })"
              >
                <el-icon class="mr-1">
                  <Plus />
                </el-icon>{{ t('unitDialog.addSymbol') }}
              </el-button>
            </div>
          </el-form-item>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">
            {{ t('unitDialog.timeframeAndRange') }}
          </div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item :label="t('unitDialog.timeframe')">
                <el-select
                  v-model="form.timeframe"
                  style="width: 100%"
                >
                  <el-option
                    label="1m"
                    value="1m"
                  />
                  <el-option
                    label="5m"
                    value="5m"
                  />
                  <el-option
                    label="15m"
                    value="15m"
                  />
                  <el-option
                    label="30m"
                    value="30m"
                  />
                  <el-option
                    label="1h"
                    value="1h"
                  />
                  <el-option
                    label="4h"
                    value="4h"
                  />
                  <el-option
                    :label="t('unitDialog.daily')"
                    value="1d"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="N">
                <el-input-number
                  v-model="form.timeframe_n"
                  :min="1"
                  :max="100"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item :label="t('unitDialog.rangeType')">
                <el-radio-group v-model="form.range_type">
                  <el-radio value="date">
                    {{ t('unitDialog.dateLabel') }}
                  </el-radio>
                  <el-radio value="sample">
                    {{ t('unitDialog.sampleCount') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col
              v-if="form.range_type === 'sample'"
              :span="8"
            >
              <el-form-item :label="t('unitDialog.sampleCount')">
                <el-input-number
                  v-model="form.sample_count"
                  :min="100"
                  :max="100000"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row
            v-if="form.range_type === 'date'"
            :gutter="20"
          >
            <el-col :span="12">
              <el-form-item :label="t('unitDialog.rangeStartDate')">
                <el-date-picker
                  v-model="form.start_date"
                  type="datetime"
                  :placeholder="t('unitDialog.selectStartDate')"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('unitDialog.rangeEndDate')">
                <div class="flex w-full items-center gap-3">
                  <el-checkbox v-model="form.use_end_date" />
                  <el-date-picker
                    v-model="form.end_date"
                    type="datetime"
                    :placeholder="t('unitDialog.selectEndDate')"
                    :disabled="!form.use_end_date"
                    style="width: 100%"
                  />
                </div>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item :label="t('units.config')">
                <el-radio-group v-model="form.adjust_type">
                  <el-radio value="none">
                    {{ t('unitDialog.adjustNone') }}
                  </el-radio>
                  <el-radio value="forward">
                    {{ t('unitDialog.adjustPost') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('unitDialog.splitMode')">
                <el-radio-group v-model="form.split_type">
                  <el-radio value="natural">
                    {{ t('unitDialog.timestampNatural') }}
                  </el-radio>
                  <el-radio value="trading">
                    {{ t('unitDialog.tradingTime') }}
                  </el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('unitDialog.dataRange')">
                <el-select
                  v-model="form.data_range"
                  style="width: 100%"
                >
                  <el-option
                    :label="t('unitDialog.all')"
                    value="all"
                  />
                  <el-option
                    :label="t('unitDialog.main')"
                    value="main"
                  />
                  <el-option
                    :label="t('unitDialog.nightSession')"
                    value="night"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </div>
      </el-form>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">
        {{ t('unitDialog.cancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="handleSubmit"
      >
        {{ t('unitDialog.create') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Delete, Plus } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { getErrorMessage } from '@/api/index'
import { useStrategyStore } from '@/stores/strategy'
import { useWorkspaceStore } from '@/stores/workspace'
import type { GatewayConfig, WorkspaceType } from '@/types/workspace'
import TradingGatewaySelect from './TradingGatewaySelect.vue'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: string
  workspaceType?: WorkspaceType
}>(), {
  workspaceType: 'research',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const strategyStore = useStrategyStore()
const workspaceStore = useWorkspaceStore()

const UNIT_CATEGORY_OPTIONS = computed(() => [t('unitDialog.catStock'), t('unitDialog.catFuture'), t('unitDialog.catOption'), t('unitDialog.catFx'), t('unitDialog.catFund'), t('unitDialog.catBond'), 'crypto'])

const formRef = ref<FormInstance>()
const submitting = ref(false)

const isTradingWorkspace = computed(() => props.workspaceType === 'trading')
const dialogTitle = computed(() =>
  (isTradingWorkspace.value ? t('unitDialog.tradingTrading') : t('unitDialog.tradingResearch')) + '--' + t('unitDialog.title')
)
const validSymbolCount = computed(() => form.value.symbols.filter(symbol => symbol.code.trim()).length)
const tradingModeLabel = computed(() => (form.value.trading_mode === 'live' ? t('unitDialog.liveTrading') : t('unitDialog.paperTrading')))
const selectedStrategyName = computed(() => {
  const template = strategyStore.templates.find(item => item.id === form.value.strategy_id)
  return template?.name || form.value.strategy_name || ''
})

function defaultStartDate(): Date {
  return new Date('2020-01-01T00:00:00.000Z')
}

function defaultEndDate(): Date {
  return new Date()
}

const defaultForm = () => ({
  create_mode: 'batch' as const,
  group_name: '',
  category: t('unitDialog.catStock'),
  strategy_id: '',
  strategy_name: '',
  symbols: [{ code: '', name: '' }],
  timeframe: '1d',
  timeframe_n: 1,
  range_type: 'date' as 'date' | 'sample',
  sample_count: 1000,
  start_date: defaultStartDate(),
  end_date: defaultEndDate(),
  use_end_date: true,
  adjust_type: 'none',
  split_type: 'natural',
  data_range: 'all',
  trading_mode: 'paper' as 'paper' | 'live',
  gateway_config: {} as GatewayConfig,
})

const form = ref(defaultForm())

const rules: FormRules = {
  group_name: [{ required: true, message: t('unitDialog.pleaseEnterGroup'), trigger: 'blur' }],
  strategy_id: [{ required: true, message: t('unitDialog.pleaseSelectStrategy'), trigger: 'change' }],
}

onMounted(() => {
  if (!strategyStore.templates.length) {
    strategyStore.fetchTemplates()
  }
})

function onStrategyChange(id: string) {
  const template = strategyStore.templates.find(item => item.id === id)
  if (!template) return
  form.value.strategy_name = template.name
  if (!form.value.group_name) {
    form.value.group_name = template.name
  }
}

function resetForm() {
  form.value = defaultForm()
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const validSymbols = form.value.symbols.filter(symbol => symbol.code.trim())
  if (!validSymbols.length) {
    ElMessage.warning(t('unitDialog.pleaseAddSymbol'))
    return
  }

  submitting.value = true
  try {
    if (
      isTradingWorkspace.value
      && form.value.trading_mode === 'live'
      && !form.value.gateway_config?.preset_id
    ) {
      ElMessage.warning(t('unitDialog.selectLiveGateway'))
      return
    }

    const dataConfig = {
      range_type: form.value.range_type,
      sample_count: form.value.sample_count,
      start_date: form.value.start_date ? new Date(form.value.start_date).toISOString() : '',
      end_date: form.value.end_date ? new Date(form.value.end_date).toISOString() : '',
      use_end_date: form.value.use_end_date,
      adjust_type: form.value.adjust_type,
      split_type: form.value.split_type,
      data_range: form.value.data_range,
    }

    const tradingPayload = isTradingWorkspace.value
      ? {
          trading_mode: form.value.trading_mode,
          gateway_config: form.value.gateway_config,
        }
      : {}

    if (validSymbols.length === 1) {
      await workspaceStore.createUnit(props.workspaceId, {
        group_name: form.value.group_name,
        strategy_id: form.value.strategy_id,
        strategy_name: form.value.strategy_name,
        symbol: validSymbols[0].code,
        symbol_name: validSymbols[0].name,
        timeframe: form.value.timeframe,
        timeframe_n: form.value.timeframe_n,
        category: form.value.category,
        data_config: dataConfig,
        ...tradingPayload,
      })
    } else {
      const units = validSymbols.map(symbol => ({
        group_name: form.value.group_name,
        strategy_id: form.value.strategy_id,
        strategy_name: form.value.strategy_name,
        symbol: symbol.code,
        symbol_name: symbol.name,
        timeframe: form.value.timeframe,
        timeframe_n: form.value.timeframe_n,
        category: form.value.category,
        data_config: dataConfig,
        ...tradingPayload,
      }))
      await workspaceStore.batchCreateUnits(props.workspaceId, units)
    }

    ElMessage.success(`${t('unitDialog.created')} ${validSymbols.length} ${t('unitDialog.nUnits')}`)
    emit('update:modelValue', false)
    emit('created')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, t('unitDialog.createFailed')))
  } finally {
    submitting.value = false
  }
}
</script>
