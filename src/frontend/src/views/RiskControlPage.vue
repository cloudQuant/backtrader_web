<template>
  <section class="risk-control-page">
    <header class="page-header">
      <div><h1>{{ t('riskControl.title') }}</h1><p>{{ t('riskControl.subtitle') }}</p></div>
      <el-button @click="load">{{ t('riskControl.refresh') }}</el-button>
    </header>
    <el-card>
      <template #header><strong>{{ t('riskControl.newRule') }}</strong></template>
      <el-form inline @submit.prevent="createRule">
        <el-form-item :label="t('riskControl.name')"><el-input v-model="form.name" /></el-form-item>
        <el-form-item :label="t('riskControl.type')"><el-input v-model="form.ruleType" placeholder="max_drawdown" /></el-form-item>
        <el-form-item :label="t('riskControl.runtimeInstance')"><el-input v-model="form.instanceId" :placeholder="t('riskControl.optional')" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="saving" @click="createRule">{{ t('riskControl.saveRule') }}</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-card>
      <template #header><strong>{{ t('riskControl.ruleList') }}</strong></template>
      <div v-if="loading" class="page-state">{{ t('riskControl.loading') }}</div>
      <el-empty v-else-if="!rules.length" :description="t('riskControl.noRules')" />
      <el-table v-else :data="rules">
        <el-table-column prop="name" :label="t('riskControl.name')" min-width="150" />
        <el-table-column prop="rule_type" :label="t('riskControl.type')" min-width="150" />
        <el-table-column prop="instance_id" :label="t('riskControl.runtimeInstance')" min-width="200" />
        <el-table-column :label="t('riskControl.status')" width="120"><template #default="{ row }"><el-switch v-model="row.is_active" @change="toggleRule(row)" /></template></el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { paperRuntimeApi, type RiskRule } from '@/api/paperRuntime'
import { getErrorMessage } from '@/api'

const loading = ref(true)
const { t } = useI18n()
const saving = ref(false)
const rules = ref<RiskRule[]>([])
const form = reactive({ name: '', ruleType: 'max_drawdown', instanceId: '' })

onMounted(load)

async function load() {
  loading.value = true
  try { rules.value = await paperRuntimeApi.listRules() }
  catch (reason) { ElMessage.error(getErrorMessage(reason, t('riskControl.loadFailed'))) }
  finally { loading.value = false }
}

async function createRule() {
  if (!form.name.trim() || !form.ruleType.trim()) return
  saving.value = true
  try {
    const rule = await paperRuntimeApi.createRule({
      name: form.name.trim(), rule_type: form.ruleType.trim(), instance_id: form.instanceId.trim() || undefined,
    })
    rules.value = [rule, ...rules.value]
    form.name = ''
    ElMessage.success(t('riskControl.saveSuccess'))
  } catch (reason) { ElMessage.error(getErrorMessage(reason, t('riskControl.saveFailed'))) }
  finally { saving.value = false }
}

async function toggleRule(rule: RiskRule) {
  try { await paperRuntimeApi.updateRule(rule.id, { is_active: rule.is_active }) }
  catch (reason) { rule.is_active = !rule.is_active; ElMessage.error(getErrorMessage(reason, t('riskControl.updateFailed'))) }
}
</script>

<style scoped>
.risk-control-page { display: grid; gap: 16px; }.page-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-header h1 { margin: 0; }.page-header p { margin: 6px 0 0; color: var(--el-text-color-secondary); }.page-state { padding: 32px; text-align: center; color: var(--el-text-color-secondary); }
</style>
