<template>
  <div class="space-y-6">
    <!-- 页面标题和操作栏 -->
    <div class="flex justify-between items-center">
      <h1 class="text-2xl font-bold">策略中心</h1>
      <el-button type="primary" @click="showCreateDialog">
        <el-icon class="mr-1"><Plus /></el-icon>
        创建策略
      </el-button>
    </div>

    <!-- 主Tab: 策略库 / 我的策略 -->
    <el-tabs v-model="activeTab" type="border-card">
      <!-- ========== 策略库 ========== -->
      <el-tab-pane label="策略库" name="gallery">
        <!-- 搜索和筛选栏 -->
        <div class="flex flex-wrap gap-4 mb-6">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索策略名称或描述..."
            clearable
            class="w-64"
            prefix-icon="Search"
          />
          <el-radio-group v-model="categoryFilter" size="default">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button label="trend">趋势</el-radio-button>
            <el-radio-button label="mean_reversion">均值回归</el-radio-button>
            <el-radio-button label="volatility">波动率</el-radio-button>
            <el-radio-button label="indicator">指标</el-radio-button>
            <el-radio-button label="arbitrage">套利</el-radio-button>
            <el-radio-button label="custom">其他</el-radio-button>
          </el-radio-group>
          <span class="text-gray-400 text-sm self-center ml-auto">
            共 {{ filteredTemplates.length }} 个策略
          </span>
        </div>

        <!-- 策略卡片网格 -->
        <div v-if="filteredTemplates.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <el-card
            v-for="t in paginatedTemplates"
            :key="t.id"
            shadow="hover"
            class="strategy-card cursor-pointer"
            @click="openTemplateDetail(t)"
          >
            <div class="flex flex-col h-full">
              <div class="flex justify-between items-start mb-2">
                <h3 class="font-bold text-base leading-tight">{{ t.name }}</h3>
                <el-tag size="small" :type="getCategoryType(t.category)" effect="light">
                  {{ getCategoryLabel(t.category) }}
                </el-tag>
              </div>
              <p class="text-gray-500 text-sm mb-3 line-clamp-2 flex-1">{{ stripMeta(t.description) }}</p>
              <div class="flex items-center justify-between text-xs text-gray-400">
                <span>{{ getParamCount(t) }} 个参数</span>
                <span>{{ t.id }}</span>
              </div>
              <div class="flex gap-2 mt-3 pt-3 border-t">
                <el-button size="small" type="primary" @click.stop="openTemplateDetail(t)">
                  详情
                </el-button>
                <el-button size="small" @click.stop="useTemplate(t)">
                  复制为我的策略
                </el-button>
                <el-button size="small" type="success" @click.stop="goBacktest(t)">
                  回测
                </el-button>
              </div>
            </div>
          </el-card>
        </div>
        <el-empty v-else description="没有匹配的策略" />

        <!-- 分页 -->
        <div v-if="filteredTemplates.length > pageSize" class="flex justify-center mt-6">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="filteredTemplates.length"
            layout="prev, pager, next"
          />
        </div>
      </el-tab-pane>

      <!-- ========== 我的策略 ========== -->
      <el-tab-pane label="我的策略" name="my">
        <el-table :data="strategies" stripe v-loading="loading" empty-text="暂无自定义策略">
          <el-table-column prop="name" label="策略名称" width="200" />
          <el-table-column prop="description" label="描述" show-overflow-tooltip />
          <el-table-column prop="category" label="分类" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="getCategoryType(row.category)">
                {{ getCategoryLabel(row.category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="viewStrategy(row)">查看</el-button>
              <el-button type="warning" link size="small" @click="editStrategy(row)">编辑</el-button>
              <el-button type="danger" link size="small" @click="deleteStrategy(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ========== 策略详情弹窗 (模板) ========== -->
    <el-dialog v-model="detailVisible" :title="detailTemplate?.name" width="900px" top="5vh">
      <div v-if="detailTemplate" class="space-y-4">
        <div class="flex items-center gap-3 flex-wrap">
          <el-tag :type="getCategoryType(detailTemplate.category)">{{ getCategoryLabel(detailTemplate.category) }}</el-tag>
          <span class="text-gray-400 text-sm">{{ detailTemplate.id }}</span>
        </div>
        <p class="text-gray-600">{{ stripMeta(detailTemplate.description) }}</p>

        <!-- 参数表 -->
        <div v-if="Object.keys(detailTemplate.params).length">
          <h4 class="font-bold text-sm mb-2">策略参数</h4>
          <el-table :data="paramTableData" size="small" border stripe>
            <el-table-column prop="name" label="参数名" width="180" />
            <el-table-column prop="default" label="默认值" width="120" />
            <el-table-column prop="type" label="类型" width="80" />
            <el-table-column prop="description" label="说明" />
          </el-table>
        </div>

        <!-- Tab: README / 代码 -->
        <el-tabs v-model="detailTab">
          <el-tab-pane label="策略文档" name="readme">
            <div v-if="readmeLoading" class="flex justify-center py-8">
              <el-icon class="is-loading text-2xl"><Loading /></el-icon>
            </div>
            <div v-else-if="readmeContent" class="prose prose-sm max-w-none readme-content" v-html="renderedReadme"></div>
            <el-empty v-else description="暂无文档" />
          </el-tab-pane>
          <el-tab-pane label="策略代码" name="code">
            <MonacoEditor
              v-model="detailTemplate.code"
              language="python"
              :height="450"
              :readOnly="true"
              theme="vs"
            />
          </el-tab-pane>
        </el-tabs>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button @click="useTemplate(detailTemplate!)">复制为我的策略</el-button>
        <el-button type="primary" @click="goBacktest(detailTemplate!)">去回测</el-button>
      </template>
    </el-dialog>

    <!-- ========== 创建/编辑弹窗 ========== -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑策略' : '创建策略'" width="800px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="策略名称" required>
          <el-input v-model="form.name" placeholder="输入策略名称" />
        </el-form-item>
        <el-form-item label="策略描述">
          <el-input v-model="form.description" type="textarea" rows="2" placeholder="策略描述" />
        </el-form-item>
        <el-form-item label="策略分类">
          <el-select v-model="form.category" class="w-full">
            <el-option label="趋势策略" value="trend" />
            <el-option label="均值回归" value="mean_reversion" />
            <el-option label="波动率" value="volatility" />
            <el-option label="指标策略" value="indicator" />
            <el-option label="套利策略" value="arbitrage" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略代码" required>
          <MonacoEditor v-model="form.code" language="python" :height="400" theme="vs" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveStrategy" :loading="saving">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ========== 查看我的策略弹窗 ========== -->
    <el-dialog v-model="viewDialogVisible" title="策略详情" width="800px">
      <div v-if="currentStrategy" class="space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-xl font-bold">{{ currentStrategy.name }}</h2>
          <el-tag :type="getCategoryType(currentStrategy.category)">
            {{ getCategoryLabel(currentStrategy.category) }}
          </el-tag>
        </div>
        <p class="text-gray-500">{{ currentStrategy.description }}</p>
        <el-divider />
        <MonacoEditor v-model="currentStrategy.code" language="python" :height="400" :readOnly="true" theme="vs" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useStrategyStore } from '@/stores/strategy'
import { strategyApi } from '@/api/strategy'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
import type { Strategy, StrategyTemplate } from '@/types'

const router = useRouter()
const strategyStore = useStrategyStore()

// ---- State ----
const activeTab = ref('gallery')
const searchKeyword = ref('')
const categoryFilter = ref('')
const currentPage = ref(1)
const pageSize = 12

const dialogVisible = ref(false)
const viewDialogVisible = ref(false)
const detailVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const editingId = ref('')
const currentStrategy = ref<Strategy | null>(null)

const detailTemplate = ref<StrategyTemplate | null>(null)
const detailTab = ref('readme')
const readmeContent = ref('')
const readmeLoading = ref(false)

const form = reactive({
  name: '',
  description: '',
  code: '',
  category: 'custom',
})

// ---- Computed ----
const strategies = computed(() => strategyStore.strategies)
const templates = computed(() => strategyStore.templates)
const loading = computed(() => strategyStore.loading)

const filteredTemplates = computed(() => {
  let list = templates.value
  if (categoryFilter.value) {
    list = list.filter(t => t.category === categoryFilter.value)
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(t =>
      t.name.toLowerCase().includes(kw) ||
      t.description.toLowerCase().includes(kw) ||
      t.id.toLowerCase().includes(kw)
    )
  }
  return list
})

const paginatedTemplates = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredTemplates.value.slice(start, start + pageSize)
})

const paramTableData = computed(() => {
  if (!detailTemplate.value) return []
  return Object.entries(detailTemplate.value.params).map(([name, spec]: [string, any]) => ({
    name,
    default: spec.default ?? '-',
    type: spec.type ?? '-',
    description: spec.description ?? name,
  }))
})

const renderedReadme = computed(() => {
  // Simple markdown to HTML - headings, bold, code blocks, tables, lists
  if (!readmeContent.value) return ''
  let md = readmeContent.value
  // Code blocks
  md = md.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-100 p-3 rounded overflow-auto text-sm"><code>$2</code></pre>')
  // Headings
  md = md.replace(/^#### (.+)$/gm, '<h4 class="font-bold text-base mt-4 mb-1">$1</h4>')
  md = md.replace(/^### (.+)$/gm, '<h3 class="font-bold text-lg mt-5 mb-1">$1</h3>')
  md = md.replace(/^## (.+)$/gm, '<h2 class="font-bold text-xl mt-6 mb-2">$1</h2>')
  md = md.replace(/^# (.+)$/gm, '<h1 class="font-bold text-2xl mt-6 mb-3">$1</h1>')
  // Bold
  md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Inline code
  md = md.replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 rounded text-sm">$1</code>')
  // Tables
  md = md.replace(/^\|(.+)\|$/gm, (match) => {
    const cells = match.split('|').filter(Boolean).map(c => c.trim())
    if (cells.every(c => /^[-:]+$/.test(c))) return '' // separator row
    const tag = 'td'
    return '<tr>' + cells.map(c => `<${tag} class="border px-2 py-1">${c}</${tag}>`).join('') + '</tr>'
  })
  md = md.replace(/((<tr>.*<\/tr>\s*)+)/g, '<table class="w-full border-collapse border text-sm my-2">$1</table>')
  // Lists
  md = md.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
  md = md.replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
  // Paragraphs
  md = md.replace(/\n\n/g, '</p><p class="my-2">')
  md = '<p class="my-2">' + md + '</p>'
  return md
})

// ---- Methods ----
function getCategoryLabel(category: string) {
  const labels: Record<string, string> = {
    trend: '趋势', mean_reversion: '均值回归', volatility: '波动率',
    indicator: '指标', arbitrage: '套利', custom: '其他',
  }
  return labels[category] || category
}

function getCategoryType(category: string) {
  const types: Record<string, string> = {
    trend: '', mean_reversion: 'success', volatility: 'warning',
    indicator: 'info', arbitrage: 'danger', custom: 'info',
  }
  return types[category] || 'info'
}

function stripMeta(desc: string) {
  return desc.split(' | ')[0]
}

function getParamCount(t: StrategyTemplate) {
  return Object.keys(t.params).length
}

async function openTemplateDetail(t: StrategyTemplate) {
  detailTemplate.value = t
  detailTab.value = 'readme'
  detailVisible.value = true
  readmeContent.value = ''
  readmeLoading.value = true
  try {
    const res: any = await strategyApi.getTemplateReadme(t.id)
    readmeContent.value = res.content || ''
  } catch {
    readmeContent.value = ''
  } finally {
    readmeLoading.value = false
  }
}

function goBacktest(t: StrategyTemplate) {
  detailVisible.value = false
  router.push({ path: '/backtest', query: { strategy: t.id } })
}

function showCreateDialog() {
  isEdit.value = false
  editingId.value = ''
  Object.assign(form, { name: '', description: '', code: '', category: 'custom' })
  dialogVisible.value = true
}

function editStrategy(strategy: Strategy) {
  isEdit.value = true
  editingId.value = strategy.id
  Object.assign(form, {
    name: strategy.name,
    description: strategy.description || '',
    code: strategy.code,
    category: strategy.category,
  })
  dialogVisible.value = true
}

function viewStrategy(strategy: Strategy) {
  currentStrategy.value = strategy
  viewDialogVisible.value = true
}

function useTemplate(template: StrategyTemplate) {
  detailVisible.value = false
  isEdit.value = false
  editingId.value = ''
  Object.assign(form, {
    name: template.name + ' (副本)',
    description: stripMeta(template.description),
    code: template.code,
    category: template.category,
  })
  activeTab.value = 'my'
  dialogVisible.value = true
}

async function saveStrategy() {
  if (!form.name || !form.code) {
    ElMessage.warning('请填写策略名称和代码')
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await strategyStore.updateStrategy(editingId.value, form)
      ElMessage.success('策略已更新')
    } else {
      await strategyStore.createStrategy(form)
      ElMessage.success('策略已创建')
    }
    dialogVisible.value = false
  } finally {
    saving.value = false
  }
}

async function deleteStrategy(id: string) {
  await ElMessageBox.confirm('确定删除此策略？', '提示', { type: 'warning' })
  await strategyStore.deleteStrategy(id)
  ElMessage.success('删除成功')
}

onMounted(async () => {
  await Promise.all([
    strategyStore.fetchStrategies(),
    strategyStore.fetchTemplates(),
  ])
})
</script>

<style scoped>
.strategy-card {
  transition: transform 0.15s, box-shadow 0.15s;
}
.strategy-card:hover {
  transform: translateY(-2px);
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.readme-content h1, .readme-content h2, .readme-content h3 {
  border-bottom: 1px solid #eee;
  padding-bottom: 4px;
}
</style>
