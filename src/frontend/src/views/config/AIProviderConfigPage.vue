<template>
  <div
    class="ai-provider-page"
    data-test="ai-provider-page"
  >
    <section
      class="ai-provider-hero"
      data-test="ai-provider-hero"
    >
      <div class="ai-provider-hero-copy">
        <div class="provider-kicker">
          {{ t('configPages.aiProviderHeroKicker') }}
        </div>
        <h1>{{ t('configPages.aiProviderHeroTitle') }}</h1>
        <p>{{ t('configPages.aiProviderHeroDesc') }}</p>
      </div>

      <div class="ai-provider-hero-actions">
        <el-button
          :icon="Refresh"
          :loading="loading"
          @click="loadConfigs"
        >
          {{ t('configPages.aiRefreshProviders') }}
        </el-button>
        <el-button
          type="primary"
          :icon="Plus"
          @click="openCreateDialog"
        >
          {{ t('configPages.aiAddProvider') }}
        </el-button>
      </div>

      <div
        class="provider-metrics"
        data-test="ai-provider-metrics"
      >
        <article class="provider-metric">
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          <span>{{ t('configPages.aiStatProviders') }}</span>
          <strong>{{ providerDrafts.length }}</strong>
        </article>
        <article class="provider-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('configPages.aiStatEnabled') }}</span>
          <strong>{{ enabledProviderCount }}</strong>
        </article>
        <article class="provider-metric">
          <el-icon aria-hidden="true">
            <Collection />
          </el-icon>
          <span>{{ t('configPages.aiStatModels') }}</span>
          <strong>{{ totalModelCount }}</strong>
        </article>
        <article class="provider-metric">
          <el-icon aria-hidden="true">
            <Key />
          </el-icon>
          <span>{{ t('configPages.aiStatKeys') }}</span>
          <strong>{{ configuredKeyCount }}</strong>
        </article>
      </div>
    </section>

    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      class="provider-alert"
      data-test="ai-provider-alert"
    >
      {{ loadError }}
    </el-alert>

    <el-card
      class="provider-workbench"
      data-test="ai-provider-workbench"
    >
      <template #header>
        <div class="provider-panel-heading">
          <div>
            <div class="provider-kicker">
              {{ t('configPages.aiProviderWorkbenchKicker') }}
            </div>
            <div class="provider-panel-title">
              {{ t('configPages.aiProviderWorkbenchTitle') }}
            </div>
            <p>{{ t('configPages.aiProviderWorkbenchDesc') }}</p>
          </div>
          <div class="provider-count">
            {{ t('configPages.aiVisibleProviders', { count: filteredDrafts.length }) }}
            <span>{{ t('configPages.aiTotalProviders', { count: providerDrafts.length }) }}</span>
          </div>
        </div>
      </template>

      <div class="provider-toolbar">
        <el-input
          v-model="providerSearch"
          clearable
          class="toolbar-search"
          :prefix-icon="Search"
          :placeholder="t('configPages.aiProviderSearchPh')"
        />
        <el-select
          v-model="statusFilter"
          class="toolbar-item"
        >
          <el-option
            :label="t('configPages.aiFilterAll')"
            value="all"
          />
          <el-option
            :label="t('configPages.aiFilterEnabled')"
            value="enabled"
          />
          <el-option
            :label="t('configPages.aiFilterDisabled')"
            value="disabled"
          />
        </el-select>
        <el-select
          v-model="typeFilter"
          class="toolbar-item"
        >
          <el-option
            :label="t('configPages.aiTypeAll')"
            value="all"
          />
          <el-option
            v-for="option in providerTypeOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>

      <div
        v-if="!loading && filteredDrafts.length === 0"
        class="provider-empty"
        data-test="ai-provider-empty"
      >
        <el-icon aria-hidden="true">
          <Connection />
        </el-icon>
        <strong>{{ t('configPages.aiEmptyProvidersTitle') }}</strong>
        <span>{{ t('configPages.aiEmptyProviders') }}</span>
        <el-button
          type="primary"
          :icon="Plus"
          @click="openCreateDialog"
        >
          {{ t('configPages.aiAddProvider') }}
        </el-button>
      </div>

      <template v-else>
        <el-table
          v-loading="loading"
          :data="filteredDrafts"
          row-key="provider"
          stripe
          class="provider-table"
          data-test="ai-provider-table"
        >
          <el-table-column
            :label="t('configPages.aiProviderName')"
            min-width="220"
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
            :label="t('configPages.aiProviderType')"
            width="145"
          >
            <template #default="{ row }">
              <el-tag size="small">
                {{ providerTypeLabel(row.provider_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('configPages.aiModels')"
            min-width="220"
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
            :label="t('configPages.aiAccessState')"
            width="140"
          >
            <template #default="{ row }">
              <el-tag :type="row.api_key_configured ? 'success' : 'info'">
                {{ row.api_key_configured ? t('configPages.aiKeyConfigured') : t('configPages.aiKeyMissing') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('configPages.aiProviderStatus')"
            width="145"
          >
            <template #default="{ row }">
              <div class="status-stack">
                <el-tag :type="row.enabled ? 'success' : 'info'">
                  {{ row.enabled ? t('configPages.aiEnabled') : t('configPages.aiDisabled') }}
                </el-tag>
                <span>{{ sourceLabel(row.source) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('common.action')"
            fixed="right"
            width="230"
          >
            <template #default="{ row }">
              <div class="row-actions">
                <label class="provider-enabled">
                  <span>{{ row.enabled ? t('configPages.aiEnabled') : t('configPages.aiDisabled') }}</span>
                  <el-switch
                    :model-value="row.enabled"
                    :loading="savingProvider === row.provider"
                    @change="(value: string | number | boolean) => toggleProviderEnabled(row, value)"
                  />
                </label>
                <el-button
                  link
                  type="primary"
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
                      link
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

        <div
          class="provider-mobile-list"
          data-test="ai-provider-mobile-list"
        >
          <article
            v-for="provider in filteredDrafts"
            :key="provider.provider"
            class="provider-card"
          >
            <div class="provider-card-head">
              <div>
                <strong>{{ provider.display_name || provider.provider }}</strong>
                <span>{{ provider.provider }}</span>
              </div>
              <el-tag :type="provider.enabled ? 'success' : 'info'">
                {{ provider.enabled ? t('configPages.aiEnabled') : t('configPages.aiDisabled') }}
              </el-tag>
            </div>

            <div class="provider-card-grid">
              <span>{{ t('configPages.aiProviderType') }}</span>
              <strong>{{ providerTypeLabel(provider.provider_type) }}</strong>
              <span>{{ t('configPages.aiBaseUrl') }}</span>
              <strong>{{ provider.base_url || '-' }}</strong>
              <span>{{ t('configPages.aiApiKey') }}</span>
              <strong>{{ provider.api_key_configured ? t('configPages.aiKeyConfigured') : t('configPages.aiKeyMissing') }}</strong>
              <span>{{ t('configPages.aiProviderSource') }}</span>
              <strong>{{ sourceLabel(provider.source) }}</strong>
            </div>

            <div class="model-tags">
              <el-tag
                v-for="model in modelPreview(provider)"
                :key="model"
                size="small"
                type="info"
              >
                {{ model }}
              </el-tag>
              <span
                v-if="modelCount(provider) > modelPreview(provider).length"
                class="model-count"
              >
                {{ t('configPages.aiMoreModels', { count: modelCount(provider) - modelPreview(provider).length }) }}
              </span>
            </div>

            <div class="provider-card-actions">
              <label class="provider-enabled">
                <span>{{ provider.enabled ? t('configPages.aiEnabled') : t('configPages.aiDisabled') }}</span>
                <el-switch
                  :model-value="provider.enabled"
                  :loading="savingProvider === provider.provider"
                  @change="(value: string | number | boolean) => toggleProviderEnabled(provider, value)"
                />
              </label>
              <el-button
                size="small"
                type="primary"
                :icon="EditPen"
                @click="openEditDialog(provider)"
              >
                {{ t('common.edit') }}
              </el-button>
              <el-popconfirm
                :title="t('configPages.aiDeleteProviderConfirm', { name: provider.display_name || provider.provider })"
                :confirm-button-text="t('common.delete')"
                :cancel-button-text="t('common.cancel')"
                @confirm="deleteProvider(provider)"
              >
                <template #reference>
                  <el-button
                    size="small"
                    type="danger"
                    :icon="Delete"
                    :loading="deletingProvider === provider.provider"
                  >
                    {{ t('common.delete') }}
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
          </article>
        </div>
      </template>
    </el-card>

    <el-dialog
      v-model="editorVisible"
      :title="editorMode === 'create' ? t('configPages.aiCreateProvider') : t('configPages.aiEditProvider')"
      width="720px"
      destroy-on-close
      class="provider-editor-dialog"
    >
      <el-form
        label-position="top"
        class="provider-editor"
      >
        <section class="editor-section">
          <div>
            <div class="provider-kicker">
              {{ t('configPages.aiEditorIdentityKicker') }}
            </div>
            <h3>{{ t('configPages.aiEditorIdentityTitle') }}</h3>
          </div>
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
        </section>

        <section class="editor-section">
          <div>
            <div class="provider-kicker">
              {{ t('configPages.aiEditorAccessKicker') }}
            </div>
            <h3>{{ t('configPages.aiEditorAccessTitle') }}</h3>
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
        </section>

        <section class="editor-section">
          <div>
            <div class="provider-kicker">
              {{ t('configPages.aiEditorModelsKicker') }}
            </div>
            <h3>{{ t('configPages.aiEditorModelsTitle') }}</h3>
          </div>
          <el-form-item :label="t('configPages.aiModels')">
            <el-input
              v-model="editor.modelsText"
              type="textarea"
              :rows="6"
              placeholder="gpt-4o&#10;gpt-4o-mini"
            />
          </el-form-item>
        </section>
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
import { computed, onMounted, reactive, ref } from 'vue'
import {
  CircleCheck,
  Collection,
  Connection,
  Delete,
  EditPen,
  Key,
  Plus,
  Refresh,
  Search,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

import {
  aiObservabilityApi,
  type AIProviderConfig,
  type AIProviderConfigUpdate,
} from '@/api/aiObservability'

type ProviderType = 'litellm' | 'openai_compatible'
type EditorMode = 'create' | 'edit'
type StatusFilter = 'all' | 'enabled' | 'disabled'
type TypeFilter = 'all' | ProviderType

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
const providerSearch = ref('')
const statusFilter = ref<StatusFilter>('all')
const typeFilter = ref<TypeFilter>('all')

const providerTypeOptions = [
  { label: 'LiteLLM', value: 'litellm' as const },
  { label: 'OpenAI Compatible', value: 'openai_compatible' as const },
]

const editor = reactive<ProviderDraft>(emptyDraft())

const enabledProviderCount = computed(() => providerDrafts.value.filter((item) => item.enabled).length)
const configuredKeyCount = computed(() => providerDrafts.value.filter((item) => item.api_key_configured || item.api_key_env).length)
const totalModelCount = computed(() =>
  providerDrafts.value.reduce((sum, item) => sum + parseModels(item.modelsText).length, 0)
)
const filteredDrafts = computed(() => {
  const keyword = providerSearch.value.trim().toLowerCase()
  return providerDrafts.value.filter((item) => {
    if (statusFilter.value === 'enabled' && !item.enabled) return false
    if (statusFilter.value === 'disabled' && item.enabled) return false
    if (typeFilter.value !== 'all' && item.provider_type !== typeFilter.value) return false
    if (!keyword) return true
    return [
      item.provider,
      item.display_name,
      item.provider_type,
      item.base_url,
      item.api_key_env,
      item.source,
      ...parseModels(item.modelsText),
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

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
.ai-provider-page {
  display: grid;
  gap: 24px;
}

.ai-provider-hero,
.provider-workbench {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.ai-provider-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.ai-provider-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.provider-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.ai-provider-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.ai-provider-hero p,
.provider-panel-heading p {
  max-width: 840px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.ai-provider-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.provider-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.provider-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.provider-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.provider-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.provider-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.provider-alert {
  border-radius: 8px;
}

.provider-workbench {
  min-width: 0;
  box-shadow: none;
}

.provider-workbench :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.provider-workbench :deep(.el-card__body) {
  padding: 18px;
}

.provider-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.provider-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.provider-count {
  display: grid;
  flex: none;
  gap: 4px;
  min-width: 120px;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 720;
  line-height: 1.35;
  text-align: right;
}

.provider-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.provider-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-search {
  width: min(380px, 100%);
}

.toolbar-item {
  width: 190px;
}

.provider-empty {
  display: grid;
  gap: 10px;
  min-height: 220px;
  place-items: center;
  padding: 28px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  text-align: center;
}

.provider-empty .el-icon {
  color: var(--primary-color);
  font-size: 24px;
}

.provider-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.provider-empty span {
  max-width: 560px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.provider-table {
  width: 100%;
}

.provider-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.provider-identity {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.provider-identity strong {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.provider-identity span,
.model-count {
  color: var(--text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.model-tags,
.row-actions,
.provider-enabled,
.dialog-footer,
.provider-card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-tags {
  flex-wrap: wrap;
}

.status-stack {
  display: grid;
  gap: 6px;
  justify-items: start;
}

.status-stack span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.25;
}

.row-actions {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.provider-enabled {
  color: var(--text-color-regular);
  font-size: 13px;
  white-space: nowrap;
}

.provider-mobile-list {
  display: none;
  gap: 12px;
}

.provider-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.provider-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.provider-card-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.provider-card-head strong {
  color: var(--text-color-primary);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.provider-card-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.provider-card-grid {
  display: grid;
  grid-template-columns: minmax(110px, 0.36fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.provider-card-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.provider-card-grid strong {
  color: var(--text-color-primary);
  overflow-wrap: break-word;
}

.provider-card-actions {
  flex-wrap: wrap;
}

.provider-editor {
  display: grid;
  gap: 14px;
}

.editor-section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.editor-section h3 {
  margin: 4px 0 0;
  color: var(--text-color-primary);
  font-size: 16px;
  line-height: 1.25;
}

.provider-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.provider-editor :deep(.el-input__wrapper),
.provider-editor :deep(.el-textarea__inner) {
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
}

.dialog-footer {
  justify-content: flex-end;
}

@media (max-width: 1100px) {
  .provider-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .provider-table {
    display: none;
  }

  .provider-mobile-list {
    display: grid;
  }
}

@media (max-width: 900px) {
  .ai-provider-hero {
    grid-template-columns: 1fr;
  }

  .ai-provider-hero-actions {
    justify-content: flex-start;
  }

  .provider-panel-heading {
    display: grid;
  }

  .provider-count {
    width: 100%;
    text-align: left;
  }

  .toolbar-search,
  .toolbar-item {
    width: 100%;
  }
}

@media (max-width: 620px) {
  .ai-provider-page {
    gap: 16px;
  }

  .ai-provider-hero {
    padding: 18px;
  }

  .ai-provider-hero h1 {
    font-size: 24px;
  }

  .provider-metrics {
    grid-template-columns: 1fr;
  }

  .provider-workbench :deep(.el-card__body) {
    padding: 14px;
  }

  .provider-card-head {
    display: grid;
  }

  .provider-card-grid {
    grid-template-columns: 1fr;
  }

  .provider-editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
