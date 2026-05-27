<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold">
          Broker Profiles
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          管理 broker profile、查看只读运行态，并对实盘写入权限做显式开关。
        </p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <el-button
          :loading="loading"
          @click="loadProfiles"
        >
          刷新列表
        </el-button>
        <el-button
          type="primary"
          :loading="creating"
          @click="createDemoProfile"
        >
          创建示例 Profile
        </el-button>
        <el-button
          v-if="isAdmin"
          type="warning"
          :disabled="!selectedProfileId"
          :loading="enablingWrite"
          @click="enableLiveWrite()"
        >
          Enable Live Write
        </el-button>
      </div>
    </div>

    <el-card>
      <template #header>
        <div class="font-bold">
          新建 Profile
        </div>
      </template>
      <div class="grid gap-3 md:grid-cols-2">
        <el-input v-model="form.broker_id" placeholder="broker_id" />
        <el-input v-model="form.account_alias" placeholder="account_alias" />
        <el-input v-model="form.runtimeGatewayKey" placeholder="manual:IB_WEB:DU123456" />
        <el-input v-model="form.runtimeAccountId" placeholder="DU123456" />
        <el-input v-model="form.capabilitiesText" placeholder="health, accounts, positions, orders, quotes" />
        <el-input v-model="form.credentialsRotatedAt" placeholder="2026-02-01T00:00:00+00:00" />
        <el-input v-model="form.apiKeyEnv" placeholder="BT_BROKER_SIM_KEY" />
        <el-input v-model="form.apiSecretEnv" placeholder="BT_BROKER_SIM_SECRET" />
      </div>
      <div class="mt-3 flex gap-2 flex-wrap">
        <el-button type="primary" :loading="creating" @click="submitCreateProfile">
          保存 Profile
        </el-button>
        <el-button @click="fillDemoForm">
          填充示例
        </el-button>
      </div>
    </el-card>

    <el-card>
      <template #header>
        <div class="font-bold">
          Profiles
        </div>
      </template>
      <div class="profile-tags">
        <el-tag
          v-for="item in profiles"
          :key="item.id"
          class="cursor-pointer"
          :type="selectedProfileId === item.id ? 'success' : 'info'"
          @click="inspectProfile(item.id)"
        >
          {{ item.account_alias }}
        </el-tag>
      </div>
      <el-table
        :data="profiles"
        class="mt-4"
      >
        <el-table-column
          prop="broker_id"
          label="Broker"
        />
        <el-table-column
          prop="account_alias"
          label="Alias"
        />
        <el-table-column
          prop="rotation_warning"
          label="轮换提醒"
        />
        <el-table-column label="Runtime 绑定">
          <template #default="{ row }">
            {{ row.runtime_binding?.gateway_key || '未绑定' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="font-bold">
          当前 Profile
        </div>
      </template>
      <div class="grid gap-3 md:grid-cols-4">
        <el-statistic
          title="Profile 数量"
          :value="profiles.length"
        />
        <el-statistic
          title="账户数"
          :value="accounts.length"
        />
        <el-statistic
          title="持仓数"
          :value="positions.length"
        />
        <el-statistic
          title="订单数"
          :value="orders.length"
        />
      </div>
      <div class="space-y-2 text-sm mt-4">
        <div>
          <strong>Selected:</strong> {{ selectedProfile?.account_alias || '未选择' }}
        </div>
        <div>
          <strong>Write Enabled:</strong> {{ selectedProfile?.is_destructive_enabled ? 'yes' : 'no' }}
        </div>
        <div>
          <strong>Rotation Warning:</strong> {{ selectedProfile?.rotation_warning || 'none' }}
        </div>
        <div>
          <strong>Runtime Binding:</strong> {{ selectedProfile?.runtime_binding?.gateway_key || 'none' }}
        </div>
        <div v-if="isAdmin" class="space-y-2">
          <div>
            <strong>Enable Write Confirmation:</strong> {{ enableWriteExpectedConfirmation }}
          </div>
          <el-input v-model="enableWriteForm.confirmationText" placeholder="type confirmation phrase" />
          <div v-if="enableWriteError" class="text-red-500">
            {{ enableWriteError }}
          </div>
        </div>
        <div>
          <strong>Health:</strong>
        </div>
        <pre class="preview-box">{{ healthText }}</pre>
        <div>
          <strong>Accounts:</strong>
        </div>
        <pre class="preview-box">{{ accountsText }}</pre>
        <div>
          <strong>Positions:</strong>
        </div>
        <pre class="preview-box">{{ positionsText }}</pre>
        <div>
          <strong>Orders:</strong>
        </div>
        <pre class="preview-box">{{ ordersText }}</pre>
        <div>
          <strong>Quote:</strong>
        </div>
        <pre class="preview-box">{{ quoteText }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { brokerProfilesApi, type BrokerAccountItem, type BrokerProfile } from '@/api/brokerProfiles'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const loading = ref(false)
const creating = ref(false)
const enablingWrite = ref(false)
const profiles = ref<BrokerProfile[]>([])
const selectedProfileId = ref('')
const health = ref<Record<string, unknown> | null>(null)
const accounts = ref<BrokerAccountItem[]>([])
const positions = ref<Array<Record<string, unknown>>>([])
const orders = ref<Array<Record<string, unknown>>>([])
const quote = ref<Record<string, unknown> | null>(null)
const form = reactive({
  broker_id: 'gateway_bridge',
  account_alias: '',
  runtimeGatewayKey: '',
  runtimeAccountId: '',
  capabilitiesText: 'health, accounts, positions, orders, quotes',
  apiKeyEnv: '',
  apiSecretEnv: '',
  credentialsRotatedAt: '',
})
const enableWriteForm = reactive({
  confirmationText: '',
})
const enableWriteError = ref('')

const isAdmin = computed(() => authStore.user?.is_admin ?? false)
const selectedProfile = computed(() => profiles.value.find((item) => item.id === selectedProfileId.value) ?? null)
const healthText = computed(() => JSON.stringify(health.value, null, 2))
const accountsText = computed(() => JSON.stringify(accounts.value, null, 2))
const positionsText = computed(() => JSON.stringify(positions.value, null, 2))
const ordersText = computed(() => JSON.stringify(orders.value, null, 2))
const quoteText = computed(() => JSON.stringify(quote.value, null, 2))
const enableWriteExpectedConfirmation = computed(() => {
  const alias = selectedProfile.value?.account_alias || 'profile'
  return `ENABLE ${alias}`
})

function buildIdempotencyKey() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }
  return `broker-write-${Date.now()}`
}

function fillDemoForm() {
  form.broker_id = 'gateway_bridge'
  form.account_alias = 'sim-account'
  form.runtimeGatewayKey = 'manual:IB_WEB:DU123456'
  form.runtimeAccountId = 'DU123456'
  form.capabilitiesText = 'health, accounts, positions, orders, quotes'
  form.apiKeyEnv = 'BT_BROKER_SIM_KEY'
  form.apiSecretEnv = 'BT_BROKER_SIM_SECRET'
  form.credentialsRotatedAt = new Date().toISOString()
}

function buildCreatePayload() {
  const capabilities = form.capabilitiesText
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

  const credentials_ref: Record<string, string> = {}
  if (form.apiKeyEnv.trim()) {
    credentials_ref.api_key_env = form.apiKeyEnv.trim()
  }
  if (form.apiSecretEnv.trim()) {
    credentials_ref.api_secret_env = form.apiSecretEnv.trim()
  }

  return {
    broker_id: form.broker_id.trim() || 'gateway_bridge',
    account_alias: form.account_alias.trim() || 'gateway',
    capabilities,
    credentials_ref,
    credentials_rotated_at: form.credentialsRotatedAt.trim() || undefined,
    runtime_gateway_key: form.runtimeGatewayKey.trim() || undefined,
    runtime_account_id: form.runtimeAccountId.trim() || undefined,
  }
}

async function loadProfiles() {
  loading.value = true
  try {
    const response = await brokerProfilesApi.listProfiles()
    profiles.value = response.items
    if (!selectedProfileId.value && response.items.length > 0) {
      selectedProfileId.value = response.items[0].id
    }
  } finally {
    loading.value = false
  }
}

async function createDemoProfile() {
  fillDemoForm()
  await submitCreateProfile()
}

async function submitCreateProfile() {
  creating.value = true
  try {
    const created = await brokerProfilesApi.createProfile(buildCreatePayload())
    selectedProfileId.value = created.id
    await loadProfiles()
  } finally {
    creating.value = false
  }
}

async function inspectProfile(profileId: string) {
  selectedProfileId.value = profileId
  enableWriteError.value = ''
  enableWriteForm.confirmationText = ''
  const [healthResp, accountsResp, positionsResp, ordersResp, quoteResp] = await Promise.all([
    brokerProfilesApi.getHealth(profileId),
    brokerProfilesApi.getAccounts(profileId),
    brokerProfilesApi.getPositions(profileId),
    brokerProfilesApi.getOrders(profileId),
    brokerProfilesApi.getQuote(profileId, 'RB2510'),
  ])
  health.value = healthResp
  accounts.value = accountsResp.items
  positions.value = positionsResp.items
  orders.value = ordersResp.items
  quote.value = quoteResp
  await loadProfiles()
}

async function enableLiveWrite(profileId: string = selectedProfileId.value) {
  if (!isAdmin.value || !profileId) {
    return
  }
  if (enableWriteForm.confirmationText.trim() !== enableWriteExpectedConfirmation.value) {
    enableWriteError.value = `请输入确认短语: ${enableWriteExpectedConfirmation.value}`
    return
  }

  enablingWrite.value = true
  try {
    enableWriteError.value = ''
    await brokerProfilesApi.enableWrite(profileId, {
      confirmation_text: enableWriteForm.confirmationText.trim(),
      idempotency_key: buildIdempotencyKey(),
    })
    enableWriteForm.confirmationText = ''
    await loadProfiles()
  } finally {
    enablingWrite.value = false
  }
}

onMounted(() => {
  fillDemoForm()
  void loadProfiles()
})
</script>

<style scoped>
.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preview-box {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
  min-height: 60px;
}
</style>
