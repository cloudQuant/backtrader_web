<template>
  <el-dialog :model-value="modelValue" title="策略研究--新建单元" width="680px" @update:model-value="$emit('update:modelValue', $event)" @closed="resetForm">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
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
            v-for="t in strategyStore.templates"
            :key="t.id"
            :label="t.name"
            :value="t.id"
          />
        </el-select>
      </el-form-item>

      <el-divider content-position="left">商品列表</el-divider>

      <el-form-item label="品种代码" prop="symbols">
        <div class="w-full">
          <div v-for="(sym, idx) in form.symbols" :key="idx" class="flex gap-2 mb-2 items-center">
            <el-input v-model="sym.code" placeholder="代码 (如 au000)" style="width: 160px" />
            <el-input v-model="sym.name" placeholder="名称 (如 黄金加权0)" style="width: 180px" />
            <el-button link type="danger" @click="form.symbols.splice(idx, 1)" :disabled="form.symbols.length <= 1">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
          <el-button size="small" @click="form.symbols.push({ code: '', name: '' })">
            <el-icon class="mr-1"><Plus /></el-icon>添加品种
          </el-button>
        </div>
      </el-form-item>

      <el-divider content-position="left">周期与范围</el-divider>

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
        <el-col :span="8" v-if="form.range_type === 'sample'">
          <el-form-item label="样本数">
            <el-input-number v-model="form.sample_count" :min="100" :max="100000" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="20" v-if="form.range_type === 'date'">
        <el-col :span="12">
          <el-form-item label="起始日期">
            <el-date-picker v-model="form.start_date" type="datetime" placeholder="选择起始日期" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="结束日期">
            <el-checkbox v-model="form.use_end_date" class="mr-2" />
            <el-date-picker v-model="form.end_date" type="datetime" placeholder="选择结束日期" :disabled="!form.use_end_date" style="width: 70%" />
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
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import { useStrategyStore } from '@/stores/strategy'
import { useWorkspaceStore } from '@/stores/workspace'
import { getErrorMessage } from '@/api/index'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const strategyStore = useStrategyStore()
const workspaceStore = useWorkspaceStore()

const UNIT_CATEGORY_OPTIONS = ['股票', '期货', '期权', '外汇', '基金', '债券', 'crypto']

const formRef = ref<FormInstance>()
const submitting = ref(false)

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
  const tpl = strategyStore.templates.find(t => t.id === id)
  if (tpl) {
    form.value.strategy_name = tpl.name
    if (!form.value.group_name) form.value.group_name = tpl.name
  }
}

function resetForm() {
  form.value = defaultForm()
  formRef.value?.resetFields()
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const validSymbols = form.value.symbols.filter(s => s.code.trim())
  if (!validSymbols.length) {
    ElMessage.warning('请至少添加一个品种')
    return
  }

  submitting.value = true
  try {
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
      })
    } else {
      const units = validSymbols.map(s => ({
        group_name: form.value.group_name,
        strategy_id: form.value.strategy_id,
        strategy_name: form.value.strategy_name,
        symbol: s.code,
        symbol_name: s.name,
        timeframe: form.value.timeframe,
        timeframe_n: form.value.timeframe_n,
        category: form.value.category,
        data_config: dataConfig,
      }))
      await workspaceStore.batchCreateUnits(props.workspaceId, units)
    }

    ElMessage.success(`已创建 ${validSymbols.length} 个策略单元`)
    emit('update:modelValue', false)
    emit('created')
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '创建失败'))
  } finally {
    submitting.value = false
  }
}
</script>
