<template>
  <div
    class="settings-page"
    data-test="settings-page"
  >
    <section
      class="settings-hero"
      data-test="settings-hero"
    >
      <div class="settings-hero-copy">
        <div class="settings-kicker">
          {{ t('userSettings.heroKicker') }}
        </div>
        <h1>{{ t('userSettings.heroTitle') }}</h1>
        <p>{{ t('userSettings.heroDesc') }}</p>
        <div class="settings-tag-row">
          <el-tag
            size="small"
            type="success"
          >
            {{ accountRoleLabel }}
          </el-tag>
          <el-tag
            size="small"
            :type="accountStatusType"
          >
            {{ accountStatusLabel }}
          </el-tag>
        </div>
      </div>

      <div class="settings-profile-panel">
        <el-avatar
          class="settings-avatar"
          :size="56"
        >
          {{ userInitial }}
        </el-avatar>
        <div>
          <strong>{{ userForm.username || t('userSettings.notAvailable') }}</strong>
          <span>{{ userForm.email || t('userSettings.notAvailable') }}</span>
        </div>
        <div class="settings-profile-meta">
          <span>{{ t('userSettings.formCreatedAt') }}</span>
          <strong>{{ userForm.createdAt || t('userSettings.notAvailable') }}</strong>
          <span>{{ t('userSettings.formDefaultModel') }}</span>
          <strong>{{ selectedAIModelLabel }}</strong>
        </div>
      </div>

      <div
        class="settings-metrics"
        data-test="settings-metrics"
      >
        <article class="settings-metric">
          <el-icon aria-hidden="true">
            <UserIcon />
          </el-icon>
          <span>{{ t('userSettings.metricAccount') }}</span>
          <strong>{{ accountStatusLabel }}</strong>
          <small>{{ t('userSettings.metricAccountHelper') }}</small>
        </article>
        <article class="settings-metric">
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          <span>{{ t('userSettings.formAiCallCount') }}</span>
          <strong>{{ formatInteger(aiUsageSummary.total_calls) }}</strong>
          <small>{{ t('userSettings.metricAiCallsHelper') }}</small>
        </article>
        <article class="settings-metric">
          <el-icon aria-hidden="true">
            <Cpu />
          </el-icon>
          <span>{{ t('userSettings.formAiTokens') }}</span>
          <strong>{{ formatInteger(aiUsageSummary.total_tokens) }}</strong>
          <small>{{ t('userSettings.metricTokensHelper') }}</small>
        </article>
        <article class="settings-metric">
          <el-icon aria-hidden="true">
            <Money />
          </el-icon>
          <span>{{ t('userSettings.formAiCost') }}</span>
          <strong>{{ formatUsd(aiUsageSummary.estimated_cost_usd) }}</strong>
          <small>{{ t('userSettings.metricCostHelper') }}</small>
        </article>
      </div>
    </section>

    <div class="settings-layout">
      <section class="settings-stack">
        <el-card
          class="settings-panel"
          data-test="settings-profile-card"
        >
          <template #header>
            <div class="settings-panel-heading">
              <div>
                <div class="settings-kicker">
                  {{ t('userSettings.cardProfile') }}
                </div>
                <h2>{{ t('userSettings.profileTitle') }}</h2>
                <p>{{ t('userSettings.profileDesc') }}</p>
              </div>
              <el-icon aria-hidden="true">
                <UserIcon />
              </el-icon>
            </div>
          </template>

          <div class="settings-detail-grid">
            <span>{{ t('userSettings.formUsername') }}</span>
            <strong>{{ userForm.username || t('userSettings.notAvailable') }}</strong>
            <span>{{ t('userSettings.formEmail') }}</span>
            <strong>{{ userForm.email || t('userSettings.notAvailable') }}</strong>
            <span>{{ t('userSettings.formCreatedAt') }}</span>
            <strong>{{ userForm.createdAt || t('userSettings.notAvailable') }}</strong>
          </div>
        </el-card>

        <el-card
          class="settings-panel"
          data-test="settings-security-card"
        >
          <template #header>
            <div class="settings-panel-heading">
              <div>
                <div class="settings-kicker">
                  {{ t('userSettings.cardChangePwd') }}
                </div>
                <h2>{{ t('userSettings.securityTitle') }}</h2>
                <p>{{ t('userSettings.securityDesc') }}</p>
              </div>
              <el-icon aria-hidden="true">
                <Lock />
              </el-icon>
            </div>
          </template>

          <el-form
            class="settings-form"
            :model="passwordForm"
            label-position="top"
          >
            <el-form-item :label="t('userSettings.formOldPassword')">
              <el-input
                v-model="passwordForm.oldPassword"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item :label="t('userSettings.formNewPassword')">
              <el-input
                v-model="passwordForm.newPassword"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item :label="t('userSettings.formConfirmPassword')">
              <el-input
                v-model="passwordForm.confirmPassword"
                type="password"
                show-password
              />
            </el-form-item>
            <div class="settings-action-row">
              <span>{{ t('userSettings.securityHint') }}</span>
              <el-button
                type="primary"
                :icon="Lock"
                :loading="changingPassword"
                @click="changePassword"
              >
                {{ t('userSettings.btnChangePwd') }}
              </el-button>
            </div>
          </el-form>
        </el-card>
      </section>

      <section class="settings-stack">
        <el-card
          class="settings-panel"
          data-test="settings-ai-usage-card"
        >
          <template #header>
            <div class="settings-panel-heading">
              <div>
                <div class="settings-kicker">
                  {{ t('userSettings.cardAiUsage') }}
                </div>
                <h2>{{ t('userSettings.aiUsageTitle') }}</h2>
                <p>{{ t('userSettings.aiUsageDesc') }}</p>
              </div>
              <el-icon aria-hidden="true">
                <Money />
              </el-icon>
            </div>
          </template>

          <div class="settings-usage-grid">
            <div>
              <span>{{ t('userSettings.formAiCallCount') }}</span>
              <strong>{{ formatInteger(aiUsageSummary.total_calls) }}</strong>
            </div>
            <div>
              <span>{{ t('userSettings.formAiTokens') }}</span>
              <strong>{{ formatInteger(aiUsageSummary.total_tokens) }}</strong>
            </div>
            <div>
              <span>{{ t('userSettings.formAiCost') }}</span>
              <strong>{{ formatUsd(aiUsageSummary.estimated_cost_usd) }}</strong>
            </div>
          </div>
        </el-card>

        <el-card
          class="settings-panel"
          data-test="settings-ai-model-card"
        >
          <template #header>
            <div class="settings-panel-heading">
              <div>
                <div class="settings-kicker">
                  {{ t('userSettings.cardAiModelPref') }}
                </div>
                <h2>{{ t('userSettings.modelPrefTitle') }}</h2>
                <p>{{ t('userSettings.modelPrefDesc') }}</p>
              </div>
              <el-icon aria-hidden="true">
                <Setting />
              </el-icon>
            </div>
          </template>

          <el-form
            class="settings-form"
            label-position="top"
          >
            <el-form-item :label="t('userSettings.formDefaultModel')">
              <el-select
                v-model="aiModelPreference.selectedModelKey"
                :placeholder="t('userSettings.selectSystemDefault')"
                class="settings-select"
              >
                <el-option
                  :label="t('userSettings.selectSystemDefault')"
                  value=""
                />
                <el-option
                  v-for="model in aiModelPreference.models"
                  :key="`${model.provider}::${model.model}`"
                  :label="model.display_name"
                  :value="`${model.provider}::${model.model}`"
                />
              </el-select>
            </el-form-item>

            <div class="settings-model-summary">
              <span>{{ t('userSettings.currentSelected', { label: selectedAIModelLabel }) }}</span>
              <strong>
                {{ t('userSettings.availableModels', { count: aiModelPreference.models.length }) }}
              </strong>
            </div>

            <div class="settings-action-row">
              <el-button
                type="primary"
                :icon="CircleCheck"
                :loading="aiModelPreference.saving"
                @click="saveAIModelPreference"
              >
                {{ t('userSettings.btnSavePref') }}
              </el-button>
              <el-button
                :icon="Connection"
                :loading="aiModelPreference.testing"
                @click="testAIModelPreference"
              >
                {{ t('userSettings.btnTestConnect') }}
              </el-button>
            </div>
          </el-form>
        </el-card>

        <el-card
          class="settings-panel"
          data-test="settings-about-card"
        >
          <template #header>
            <div class="settings-panel-heading">
              <div>
                <div class="settings-kicker">
                  {{ t('userSettings.cardAbout') }}
                </div>
                <h2>{{ t('userSettings.aboutTitle') }}</h2>
                <p>{{ t('userSettings.aboutPanelDesc') }}</p>
              </div>
              <el-icon aria-hidden="true">
                <Document />
              </el-icon>
            </div>
          </template>

          <div class="settings-about">
            <div>
              <span>{{ t('userSettings.version') }}</span>
              <strong>AI for Investor v1.0.0</strong>
            </div>
            <div>
              <span>{{ t('userSettings.stack') }}</span>
              <strong>{{ t('userSettings.aboutTechStack') }}</strong>
            </div>
            <p>{{ t('userSettings.aboutDesc') }}</p>
          </div>
        </el-card>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CircleCheck,
  Connection,
  Cpu,
  Document,
  Lock,
  Money,
  Setting,
  User as UserIcon,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import api from '@/api/index'
import { aiObservabilityApi, type AIModelOption } from '@/api/aiObservability'
import { useAuthStore } from '@/stores/auth'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const changingPassword = ref(false)

const userForm = reactive({
  username: '',
  email: '',
  createdAt: '',
})

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const aiUsageSummary = reactive({
  total_calls: 0,
  total_tokens: 0,
  estimated_cost_usd: 0,
})

const aiModelPreference = reactive({
  models: [] as AIModelOption[],
  selectedModelKey: '',
  saving: false,
  testing: false,
})

const user = computed(() => authStore.user)
const userInitial = computed(() => {
  const source = userForm.username || userForm.email || 'A'
  return source.slice(0, 1).toUpperCase()
})
const accountRoleLabel = computed(() =>
  user.value?.is_admin ? t('userSettings.roleAdmin') : t('userSettings.roleMember'),
)
const accountStatusLabel = computed(() =>
  user.value?.is_active === false
    ? t('userSettings.accountInactive')
    : t('userSettings.accountActive'),
)
const accountStatusType = computed(() => (user.value?.is_active === false ? 'warning' : 'success'))
const selectedAIModelLabel = computed(() => {
  if (!aiModelPreference.selectedModelKey) return t('userSettings.systemDefaultModel')
  const selected = aiModelPreference.models.find(
    model => `${model.provider}::${model.model}` === aiModelPreference.selectedModelKey,
  )
  return selected?.display_name ?? aiModelPreference.selectedModelKey
})

function formatInteger(value: number): string {
  return new Intl.NumberFormat(locale.value).format(Number(value ?? 0))
}

function formatUsd(value: number): string {
  return `$${Number(value ?? 0).toFixed(6)}`
}

function syncUserForm() {
  userForm.username = user.value?.username ?? ''
  userForm.email = user.value?.email ?? ''
  userForm.createdAt = user.value?.created_at ?? ''
}

async function loadMyAIUsage() {
  try {
    const usage = await aiObservabilityApi.getMyUsage()
    aiUsageSummary.total_calls = usage.summary.total_calls
    aiUsageSummary.total_tokens = usage.summary.total_tokens ?? 0
    aiUsageSummary.estimated_cost_usd = usage.summary.estimated_cost_usd ?? 0
  } catch {
    aiUsageSummary.total_calls = 0
    aiUsageSummary.total_tokens = 0
    aiUsageSummary.estimated_cost_usd = 0
  }
}

async function loadAIModelPreference() {
  try {
    const payload = await aiObservabilityApi.getMyAvailableModels()
    aiModelPreference.models = payload.models
    const provider = payload.preferences?.provider
    const model = payload.preferences?.model
    aiModelPreference.selectedModelKey = provider && model ? `${provider}::${model}` : ''
  } catch {
    aiModelPreference.models = []
    aiModelPreference.selectedModelKey = ''
  }
}

async function saveAIModelPreference() {
  const [provider, ...modelParts] = aiModelPreference.selectedModelKey.split('::')
  const model = modelParts.join('::')
  aiModelPreference.saving = true
  try {
    await aiObservabilityApi.updateMyPreferences({
      provider: provider || null,
      model: model || null,
    })
    ElMessage.success(t('userSettings.msgPrefSaved'))
  } finally {
    aiModelPreference.saving = false
  }
}

async function testAIModelPreference() {
  if (!aiModelPreference.selectedModelKey) {
    ElMessage.warning(t('userSettings.msgPickModelFirst'))
    return
  }
  const [provider, ...modelParts] = aiModelPreference.selectedModelKey.split('::')
  const model = modelParts.join('::')
  aiModelPreference.testing = true
  try {
    const result = await aiObservabilityApi.testMyPreferences({
      provider: provider || null,
      model: model || null,
    })
    if (result.available) {
      ElMessage.success(t('userSettings.msgTestOk'))
    } else {
      ElMessage.error(result.error || t('userSettings.msgTestFail'))
    }
  } finally {
    aiModelPreference.testing = false
  }
}

async function changePassword() {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    ElMessage.warning(t('userSettings.msgFillPassword'))
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.error(t('userSettings.msgPwdMismatch'))
    return
  }
  if (passwordForm.newPassword.length < 8) {
    ElMessage.error(t('userSettings.msgPwdTooShort'))
    return
  }

  changingPassword.value = true
  try {
    await api.put('/auth/change-password', {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword,
    })
    ElMessage.success(t('userSettings.msgPwdChanged'))
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch {
    // error handled by interceptor
  } finally {
    changingPassword.value = false
  }
}

watch(user, syncUserForm, { immediate: true })

onMounted(() => {
  void loadMyAIUsage()
  void loadAIModelPreference()
})
</script>

<style scoped>
.settings-page {
  display: grid;
  gap: 24px;
}

.settings-hero,
.settings-panel {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.settings-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  gap: 24px;
  padding: 24px;
}

.settings-hero-copy {
  display: grid;
  align-content: start;
  gap: 10px;
  min-width: 0;
}

.settings-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.settings-hero h1,
.settings-panel h2 {
  margin: 0;
  color: var(--text-color-primary);
  line-height: 1.18;
}

.settings-hero h1 {
  font-size: 30px;
}

.settings-panel h2 {
  font-size: 18px;
  font-weight: 780;
}

.settings-hero p,
.settings-panel-heading p {
  max-width: 780px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.settings-tag-row,
.settings-action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.settings-profile-panel {
  display: grid;
  gap: 14px;
  align-content: start;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.settings-avatar {
  background: var(--primary-color);
  color: #fff;
  font-weight: 800;
}

.settings-profile-panel > div:not(.settings-profile-meta) {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.settings-profile-panel strong,
.settings-detail-grid strong,
.settings-profile-meta strong,
.settings-about strong {
  color: var(--text-color-primary);
  overflow-wrap: anywhere;
}

.settings-profile-panel span,
.settings-detail-grid span,
.settings-profile-meta span,
.settings-usage-grid span,
.settings-about span,
.settings-model-summary span,
.settings-action-row span,
.settings-metric span,
.settings-metric small {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.3;
}

.settings-profile-meta,
.settings-detail-grid {
  display: grid;
  grid-template-columns: minmax(96px, 0.36fr) minmax(0, 1fr);
  gap: 8px 12px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.settings-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.settings-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.settings-metric .el-icon,
.settings-panel-heading > .el-icon {
  color: var(--primary-color);
  font-size: 20px;
}

.settings-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.settings-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
  gap: 20px;
  align-items: start;
}

.settings-stack {
  display: grid;
  gap: 20px;
  min-width: 0;
}

.settings-panel {
  min-width: 0;
  box-shadow: none;
}

.settings-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.settings-panel :deep(.el-card__body) {
  padding: 18px;
}

.settings-panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.settings-panel-heading > div {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.settings-form {
  display: grid;
  gap: 2px;
}

.settings-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.settings-form :deep(.el-form-item__label) {
  color: var(--text-color-secondary);
  font-weight: 680;
}

.settings-form :deep(.el-input__wrapper),
.settings-form :deep(.el-select__wrapper) {
  background: var(--fill-color-lighter);
  box-shadow: 0 0 0 1px var(--border-color-light) inset;
}

.settings-action-row {
  justify-content: space-between;
  padding-top: 4px;
}

.settings-action-row span {
  max-width: 360px;
  line-height: 1.45;
}

.settings-usage-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.settings-usage-grid div,
.settings-model-summary,
.settings-about div {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.settings-usage-grid strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.settings-select {
  width: 100%;
}

.settings-model-summary {
  margin-bottom: 14px;
}

.settings-model-summary strong {
  color: var(--text-color-primary);
  font-size: 13px;
}

.settings-about {
  display: grid;
  gap: 12px;
}

.settings-about p {
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.6;
}

@media (max-width: 1180px) {
  .settings-hero,
  .settings-layout {
    grid-template-columns: 1fr;
  }

  .settings-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .settings-page {
    gap: 16px;
  }

  .settings-hero {
    padding: 18px;
  }

  .settings-hero h1 {
    font-size: 24px;
  }

  .settings-metrics,
  .settings-profile-meta,
  .settings-detail-grid,
  .settings-usage-grid {
    grid-template-columns: 1fr;
  }

  .settings-panel :deep(.el-card__body) {
    padding: 14px;
  }

  .settings-panel-heading,
  .settings-action-row {
    display: grid;
    justify-items: start;
  }
}
</style>
