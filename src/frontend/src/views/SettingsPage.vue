<template>
  <div class="space-y-6 max-w-3xl">
    <!-- 用户信息 -->
    <el-card>
      <template #header>
        <span class="font-bold">个人信息</span>
      </template>
      
      <el-form
        :model="userForm"
        label-width="100px"
      >
        <el-form-item label="用户名">
          <el-input
            v-model="userForm.username"
            disabled
          />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input
            v-model="userForm.email"
            disabled
          />
        </el-form-item>
        <el-form-item label="注册时间">
          <el-input
            v-model="userForm.createdAt"
            disabled
          />
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 修改密码 -->
    <el-card>
      <template #header>
        <span class="font-bold">修改密码</span>
      </template>
      
      <el-form
        :model="passwordForm"
        label-width="100px"
      >
        <el-form-item label="当前密码">
          <el-input
            v-model="passwordForm.oldPassword"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="passwordForm.newPassword"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认新密码">
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
            修改密码
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <el-card>
      <template #header>
        <span class="font-bold">我的 AI 用量</span>
      </template>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <div class="text-sm text-gray-500">
            调用次数
          </div>
          <div class="text-xl font-bold mt-1">
            {{ aiUsageSummary.total_calls }}
          </div>
        </div>
        <div>
          <div class="text-sm text-gray-500">
            Token
          </div>
          <div class="text-xl font-bold mt-1">
            {{ aiUsageSummary.total_tokens }}
          </div>
        </div>
        <div>
          <div class="text-sm text-gray-500">
            估算成本
          </div>
          <div class="text-xl font-bold mt-1">
            {{ formatUsd(aiUsageSummary.estimated_cost_usd) }}
          </div>
        </div>
      </div>
    </el-card>
    
    <el-card>
      <template #header>
        <span class="font-bold">AI 模型偏好</span>
      </template>

      <el-form label-width="100px">
        <el-form-item label="默认模型">
          <el-select
            v-model="aiModelPreference.selectedModelKey"
            placeholder="使用系统默认模型"
            style="width: 100%"
          >
            <el-option
              label="使用系统默认模型"
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
              当前选择：{{ selectedAIModelLabel }}
            </div>
            <el-button
              type="primary"
              :loading="aiModelPreference.saving"
              @click="saveAIModelPreference"
            >
              保存 AI 模型偏好
            </el-button>
            <el-button
              :loading="aiModelPreference.testing"
              @click="testAIModelPreference"
            >
              测试连通性
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 关于 -->
    <el-card>
      <template #header>
        <span class="font-bold">关于</span>
      </template>
      
      <div class="space-y-2 text-gray-600">
        <p><strong>Backtrader Web</strong> v1.0.0</p>
        <p>基于 Backtrader 的量化交易回测平台</p>
        <p>技术栈: Vue 3 + FastAPI + Backtrader</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/index'
import { aiObservabilityApi, type AIModelOption } from '@/api/aiObservability'

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
  if (!aiModelPreference.selectedModelKey) return '系统默认模型'
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
    ElMessage.success('AI 模型偏好已保存')
  } finally {
    aiModelPreference.saving = false
  }
}

async function testAIModelPreference() {
  if (!aiModelPreference.selectedModelKey) {
    ElMessage.warning('请先选择要测试的 AI 模型')
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
      ElMessage.success('AI 模型连通性正常')
    } else {
      ElMessage.error(result.error || 'AI 模型当前不可用')
    }
  } finally {
    aiModelPreference.testing = false
  }
}

async function changePassword() {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    ElMessage.warning('请填写密码')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  if (passwordForm.newPassword.length < 8) {
    ElMessage.error('密码至少8位')
    return
  }
  
  changingPassword.value = true
  try {
    await api.put('/auth/change-password', {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword,
    })
    ElMessage.success('密码修改成功')
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
