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
          <div class="text-xs text-slate-500">工作区类型</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ isTradingWorkspace ? '策略交易' : '策略研究' }}</div>
          <div class="text-xs text-slate-400">当前创建上下文</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">新建方式</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ form.create_mode === 'batch' ? '批量' : '叠加' }}</div>
          <div class="text-xs text-slate-400">支持多品种展开</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">品种数量</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ validSymbolCount }}</div>
          <div class="text-xs text-slate-400">有效代码行数</div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">交易模式</div>
          <div class="mt-1 text-lg font-semibold text-slate-700">{{ isTradingWorkspace ? tradingModeLabel : '研究模式' }}</div>
          <div class="text-xs text-slate-400">{{ selectedStrategyName || '未选择策略' }}</div>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">基本信息</div>
          <el-row :gutter="20">
            <el-col :span="24">
              <el-form-item label="新建方式">
                <el-radio-group v-model="form.create_mode">
                  <el-radio value="batch">批量</el-radio>
                  <el-radio value="overlay" disabled>叠加</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="单元组名" prop="group_name">
                <el-input v-model="form.group_name" placeholder="例如: 黄金策略组" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="分类">
                <el-select v-model="form.category" placeholder="选择分类" style="width: 100%">
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

          <el-form-item label="选择策略" prop="strategy_id">
            <el-select
              v-model="form.strategy_id"
              filterable
              placeholder="选择策略模板"
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

        <div v-if="isTradingWorkspace" class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">交易设置</div>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="交易模式">
                <el-radio-group v-model="form.trading_mode">
                  <el-radio value="paper">模拟交易</el-radio>
                  <el-radio value="live">实盘交易</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item v-if="form.trading_mode === 'live'" label="网关配置">
            <TradingGatewaySelect v-model="form.gateway_config" />
          </el-form-item>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">商品列表</div>
          <el-form-item label="品种代码" prop="symbols">
            <div class="w-full">
              <div
                v-for="(symbol, index) in form.symbols"
                :key="index"
                class="mb-2 flex items-center gap-2"
              >
                <el-input v-model="symbol.code" placeholder="代码 (如 au000)" style="width: 180px" />
                <el-input v-model="symbol.name" placeholder="名称 (如 黄金加权0)" style="width: 220px" />
                <el-button
                  link
                  type="danger"
                  :disabled="form.symbols.length <= 1"
                  @click="form.symbols.splice(index, 1)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
              <el-button size="small" @click="form.symbols.push({ code: '', name: '' })">
                <el-icon class="mr-1"><Plus /></el-icon>添加品种
              </el-button>
            </div>
          </el-form-item>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
          <div class="mb-4 text-sm font-medium text-slate-700">周期与范围</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="周期">
                <el-select v-model="form.timeframe" style="width: 100%">
                  <el-option label="1分钟" value="1m" />
                  <el-option label="5分钟" value="5m" />
                  <el-option label="15分钟" value="15m" />
                  <el-option label="30分钟" value="30m" />
                  <el-option label="1小时" value="1h" />
                  <el-option label="4小时" value="4h" />
                  <el-option label="日线" value="1d" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="N值">
                <el-input-number v-model="form.timeframe_n" :min="1" :max="100" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="范围类型">
                <el-radio-group v-model="form.range_type">
                  <el-radio value="date">日期</el-radio>
                  <el-radio value="sample">样本数</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col v-if="form.range_type === 'sample'" :span="8">
              <el-form-item label="样本数">
                <el-input-number v-model="form.sample_count" :min="100" :max="100000" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row v-if="form.range_type === 'date'" :gutter="20">
            <el-col :span="12">
              <el-form-item label="起始日期">
                <el-date-picker v-model="form.start_date" type="datetime" placeholder="选择起始日期" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="结束日期">
                <div class="flex w-full items-center gap-3">
                  <el-checkbox v-model="form.use_end_date" />
                  <el-date-picker
                    v-model="form.end_date"
                    type="datetime"
                    placeholder="选择结束日期"
                    :disabled="!form.use_end_date"
                    style="width: 100%"
                  />
                </div>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="复权方式">
                <el-radio-group v-model="form.adjust_type">
                  <el-radio value="none">不复权</el-radio>
                  <el-radio value="forward">后复权</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="分割方式">
                <el-radio-group v-model="form.split_type">
                  <el-radio value="natural">自然时间</el-radio>
                  <el-radio value="trading">交易时间</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="数据范围">
                <el-select v-model="form.data_range" style="width: 100%">
                  <el-option label="全部" value="all" />
                  <el-option label="主力" value="main" />
                  <el-option label="夜盘" value="night" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </div>
      </el-form>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Delete, Plus } from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api/index'
import { useStrategyStore } from '@/stores/strategy'
import { useWorkspaceStore } from '@/stores/workspace'
import type { GatewayConfig, WorkspaceType } from '@/types/workspace'
import TradingGatewaySelect from './TradingGatewaySelect.vue'

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

const UNIT_CATEGORY_OPTIONS = ['股票', '期货', '期权', '外汇', '基金', '债券', 'crypto']

const formRef = ref<FormInstance>()
const submitting = ref(false)

const isTradingWorkspace = computed(() => props.workspaceType === 'trading')
const dialogTitle = computed(() =>
  isTradingWorkspace.value ? '策略交易--新建策略单元' : '策略研究--新建策略单元'
)
const validSymbolCount = computed(() => form.value.symbols.filter(symbol => symbol.code.trim()).length)
const tradingModeLabel = computed(() => (form.value.trading_mode === 'live' ? '实盘交易' : '模拟交易'))
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
  category: '股票',
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
  group_name: [{ required: true, message: '请输入组名', trigger: 'blur' }],
  strategy_id: [{ required: true, message: '请选择策略', trigger: 'change' }],
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
    ElMessage.warning('请至少添加一个品种')
    return
  }

  submitting.value = true
  try {
    if (
      isTradingWorkspace.value
      && form.value.trading_mode === 'live'
      && !form.value.gateway_config?.preset_id
    ) {
      ElMessage.warning('请选择实盘网关预设')
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

    ElMessage.success(`已创建 ${validSymbols.length} 个策略单元`)
    emit('update:modelValue', false)
    emit('created')
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '创建失败'))
  } finally {
    submitting.value = false
  }
}
</script>
