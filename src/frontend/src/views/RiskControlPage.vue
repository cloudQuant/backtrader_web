<template>
  <section class="risk-control-page">
    <header class="page-header">
      <div><h1>模拟交易风控</h1><p>管理策略级、运行实例级和账户关联风控规则。</p></div>
      <el-button @click="load">刷新</el-button>
    </header>
    <el-card>
      <template #header><strong>新增规则</strong></template>
      <el-form inline @submit.prevent="createRule">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型"><el-input v-model="form.ruleType" placeholder="max_drawdown" /></el-form-item>
        <el-form-item label="运行实例"><el-input v-model="form.instanceId" placeholder="可选" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="saving" @click="createRule">保存规则</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-card>
      <template #header><strong>规则列表</strong></template>
      <div v-if="loading" class="page-state">查询中…</div>
      <el-empty v-else-if="!rules.length" description="暂无风控规则" />
      <el-table v-else :data="rules">
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="rule_type" label="类型" min-width="150" />
        <el-table-column prop="instance_id" label="运行实例" min-width="200" />
        <el-table-column label="状态" width="120"><template #default="{ row }"><el-switch v-model="row.is_active" @change="toggleRule(row)" /></template></el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { paperRuntimeApi, type RiskRule } from '@/api/paperRuntime'
import { getErrorMessage } from '@/api'

const loading = ref(true)
const saving = ref(false)
const rules = ref<RiskRule[]>([])
const form = reactive({ name: '', ruleType: 'max_drawdown', instanceId: '' })

onMounted(load)

async function load() {
  loading.value = true
  try { rules.value = await paperRuntimeApi.listRules() }
  catch (reason) { ElMessage.error(getErrorMessage(reason, '加载风控规则失败')) }
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
    ElMessage.success('风控规则已保存')
  } catch (reason) { ElMessage.error(getErrorMessage(reason, '保存风控规则失败')) }
  finally { saving.value = false }
}

async function toggleRule(rule: RiskRule) {
  try { await paperRuntimeApi.updateRule(rule.id, { is_active: rule.is_active }) }
  catch (reason) { rule.is_active = !rule.is_active; ElMessage.error(getErrorMessage(reason, '更新规则失败')) }
}
</script>

<style scoped>
.risk-control-page { display: grid; gap: 16px; }.page-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-header h1 { margin: 0; }.page-header p { margin: 6px 0 0; color: var(--el-text-color-secondary); }.page-state { padding: 32px; text-align: center; color: var(--el-text-color-secondary); }
</style>
