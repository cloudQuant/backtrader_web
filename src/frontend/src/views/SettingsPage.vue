<template>
  <div class="space-y-6 max-w-3xl">
    <!-- Profile -->
    <el-card>
      <template #header>
        <span class="font-bold">{{ t('userSettings.cardProfile') }}</span>
      </template>
      
      <el-form
        :model="userForm"
        label-width="100px"
      >
        <el-form-item :label="t('userSettings.formUsername')">
          <el-input
            v-model="userForm.username"
            disabled
          />
        </el-form-item>
        <el-form-item :label="t('userSettings.formEmail')">
          <el-input
            v-model="userForm.email"
            disabled
          />
        </el-form-item>
        <el-form-item :label="t('userSettings.formCreatedAt')">
          <el-input
            v-model="userForm.createdAt"
            disabled
          />
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- Change password -->
    <el-card>
      <template #header>
        <span class="font-bold">{{ t('userSettings.cardChangePwd') }}</span>
      </template>
      
      <el-form
        :model="passwordForm"
        label-width="100px"
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
        <el-form-item>
          <el-button
            type="primary"
            @click="changePassword"
          >
            {{ t('userSettings.btnChangePwd') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <el-card>
      <template #header>
        <span class="font-bold">{{ t('userSettings.cardAiUsage') }}</span>
      </template>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <div class="text-sm text-gray-500">
            {{ t('userSettings.formAiCallCount') }}
          </div>
          <div class="text-xl font-bold mt-1">
            {{ aiUsageSummary.total_calls }}
          </div>
        </div>
        <div>
          <div class="text-sm text-gray-500">
            {{ t('userSettings.formAiTokens') }}
          </div>
          <div class="text-xl font-bold mt-1">
            {{ aiUsageSummary.total_tokens }}
          </div>
        </div>
        <div>
          <div class="text-sm text-gray-500">
            {{ t('userSettings.formAiCost') }}
          </div>
          <div class="text-xl font-bold mt-1">
            {{ formatUsd(aiUsageSummary.estimated_cost_usd) }}
          </div>
        </div>
      </div>
    </el-card>
    
    <el-card>
      <template #header>
        <span class="font-bold">{{ t('userSettings.cardAiModelPref') }}</span>
      </template>

      <el-form label-width="100px">
        <el-form-item :label="t('userSettings.formDefaultModel')">
          <el-select
            v-model="aiModelPreference.selectedModelKey"
            :placeholder="t('userSettings.selectSystemDefault')"
            style="width: 100%"
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
        <el-form-item>
          <div class="space-y-2">
            <div class="text-sm text-gray-500">
              {{ t('userSettings.currentSelected', { label: selectedAIModelLabel }) }}
            </div>
            <el-button
              type="primary"
              :loading="aiModelPreference.saving"
              @click="saveAIModelPreference"
            >
              {{ t('userSettings.btnSavePref') }}
            </el-button>
            <el-button
              :loading="aiModelPreference.testing"
              @click="testAIModelPreference"
            >
              {{ t('userSettings.btnTestConnect') }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- About -->
    <el-card>
      <template #header>
        <span class="font-bold">{{ t('userSettings.cardAbout') }}</span>
      </template>
      
      <div class="space-y-2 text-gray-600">
        <p><strong>AI for Trader</strong> v1.0.0</p>
        <p>{{ t('userSettings.aboutDesc') }}</p>
        <p>{{ t('userSettings.aboutTechStack') }}</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/index'
import { aiObservabilityApi, type AIModelOption } from '@/api/aiObservability'

const { t } = useI18n()
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
const selectedAIModelLabel = computed(() => {
  if (!aiModelPreference.selectedModelKey) return t('userSettings.systemDefaultModel')
  const selected = aiModelPreference.models.find(
    model => `${model.provider}::${model.model}` === aiModelPreference.selectedModelKey
  )
  return selected?.display_name ?? aiModelPreference.selectedModelKey
})

function formatUsd(value: number): string {
  return `$${Number(value ?? 0).toFixed(6)}`
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

onMounted(() => {
  if (user.value) {
    userForm.username = user.value.username
    userForm.email = user.value.email
    userForm.createdAt = user.value.created_at
  }
  void loadMyAIUsage()
  void loadAIModelPreference()
})
</script>
