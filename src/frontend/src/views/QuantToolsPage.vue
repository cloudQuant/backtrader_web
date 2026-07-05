<template>
  <div class="quant-tools-page">
    <section
      class="quant-tools-hero"
      aria-labelledby="quant-tools-title"
      data-test="quant-tools-page"
    >
      <div class="quant-tools-copy">
        <span class="quant-tools-kicker">{{ t('quantTools.heroKicker') }}</span>
        <h1 id="quant-tools-title">
          {{ t('quantTools.headerTitle') }}
        </h1>
        <p>{{ t('quantTools.headerDesc') }}</p>
      </div>

      <div class="quant-tools-actions">
        <el-button
          type="primary"
          :loading="loading"
          :aria-label="t('quantTools.btnRefreshTools')"
          @click="load"
        >
          <el-icon aria-hidden="true">
            <Refresh />
          </el-icon>
          {{ t('quantTools.btnRefreshTools') }}
        </el-button>

        <el-button
          :loading="loading"
          :disabled="!selectedTool"
          :aria-label="t('quantTools.btnCallTool')"
          @click="callSelectedTool"
        >
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          {{ t('quantTools.btnCallTool') }}
        </el-button>
      </div>

      <div class="quant-tools-stats">
        <article
          v-for="stat in heroStats"
          :key="stat.key"
          class="quant-tools-stat"
        >
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
        </article>
      </div>
    </section>

    <section class="quant-tools-workbench">
      <div class="quant-tools-panel quant-tools-console">
        <header class="quant-tools-panel-head">
          <div>
            <span>{{ t('quantTools.consoleKicker') }}</span>
            <h2>{{ t('quantTools.consoleTitle') }}</h2>
          </div>
          <p>{{ t('quantTools.consoleSubtitle') }}</p>
        </header>

        <div class="quant-tools-field">
          <label>{{ t('quantTools.selectedTool') }}</label>
          <el-select
            v-model="selectedTool"
            class="quant-tools-select"
          >
            <el-option
              v-for="tool in tools"
              :key="toolName(tool)"
              :label="toolName(tool)"
              :value="toolName(tool)"
            />
          </el-select>
        </div>

        <div
          v-if="selectedToolMeta"
          class="quant-tool-meta"
        >
          <div>
            <span>{{ t('quantTools.colAuth') }}</span>
            <strong>{{ toolText(selectedToolMeta, 'auth_level') }}</strong>
          </div>
          <div>
            <span>{{ t('quantTools.colTimeoutMs') }}</span>
            <strong>{{ toolText(selectedToolMeta, 'timeout_ms') }}</strong>
          </div>
          <div>
            <span>{{ t('quantTools.colRateLimit') }}</span>
            <strong>{{ toolText(selectedToolMeta, 'rate_limit_per_user_per_min') }}</strong>
          </div>
          <div>
            <span>{{ t('quantTools.requiresConfirmation') }}</span>
            <strong>{{ formatBoolean(toolBool(selectedToolMeta, 'requires_confirmation')) }}</strong>
          </div>
        </div>

        <div class="quant-tools-field">
          <label>{{ t('quantTools.requestPayload') }}</label>
          <el-input
            v-model="payloadText"
            type="textarea"
            :rows="10"
            class="quant-tools-payload"
          />
        </div>

        <div
          v-if="errorMessage"
          class="quant-tools-error"
          role="alert"
        >
          {{ errorMessage }}
        </div>
      </div>

      <aside class="quant-tools-side">
        <section class="quant-tools-panel">
          <header class="quant-tools-side-head">
            <span>{{ t('quantTools.resultTitle') }}</span>
            <p>{{ result ? t('quantTools.resultReady') : t('quantTools.resultEmpty') }}</p>
          </header>
          <pre
            v-if="result"
            class="quant-tools-result"
          >{{ resultPreview }}</pre>
          <div
            v-else
            class="quant-tools-empty"
          >
            <el-icon aria-hidden="true">
              <DataAnalysis />
            </el-icon>
            <span>{{ t('quantTools.noResult') }}</span>
          </div>
        </section>

        <section class="quant-tools-panel">
          <header class="quant-tools-side-head">
            <span>{{ t('quantTools.registrySummaryTitle') }}</span>
            <p>{{ t('quantTools.registrySummaryDesc') }}</p>
          </header>
          <div class="quant-tools-registry-list">
            <article
              v-for="tool in tools.slice(0, 4)"
              :key="toolName(tool)"
            >
              <strong>{{ toolName(tool) }}</strong>
              <span>{{ toolText(tool, 'auth_level') }} · {{ toolText(tool, 'timeout_ms') }}ms</span>
            </article>
          </div>
        </section>
      </aside>
    </section>

    <section class="quant-tools-panel quant-tools-table-panel">
      <header class="quant-tools-panel-head">
        <div>
          <span>{{ t('quantTools.registryKicker') }}</span>
          <h2>{{ t('quantTools.registryTitle') }}</h2>
        </div>
        <p>{{ t('quantTools.registrySubtitle') }}</p>
      </header>

      <el-table
        :data="tools"
        :empty-text="loading ? t('common.loading') : t('quantTools.emptyTools')"
        class="quant-tools-table"
      >
        <el-table-column
          prop="name"
          :label="t('quantTools.colName')"
          min-width="180"
        />
        <el-table-column
          prop="description"
          :label="t('quantTools.colDesc')"
          min-width="260"
        />
        <el-table-column
          prop="auth_level"
          :label="t('quantTools.colAuth')"
          width="120"
        />
        <el-table-column
          prop="timeout_ms"
          :label="t('quantTools.colTimeoutMs')"
          width="130"
        />
        <el-table-column
          prop="rate_limit_per_user_per_min"
          :label="t('quantTools.colRateLimit')"
          width="130"
        />
      </el-table>

      <div class="quant-tools-mobile-list">
        <article
          v-for="tool in tools"
          :key="toolName(tool)"
          class="quant-tools-mobile-card"
        >
          <header>
            <strong>{{ toolName(tool) }}</strong>
            <span>{{ toolText(tool, 'auth_level') }}</span>
          </header>
          <p>{{ toolText(tool, 'description') }}</p>
          <dl>
            <div>
              <dt>{{ t('quantTools.colTimeoutMs') }}</dt>
              <dd>{{ toolText(tool, 'timeout_ms') }}</dd>
            </div>
            <div>
              <dt>{{ t('quantTools.colRateLimit') }}</dt>
              <dd>{{ toolText(tool, 'rate_limit_per_user_per_min') }}</dd>
            </div>
          </dl>
        </article>
        <div
          v-if="tools.length === 0"
          class="quant-tools-mobile-empty"
        >
          {{ loading ? t('common.loading') : t('quantTools.emptyTools') }}
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Connection, DataAnalysis, Refresh } from '@element-plus/icons-vue'
import { getErrorMessage } from '@/api'
import { marketIntelApi } from '@/api/marketIntel'

const { t } = useI18n()

const loading = ref(false)
const tools = ref<Array<Record<string, unknown>>>([])
const result = ref<Record<string, unknown> | null>(null)
const selectedTool = ref('markets.get_quote')
const payloadText = ref('{\n  "symbol": "RB2510"\n}')
const errorMessage = ref('')

const selectedToolMeta = computed(() =>
  tools.value.find(tool => toolName(tool) === selectedTool.value) ?? null,
)

const heroStats = computed(() => [
  {
    key: 'tool-count',
    label: t('quantTools.metricToolCount'),
    value: String(tools.value.length),
  },
  {
    key: 'selected-tool',
    label: t('quantTools.metricSelectedTool'),
    value: selectedTool.value || '--',
  },
  {
    key: 'auth-level',
    label: t('quantTools.metricAuthLevel'),
    value: selectedToolMeta.value ? toolText(selectedToolMeta.value, 'auth_level') : '--',
  },
  {
    key: 'confirmation',
    label: t('quantTools.metricConfirmation'),
    value: selectedToolMeta.value
      ? formatBoolean(toolBool(selectedToolMeta.value, 'requires_confirmation'))
      : '--',
  },
])

const resultPreview = computed(() => JSON.stringify(result.value, null, 2))

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await marketIntelApi.listQuantTools()
    tools.value = response.tools
    const firstTool = response.tools[0]
    if (firstTool?.name) {
      selectedTool.value = String(firstTool.name)
    }
  } catch (error: unknown) {
    errorMessage.value = getErrorMessage(error, t('quantTools.msgLoadFailed'))
  } finally {
    loading.value = false
  }
}

async function callSelectedTool() {
  let input: Record<string, unknown>
  try {
    input = JSON.parse(payloadText.value || '{}') as Record<string, unknown>
  } catch {
    ElMessage.warning(t('quantTools.msgInvalidJson'))
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    result.value = await marketIntelApi.callQuantTool({
      tool_name: selectedTool.value,
      input,
    })
  } catch (error: unknown) {
    errorMessage.value = getErrorMessage(error, t('quantTools.msgCallFailed'))
  } finally {
    loading.value = false
  }
}

function toolName(tool: Record<string, unknown>): string {
  return String(tool.name ?? '')
}

function toolText(tool: Record<string, unknown>, key: string): string {
  const value = tool[key]
  if (value === null || value === undefined || value === '') return '--'
  return String(value)
}

function toolBool(tool: Record<string, unknown>, key: string): boolean {
  return Boolean(tool[key])
}

function formatBoolean(value: boolean): string {
  return value ? t('common.yes') : t('common.no')
}

void load()
</script>

<style scoped>
.quant-tools-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--text-color-primary);
}

.quant-tools-hero,
.quant-tools-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 10px 28px var(--shadow-color);
}

.quant-tools-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  padding: 20px;
}

.quant-tools-copy {
  min-width: 0;
}

.quant-tools-kicker,
.quant-tools-panel-head span {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
}

.quant-tools-copy h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
}

.quant-tools-copy p {
  max-width: 820px;
  margin: 8px 0 0;
  color: var(--text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.quant-tools-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.quant-tools-actions :deep(.el-button) {
  gap: 6px;
}

.quant-tools-stats {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.quant-tools-stat {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.quant-tools-stat span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
}

.quant-tools-stat strong {
  display: block;
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quant-tools-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
  gap: 18px;
  align-items: start;
}

.quant-tools-panel {
  min-width: 0;
  padding: 18px;
}

.quant-tools-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.quant-tools-panel-head h2 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 740;
  line-height: 1.25;
}

.quant-tools-panel-head p {
  flex: 0 1 460px;
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
  text-align: right;
}

.quant-tools-console {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.quant-tools-field {
  display: grid;
  gap: 8px;
}

.quant-tools-field label {
  color: var(--text-color-regular);
  font-size: 13px;
  font-weight: 700;
}

.quant-tools-select {
  width: 100%;
}

.quant-tool-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.quant-tool-meta div {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.quant-tool-meta span {
  display: block;
  margin-bottom: 5px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.quant-tool-meta strong {
  display: block;
  color: var(--text-color-primary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.quant-tools-payload :deep(.el-textarea__inner) {
  min-height: 240px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 1.55;
}

.quant-tools-error {
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--danger-color) 45%, var(--border-color));
  border-radius: 8px;
  background: color-mix(in srgb, var(--danger-color) 10%, var(--bg-color));
  color: var(--danger-color);
  font-size: 13px;
}

.quant-tools-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.quant-tools-side-head span {
  display: block;
  color: var(--text-color-primary);
  font-size: 15px;
  font-weight: 740;
}

.quant-tools-side-head p {
  margin: 6px 0 0;
  color: var(--text-color-secondary);
  font-size: 13px;
  line-height: 1.45;
}

.quant-tools-result {
  max-height: 440px;
  margin: 14px 0 0;
  padding: 14px;
  overflow: auto;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.55;
}

.quant-tools-empty {
  display: flex;
  min-height: 160px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-color-secondary);
  font-size: 13px;
}

.quant-tools-registry-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.quant-tools-registry-list article {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.quant-tools-registry-list strong,
.quant-tools-registry-list span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quant-tools-registry-list strong {
  color: var(--text-color-primary);
  font-size: 13px;
}

.quant-tools-registry-list span {
  margin-top: 4px;
  color: var(--text-color-secondary);
  font-size: 12px;
}

.quant-tools-table {
  --el-table-header-bg-color: var(--fill-color-lighter);
  --el-table-tr-bg-color: var(--bg-color);
  --el-table-row-hover-bg-color: var(--fill-color-light);
  --el-table-border-color: var(--border-color-light);
  --el-table-text-color: var(--text-color-regular);
  --el-table-header-text-color: var(--text-color-secondary);
}

.quant-tools-mobile-list {
  display: none;
}

.quant-tools-mobile-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.quant-tools-mobile-card + .quant-tools-mobile-card {
  margin-top: 10px;
}

.quant-tools-mobile-card header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.quant-tools-mobile-card strong {
  min-width: 0;
  color: var(--text-color-primary);
  font-size: 13px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.quant-tools-mobile-card header span {
  flex: none;
  padding: 3px 7px;
  border: 1px solid var(--border-color-light);
  border-radius: 999px;
  background: var(--bg-color);
  color: var(--text-color-secondary);
  font-size: 11px;
  line-height: 1.2;
}

.quant-tools-mobile-card p {
  margin: 10px 0 0;
  color: var(--text-color-regular);
  font-size: 12px;
  line-height: 1.55;
}

.quant-tools-mobile-card dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0 0;
}

.quant-tools-mobile-card dl div {
  min-width: 0;
  padding: 9px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.quant-tools-mobile-card dt,
.quant-tools-mobile-card dd {
  margin: 0;
}

.quant-tools-mobile-card dt {
  color: var(--text-color-secondary);
  font-size: 11px;
  line-height: 1.25;
}

.quant-tools-mobile-card dd {
  margin-top: 4px;
  color: var(--text-color-primary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.quant-tools-mobile-empty {
  padding: 18px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-color-secondary);
  text-align: center;
}

.quant-tools-page :deep(.el-input__wrapper),
.quant-tools-page :deep(.el-select__wrapper) {
  background: var(--fill-color-lighter);
}

@media (max-width: 1180px) {
  .quant-tools-hero,
  .quant-tools-workbench {
    grid-template-columns: 1fr;
  }

  .quant-tools-actions {
    justify-content: flex-start;
  }

  .quant-tools-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .quant-tools-page {
    gap: 14px;
  }

  .quant-tools-hero,
  .quant-tools-panel {
    padding: 14px;
  }

  .quant-tools-copy h1 {
    font-size: 22px;
  }

  .quant-tools-actions :deep(.el-button) {
    width: 100%;
    justify-content: center;
  }

  .quant-tools-stats,
  .quant-tool-meta {
    grid-template-columns: 1fr;
  }

  .quant-tools-panel-head {
    flex-direction: column;
  }

  .quant-tools-panel-head p {
    flex-basis: auto;
    text-align: left;
  }

  .quant-tools-table {
    display: none;
  }

  .quant-tools-mobile-list {
    display: block;
  }
}
</style>
