<template>
  <el-dialog
    v-model="visible"
    title="联动分组"
    width="720px"
  >
    <div class="space-y-4">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            选中单元
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ props.unitIds.length }}
          </div>
          <div class="text-xs text-slate-400">
            待配置联动范围
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            当前联动组
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ groupName.trim() || '未设置' }}
          </div>
          <div class="text-xs text-slate-400">
            组名可跨单元复用
          </div>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="text-xs text-slate-500">
            已存在联动组
          </div>
          <div class="mt-1 text-lg font-semibold text-slate-700">
            {{ existingGroupCount }}
          </div>
          <div class="text-xs text-slate-400">
            工作区级配置
          </div>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="`当前将为 ${props.unitIds.length} 个策略单元设置联动分组。`"
      />

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <el-form label-width="100px">
          <el-form-item label="联动组名称">
            <el-input
              v-model="groupName"
              placeholder="例如：黑色系联动、股指对冲组"
            />
          </el-form-item>
        </el-form>
      </div>

      <div class="rounded-xl border border-slate-200 bg-white px-4 py-4">
        <div class="mb-2 text-sm font-medium text-gray-700">
          包含单元
        </div>
        <div class="flex flex-wrap gap-2">
          <el-tag
            v-for="unit in selectedUnits"
            :key="unit.id"
            size="small"
            effect="plain"
          >
            {{ unit.strategy_name || unit.strategy_id }}
          </el-tag>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">
        取消
      </el-button>
      <el-button @click="handleClear">
        清除联动
      </el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="handleSave"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api/index'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  unitIds: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [value: Record<string, unknown>]
}>()

const store = useWorkspaceStore()
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const loading = computed(() => store.loading)
const groupName = ref('')
const existingGroupCount = computed(() => new Set(Object.values(readGroupLinks()).filter(Boolean)).size)

const selectedUnits = computed(() =>
  store.units.filter(unit => props.unitIds.includes(unit.id)),
)

function readGroupLinks() {
  const tradingConfig = (store.currentWorkspace?.trading_config || {}) as Record<string, unknown>
  return ((tradingConfig.group_links || {}) as Record<string, string>)
}

watch(
  () => props.modelValue,
  (value) => {
    if (!value) return
    const links = readGroupLinks()
    const values = props.unitIds.map(unitId => links[unitId]).filter(Boolean)
    groupName.value = values.length && values.every(value => value === values[0]) ? values[0] : ''
  },
)

async function saveLinks(nextLinks: Record<string, string>) {
  const tradingConfig = {
    ...((store.currentWorkspace?.trading_config || {}) as Record<string, unknown>),
    group_links: nextLinks,
  }
  await store.updateWorkspace(props.workspaceId, { trading_config: tradingConfig })
  emit('saved', tradingConfig)
}

async function handleSave() {
  if (!props.unitIds.length) {
    ElMessage.warning('请先选择要联动的策略单元')
    return
  }
  const trimmed = groupName.value.trim()
  if (!trimmed) {
    ElMessage.warning('请输入联动组名称')
    return
  }
  try {
    const links = { ...readGroupLinks() }
    for (const unitId of props.unitIds) {
      links[unitId] = trimmed
    }
    await saveLinks(links)
    ElMessage.success('联动分组已保存')
    visible.value = false
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '保存联动分组失败'))
  }
}

async function handleClear() {
  try {
    const links = { ...readGroupLinks() }
    for (const unitId of props.unitIds) {
      delete links[unitId]
    }
    await saveLinks(links)
    ElMessage.success('联动分组已清除')
    visible.value = false
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error, '清除联动分组失败'))
  }
}
</script>
