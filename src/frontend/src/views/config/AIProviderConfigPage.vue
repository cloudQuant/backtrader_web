<template>
  <div class="ai-provider-config-page">
    <header class="config-page-header">
      <div>
        <h1>{{ t('configPages.aiTitle') }}</h1>
        <p>{{ t('configPages.aiDesc') }}</p>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          :icon="Plus"
          @click="openCreateDialog"
        >
          {{ t('configPages.aiAddProvider') }}
        </el-button>
        <el-button
          :icon="Refresh"
          :loading="loading"
          @click="loadConfigs"
        >
          {{ t('common.reset') }}
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      class="config-alert"
    >
      {{ loadError }}
    </el-alert>

    <el-card class="provider-list-card">
      <el-table
        v-loading="loading"
        :data="providerDrafts"
        row-key="provider"
        stripe
        class="provider-table"
      >
        <el-table-column
          prop="display_name"
          :label="t('configPages.aiProviderName')"
          min-width="190"
          fixed="left"
        >
          <template #default="{ row }">
            <div class="provider-identity">
              <strong>{{ row.display_name || row.provider }}</strong>
              <span>{{ row.provider }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="provider_type"
          :label="t('configPages.aiProviderType')"
          width="170"
        >
          <template #default="{ row }">
            <el-tag size="small">
              {{ providerTypeLabel(row.provider_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('configPages.aiModels')"
          min-width="240"
        >
          <template #default="{ row }">
            <div class="model-tags">
              <el-tag
                v-for="model in modelPreview(row)"
                :key="model"
                size="small"
                type="info"
              >
                {{ model }}
              </el-tag>
              <span
                v-if="modelCount(row) > modelPreview(row).length"
                class="model-count"
              >
                {{ t('configPages.aiMoreModels', { count: modelCount(row) - modelPreview(row).length }) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('configPages.aiApiKey')"
          width="120"
        >
          <template #default="{ row }">
            <el-tag :type="row.api_key_configured ? 'success' : 'info'">
              {{ row.api_key_configured ? t('configPages.aiKeyConfigured') : t('configPages.aiKeyMissing') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="source"
          :label="t('configPages.aiProviderSource')"
          width="110"
        >
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.source === 'override' ? 'warning' : 'info'"
            >
              {{ sourceLabel(row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('common.action')"
          width="260"
          fixed="right"
        >
          <template #default="{ row }">
            <div class="row-actions">
              <label class="provider-enabled">
                <span>{{ t('common.enable') }}</span>
                <el-switch
                  :model-value="row.enabled"
                  :loading="savingProvider === row.provider"
                  @change="(value) => toggleProviderEnabled(row, value)"
                />
              </label>
              <el-button
                size="small"
                :icon="EditPen"
                @click="openEditDialog(row)"
              >
                {{ t('common.edit') }}
              </el-button>
              <el-popconfirm
                :title="t('configPages.aiDeleteProviderConfirm', { name: row.display_name || row.provider })"
                :confirm-button-text="t('common.delete')"
                :cancel-button-text="t('common.cancel')"
                @confirm="deleteProvider(row)"
              >
                <template #reference>
                  <el-button
                    size="small"
                    type="danger"
                    :icon="Delete"
                    :loading="deletingProvider === row.provider"
                  >
                    {{ t('common.delete') }}
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!loading && providerDrafts.length === 0"
        :description="t('configPages.aiEmptyProviders')"
      />
    </el-card>

    <el-dialog
      v-model="editorVisible"
      :title="editorMode === 'create' ? t('configPages.aiCreateProvider') : t('configPages.aiEditProvider')"
      width="720px"
      destroy-on-close
    >
      <el-form
        label-position="top"
        class="provider-editor"
      >
        <div class="provider-editor-grid">
          <el-form-item :label="t('configPages.aiProviderKey')">
            <el-input
              v-model="editor.provider"
              :disabled="editorMode === 'edit'"
              placeholder="local_openai"
            />
          </el-form-item>
          <el-form-item :label="t('configPages.aiProviderName')">
            <el-input
              v-model="editor.display_name"
              placeholder="Local OpenAI"
            />
          </el-form-item>
          <el-form-item :label="t('configPages.aiProviderType')">
            <el-select v-model="editor.provider_type">
              <el-option
                v-for="option in providerTypeOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('common.enable')">
            <el-switch v-model="editor.enabled" />
          </el-form-item>
        </div>

        <el-form-item :label="t('configPages.aiBaseUrl')">
          <el-input
            v-model="editor.base_url"
            placeholder="https://api.openai.com/v1"
          />
        </el-form-item>
        <div class="provider-editor-grid">
          <el-form-item :label="t('configPages.aiApiKey')">
            <el-input
              v-model="editor.api_key"
              type="password"
              show-password
              :placeholder="editor.api_key_configured ? t('configPages.aiApiKeyKeep') : 'sk-...'"
            />
          </el-form-item>
          <el-form-item :label="t('configPages.aiApiKeyEnv')">
            <el-input
              v-model="editor.api_key_env"
              placeholder="OPENAI_API_KEY"
            />
          </el-form-item>
        </div>
        <el-form-item :label="t('configPages.aiModels')">
          <el-input
            v-model="editor.modelsText"
            type="textarea"
            :rows="6"
            placeholder="gpt-4o&#10;gpt-4o-mini"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editorVisible = false">
            {{ t('common.cancel') }}
          </el-button>
          <el-button
            type="primary"
            :loading="savingProvider === editor.provider"
            @click="saveEditor"
          >
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Delete, EditPen, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import {
  aiObservabilityApi,
  type AIProviderConfig,
  type AIProviderConfigUpdate,
} from '@/api/aiObservability'

type ProviderType = 'litellm' | 'openai_compatible'
type EditorMode = 'create' | 'edit'

interface ProviderDraft {
  provider: string
  display_name: string
  provider_type: ProviderType
  base_url: string
  api_key: string
  api_key_env: string
  api_key_configured: boolean
  modelsText: string
  enabled: boolean
  source: string
}

const { t } = useI18n()

const loading = ref(false)
const savingProvider = ref('')
const deletingProvider = ref('')
const loadError = ref('')
const providerDrafts = ref<ProviderDraft[]>([])
const editorVisible = ref(false)
const editorMode = ref<EditorMode>('create')

const providerTypeOptions = [
  { label: 'LiteLLM', value: 'litellm' as const },
  { label: 'OpenAI Compatible', value: 'openai_compatible' as const },
]

const editor = reactive<ProviderDraft>(emptyDraft())

onMounted(() => {
  void loadConfigs()
})

async function loadConfigs() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await aiObservabilityApi.getAdminAIProviderConfigs()
    providerDrafts.value = response.items.map(toDraft)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : t('configPages.aiLoadFailed')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  assignDraft(editor, emptyDraft())
  editorMode.value = 'create'
  editorVisible.value = true
}

function openEditDialog(draft: ProviderDraft) {
  assignDraft(editor, { ...draft, api_key: '' })
  editorMode.value = 'edit'
  editorVisible.value = true
}

async function saveEditor() {
  const saved = await saveDraft(editor)
  if (!saved) return
  editorVisible.value = false
}

async function toggleProviderEnabled(draft: ProviderDraft, value: string | number | boolean) {
  const enabled = Boolean(value)
  const previousEnabled = draft.enabled
  draft.enabled = enabled
  const saved = await saveDraft(draft, { showSuccess: false })
  if (!saved) {
    draft.enabled = previousEnabled
    return
  }
  ElMessage.success(t('configPages.aiToggleSaved'))
}

async function deleteProvider(draft: ProviderDraft) {
  deletingProvider.value = draft.provider
  try {
    await aiObservabilityApi.deleteAdminAIProviderConfig(draft.provider)
    providerDrafts.value = providerDrafts.value.filter((item) => item.provider !== draft.provider)
    if (editor.provider === draft.provider) {
      editorVisible.value = false
    }
    ElMessage.success(t('configPages.aiDeleteProviderSuccess'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('common.failed'))
  } finally {
    deletingProvider.value = ''
  }
}

async function saveDraft(
  draft: ProviderDraft,
  options: { showSuccess?: boolean } = {},
) {
  const provider = draft.provider.trim()
  if (!provider) {
    ElMessage.error(t('configPages.aiProviderKeyRequired'))
    return null
  }

  const models = parseModels(draft.modelsText)
  if (models.length === 0) {
    ElMessage.error(t('configPages.aiModelsRequired'))
    return null
  }

  const payload: AIProviderConfigUpdate = {
    display_name: draft.display_name.trim() || provider,
    provider_type: draft.provider_type,
    base_url: draft.base_url.trim() || null,
    api_key: draft.api_key.trim() || null,
    api_key_env: draft.api_key_env.trim() || null,
    models,
    enabled: draft.enabled,
  }

  savingProvider.value = provider
  try {
    const saved = await aiObservabilityApi.updateAdminAIProviderConfig(provider, payload)
    const nextDraft = toDraft(saved)
    upsertDraft(nextDraft)
    assignDraft(draft, { ...nextDraft, api_key: '' })
    if (options.showSuccess !== false) {
      ElMessage.success(t('common.success'))
    }
    return nextDraft
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('common.failed'))
    return null
  } finally {
    savingProvider.value = ''
  }
}

function toDraft(config: AIProviderConfig): ProviderDraft {
  return {
    provider: config.provider,
    display_name: config.display_name,
    provider_type: config.provider_type === 'litellm' ? 'litellm' : 'openai_compatible',
    base_url: config.base_url ?? '',
    api_key: '',
    api_key_env: config.api_key_env ?? '',
    api_key_configured: config.api_key_configured,
    modelsText: config.models.join('\n'),
    enabled: config.enabled,
    source: config.source,
  }
}

function emptyDraft(): ProviderDraft {
  return {
    provider: '',
    display_name: '',
    provider_type: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    api_key_env: '',
    api_key_configured: false,
    modelsText: 'gpt-4o-mini',
    enabled: true,
    source: 'override',
  }
}

function parseModels(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function upsertDraft(nextDraft: ProviderDraft) {
  const index = providerDrafts.value.findIndex((item) => item.provider === nextDraft.provider)
  if (index >= 0) {
    providerDrafts.value[index] = nextDraft
    return
  }
  providerDrafts.value.push(nextDraft)
  providerDrafts.value.sort((left, right) => left.provider.localeCompare(right.provider))
}

function assignDraft(target: ProviderDraft, source: ProviderDraft) {
  target.provider = source.provider
  target.display_name = source.display_name
  target.provider_type = source.provider_type
  target.base_url = source.base_url
  target.api_key = source.api_key
  target.api_key_env = source.api_key_env
  target.api_key_configured = source.api_key_configured
  target.modelsText = source.modelsText
  target.enabled = source.enabled
  target.source = source.source
}

function modelPreview(draft: ProviderDraft) {
  return parseModels(draft.modelsText).slice(0, 4)
}

function modelCount(draft: ProviderDraft) {
  return parseModels(draft.modelsText).length
}

function providerTypeLabel(type: ProviderType) {
  return providerTypeOptions.find((option) => option.value === type)?.label || type
}

function sourceLabel(source: string) {
  return source === 'override' ? t('configPages.aiSourceOverride') : t('configPages.aiSourceDefault')
}
</script>

<style scoped>
.ai-provider-config-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.config-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.config-page-header h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 28px;
}

.config-page-header p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
}

.header-actions,
.row-actions,
.provider-enabled,
.dialog-footer,
.model-tags {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.config-alert {
  width: 100%;
}

.provider-list-card {
  min-width: 0;
}

.provider-table {
  width: 100%;
}

.provider-identity {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.provider-identity strong {
  color: var(--text-color-primary);
  font-size: 14px;
  overflow-wrap: anywhere;
}

.provider-identity span,
.model-count {
  color: var(--text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.model-tags {
  flex-wrap: wrap;
}

.row-actions {
  justify-content: flex-end;
  flex-wrap: nowrap;
}

.provider-enabled {
  color: var(--text-color-regular);
  font-size: 13px;
  white-space: nowrap;
}

.provider-editor {
  display: grid;
  gap: 12px;
}

.provider-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.dialog-footer {
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .config-page-header {
    flex-direction: column;
  }

  .header-actions {
    justify-content: flex-start;
  }

  .provider-editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
