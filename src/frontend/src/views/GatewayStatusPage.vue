<template>
  <div
    class="gateway-page"
    data-test="gateway-page"
  >
    <section
      class="gateway-hero"
      data-test="gateway-hero"
    >
      <div class="gateway-hero-copy">
        <div class="gateway-kicker">
          {{ t('gatewayStatus.heroKicker') }}
        </div>
        <h1>{{ t('gatewayStatus.heroTitle') }}</h1>
        <p>{{ t('gatewayStatus.heroDesc') }}</p>
      </div>

      <div class="gateway-hero-actions">
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
          :icon="Refresh"
          :loading="loading"
          @click="fetchHealth"
        >
          {{ t('gatewayStatus.btnRefresh') }}
        </el-button>
        <el-button
          type="primary"
          :icon="Connection"
          @click="openConnectDialog"
        >
          {{ t('gatewayStatus.btnConnect') }}
        </el-button>
      </div>

      <div
        class="gateway-metrics"
        data-test="gateway-metrics"
      >
        <article class="gateway-metric">
          <el-icon aria-hidden="true">
            <Connection />
          </el-icon>
          <span>{{ t('gatewayStatus.statConnectedGateways') }}</span>
          <strong>{{ visibleGateways.length }}</strong>
        </article>
        <article class="gateway-metric">
          <el-icon aria-hidden="true">
            <CircleCheckFilled />
          </el-icon>
          <span>{{ t('gatewayStatus.statHealthyGateways') }}</span>
          <strong>{{ healthyCount }}</strong>
        </article>
        <article class="gateway-metric">
          <el-icon aria-hidden="true">
            <Grid />
          </el-icon>
          <span>{{ t('gatewayStatus.statSymbolCount') }}</span>
          <strong>{{ totalSymbolCount }}</strong>
        </article>
        <article class="gateway-metric">
          <el-icon aria-hidden="true">
            <List />
          </el-icon>
          <span>{{ t('gatewayStatus.statOrderCount') }}</span>
          <strong>{{ totalOrderCount }}</strong>
        </article>
      </div>
    </section>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="gateway-alert"
      data-test="gateway-alert"
    />

    <el-card
      class="gateway-panel gateway-workbench"
      data-test="gateway-workbench"
    >
      <template #header>
        <div class="gateway-panel-heading">
          <div>
            <div class="gateway-kicker">
              {{ t('gatewayStatus.workbenchKicker') }}
            </div>
            <div class="gateway-panel-title">
              {{ t('gatewayStatus.workbenchTitle') }}
            </div>
            <p>{{ t('gatewayStatus.workbenchDesc') }}</p>
          </div>
          <div class="gateway-count">
            {{ t('gatewayStatus.headerHealthSummary', { healthy: healthyCount, total: visibleGateways.length }) }}
            <span>{{ t('gatewayStatus.staleHeartbeatSummary', { count: staleHeartbeatCount }) }}</span>
          </div>
        </div>
      </template>

      <div class="gateway-toolbar">
        <el-input
          v-model="gatewaySearch"
          clearable
          class="toolbar-search"
          :prefix-icon="Search"
          :placeholder="t('gatewayStatus.searchPlaceholder')"
        />
        <el-select
          v-model="stateFilter"
          class="toolbar-item"
        >
          <el-option
            :label="t('gatewayStatus.filterAllStates')"
            value="all"
          />
          <el-option
            :label="t('gatewayStatus.stateRunning')"
            value="running"
          />
          <el-option
            :label="t('gatewayStatus.stateError')"
            value="error"
          />
          <el-option
            :label="t('gatewayStatus.stateRegistered')"
            value="registered"
          />
        </el-select>
        <el-select
          v-model="healthFilter"
          class="toolbar-item"
        >
          <el-option
            :label="t('gatewayStatus.filterAllHealth')"
            value="all"
          />
          <el-option
            :label="t('gatewayStatus.filterHealthy')"
            value="healthy"
          />
          <el-option
            :label="t('gatewayStatus.filterUnhealthy')"
            value="unhealthy"
          />
        </el-select>
      </div>

      <div
        v-if="loading && visibleGateways.length === 0"
        class="gateway-loading"
      >
        <el-icon class="is-loading">
          <Loading />
        </el-icon>
      </div>

      <div
        v-else-if="visibleGateways.length === 0"
        class="gateway-empty"
        data-test="gateway-empty"
      >
        <el-icon aria-hidden="true">
          <Connection />
        </el-icon>
        <strong>{{ t('gatewayStatus.emptyTitle') }}</strong>
        <span>{{ t('gatewayStatus.emptyDesc') }}</span>
        <el-button
          type="primary"
          :icon="Connection"
          @click="openConnectDialog"
        >
          {{ t('gatewayStatus.btnConnect') }}
        </el-button>
      </div>

      <template v-else>
        <div
          v-if="viewMode === 'card'"
          class="gateway-card-grid"
          data-test="gateway-card-grid"
        >
          <article
            v-for="gw in visibleGateways"
            :key="gw.gateway_key"
            class="gateway-card"
          >
            <div class="gateway-card-head">
              <div>
                <div class="gateway-title-line">
                  <el-icon
                    :class="gw.is_healthy ? 'is-healthy' : 'is-unhealthy'"
                    aria-hidden="true"
                  >
                    <CircleCheckFilled v-if="gw.is_healthy" />
                    <CircleCloseFilled v-else />
                  </el-icon>
                  <strong>{{ gw.strategy_name || gw.gateway_key }}</strong>
                </div>
                <span>{{ gw.gateway_key }}</span>
              </div>
              <div class="gateway-card-state">
                <el-tag
                  :type="stateTagType(gw.state)"
                  size="small"
                >
                  {{ stateLabel(gw.state) }}
                </el-tag>
                <el-tag
                  v-if="gw.gateway_key.startsWith('manual:')"
                  type="warning"
                  size="small"
                  effect="plain"
                >
                  {{ t('gatewayStatus.tagManual') }}
                </el-tag>
              </div>
            </div>

            <div class="gateway-info-grid">
              <span>{{ t('gatewayStatus.fieldExchange') }}</span>
              <strong>{{ gw.exchange || '-' }}</strong>
              <span>{{ t('gatewayStatus.fieldAssetType') }}</span>
              <strong>{{ gw.asset_type || '-' }}</strong>
              <span>{{ t('gatewayStatus.fieldAccount') }}</span>
              <strong>{{ gw.account_id || '-' }}</strong>
              <span>{{ t('gatewayStatus.fieldUptime') }}</span>
              <strong>{{ formatUptime(gw.uptime_sec) }}</strong>
              <span>{{ t('gatewayStatus.fieldMarketConn') }}</span>
              <strong>{{ connLabel(gw.market_connection) }}</strong>
              <span>{{ t('gatewayStatus.fieldTradeConn') }}</span>
              <strong>{{ connLabel(gw.trade_connection) }}</strong>
            </div>

            <div class="gateway-stat-grid">
              <div>
                <span>{{ t('gatewayStatus.statStrategyCount') }}</span>
                <strong>{{ gw.strategy_count }}</strong>
              </div>
              <div>
                <span>{{ t('gatewayStatus.statSymbolCount') }}</span>
                <strong>{{ gw.symbol_count }}</strong>
              </div>
              <div>
                <span>{{ t('gatewayStatus.statTickCount') }}</span>
                <strong>{{ formatNumber(gw.tick_count) }}</strong>
              </div>
              <div>
                <span>{{ t('gatewayStatus.statOrderCount') }}</span>
                <strong>{{ gw.order_count }}</strong>
              </div>
            </div>

            <div class="gateway-meta-row">
              <span>{{ t('gatewayStatus.fieldHeartbeat') }}</span>
              <strong :class="heartbeatClass(getHeartbeatAge(gw, nowMs, lastHealthFetchMs))">
                {{ formatHeartbeatAge(gw, nowMs, lastHealthFetchMs) }}
              </strong>
              <span>{{ t('gatewayStatus.fieldRefCount') }}</span>
              <strong>{{ gw.ref_count }}</strong>
            </div>

            <div
              v-if="gw.instances.length > 0"
              class="gateway-tag-list"
            >
              <span>{{ t('gatewayStatus.fieldInstances') }}</span>
              <el-tag
                v-for="iid in gw.instances.slice(0, 4)"
                :key="iid"
                size="small"
                effect="plain"
              >
                {{ iid.slice(0, 8) }}
              </el-tag>
            </div>

            <div
              v-if="gw.recent_errors?.length"
              class="gateway-error-list"
            >
              <strong>{{ t('gatewayStatus.recentErrors', { n: gw.recent_errors.length }) }}</strong>
              <span
                v-for="(err, idx) in gw.recent_errors.slice(-3)"
                :key="idx"
                :title="err.message"
              >
                [{{ err.source }}] {{ err.message }}
              </span>
            </div>

            <div class="gateway-card-actions">
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
          </article>
        </div>

        <el-table
          v-else
          :data="visibleGateways"
          stripe
          class="gateway-table"
          data-test="gateway-table"
        >
          <el-table-column
            :label="t('gatewayStatus.colGateway')"
            min-width="240"
          >
            <template #default="{ row }">
              <div class="gateway-table-identity">
                <strong>{{ row.strategy_name || row.gateway_key }}</strong>
                <span>{{ row.gateway_key }}</span>
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
            :label="t('gatewayStatus.colState')"
            width="120"
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
            width="125"
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
            width="125"
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
            :label="t('gatewayStatus.fieldHeartbeat')"
            width="120"
          >
            <template #default="{ row }">
              <span :class="heartbeatClass(getHeartbeatAge(row, nowMs, lastHealthFetchMs))">
                {{ formatHeartbeatAge(row, nowMs, lastHealthFetchMs) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('gatewayStatus.colActions')"
            fixed="right"
            width="110"
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
                class="gateway-muted"
              >-</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Refresh,
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  Connection,
  Grid,
  List,
  Search,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api'
import { liveTradingApi } from '@/api/liveTrading'
import type { GatewayHealthInfo } from '@/api/liveTrading'
import {
  connLabel,
  connTagType,
  formatHeartbeatAge,
  formatNumber,
  formatUptime,
  getHeartbeatAge,
  heartbeatClass,
  stateLabel,
  stateTagType,
} from './gatewayStatusHelpers'

const { t } = useI18n()

const loading = ref(false)
const gateways = ref<GatewayHealthInfo[]>([])
const loadError = ref('')
const viewMode = ref<'card' | 'table'>('card')
const gatewaySearch = ref('')
const stateFilter = ref('all')
const healthFilter = ref('all')
const nowMs = ref(Date.now())
const lastHealthFetchMs = ref(Date.now())
let pollTimer: ReturnType<typeof setInterval> | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null

const baseGateways = computed(() => gateways.value.filter((g) => !g.gateway_key.startsWith('direct:')))
const visibleGateways = computed(() => {
  const keyword = gatewaySearch.value.trim().toLowerCase()
  return baseGateways.value.filter((gateway) => {
    if (stateFilter.value !== 'all' && gateway.state !== stateFilter.value) return false
    if (healthFilter.value === 'healthy' && !gateway.is_healthy) return false
    if (healthFilter.value === 'unhealthy' && gateway.is_healthy) return false
    if (!keyword) return true
    return [
      gateway.gateway_key,
      gateway.strategy_name,
      gateway.exchange,
      gateway.asset_type,
      gateway.account_id,
      gateway.state,
      gateway.market_connection,
      gateway.trade_connection,
      ...gateway.instances,
      ...(gateway.recent_errors || []).map((item) => `${item.source} ${item.message}`),
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})
const healthyCount = computed(() => visibleGateways.value.filter((g) => g.is_healthy).length)
const totalSymbolCount = computed(() => visibleGateways.value.reduce((sum, item) => sum + item.symbol_count, 0))
const totalOrderCount = computed(() => visibleGateways.value.reduce((sum, item) => sum + item.order_count, 0))
const staleHeartbeatCount = computed(() =>
  visibleGateways.value.filter((gateway) => {
    const age = getHeartbeatAge(gateway, nowMs.value, lastHealthFetchMs.value)
    return age != null && age >= 30
  }).length
)

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


onMounted(() => {
  void fetchHealth()
  void fetchSavedCredentials()
  heartbeatTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1_000)
  pollTimer = setInterval(fetchHealth, 10_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (heartbeatTimer) clearInterval(heartbeatTimer)
})
</script>

<style scoped>
.gateway-page {
  display: grid;
  gap: 24px;
}

.gateway-hero,
.gateway-panel {
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color-primary);
  box-shadow: 0 1px 2px var(--shadow-color);
}

.gateway-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 24px;
}

.gateway-hero-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.gateway-kicker {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.gateway-hero h1 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 30px;
  line-height: 1.12;
}

.gateway-hero p,
.gateway-panel-heading p {
  max-width: 840px;
  margin: 0;
  color: var(--text-color-regular);
  line-height: 1.65;
}

.gateway-hero-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.gateway-metrics {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.gateway-metric {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.gateway-metric .el-icon {
  color: var(--primary-color);
  font-size: 18px;
}

.gateway-metric span,
.gateway-stat-grid span,
.gateway-info-grid span,
.gateway-meta-row span,
.gateway-tag-list > span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.gateway-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.gateway-alert {
  border-radius: 8px;
}

.gateway-panel {
  min-width: 0;
  box-shadow: none;
}

.gateway-panel :deep(.el-card__header) {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-color-light);
}

.gateway-panel :deep(.el-card__body) {
  padding: 18px;
}

.gateway-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.gateway-panel-title {
  margin: 4px 0 6px;
  color: var(--text-color-primary);
  font-size: 18px;
  font-weight: 780;
  line-height: 1.25;
}

.gateway-count {
  display: grid;
  flex: none;
  gap: 4px;
  min-width: 150px;
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

.gateway-count span {
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

.gateway-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-search {
  width: min(420px, 100%);
}

.toolbar-item {
  width: 180px;
}

.gateway-loading,
.gateway-empty {
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

.gateway-loading .el-icon,
.gateway-empty .el-icon {
  color: var(--primary-color);
  font-size: 28px;
}

.gateway-empty strong {
  color: var(--text-color-primary);
  font-size: 18px;
}

.gateway-empty span {
  max-width: 560px;
  color: var(--text-color-secondary);
  line-height: 1.5;
}

.gateway-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.gateway-card {
  display: grid;
  gap: 14px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.gateway-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.gateway-card-head > div:first-child {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.gateway-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.gateway-title-line strong,
.gateway-table-identity strong {
  color: var(--text-color-primary);
  font-weight: 760;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.gateway-title-line .el-icon {
  flex: none;
}

.gateway-title-line .is-healthy {
  color: var(--success-color);
}

.gateway-title-line .is-unhealthy {
  color: var(--danger-color);
}

.gateway-card-head span,
.gateway-table-identity span {
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.gateway-card-state,
.gateway-card-actions,
.gateway-tag-list {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gateway-card-state {
  justify-content: flex-end;
  flex: none;
}

.gateway-info-grid,
.gateway-meta-row {
  display: grid;
  grid-template-columns: minmax(110px, 0.36fr) minmax(0, 1fr);
  gap: 8px 10px;
  padding: 12px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.gateway-info-grid strong,
.gateway-meta-row strong {
  color: var(--text-color-primary);
  overflow-wrap: break-word;
}

.gateway-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.gateway-stat-grid div {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.gateway-stat-grid strong {
  color: var(--text-color-primary);
  font-size: 17px;
  line-height: 1.2;
}

.gateway-tag-list {
  align-items: flex-start;
}

.gateway-error-list {
  display: grid;
  gap: 5px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--danger-color) 35%, var(--border-color-light) 65%);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 84%, var(--danger-color) 16%);
}

.gateway-error-list strong {
  color: var(--danger-color);
  font-size: 12px;
}

.gateway-error-list span {
  color: var(--text-color-primary);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.gateway-card-actions {
  justify-content: flex-end;
}

.gateway-table {
  width: 100%;
}

.gateway-table :deep(.el-table__header-wrapper th) {
  background: var(--fill-color-lighter);
  color: var(--text-color-secondary);
  font-weight: 760;
}

.gateway-table-identity {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.gateway-muted {
  color: var(--text-color-secondary);
}

.text-gray-400 {
  color: var(--text-color-secondary);
}

.text-green-600 {
  color: var(--success-color);
}

.text-yellow-600 {
  color: var(--warning-color);
}

.text-red-600 {
  color: var(--danger-color);
}

.font-medium {
  font-weight: 760;
}

@media (max-width: 1180px) {
  .gateway-metrics,
  .gateway-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .gateway-hero {
    grid-template-columns: 1fr;
  }

  .gateway-hero-actions {
    justify-content: flex-start;
  }

  .gateway-panel-heading {
    display: grid;
  }

  .gateway-count {
    width: 100%;
    text-align: left;
  }

  .toolbar-search,
  .toolbar-item {
    width: 100%;
  }

  .gateway-table {
    display: none;
  }

  .gateway-card-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 620px) {
  .gateway-page {
    gap: 16px;
  }

  .gateway-hero {
    padding: 18px;
  }

  .gateway-hero h1 {
    font-size: 24px;
  }

  .gateway-metrics,
  .gateway-info-grid,
  .gateway-meta-row,
  .gateway-stat-grid {
    grid-template-columns: 1fr;
  }

  .gateway-panel :deep(.el-card__body) {
    padding: 14px;
  }

  .gateway-card-head {
    display: grid;
  }

  .gateway-card-state,
  .gateway-card-actions {
    justify-content: flex-start;
  }
}
</style>
