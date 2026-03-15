<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="优化线程设置"
    width="420px"
    destroy-on-close
  >
    <el-form label-width="120px" size="small">
      <el-form-item label="并行线程数">
        <el-input-number v-model="form.n_workers" :min="1" :max="32" />
      </el-form-item>
      <el-form-item label="运行模式">
        <el-radio-group v-model="form.mode">
          <el-radio value="grid">网格搜索</el-radio>
          <el-radio value="random">随机搜索</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="超时时间(秒)">
        <el-input-number v-model="form.timeout" :min="0" :max="86400" :step="60" />
        <div class="text-xs text-gray-400 mt-1">0 表示不限制</div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="handleSave">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { workspaceApi } from '@/api/workspace'
import { getErrorMessage } from '@/api/index'
import type { StrategyUnit } from '@/types/workspace'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unit: StrategyUnit | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  saved: []
}>()

const form = reactive({
  n_workers: 4,
  mode: 'grid' as 'grid' | 'random',
  timeout: 0,
})

watch(() => props.unit, (u) => {
  if (u?.optimization_config) {
    form.n_workers = u.optimization_config.n_workers ?? 4
    form.mode = (u.optimization_config as Record<string, unknown>).mode as 'grid' | 'random' ?? 'grid'
    form.timeout = (u.optimization_config as Record<string, unknown>).timeout as number ?? 0
  }
}, { immediate: true })

async function handleSave() {
  if (!props.unit) return
  try {
    const existingConfig = props.unit.optimization_config || {}
    await workspaceApi.updateUnit(props.workspaceId, props.unit.id, {
      optimization_config: {
        ...existingConfig,
        n_workers: form.n_workers,
        mode: form.mode,
        timeout: form.timeout,
      },
    })
    ElMessage.success('优化线程设置已保存')
    emit('saved')
    emit('update:modelValue', false)
  } catch (e: unknown) {
    ElMessage.error(getErrorMessage(e, '保存失败'))
  }
}
</script>
