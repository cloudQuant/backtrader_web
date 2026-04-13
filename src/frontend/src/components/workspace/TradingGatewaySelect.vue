<template>
  <div class="w-full space-y-3">
    <el-select
      v-model="selectedPresetId"
      class="w-full"
      filterable
      clearable
      :loading="loading"
      placeholder="选择网关预设"
      @change="handlePresetChange"
    >
      <el-option
        v-for="preset in presets"
        :key="preset.id"
        :label="preset.name"
        :value="preset.id"
      />
    </el-select>

    <div v-if="selectedPreset" class="rounded border border-gray-200 bg-gray-50 p-3">
      <div class="text-sm font-medium text-gray-700">
        {{ selectedPreset.name }}
      </div>
      <div v-if="selectedPreset.description" class="mt-1 text-xs text-gray-500">
        {{ selectedPreset.description }}
      </div>
    </div>

    <div v-if="editableFields.length" class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <el-form-item
        v-for="field in editableFields"
        :key="field.key"
        :label="field.label"
        label-width="90px"
        class="!mb-0"
      >
        <el-switch
          v-if="field.input_type === 'boolean'"
          v-model="booleanOverrides[field.key]"
          @change="emitCurrent"
        />
        <el-input
          v-else
          v-model="stringOverrides[field.key]"
          :placeholder="field.placeholder || ''"
          @input="emitCurrent"
        />
      </el-form-item>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { liveTradingApi } from '@/api/liveTrading'
import type { GatewayConfig } from '@/types/workspace'

type TradingPreset = Awaited<ReturnType<typeof liveTradingApi.listPresets>>['presets'][number]

const props = defineProps<{
  modelValue?: GatewayConfig
}>()

const emit = defineEmits<{
  'update:modelValue': [value: GatewayConfig]
}>()

const loading = ref(false)
const presets = ref<TradingPreset[]>([])
const selectedPresetId = ref('')
const stringOverrides = reactive<Record<string, string>>({})
const booleanOverrides = reactive<Record<string, boolean>>({})

const selectedPreset = computed(() =>
  presets.value.find(preset => preset.id === selectedPresetId.value) ?? null
)
const editableFields = computed(() => selectedPreset.value?.editable_fields ?? [])

function clearOverrides() {
  for (const key of Object.keys(stringOverrides)) {
    delete stringOverrides[key]
  }
  for (const key of Object.keys(booleanOverrides)) {
    delete booleanOverrides[key]
  }
}

function extractGatewayData(config?: GatewayConfig): Record<string, unknown> {
  const params = config?.params
  const gateway = params?.gateway
  return gateway && typeof gateway === 'object' ? { ...(gateway as Record<string, unknown>) } : {}
}

function applyModelValue(config?: GatewayConfig) {
  selectedPresetId.value = config?.preset_id ?? ''
  clearOverrides()
  const gatewayData = extractGatewayData(config)
  const preset = presets.value.find(item => item.id === selectedPresetId.value) ?? null
  const fields = preset?.editable_fields ?? []
  for (const field of fields) {
    if (field.input_type === 'boolean') {
      booleanOverrides[field.key] = Boolean(gatewayData[field.key])
    } else {
      stringOverrides[field.key] = String(gatewayData[field.key] ?? '')
    }
  }
}

function emitCurrent() {
  if (!selectedPreset.value) {
    emit('update:modelValue', {})
    return
  }
  const baseGateway = {
    ...((selectedPreset.value.params?.gateway as Record<string, unknown> | undefined) ?? {}),
  }
  for (const field of editableFields.value) {
    if (field.input_type === 'boolean') {
      baseGateway[field.key] = Boolean(booleanOverrides[field.key])
    } else {
      baseGateway[field.key] = String(stringOverrides[field.key] ?? '')
    }
  }
  emit('update:modelValue', {
    preset_id: selectedPreset.value.id,
    name: selectedPreset.value.name,
    params: { gateway: baseGateway },
  })
}

function handlePresetChange() {
  const nextConfig = props.modelValue?.preset_id === selectedPresetId.value
    ? props.modelValue
    : undefined
  applyModelValue(nextConfig)
  emitCurrent()
}

watch(() => props.modelValue, (value) => {
  applyModelValue(value)
}, { immediate: true, deep: true })

onMounted(async () => {
  loading.value = true
  try {
    const response = await liveTradingApi.listPresets()
    presets.value = response.presets
    applyModelValue(props.modelValue)
  } finally {
    loading.value = false
  }
})
</script>
