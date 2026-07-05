<template>
  <main class="auth-page">
    <div class="auth-toolbar">
      <ThemeSwitcher />
      <LanguageSwitcher />
    </div>

    <section class="auth-layout">
      <section
        class="auth-form-card"
        :aria-labelledby="titleId"
      >
        <div class="auth-brand">
          <span class="auth-brand-mark">
            <el-icon aria-hidden="true">
              <TrendCharts />
            </el-icon>
          </span>
          <span>AI for Investor</span>
        </div>

        <div class="auth-heading">
          <p class="auth-kicker">
            {{ eyebrow }}
          </p>
          <h1 :id="titleId">
            {{ title }}
          </h1>
          <p>{{ subtitle }}</p>
        </div>

        <slot />

        <div
          v-if="$slots.footer"
          class="auth-card-footer"
        >
          <slot name="footer" />
        </div>
      </section>

      <aside
        class="auth-preview"
        :aria-label="t('auth.workspacePreview')"
      >
        <div class="auth-preview-shell">
          <div class="auth-preview-header">
            <div>
              <p>{{ t('auth.previewEyebrow') }}</p>
              <h2>{{ t('auth.previewTitle') }}</h2>
            </div>
            <span class="auth-preview-icon">
              <el-icon aria-hidden="true">
                <DataLine />
              </el-icon>
            </span>
          </div>

          <div class="auth-preview-metrics">
            <div
              v-for="metric in previewMetrics"
              :key="metric.label"
              class="auth-preview-metric"
            >
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>

          <div
            class="auth-preview-chart"
            aria-hidden="true"
          >
            <span
              v-for="bar in previewBars"
              :key="bar"
              class="auth-preview-bar"
              :style="{ '--bar-height': `${bar}%` }"
            />
          </div>

          <div class="auth-preview-status">
            <span>
              <el-icon aria-hidden="true">
                <Lock />
              </el-icon>
              {{ t('auth.previewStatusProtected') }}
            </span>
            <span>
              <el-icon aria-hidden="true">
                <Connection />
              </el-icon>
              {{ t('auth.previewStatusSynced') }}
            </span>
          </div>
        </div>
      </aside>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Connection, DataLine, Lock, TrendCharts } from '@element-plus/icons-vue'
import { useThemeStore } from '@/stores/theme'
import ThemeSwitcher from '@/components/common/ThemeSwitcher.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'

defineProps<{
  title: string
  subtitle: string
  eyebrow: string
  titleId: string
}>()

const { t } = useI18n()
const themeStore = useThemeStore()

const previewBars = [52, 68, 45, 78, 63, 86, 58, 72]

const previewMetrics = computed(() => [
  { label: t('auth.previewMetricSignals'), value: '18' },
  { label: t('auth.previewMetricLatency'), value: '21ms' },
  { label: t('auth.previewMetricRisk'), value: t('auth.previewRiskNormal') },
])

onMounted(() => {
  themeStore.init()
})
</script>

<style lang="scss">
.auth-page {
  position: relative;
  display: grid;
  min-height: 100vh;
  place-items: center;
  overflow: hidden;
  padding: 32px;
  background:
    linear-gradient(135deg, var(--bg-color-page), var(--fill-color-lighter) 48%, var(--bg-color));
  color: var(--text-color-primary);
}

.auth-toolbar {
  position: absolute;
  z-index: 2;
  top: 24px;
  right: 24px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-color-primary);
}

.auth-layout {
  position: relative;
  z-index: 1;
  display: grid;
  width: min(1080px, 100%);
  grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
  gap: 24px;
  align-items: stretch;
}

.auth-form-card,
.auth-preview-shell {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  box-shadow: 0 18px 44px var(--shadow-color);
}

.auth-form-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 32px;
}

.auth-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: fit-content;
  color: var(--text-color-primary);
  font-weight: 750;
  line-height: 1;
}

.auth-brand-mark,
.auth-preview-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-light);
  color: var(--primary-color);
  font-size: 20px;
  flex: none;
}

.auth-heading {
  display: grid;
  gap: 8px;
  margin: 28px 0 24px;
}

.auth-heading h1,
.auth-heading p,
.auth-preview-header h2,
.auth-preview-header p {
  margin: 0;
}

.auth-heading h1 {
  color: var(--text-color-primary);
  font-size: 28px;
  font-weight: 760;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.auth-heading p {
  color: var(--text-color-secondary);
  line-height: 1.55;
}

.auth-kicker {
  color: var(--primary-color) !important;
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
  text-transform: uppercase;
}

.auth-form {
  display: grid;
  gap: 2px;
}

.auth-form .el-form-item {
  margin-bottom: 18px;
}

.auth-submit {
  width: 100%;
}

.auth-card-footer {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--border-color-light);
  color: var(--text-color-secondary);
  font-size: 14px;
  text-align: center;
}

.auth-link {
  margin-left: 6px;
  color: var(--primary-color);
  font-weight: 650;
  text-decoration: none;
}

.auth-link:hover {
  text-decoration: underline;
}

.auth-link:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.auth-preview {
  display: grid;
  min-width: 0;
}

.auth-preview-shell {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100%;
  padding: 28px;
}

.auth-preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.auth-preview-header p {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
  text-transform: uppercase;
}

.auth-preview-header h2 {
  margin-top: 8px;
  color: var(--text-color-primary);
  font-size: 22px;
  font-weight: 760;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.auth-preview-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.auth-preview-metric {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.auth-preview-metric span {
  overflow: hidden;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.auth-preview-metric strong {
  color: var(--text-color-primary);
  font-size: 18px;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.auth-preview-chart {
  display: flex;
  align-items: end;
  gap: 10px;
  min-height: 180px;
  padding: 18px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.auth-preview-bar {
  display: block;
  flex: 1;
  height: var(--bar-height);
  min-height: 24px;
  border-radius: 6px 6px 2px 2px;
  background: var(--primary-color);
  opacity: 0.78;
}

.auth-preview-bar:nth-child(2n) {
  background: var(--success-color);
}

.auth-preview-bar:nth-child(3n) {
  background: var(--warning-color);
}

.auth-preview-status {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: auto;
}

.auth-preview-status span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid var(--success-border-color);
  border-radius: 8px;
  background: var(--fill-color-light);
  color: var(--success-color);
  font-size: 13px;
  font-weight: 650;
}

@media (max-width: 920px) {
  .auth-page {
    align-items: start;
    padding: 84px 20px 24px;
  }

  .auth-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth-preview-shell {
    min-height: auto;
  }
}

@media (max-width: 560px) {
  .auth-page {
    padding: 76px 12px 16px;
  }

  .auth-toolbar {
    top: 16px;
    right: 12px;
  }

  .auth-form-card,
  .auth-preview-shell {
    padding: 20px;
  }

  .auth-heading h1 {
    font-size: 24px;
  }

  .auth-preview-metrics {
    grid-template-columns: 1fr;
  }

  .auth-preview-chart {
    min-height: 132px;
  }
}
</style>
