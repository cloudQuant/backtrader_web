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
            <el-icon aria-hidden="true"><Grid /></el-icon>
          </el-radio-button>
          <el-radio-button value="table">
            <el-icon aria-hidden="true"><List /></el-icon>
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
        <el-icon class="is-loading" aria-hidden="true">
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

    <GatewayConnectDialog
      v-model:visible="showConnectDialog"
      :connect-form="connectForm"
      v-model:ctp-env="ctpEnv"
      v-model:ctp-group="ctpGroup"
      v-model:mt5-env="mt5Env"
      v-model:ib-env="ibEnv"
      :connecting="connecting"
      :on-exchange-change="onExchangeChange"
      :on-ctp-env-change="onCtpEnvChange"
      :on-ctp-group-change="onCtpGroupChange"
      :on-mt5-env-change="onMt5EnvChange"
      :on-ib-env-change="onIbEnvChange"
      :on-connect="handleConnect"
    />
  </div>
</template>


<script setup lang="ts">
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
import GatewayConnectDialog from './GatewayConnectDialog.vue'
import { useGatewayStatusPage } from './gateway/useGatewayStatusPage'

const gatewayStatusPage = useGatewayStatusPage()
const {
  connLabel,
  connTagType,
  connectForm,
  connecting,
  ctpEnv,
  ctpGroup,
  disconnecting,
  fetchHealth,
  formatHeartbeatAge,
  formatNumber,
  formatUptime,
  gatewaySearch,
  getHeartbeatAge,
  handleConnect,
  handleDisconnect,
  healthFilter,
  healthyCount,
  heartbeatClass,
  ibEnv,
  lastHealthFetchMs,
  loadError,
  loading,
  mt5Env,
  nowMs,
  onCtpEnvChange,
  onCtpGroupChange,
  onExchangeChange,
  onIbEnvChange,
  onMt5EnvChange,
  openConnectDialog,
  showConnectDialog,
  staleHeartbeatCount,
  stateFilter,
  stateLabel,
  stateTagType,
  t,
  totalOrderCount,
  totalSymbolCount,
  viewMode,
  visibleGateways,
} = gatewayStatusPage

defineExpose(gatewayStatusPage)
</script>

<style scoped src="./GatewayStatusPage.css" />
