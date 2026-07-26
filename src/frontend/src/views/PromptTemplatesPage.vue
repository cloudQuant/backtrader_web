<template>
  <div
    class="prompt-page"
    data-test="prompt-page"
  >
    <section
      class="prompt-hero"
      data-test="prompt-hero"
    >
      <div class="prompt-hero-copy">
        <div class="prompt-kicker">
          {{ t('promptTpl.heroKicker') }}
        </div>
        <h1>{{ t('promptTpl.heroTitle') }}</h1>
        <p>{{ t('promptTpl.heroDesc') }}</p>
      </div>

      <div class="prompt-hero-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="loading"
          @click="loadTemplates"
        >
          {{ t('promptTpl.btnRefresh') }}
        </el-button>
      </div>

      <div
        class="prompt-metrics"
        data-test="prompt-metrics"
      >
        <article class="prompt-metric">
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <span>{{ t('promptTpl.statTemplates') }}</span>
          <strong>{{ templates.length }}</strong>
        </article>
        <article class="prompt-metric">
          <el-icon aria-hidden="true">
            <CircleCheck />
          </el-icon>
          <span>{{ t('promptTpl.statActive') }}</span>
          <strong>{{ activeTemplateCount }}</strong>
        </article>
        <article class="prompt-metric">
          <el-icon aria-hidden="true">
            <DataLine />
          </el-icon>
          <span>{{ t('promptTpl.statRollout') }}</span>
          <strong>{{ rolloutTemplateCount }}</strong>
        </article>
        <article class="prompt-metric">
          <el-icon aria-hidden="true">
            <Collection />
          </el-icon>
          <span>{{ t('promptTpl.statVariables') }}</span>
          <strong>{{ uniqueVariableCount }}</strong>
        </article>
      </div>
    </section>

    <div class="prompt-grid">
      <el-card
        class="prompt-panel prompt-create-panel"
        data-test="prompt-create-panel"
      >
        <template #header>
          <div class="prompt-panel-heading">
            <div>
              <div class="prompt-kicker">
                {{ t('promptTpl.createKicker') }}
              </div>
              <div class="prompt-panel-title">
                {{ t('promptTpl.cardCreate') }}
              </div>
              <p>{{ t('promptTpl.createDesc') }}</p>
            </div>
          </div>
        </template>

        <el-form
          label-position="top"
          class="prompt-form"
        >
          <div class="prompt-form-grid">
            <el-form-item :label="t('promptTpl.formName')">
              <el-input
                v-model="form.name"
                placeholder="knowledge_qa"
              />
            </el-form-item>
            <el-form-item :label="t('promptTpl.formVersion')">
              <el-input
                v-model="form.version"
                placeholder="v1 / canary"
              />
            </el-form-item>
          </div>
          <el-form-item :label="t('promptTpl.formVariables')">
            <el-input
              v-model="form.variablesText"
              :placeholder="t('promptTpl.variablesPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('promptTpl.formContent')">
            <el-input
              v-model="form.content"
              type="textarea"
              :rows="8"
              :placeholder="t('promptTpl.formContentPlaceholder', { var: '{{question}}' })"
            />
          </el-form-item>
          <el-form-item :label="t('promptTpl.formRollout')">
            <div class="rollout-control">
              <el-slider
                v-model="form.rollout_percentage"
                :min="0"
                :max="100"
                :step="5"
              />
              <span>{{ t('promptTpl.rolloutCurrent', { pct: form.rollout_percentage }) }}</span>
            </div>
          </el-form-item>
          <el-button
            type="primary"
            :loading="saving"
            @click="createTemplate"
          >
            {{ t('promptTpl.btnCreate') }}
          </el-button>
        </el-form>
      </el-card>

      <el-card
        class="prompt-panel prompt-registry-panel"
        data-test="prompt-workbench"
      >
        <template #header>
          <div class="prompt-panel-heading">
            <div>
              <div class="prompt-kicker">
                {{ t('promptTpl.registryKicker') }}
              </div>
              <div class="prompt-panel-title">
                {{ t('promptTpl.cardList') }}
              </div>
              <p>{{ t('promptTpl.registryDesc') }}</p>
            </div>
            <div class="prompt-count">
              {{ t('promptTpl.visibleCount', { count: filteredTemplates.length }) }}
              <span>{{ t('promptTpl.totalCount', { count: templates.length }) }}</span>
            </div>
          </div>
        </template>

        <div class="prompt-toolbar">
          <el-input
            v-model="templateSearch"
            clearable
            class="toolbar-search"
            :prefix-icon="Search"
            :placeholder="t('promptTpl.searchPlaceholder')"
          />
          <el-select
            v-model="statusFilter"
            class="toolbar-item"
          >
            <el-option
              :label="t('promptTpl.filterAll')"
              value="all"
            />
            <el-option
              :label="t('promptTpl.filterActive')"
              value="active"
            />
            <el-option
              :label="t('promptTpl.filterDraft')"
              value="draft"
            />
            <el-option
              :label="t('promptTpl.filterArchived')"
              value="archived"
            />
          </el-select>
        </div>

        <div
          v-if="!loading && filteredTemplates.length === 0"
          class="prompt-empty"
          data-test="prompt-empty"
        >
          <el-icon aria-hidden="true">
            <Document />
          </el-icon>
          <strong>{{ t('promptTpl.emptyTitle') }}</strong>
          <span>{{ t('promptTpl.emptyDesc') }}</span>
        </div>

        <template v-else>
          <el-table
            v-loading="loading"
            :data="filteredTemplates"
            stripe
            class="prompt-table"
            data-test="prompt-table"
          >
            <el-table-column
              :label="t('promptTpl.colTemplate')"
              min-width="220"
            >
              <template #default="{ row }">
                <div class="template-identity">
                  <strong>{{ row.name }}</strong>
                  <span>{{ row.version }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('promptTpl.colStatus')"
              width="130"
            >
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('promptTpl.colRollout')"
              width="125"
            >
              <template #default="{ row }">
                <strong>{{ row.rollout_percentage }}%</strong>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('promptTpl.colVariables')"
              min-width="190"
            >
              <template #default="{ row }">
                <div class="variable-tags">
                  <el-tag
                    v-for="variable in row.variables"
                    :key="variable"
                    size="small"
                    type="info"
                  >
                    {{ variable }}
                  </el-tag>
                  <span v-if="row.variables.length === 0">-</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('promptTpl.colCreated')"
              width="170"
            >
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('common.action')"
              fixed="right"
              width="190"
            >
              <template #default="{ row }">
                <div class="row-actions">
                  <el-button
                    link
                    type="primary"
                    :disabled="row.status === 'active'"
                    @click="activateTemplate(row.id)"
                  >
                    {{ t('promptTpl.btnActivate') }}
                  </el-button>
                  <el-button
                    link
                    :icon="View"
                    @click="openTestDrawer(row)"
                  >
                    {{ t('promptTpl.btnTest') }}
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div
            class="prompt-mobile-list"
            data-test="prompt-mobile-list"
          >
            <article
              v-for="template in filteredTemplates"
              :key="template.id"
              class="template-card"
            >
              <div class="template-card-head">
                <div>
                  <strong>{{ template.name }}</strong>
                  <span>{{ template.version }}</span>
                </div>
                <el-tag :type="statusTagType(template.status)">
                  {{ statusLabel(template.status) }}
                </el-tag>
              </div>

              <div class="template-card-grid">
                <span>{{ t('promptTpl.colRollout') }}</span>
                <strong>{{ template.rollout_percentage }}%</strong>
                <span>{{ t('promptTpl.colCreated') }}</span>
                <strong>{{ formatDateTime(template.created_at) }}</strong>
                <span>{{ t('promptTpl.colVariables') }}</span>
                <strong>{{ template.variables.join(', ') || '-' }}</strong>
              </div>

              <pre>{{ template.content }}</pre>

              <div class="template-card-actions">
                <el-button
                  size="small"
                  type="primary"
                  :disabled="template.status === 'active'"
                  @click="activateTemplate(template.id)"
                >
                  {{ t('promptTpl.btnActivate') }}
                </el-button>
                <el-button
                  size="small"
                  :icon="View"
                  @click="openTestDrawer(template)"
                >
                  {{ t('promptTpl.btnTest') }}
                </el-button>
              </div>
            </article>
          </div>
        </template>
      </el-card>
    </div>

    <el-drawer
      v-model="testDrawerVisible"
      :title="t('promptTpl.testDrawerTitle')"
      size="52%"
      class="prompt-test-drawer"
    >
      <div
        v-if="currentTemplate"
        class="prompt-test"
        data-test="prompt-test-drawer"
      >
        <section class="test-summary">
          <div>
            <div class="prompt-kicker">
              {{ t('promptTpl.testKicker') }}
            </div>
            <h3>{{ currentTemplate.name }} / {{ currentTemplate.version }}</h3>
            <p>{{ t('promptTpl.statusLabel', { status: statusLabel(currentTemplate.status), pct: currentTemplate.rollout_percentage }) }}</p>
          </div>
          <el-tag :type="statusTagType(currentTemplate.status)">
            {{ statusLabel(currentTemplate.status) }}
          </el-tag>
        </section>

        <div class="test-section">
          <div class="section-title">
            {{ t('promptTpl.testVariables') }}
          </div>
          <el-input
            v-model="testVariablesText"
            type="textarea"
            :rows="7"
          />
          <el-button
            type="primary"
            :loading="testing"
            @click="testTemplate"
          >
            {{ t('promptTpl.btnRender') }}
          </el-button>
        </div>

        <div class="test-section">
          <div class="section-title">
            {{ t('promptTpl.formContent') }}
          </div>
          <pre>{{ currentTemplate.content }}</pre>
        </div>

        <div
          v-if="testResult"
          class="test-section"
          data-test="prompt-test-result"
        >
          <div class="section-title">
            {{ t('promptTpl.testResult') }}
          </div>
          <div
            v-if="testResult.missing_variables.length > 0"
            class="test-warning"
          >
            {{ t('promptTpl.missingVariables', { vars: testResult.missing_variables.join(', ') }) }}
          </div>
          <pre>{{ testResult.rendered_prompt }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Collection,
  DataLine,
  Document,
  Refresh,
  Search,
  View,
} from '@element-plus/icons-vue'

import {
  promptTemplatesApi,
  type PromptTemplate,
  type PromptTemplateStatus,
  type PromptTemplateTestResponse,
} from '@/api/promptTemplates'

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const templates = ref<PromptTemplate[]>([])
const templateSearch = ref('')
const statusFilter = ref<'all' | PromptTemplateStatus>('all')
const testDrawerVisible = ref(false)
const currentTemplate = ref<PromptTemplate | null>(null)
const testVariablesText = ref('{}')
const testResult = ref<PromptTemplateTestResponse | null>(null)

const form = reactive({
  name: '',
  version: '',
  content: '',
  variablesText: '',
  rollout_percentage: 0,
})

const activeTemplateCount = computed(() => templates.value.filter((item) => item.status === 'active').length)
const rolloutTemplateCount = computed(() => templates.value.filter((item) => item.rollout_percentage > 0).length)
const uniqueVariableCount = computed(() => {
  const variables = new Set<string>()
  templates.value.forEach((template) => {
    template.variables.forEach((variable) => variables.add(variable))
  })
  return variables.size
})
const filteredTemplates = computed(() => {
  const keyword = templateSearch.value.trim().toLowerCase()
  return templates.value.filter((template) => {
    if (statusFilter.value !== 'all' && template.status !== statusFilter.value) return false
    if (!keyword) return true
    return [
      template.name,
      template.version,
      template.status,
      template.content,
      template.created_by,
      ...template.variables,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

function parseVariables(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

async function loadTemplates() {
  loading.value = true
  try {
    const result = await promptTemplatesApi.list()
    templates.value = result.items
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('promptTpl.msgLoadFailed'))
  } finally {
    loading.value = false
  }
}

async function createTemplate() {
  const variables = parseVariables(form.variablesText)
  saving.value = true
  try {
    await promptTemplatesApi.create({
      name: form.name,
      version: form.version,
      content: form.content,
      variables,
      rollout_percentage: form.rollout_percentage,
    })
    ElMessage.success(t('promptTpl.msgCreated'))
    await loadTemplates()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('promptTpl.msgCreateFailed'))
  } finally {
    saving.value = false
  }
}

async function activateTemplate(id: string) {
  try {
    await promptTemplatesApi.activate(id)
    ElMessage.success(t('promptTpl.msgActivated'))
    await loadTemplates()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('promptTpl.msgActivateFailed'))
  }
}

function openTestDrawer(template: PromptTemplate) {
  currentTemplate.value = template
  testResult.value = null
  testVariablesText.value = JSON.stringify(
    Object.fromEntries(template.variables.map((variable) => [variable, sampleValueFor(variable)])),
    null,
    2
  )
  testDrawerVisible.value = true
}

async function testTemplate() {
  if (!currentTemplate.value) return
  testing.value = true
  try {
    testResult.value = await promptTemplatesApi.test(currentTemplate.value.id, parseVariablesObject(testVariablesText.value))
    ElMessage.success(t('promptTpl.msgTested'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('promptTpl.msgTestFailed'))
  } finally {
    testing.value = false
  }
}

function parseVariablesObject(value: string): Record<string, string> {
  const parsed = JSON.parse(value || '{}') as Record<string, unknown>
  return Object.fromEntries(
    Object.entries(parsed).map(([key, item]) => [key, item === undefined || item === null ? '' : String(item)])
  )
}

function sampleValueFor(variable: string) {
  if (variable.toLowerCase().includes('question')) return t('promptTpl.sampleQuestion')
  if (variable.toLowerCase().includes('context')) return t('promptTpl.sampleContext')
  return variable
}

function statusTagType(status: PromptTemplateStatus) {
  if (status === 'active') return 'success'
  if (status === 'archived') return 'info'
  return 'warning'
}

function statusLabel(status: PromptTemplateStatus) {
  if (status === 'active') return t('promptTpl.statusActive')
  if (status === 'archived') return t('promptTpl.statusArchived')
  return t('promptTpl.statusDraft')
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadTemplates)
</script>

<style scoped>
.prompt-page {
  display: grid;
  gap: 24px;
}

.prompt-hero,
.prompt-panel {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.prompt-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.prompt-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.prompt-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.prompt-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.prompt-hero p,
.prompt-panel-heading p,
.test-summary p {
  max-width: 840px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.prompt-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.prompt-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.prompt-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.prompt-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.prompt-metric span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.prompt-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
}

.prompt-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.38fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.prompt-panel {
  min-width: 0;
  box-shadow: none;
}

.prompt-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.prompt-panel :deep(.el-card__body) {
  padding: 18px;
}

.prompt-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.prompt-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.prompt-count {
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

.prompt-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.prompt-form,
.test-section,
.prompt-test {
  display: grid;
  gap: 14px;
}

.prompt-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.rollout-control {
  display: grid;
  gap: 6px;
  width: 100%;
}

.rollout-control span {
  color: var(--text-color-secondary);
  font-size: 12px;
}

.prompt-toolbar {
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
  width: 180px;
}

.prompt-empty {
  display: grid;
  gap: 10px;
  min-height: 200px;
  place-items: center;
  padding: 28px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  text-align: center;
}

.prompt-empty .el-icon {
  color: var(--primary-color);
  font-size: 24px;
}

.prompt-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.prompt-empty span {
  max-width: 560px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.prompt-table {
  width: 100%;
}

.prompt-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.template-identity {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.template-identity strong {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.template-identity span {
  color: var(--text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.variable-tags,
.row-actions,
.template-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.prompt-mobile-list {
  display: none;
  gap: 12px;
}

.template-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.template-card-head,
.test-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.template-card-head > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.template-card-head strong {
  color: var(--text-color-primary);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.template-card-head span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.template-card-grid {
  display: grid;
  grid-template-columns: minmax(100px, 0.35fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.template-card-grid span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.template-card-grid strong {
  color: var(--text-color-primary);
  overflow-wrap: break-word;
}

.template-card pre,
.test-section pre {
  max-height: 260px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.test-summary {
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.test-summary h3 {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 20px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.section-title {
  color: var(--text-color-primary);
  font-weight: 760;
}

.test-warning {
  padding: 10px 12px;
  border: 1px solid var(--warning-color);
  border-radius: 8px;
  background: var(--fill-color-light);
  color: var(--text-color-primary);
}

.prompt-form :deep(.el-input__wrapper),
.prompt-form :deep(.el-textarea__inner),
.prompt-test :deep(.el-textarea__inner) {
  border-radius: 8px;
  background: var(--bg-color-overlay);
  color: var(--text-color-primary);
}

@media (max-width: 1500px) {
  .prompt-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1180px) {
  .prompt-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1100px) {
  .prompt-table {
    display: none;
  }

  .prompt-mobile-list {
    display: grid;
  }
}

@media (max-width: 900px) {
  .prompt-hero {
    grid-template-columns: 1fr;
  }

  .prompt-hero-actions {
    justify-content: flex-start;
  }

  .prompt-panel-heading {
    display: grid;
  }

  .prompt-count {
    width: 100%;
    text-align: left;
  }

  .toolbar-search,
  .toolbar-item {
    width: 100%;
  }

  .prompt-test-drawer :deep(.el-drawer) {
    width: 92% !important;
  }
}

@media (max-width: 620px) {
  .prompt-page {
    gap: 16px;
  }

  .prompt-hero {
    padding: 18px;
  }

  .prompt-hero h1 {
    font-size: 24px;
  }

  .prompt-metrics,
  .prompt-form-grid,
  .template-card-grid {
    grid-template-columns: 1fr;
  }

  .prompt-panel :deep(.el-card__body) {
    padding: 14px;
  }

  .template-card-head,
  .test-summary {
    display: grid;
  }
}
</style>
