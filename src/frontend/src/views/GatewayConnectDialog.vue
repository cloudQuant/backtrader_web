<template>
  <el-dialog
    v-model="visibleModel"
    :title="t('gatewayStatus.dialogTitle')"
    width="560px"
  >
    <el-form
      :model="connectForm"
      label-width="100px"
    >
      <el-form-item
        :label="t('gatewayStatus.formExchangeRequired')"
        required
      >
        <el-select
          v-model="connectForm.exchange_type"
          :placeholder="t('gatewayStatus.selectExchangePh')"
          class="w-full"
          @change="onExchangeChange"
        >
          <el-option
            :label="t('gatewayStatus.optCtp')"
            value="CTP"
          />
          <el-option
            :label="t('gatewayStatus.optMt5')"
            value="MT5"
          />
          <el-option
            :label="t('gatewayStatus.optIbWeb')"
            value="IB_WEB"
          />
          <el-option
            :label="t('gatewayStatus.optBinance')"
            value="BINANCE"
          />
          <el-option
            :label="t('gatewayStatus.optOkx')"
            value="OKX"
          />
        </el-select>
      </el-form-item>

      <!-- CTP Fields -->
      <template v-if="connectForm.exchange_type === 'CTP'">
        <el-form-item
          :label="t('gatewayStatus.formEnv')"
          required
        >
          <el-radio-group
            v-model="ctpEnvModel"
            @change="onCtpEnvChange"
          >
            <el-radio-button value="simnow">
              {{ t('gatewayStatus.envSimnow') }}
            </el-radio-button>
            <el-radio-button value="simnow_7x24">
              {{ t('gatewayStatus.envSimnow7x24') }}
            </el-radio-button>
            <el-radio-button
              value="live"
              disabled
            >
              {{ t('gatewayStatus.envLive') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="ctpEnvModel === 'simnow'"
          :label="t('gatewayStatus.formLine')"
        >
          <el-select
            v-model="ctpGroupModel"
            class="w-full"
            @change="onCtpGroupChange"
          >
            <el-option
              :label="t('gatewayStatus.lineGroup1')"
              :value="1"
            />
            <el-option
              :label="t('gatewayStatus.lineGroup2')"
              :value="2"
            />
            <el-option
              :label="t('gatewayStatus.lineGroup3')"
              :value="3"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formAccount')"
          required
        >
          <el-input
            v-model="connectForm.credentials.user_id"
            :placeholder="t('gatewayStatus.accountPh')"
          />
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formPassword')"
          required
        >
          <el-input
            v-model="connectForm.credentials.password"
            type="password"
            show-password
            :placeholder="t('gatewayStatus.pwdPhTrade')"
          />
        </el-form-item>
        <el-collapse class="mt-2 mb-2">
          <el-collapse-item :title="t('gatewayStatus.advanced')">
            <el-form-item :label="t('gatewayStatus.formBrokerId')">
              <el-input
                v-model="connectForm.credentials.broker_id"
                placeholder="9999"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formTdFront')">
              <el-input
                v-model="connectForm.credentials.td_front"
                :placeholder="t('gatewayStatus.autoFillPh')"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formMdFront')">
              <el-input
                v-model="connectForm.credentials.md_front"
                :placeholder="t('gatewayStatus.autoFillPh')"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formAppId')">
              <el-input
                v-model="connectForm.credentials.app_id"
                placeholder="simnow_client_test"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formAuthCode')">
              <el-input
                v-model="connectForm.credentials.auth_code"
                placeholder="0000000000000000"
              />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
        <el-alert
          v-if="ctpEnvModel === 'simnow_7x24'"
          type="info"
          :closable="false"
          show-icon
          class="mb-3"
        >
          <template #title>
            {{ t('gatewayStatus.ctp7x24Title') }}
          </template>
          {{ t('gatewayStatus.ctp7x24Desc') }}
        </el-alert>
      </template>

      <template v-if="connectForm.exchange_type === 'MT5'">
        <el-form-item
          :label="t('gatewayStatus.formEnv')"
          required
        >
          <el-radio-group
            v-model="mt5EnvModel"
            @change="onMt5EnvChange"
          >
            <el-radio-button value="demo">
              {{ t('gatewayStatus.envDemo') }}
            </el-radio-button>
            <el-radio-button value="live">
              {{ t('gatewayStatus.envLive') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formLogin')"
          required
        >
          <el-input
            v-model="connectForm.credentials.login"
            placeholder="MT5 Login"
          />
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formPassword')"
          required
        >
          <el-input
            v-model="connectForm.credentials.password"
            type="password"
            show-password
            placeholder="MT5 Password"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formServer')">
          <el-input
            v-model="connectForm.credentials.server"
            placeholder="Broker-Server"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formWsUri')">
          <el-input
            v-model="connectForm.credentials.ws_uri"
            :placeholder="t('gatewayStatus.wsUriPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formSuffix')">
          <el-input
            v-model="connectForm.credentials.symbol_suffix"
            :placeholder="t('gatewayStatus.suffixPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formTimeout')">
          <el-input
            v-model="connectForm.credentials.timeout"
            placeholder="60"
          />
        </el-form-item>
      </template>

      <!-- IB Web Fields -->
      <template v-if="connectForm.exchange_type === 'IB_WEB'">
        <el-form-item
          :label="t('gatewayStatus.formEnv')"
          required
        >
          <el-radio-group
            v-model="ibEnvModel"
            @change="onIbEnvChange"
          >
            <el-radio-button value="paper">
              {{ t('gatewayStatus.envDemo') }}
            </el-radio-button>
            <el-radio-button value="live">
              {{ t('gatewayStatus.envLive') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formAccountId')"
          required
        >
          <el-input
            v-model="connectForm.credentials.account_id"
            :placeholder="t('gatewayStatus.accountIdPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.fieldAssetType')">
          <el-select
            v-model="connectForm.credentials.asset_type"
            class="w-full"
          >
            <el-option
              :label="t('gatewayStatus.optStock')"
              value="STK"
            />
            <el-option
              :label="t('gatewayStatus.optFut')"
              value="FUT"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formBaseUrl')">
          <el-input
            v-model="connectForm.credentials.base_url"
            placeholder="https://localhost:5000"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formAccessToken')">
          <el-input
            v-model="connectForm.credentials.access_token"
            :placeholder="t('gatewayStatus.optionalPh')"
          />
        </el-form-item>
        <el-collapse class="mt-2 mb-2">
          <el-collapse-item :title="t('gatewayStatus.advancedAuth')">
            <el-form-item :label="t('gatewayStatus.formUsername')">
              <el-input
                v-model="connectForm.credentials.username"
                :placeholder="t('gatewayStatus.ibkrUserPh')"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formPassword')">
              <el-input
                v-model="connectForm.credentials.password"
                type="password"
                show-password
                :placeholder="t('gatewayStatus.ibkrPwdPh')"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formCookieSrc')">
              <el-input
                v-model="connectForm.credentials.cookie_source"
                :placeholder="t('gatewayStatus.cookieSrcPh')"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formBrowser')">
              <el-input
                v-model="connectForm.credentials.cookie_browser"
                placeholder="chrome"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formLoginBrowser')">
              <el-input
                v-model="connectForm.credentials.login_browser"
                placeholder="chrome"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formCookieOutput')">
              <el-input
                v-model="connectForm.credentials.cookie_output"
                :placeholder="t('gatewayStatus.cookieOutputPh')"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formCookiePath')">
              <el-input
                v-model="connectForm.credentials.cookie_path"
                placeholder="/sso"
              />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formHeadless')">
              <el-switch v-model="connectForm.credentials.login_headless" />
            </el-form-item>
            <el-form-item :label="t('gatewayStatus.formLoginTimeout')">
              <el-input
                v-model="connectForm.credentials.login_timeout"
                placeholder="180"
              />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="mb-3"
        >
          <template #title>
            {{ t('gatewayStatus.ibAuthTitle') }}
          </template>
          {{ t('gatewayStatus.ibAuthDesc') }}
          <code>file:C:/path/to/cookies.json</code>
          {{ t('gatewayStatus.ibAuthDescTail') }}
        </el-alert>
        <el-form-item :label="t('gatewayStatus.formVerifySsl')">
          <el-switch v-model="connectForm.credentials.verify_ssl" />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formTimeout')">
          <el-input
            v-model="connectForm.credentials.timeout"
            placeholder="10"
          />
        </el-form-item>
      </template>

      <!-- Binance Fields -->
      <template v-if="connectForm.exchange_type === 'BINANCE'">
        <el-form-item :label="t('gatewayStatus.accountIdLabel')">
          <el-input
            v-model="connectForm.credentials.account_id"
            :placeholder="t('gatewayStatus.accountIdLabelPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.fieldAssetType')">
          <el-select
            v-model="connectForm.credentials.asset_type"
            class="w-full"
          >
            <el-option
              :label="t('gatewayStatus.optSwap')"
              value="SWAP"
            />
            <el-option
              :label="t('gatewayStatus.optSpot')"
              value="SPOT"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formApiKey')"
          required
        >
          <el-input
            v-model="connectForm.credentials.api_key"
            placeholder="Binance API Key"
          />
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formSecretKey')"
          required
        >
          <el-input
            v-model="connectForm.credentials.secret_key"
            type="password"
            show-password
            placeholder="Binance Secret Key"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formBaseUrl')">
          <el-input
            v-model="connectForm.credentials.base_url"
            :placeholder="t('gatewayStatus.baseUrlPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formTestnet')">
          <el-switch v-model="connectForm.credentials.testnet" />
        </el-form-item>
      </template>

      <!-- OKX Fields -->
      <template v-if="connectForm.exchange_type === 'OKX'">
        <el-form-item :label="t('gatewayStatus.accountIdLabel')">
          <el-input
            v-model="connectForm.credentials.account_id"
            :placeholder="t('gatewayStatus.accountIdLabelPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.fieldAssetType')">
          <el-select
            v-model="connectForm.credentials.asset_type"
            class="w-full"
          >
            <el-option
              :label="t('gatewayStatus.optSwap')"
              value="SWAP"
            />
            <el-option
              :label="t('gatewayStatus.optSpot')"
              value="SPOT"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formApiKey')"
          required
        >
          <el-input
            v-model="connectForm.credentials.api_key"
            placeholder="OKX API Key"
          />
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formSecretKey')"
          required
        >
          <el-input
            v-model="connectForm.credentials.secret_key"
            type="password"
            show-password
            placeholder="OKX Secret Key"
          />
        </el-form-item>
        <el-form-item
          :label="t('gatewayStatus.formPassphrase')"
          required
        >
          <el-input
            v-model="connectForm.credentials.passphrase"
            type="password"
            show-password
            placeholder="OKX Passphrase"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formBaseUrl')">
          <el-input
            v-model="connectForm.credentials.base_url"
            :placeholder="t('gatewayStatus.baseUrlPh')"
          />
        </el-form-item>
        <el-form-item :label="t('gatewayStatus.formTestnet')">
          <el-switch v-model="connectForm.credentials.testnet" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="visibleModel = false">
        {{ t('gatewayStatus.btnCancel') }}
      </el-button>
      <el-button
        type="primary"
        :loading="connecting"
        :disabled="!connectForm.exchange_type"
        @click="onConnect"
      >
        {{ t('gatewayStatus.btnConnectAction') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

type GatewayCredentials = Record<string, any>

interface GatewayConnectForm {
  exchange_type: string
  credentials: GatewayCredentials
}

const props = defineProps<{
  visible: boolean
  connectForm: GatewayConnectForm
  ctpEnv: string
  ctpGroup: number
  mt5Env: string
  ibEnv: string
  connecting: boolean
  onExchangeChange: () => void
  onCtpEnvChange: () => void
  onCtpGroupChange: () => void
  onMt5EnvChange: () => void
  onIbEnvChange: () => void
  onConnect: () => void
}>()

const connectForm = ref(props.connectForm)

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:ctpEnv': [value: string]
  'update:ctpGroup': [value: number]
  'update:mt5Env': [value: string]
  'update:ibEnv': [value: string]
}>()

const { t } = useI18n()
const visibleModel = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})
const ctpEnvModel = computed({
  get: () => props.ctpEnv,
  set: (value: string) => emit('update:ctpEnv', value),
})
const ctpGroupModel = computed({
  get: () => props.ctpGroup,
  set: (value: number) => emit('update:ctpGroup', value),
})
const mt5EnvModel = computed({
  get: () => props.mt5Env,
  set: (value: string) => emit('update:mt5Env', value),
})
const ibEnvModel = computed({
  get: () => props.ibEnv,
  set: (value: string) => emit('update:ibEnv', value),
})
</script>
