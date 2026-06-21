<template>
  <div class="space-y-6">
    <teleport
      v-if="headerActionsTargetReady"
      to="#page-header-actions"
    >
      <div class="flex items-center gap-2 flex-wrap">
        <el-tag
          :type="healthyCount > 0 ? 'success' : 'info'"
          size="small"
        >
          {{ t('gatewayStatus.headerHealthSummary', { healthy: healthyCount, total: visibleGateways.length }) }}
        </el-tag>
        <el-radio-group
          v-model="viewMode"
          size="small"
        >
          <el-radio-button value="card">
            <el-icon><Grid /></el-icon>
          </el-radio-button>
          <el-radio-button value="table">
            <el-icon><List /></el-icon>
          </el-radio-button>
        </el-radio-group>
        <el-button
          type="primary"
          size="small"
          @click="openConnectDialog"
        >
          <el-icon><Connection /></el-icon>{{ t('gatewayStatus.btnConnect') }}
        </el-button>
        <el-button
          size="small"
          :loading="loading"
          @click="fetchHealth"
        >
          <el-icon><Refresh /></el-icon>{{ t('gatewayStatus.btnRefresh') }}
        </el-button>
      </div>
    </teleport>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    />

    <!-- Loading -->
    <div
      v-if="loading && visibleGateways.length === 0"
      class="flex justify-center py-12"
    >
      <el-icon class="is-loading text-4xl text-blue-500">
        <Loading />
      </el-icon>
    </div>

    <!-- Empty -->
    <div
      v-else-if="visibleGateways.length === 0"
      class="text-center py-12"
    >
      <el-empty :description="t('gatewayStatus.emptyDesc')" />
    </div>

    <!-- Gateway Cards -->
    <div
      v-else-if="viewMode === 'card'"
      class="grid grid-cols-1 lg:grid-cols-2 gap-4"
    >
      <el-card
        v-for="gw in visibleGateways"
        :key="gw.gateway_key"
        shadow="hover"
      >
        <!-- Card Header -->
        <template #header>
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <el-icon
                :color="gw.is_healthy ? 'var(--el-color-success)' : 'var(--el-color-danger)'"
                :size="18"
              >
                <CircleCheckFilled v-if="gw.is_healthy" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span class="font-bold text-base">{{ gw.strategy_name || gw.gateway_key }}</span>
              <el-tag
                v-if="gw.gateway_key.startsWith('direct:')"
                size="small"
                type="warning"
                effect="plain"
              >
                {{ t('gatewayStatus.tagDirect') }}
              </el-tag>
            </div>
            <div class="flex items-center gap-2">
              <el-tag
                :type="stateTagType(gw.state)"
                size="small"
              >
                {{ stateLabel(gw.state) }}
              </el-tag>
              <el-popconfirm
                v-if="gw.gateway_key.startsWith('manual:')"
                :title="t('gatewayStatus.tagDisconnect')"
                @confirm="handleDisconnect(gw.gateway_key)"
              >
                <template #reference>
                  <el-button
                    type="danger"
                    size="small"
                    plain
                    :loading="disconnecting === gw.gateway_key"
                  >
                    {{ t('gatewayStatus.btnDisconnect') }}
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </template>

        <!-- Info Grid -->
        <div class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <span class="text-gray-500">{{ t('gatewayStatus.fieldExchange') }}</span>
            <div class="font-medium">
              {{ gw.exchange || '-' }}
            </div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('gatewayStatus.fieldAssetType') }}</span>
            <div class="font-medium">
              {{ gw.asset_type || '-' }}
            </div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('gatewayStatus.fieldAccount') }}</span>
            <div class="font-medium">
              {{ gw.account_id || '-' }}
            </div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('gatewayStatus.fieldUptime') }}</span>
            <div class="font-medium">
              {{ formatUptime(gw.uptime_sec) }}
            </div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('gatewayStatus.fieldMarketConn') }}</span>
            <div>
              <el-tag
                :type="connTagType(gw.market_connection)"
                size="small"
              >
                {{ connLabel(gw.market_connection) }}
              </el-tag>
            </div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('gatewayStatus.fieldTradeConn') }}</span>
            <div>
              <el-tag
                :type="connTagType(gw.trade_connection)"
                size="small"
              >
                {{ connLabel(gw.trade_connection) }}
              </el-tag>
            </div>
          </div>
        </div>

        <!-- Stats Row -->
        <el-divider />
        <div class="grid grid-cols-4 gap-2 text-center text-sm">
          <div>
            <div class="text-gray-500">
              {{ t('gatewayStatus.statStrategyCount') }}
            </div>
            <div class="text-lg font-bold text-blue-600">
              {{ gw.strategy_count }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">
              {{ t('gatewayStatus.statSymbolCount') }}
            </div>
            <div class="text-lg font-bold text-blue-600">
              {{ gw.symbol_count }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">
              {{ t('gatewayStatus.statTickCount') }}
            </div>
            <div class="text-lg font-bold text-green-600">
              {{ formatNumber(gw.tick_count) }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">
              {{ t('gatewayStatus.statOrderCount') }}
            </div>
            <div class="text-lg font-bold text-orange-600">
              {{ gw.order_count }}
            </div>
          </div>
        </div>

        <!-- Heartbeat & Instances -->
        <el-divider />
        <div class="text-sm space-y-2">
          <div class="flex justify-between">
            <span class="text-gray-500">{{ t('gatewayStatus.fieldHeartbeat') }}</span>
            <span :class="heartbeatClass(getHeartbeatAge(gw, nowMs, lastHealthFetchMs))">
              {{ formatHeartbeatAge(gw, nowMs, lastHealthFetchMs) }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-500">{{ t('gatewayStatus.fieldRefCount') }}</span>
            <span>{{ gw.ref_count }}</span>
          </div>
          <div v-if="gw.instances.length > 0">
            <span class="text-gray-500">{{ t('gatewayStatus.fieldInstances') }}</span>
            <el-tag
              v-for="iid in gw.instances"
              :key="iid"
              size="small"
              class="ml-1 mb-1"
              effect="plain"
            >
              {{ iid.slice(0, 8) }}
            </el-tag>
          </div>
        </div>

        <!-- Recent Errors -->
        <template v-if="gw.recent_errors && gw.recent_errors.length > 0">
          <el-divider />
          <div class="text-sm">
            <div class="text-red-500 font-medium mb-1">
              {{ t('gatewayStatus.recentErrors', { n: gw.recent_errors.length }) }}
            </div>
            <div
              v-for="(err, idx) in gw.recent_errors.slice(-3)"
              :key="idx"
              class="text-xs text-gray-600 truncate"
              :title="err.message"
            >
              [{{ err.source }}] {{ err.message }}
            </div>
          </div>
        </template>
      </el-card>
    </div>

    <el-card
      v-else
      shadow="never"
    >
      <el-table
        :data="visibleGateways"
        stripe
        border
      >
        <el-table-column
          label="Gateway"
          min-width="240"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <el-icon
                :color="row.is_healthy ? 'var(--el-color-success)' : 'var(--el-color-danger)'"
                :size="16"
              >
                <CircleCheckFilled v-if="row.is_healthy" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span class="font-medium">{{ row.strategy_name || row.gateway_key }}</span>
              <el-tag
                v-if="row.gateway_key.startsWith('direct:')"
                size="small"
                type="warning"
                effect="plain"
              >
                {{ t('gatewayStatus.tagDirect') }}
              </el-tag>
            </div>
            <div class="text-xs text-gray-500 mt-1">
              {{ row.gateway_key }}
            </div>
          </template>
        </el-table-column>

        <el-table-column
          prop="exchange"
          :label="t('gatewayStatus.fieldExchange')"
          min-width="110"
        />
        <el-table-column
          prop="asset_type"
          :label="t('gatewayStatus.fieldAssetType')"
          min-width="100"
        />
        <el-table-column
          prop="account_id"
          :label="t('gatewayStatus.fieldAccount')"
          min-width="120"
          show-overflow-tooltip
        />

        <el-table-column
          :label="t('gatewayStatus.colState')"
          min-width="110"
        >
          <template #default="{ row }">
            <el-tag
              :type="stateTagType(row.state)"
              size="small"
            >
              {{ stateLabel(row.state) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          :label="t('gatewayStatus.fieldMarketConn')"
          min-width="110"
        >
          <template #default="{ row }">
            <el-tag
              :type="connTagType(row.market_connection)"
              size="small"
            >
              {{ connLabel(row.market_connection) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          :label="t('gatewayStatus.fieldTradeConn')"
          min-width="110"
        >
          <template #default="{ row }">
            <el-tag
              :type="connTagType(row.trade_connection)"
              size="small"
            >
              {{ connLabel(row.trade_connection) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          :label="t('gatewayStatus.fieldUptime')"
          min-width="110"
        >
          <template #default="{ row }">
            {{ formatUptime(row.uptime_sec) }}
          </template>
        </el-table-column>

        <el-table-column
          prop="strategy_count"
          :label="t('gatewayStatus.statStrategyCount')"
          min-width="90"
        />
        <el-table-column
          prop="symbol_count"
          :label="t('gatewayStatus.statSymbolCount')"
          min-width="100"
        />

        <el-table-column
          :label="t('gatewayStatus.statTickCount')"
          min-width="100"
        >
          <template #default="{ row }">
            {{ formatNumber(row.tick_count) }}
          </template>
        </el-table-column>

        <el-table-column
          prop="order_count"
          :label="t('gatewayStatus.statOrderCount')"
          min-width="90"
        />

        <el-table-column
          :label="t('gatewayStatus.fieldHeartbeat')"
          min-width="100"
        >
          <template #default="{ row }">
            <span :class="heartbeatClass(getHeartbeatAge(row, nowMs, lastHealthFetchMs))">
              {{ formatHeartbeatAge(row, nowMs, lastHealthFetchMs) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column
          prop="ref_count"
          :label="t('gatewayStatus.fieldRefCount')"
          min-width="100"
        />

        <el-table-column
          :label="t('gatewayStatus.colInstances')"
          min-width="180"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <div
              v-if="row.instances.length > 0"
              class="flex flex-wrap gap-1"
            >
              <el-tag
                v-for="iid in row.instances.slice(0, 3)"
                :key="iid"
                size="small"
                effect="plain"
              >
                {{ iid.slice(0, 8) }}
              </el-tag>
              <span
                v-if="row.instances.length > 3"
                class="text-xs text-gray-500"
              >
                +{{ row.instances.length - 3 }}
              </span>
            </div>
            <span
              v-else
              class="text-gray-400"
            >-</span>
          </template>
        </el-table-column>

        <el-table-column
          :label="t('gatewayStatus.colRecentErrors')"
          min-width="220"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span v-if="row.recent_errors?.length">
              [{{ row.recent_errors[row.recent_errors.length - 1].source }}]
              {{ row.recent_errors[row.recent_errors.length - 1].message }}
            </span>
            <span
              v-else
              class="text-gray-400"
            >-</span>
          </template>
        </el-table-column>

        <el-table-column
          :label="t('gatewayStatus.colActions')"
          fixed="right"
          width="100"
        >
          <template #default="{ row }">
            <el-popconfirm
              v-if="row.gateway_key.startsWith('manual:')"
              :title="t('gatewayStatus.tagDisconnect')"
              @confirm="handleDisconnect(row.gateway_key)"
            >
              <template #reference>
                <el-button
                  type="danger"
                  size="small"
                  plain
                  :loading="disconnecting === row.gateway_key"
                >
                  {{ t('gatewayStatus.btnDisconnect') }}
                </el-button>
              </template>
            </el-popconfirm>
            <span
              v-else
              class="text-gray-400 text-sm"
            >-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Connect Gateway Dialog -->
    <el-dialog
      v-model="showConnectDialog"
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
              v-model="ctpEnv"
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
            v-if="ctpEnv === 'simnow'"
            :label="t('gatewayStatus.formLine')"
          >
            <el-select
              v-model="ctpGroup"
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
            v-if="ctpEnv === 'simnow_7x24'"
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
              v-model="mt5Env"
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
              v-model="ibEnv"
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
        <el-button @click="showConnectDialog = false">
          {{ t('gatewayStatus.btnCancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="connecting"
          :disabled="!connectForm.exchange_type"
          @click="handleConnect"
        >
          {{ t('gatewayStatus.btnConnectAction') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { stateTagType, stateLabel, connTagType, connLabel, heartbeatClass, getHeartbeatAge, formatHeartbeatAge, formatUptime, formatNumber } from './gatewayStatusHelpers'
import { ref, reactive, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Refresh,
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  Connection,
  Grid,
  List,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api'
import { liveTradingApi } from '@/api/liveTrading'
import type { GatewayHealthInfo } from '@/api/liveTrading'

const { t } = useI18n()

const loading = ref(false)
const gateways = ref<GatewayHealthInfo[]>([])
const loadError = ref('')
const viewMode = ref<'card' | 'table'>('card')
const headerActionsTargetReady = ref(false)
const nowMs = ref(Date.now())
const lastHealthFetchMs = ref(Date.now())
let pollTimer: ReturnType<typeof setInterval> | null = null
let headerTargetTimer: ReturnType<typeof setInterval> | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null

const visibleGateways = computed(() => gateways.value.filter((g) => !g.gateway_key.startsWith('direct:')))
const healthyCount = computed(() => visibleGateways.value.filter((g) => g.is_healthy).length)

// ---- Connect Dialog ----
const showConnectDialog = ref(false)
const connecting = ref(false)
const disconnecting = ref<string | null>(null)

type GatewayCredentialScalar = string | number | boolean | null | undefined

interface GatewayCredentials {
  account_id?: string
  access_token?: string
  api_key?: string
  app_id?: string
  asset_type?: string
  auth_code?: string
  base_url?: string
  broker_id?: string
  cookie_browser?: string
  cookie_output?: string
  cookie_path?: string
  cookie_source?: string
  login?: string | number
  login_browser?: string
  login_headless?: boolean
  login_mode?: string
  login_timeout?: number
  md_front?: string
  passphrase?: string
  password?: string
  secret_key?: string
  server?: string
  symbol_suffix?: string
  td_front?: string
  testnet?: boolean
  timeout?: number
  user_id?: string
  username?: string
  verify_ssl?: boolean
  ws_uri?: string
  [key: string]: GatewayCredentialScalar
}

type SavedGatewayCredentials = GatewayCredentials & Record<string, GatewayCredentials | GatewayCredentialScalar>

const connectForm = reactive<{
  exchange_type: string
  credentials: GatewayCredentials
}>({
  exchange_type: '',
  credentials: {},
})

// ---- Saved Credentials from .env ----
const savedCredentials = ref<Record<string, SavedGatewayCredentials>>({})

async function fetchSavedCredentials() {
  try {
    savedCredentials.value = await liveTradingApi.getGatewayCredentials() as Record<string, SavedGatewayCredentials>
  } catch { /* ignore */ }
}

async function openConnectDialog() {
  await fetchSavedCredentials()
  connectForm.exchange_type = ''
  connectForm.credentials = {}
  showConnectDialog.value = true
}

// ---- CTP Environment Presets ----
const ctpEnv = ref<string>('simnow')
const ctpGroup = ref<number>(1)
const mt5Env = ref<string>('demo')
const ibEnv = ref<string>('paper')

const CTP_PRESETS: Record<string, { broker_id: string; td_front: string; md_front: string; app_id: string; auth_code: string }> = {
  simnow_1: { broker_id: '9999', td_front: 'tcp://182.254.243.31:30001', md_front: 'tcp://182.254.243.31:30011', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
  simnow_2: { broker_id: '9999', td_front: 'tcp://182.254.243.31:30002', md_front: 'tcp://182.254.243.31:30012', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
  simnow_3: { broker_id: '9999', td_front: 'tcp://182.254.243.31:30003', md_front: 'tcp://182.254.243.31:30013', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
  simnow_7x24: { broker_id: '9999', td_front: 'tcp://182.254.243.31:40001', md_front: 'tcp://182.254.243.31:40011', app_id: 'simnow_client_test', auth_code: '0000000000000000' },
}

function applyCtpPreset() {
  const key = ctpEnv.value === 'simnow' ? `simnow_${ctpGroup.value}` : ctpEnv.value
  const preset = CTP_PRESETS[key]
  if (!preset) return
  const saved = savedCredentials.value['CTP'] || {}
  const userId = connectForm.credentials.user_id || saved.user_id || ''
  const password = connectForm.credentials.password || saved.password || ''
  connectForm.credentials = {
    ...preset,
    broker_id: saved.broker_id || preset.broker_id,
    app_id: saved.app_id || preset.app_id,
    auth_code: saved.auth_code || preset.auth_code,
    user_id: userId,
    password: password,
  }
}

function onCtpEnvChange() {
  applyCtpPreset()
}

function onCtpGroupChange() {
  applyCtpPreset()
}

function toGatewayCredentials(value: GatewayCredentials | GatewayCredentialScalar): GatewayCredentials {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value
}

function applyMt5Preset() {
  const saved = savedCredentials.value['MT5'] || {}
  const mode = toGatewayCredentials(saved[mt5Env.value])
  connectForm.credentials = {
    login: mode.login || saved.login || '',
    password: mode.password || saved.password || '',
    server: mode.server || saved.server || '',
    ws_uri: mode.ws_uri || saved.ws_uri || '',
    symbol_suffix: mode.symbol_suffix || saved.symbol_suffix || '',
    timeout: mode.timeout || saved.timeout || 60,
  }
}

function onMt5EnvChange() {
  applyMt5Preset()
}

function applyIbPreset() {
  const saved = savedCredentials.value['IB_WEB'] || {}
  const mode = toGatewayCredentials(saved[ibEnv.value])
  connectForm.credentials = {
    account_id: mode.account_id || saved.account_id || '',
    asset_type: mode.asset_type || saved.asset_type || 'STK',
    base_url: mode.base_url || saved.base_url || '',
    access_token: mode.access_token || saved.access_token || '',
    verify_ssl: mode.verify_ssl ?? saved.verify_ssl ?? false,
    timeout: mode.timeout || saved.timeout || 10,
    cookie_source: mode.cookie_source || saved.cookie_source || '',
    cookie_browser: mode.cookie_browser || saved.cookie_browser || 'chrome',
    cookie_path: mode.cookie_path || saved.cookie_path || '/sso',
    username: mode.username || saved.username || '',
    password: mode.password || saved.password || '',
    login_mode: ibEnv.value,
    login_browser: mode.login_browser || saved.login_browser || 'chrome',
    login_headless: mode.login_headless ?? saved.login_headless ?? false,
    login_timeout: mode.login_timeout || saved.login_timeout || 180,
    cookie_output: mode.cookie_output || saved.cookie_output || '',
  }
}

function onIbEnvChange() {
  applyIbPreset()
}

function onExchangeChange() {
  const exType = connectForm.exchange_type
  const saved = savedCredentials.value[exType] || {}
  if (exType === 'CTP') {
    ctpEnv.value = 'simnow'
    ctpGroup.value = 1
    connectForm.credentials = {}
    applyCtpPreset()
  } else if (exType === 'MT5') {
    mt5Env.value = 'demo'
    applyMt5Preset()
  } else if (exType === 'IB_WEB') {
    ibEnv.value = 'paper'
    applyIbPreset()
  } else if (exType === 'BINANCE') {
    connectForm.credentials = {
      account_id: saved.account_id || '',
      asset_type: saved.asset_type || 'SWAP',
      api_key: saved.api_key || '',
      secret_key: saved.secret_key || '',
      base_url: saved.base_url || '',
      testnet: saved.testnet ?? false,
    }
  } else if (exType === 'OKX') {
    connectForm.credentials = {
      account_id: saved.account_id || '',
      asset_type: saved.asset_type || 'SWAP',
      api_key: saved.api_key || '',
      secret_key: saved.secret_key || '',
      passphrase: saved.passphrase || '',
      base_url: saved.base_url || '',
      testnet: saved.testnet ?? false,
    }
  } else {
    connectForm.credentials = { ...saved }
  }
}

async function handleConnect() {
  if (!connectForm.exchange_type) return
  connecting.value = true
  try {
    const credentials = { ...connectForm.credentials }
    if (connectForm.exchange_type === 'IB_WEB') {
      credentials.login_mode = ibEnv.value
    }
    const res = await liveTradingApi.connectGateway({
      exchange_type: connectForm.exchange_type,
      credentials,
    })
    ElMessage.success(res.message || t('gatewayStatus.msgConnected'))
    showConnectDialog.value = false
    connectForm.exchange_type = ''
    connectForm.credentials = {}
    await fetchHealth()
  } catch {
    // Error already shown by Axios interceptor
  } finally {
    connecting.value = false
  }
}

async function handleDisconnect(gatewayKey: string) {
  disconnecting.value = gatewayKey
  try {
    const res = await liveTradingApi.disconnectGateway(gatewayKey)
    gateways.value = gateways.value.filter((gw) => gw.gateway_key !== gatewayKey)
    ElMessage.success(res.message || t('gatewayStatus.msgDisconnected'))
    try {
      await fetchHealth()
    } catch {
      // fetchHealth already handles UI state; keep optimistic removal result
    }
  } catch {
    // Error already shown by Axios interceptor
  } finally {
    disconnecting.value = null
  }
}

// ---- Health Fetch ----
async function fetchHealth() {
  loading.value = true
  try {
    const res = await liveTradingApi.listGatewayHealth()
    gateways.value = res.gateways
    nowMs.value = Date.now()
    lastHealthFetchMs.value = nowMs.value
    loadError.value = ''
  } catch (error) {
    loadError.value = getErrorMessage(error, t('gatewayStatus.msgLoadFailed'))
  } finally {
    loading.value = false
  }
}


function updateHeaderActionsTargetReady() {
  if (typeof document === 'undefined') {
    headerActionsTargetReady.value = false
    return false
  }
  headerActionsTargetReady.value = document.getElementById('page-header-actions') !== null
  return headerActionsTargetReady.value
}

onMounted(async () => {
  await nextTick()
  if (!updateHeaderActionsTargetReady()) {
    headerTargetTimer = setInterval(() => {
      if (updateHeaderActionsTargetReady() && headerTargetTimer) {
        clearInterval(headerTargetTimer)
        headerTargetTimer = null
      }
    }, 100)
  }
  fetchHealth()
  fetchSavedCredentials()
  heartbeatTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1_000)
  pollTimer = setInterval(fetchHealth, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (headerTargetTimer) clearInterval(headerTargetTimer)
  if (heartbeatTimer) clearInterval(heartbeatTimer)
})
</script>
