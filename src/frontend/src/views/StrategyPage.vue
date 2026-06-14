<template>
  <div class="space-y-6">
    <!-- Page action bar -->
    <div class="flex justify-end items-center">
      <el-button
        type="primary"
        :aria-label="t('strategy.createStrategy')"
        @click="showCreateDialog"
      >
        <el-icon
          class="mr-1"
          aria-hidden="true"
        >
          <Plus />
        </el-icon>
        {{ t('strategy.createStrategy') }}
      </el-button>
    </div>

    <!-- Main tabs: Gallery / My strategies -->
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <!-- ========== Gallery ========== -->
      <el-tab-pane
        :label="t('strategy.gallery')"
        name="gallery"
      >
        <!-- Search and filter bar -->
        <div class="flex flex-wrap gap-4 mb-6">
          <el-input
            v-model="searchKeyword"
            :placeholder="t('strategy.searchPlaceholder')"
            :aria-label="t('strategy.searchAriaLabel')"
            clearable
            class="w-64"
            prefix-icon="Search"
          />
          <el-radio-group
            v-model="categoryFilter"
            size="default"
            :aria-label="t('strategy.filterAriaLabel')"
          >
            <el-radio-button label="">
              {{ t('strategy.categoryAll') }}
            </el-radio-button>
            <el-radio-button label="trend">
              {{ t('strategy.categoryTrend') }}
            </el-radio-button>
            <el-radio-button label="mean_reversion">
              {{ t('strategy.categoryMeanReversion') }}
            </el-radio-button>
            <el-radio-button label="volatility">
              {{ t('strategy.categoryVolatility') }}
            </el-radio-button>
            <el-radio-button label="indicator">
              {{ t('strategy.categoryIndicator') }}
            </el-radio-button>
            <el-radio-button label="arbitrage">
              {{ t('strategy.categoryArbitrage') }}
            </el-radio-button>
            <el-radio-button label="custom">
              {{ t('strategy.categoryOther') }}
            </el-radio-button>
          </el-radio-group>
          <span class="text-gray-400 text-sm self-center ml-auto">
            {{ t('strategy.customCount', { count: filteredTemplates.length }) }}
          </span>
        </div>

        <!-- Strategy card grid -->
        <div
          v-if="filteredTemplates.length"
          class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"
        >
          <StrategyTemplateCard
            v-for="tpl in paginatedTemplates"
            :key="tpl.id"
            :tpl="tpl"
            @detail="openTemplateDetail"
            @use="useTemplate"
            @backtest="goBacktest"
          />
        </div>
        <el-empty
          v-else
          :description="t('strategy.noMatch')"
        />

        <!-- Pagination -->
        <div
          v-if="filteredTemplates.length > pageSize"
          class="flex justify-center mt-6"
        >
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="filteredTemplates.length"
            layout="prev, pager, next"
          />
        </div>
      </el-tab-pane>

      <!-- ========== My strategies ========== -->
      <el-tab-pane
        :label="t('strategy.myStrategies')"
        name="my"
      >
        <el-table
          v-loading="loading"
          :data="strategies"
          stripe
          :empty-text="t('strategy.customEmpty')"
        >
          <el-table-column
            prop="name"
            :label="t('strategy.strategyName')"
            width="200"
          />
          <el-table-column
            prop="description"
            :label="t('strategy.paramDescription')"
            show-overflow-tooltip
          />
          <el-table-column
            prop="category"
            :label="$t('common.action')"
            width="120"
          >
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="getCategoryType(row.category)"
              >
                {{ getCategoryLabel(row.category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="created_at"
            :label="t('strategy.createdAt')"
            width="180"
          />
          <el-table-column
            :label="$t('common.action')"
            width="220"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                type="primary"
                link
                size="small"
                @click="viewStrategy(row)"
              >
                {{ t('strategy.actionView') }}
              </el-button>
              <el-button
                type="warning"
                link
                size="small"
                @click="editStrategy(row)"
              >
                {{ t('strategy.actionEdit') }}
              </el-button>
              <el-button
                type="danger"
                link
                size="small"
                @click="deleteStrategy(row.id)"
              >
                {{ t('strategy.actionDelete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ========== 策略详情弹窗 (模板) ========== -->
    <StrategyDetailDialog
      v-model:visible="detailVisible"
      v-model:detail-tab="detailTab"
      :template="detailTemplate"
      :param-table-data="paramTableData"
      :readme-loading="readmeLoading"
      :readme-content="readmeContent"
      :rendered-readme="renderedReadme"
      :strip-meta="stripStrategyMeta"
      @use="useTemplate"
      @backtest="goBacktest"
    />

    <!-- ========== 创建/编辑弹窗 ========== -->
    <StrategyEditDialog
      v-model:visible="dialogVisible"
      :is-edit="isEdit"
      :saving="saving"
      :form="form"
      @update:form="updateStrategyForm"
      @save="saveStrategy"
    />

    <!-- ========== My strategy detail dialog ========== -->
    <el-dialog
      v-model="viewDialogVisible"
      :title="t('strategy.detailLabel')"
      width="800px"
    >
      <div
        v-if="currentStrategy"
        class="space-y-4"
      >
        <div class="flex justify-between items-center">
          <h2 class="text-xl font-bold">
            {{ currentStrategy.name }}
          </h2>
          <el-tag :type="getCategoryType(currentStrategy.category)">
            {{ getCategoryLabel(currentStrategy.category) }}
          </el-tag>
        </div>
        <p class="text-gray-500">
          {{ currentStrategy.description }}
        </p>
        <el-divider />
        <MonacoEditor
          v-model="currentStrategy.code"
          language="python"
          :height="400"
          :read-only="true"
          theme="vs"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '@/stores/strategy'
import { strategyApi } from '@/api/strategy'
import { getCategoryType, getCategoryLabel, stripStrategyMeta } from '@/constants/strategy'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
import StrategyEditDialog from './strategy-components/StrategyEditDialog.vue'
import StrategyDetailDialog from './strategy-components/StrategyDetailDialog.vue'
import StrategyTemplateCard from './strategy-components/StrategyTemplateCard.vue'
import type { ParamSpec, Strategy, StrategyTemplate } from '@/types'
import DOMPurify from 'dompurify'

const { t } = useI18n()
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
  return Object.entries(detailTemplate.value.params).map(([name, spec]: [string, ParamSpec]) => ({
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
  return DOMPurify.sanitize(md)
})

// ---- Methods ----
async function openTemplateDetail(t: StrategyTemplate) {
  detailTemplate.value = t
  detailTab.value = 'readme'
  detailVisible.value = true
  readmeContent.value = ''
  readmeLoading.value = true
  try {
    const res = await strategyApi.getTemplateReadme(t.id)
    readmeContent.value = res.content ?? ''
  } catch {
    readmeContent.value = ''
  } finally {
    readmeLoading.value = false
  }
}

function goBacktest(t: StrategyTemplate) {
  detailVisible.value = false
  router.push({ path: '/backtest/legacy', query: { strategy: t.id } })
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
    name: template.name + ` (${t('strategy.typeCopy')})`,
    description: stripStrategyMeta(template.description),
    code: template.code,
    category: template.category,
  })
  activeTab.value = 'my'
  dialogVisible.value = true
}

function updateStrategyForm(nextForm: typeof form) {
  Object.assign(form, nextForm)
}

async function saveStrategy() {
  if (!form.name || !form.code) {
    ElMessage.warning(t('strategy.warnNameOrCodeEmpty'))
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await strategyStore.updateStrategy(editingId.value, form)
      ElMessage.success(t('strategy.updated'))
    } else {
      await strategyStore.createStrategy(form)
      ElMessage.success(t('strategy.created'))
    }
    dialogVisible.value = false
  } finally {
    saving.value = false
  }
}

async function deleteStrategy(id: string) {
  await ElMessageBox.confirm(t('strategy.confirmDeleteText'), t('strategy.confirmDeleteTitle'), { type: 'warning' })
  await strategyStore.deleteStrategy(id)
  ElMessage.success(t('strategy.deleted'))
}

onMounted(async () => {
  try {
    await Promise.all([
      strategyStore.fetchStrategies(),
      strategyStore.fetchTemplates(),
    ])
  } catch {
    ElMessage.error(t('strategy.loadFailed'))
  }
})
</script>

<style scoped>
.strategy-card {
  transition: transform 0.15s, box-shadow 0.15s;
}
.strategy-card:hover {
  transform: translateY(-2px);
}
.strategy-card:focus-visible {
  outline: 2px solid var(--el-color-primary, #409eff);
  outline-offset: 2px;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.readme-content h1, .readme-content h2, .readme-content h3 {
  border-bottom: 1px solid var(--border-color-light);
  padding-bottom: 4px;
}
</style>
