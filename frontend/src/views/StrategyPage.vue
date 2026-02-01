<template>
  <div class="space-y-6">
    <!-- 操作栏 -->
    <div class="flex justify-between items-center">
      <el-button type="primary" @click="showCreateDialog">
        <el-icon class="mr-1"><Plus /></el-icon>
        创建策略
      </el-button>
      
      <div class="flex gap-4">
        <el-select v-model="categoryFilter" placeholder="策略分类" clearable class="w-40">
          <el-option label="趋势策略" value="trend" />
          <el-option label="均值回归" value="mean_reversion" />
          <el-option label="波动率" value="volatility" />
          <el-option label="自定义" value="custom" />
        </el-select>
      </div>
    </div>
    
    <!-- 策略列表 -->
    <el-card>
      <el-table :data="strategies" stripe v-loading="loading">
        <el-table-column prop="name" label="策略名称" width="180" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ getCategoryLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewStrategy(row)">
              查看
            </el-button>
            <el-button type="warning" link size="small" @click="editStrategy(row)">
              编辑
            </el-button>
            <el-button type="danger" link size="small" @click="deleteStrategy(row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 策略模板 -->
    <el-card>
      <template #header>
        <span class="font-bold">策略模板</span>
      </template>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div
          v-for="template in templates"
          :key="template.id"
          class="p-4 border rounded-lg hover:border-blue-500 hover:shadow-md transition-all cursor-pointer"
          @click="useTemplate(template)"
        >
          <h3 class="font-bold text-lg mb-2">{{ template.name }}</h3>
          <p class="text-gray-500 text-sm mb-4">{{ template.description }}</p>
          <el-tag size="small">{{ getCategoryLabel(template.category) }}</el-tag>
        </div>
      </div>
    </el-card>
    
    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑策略' : '创建策略'"
      width="800px"
    >
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
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="策略代码" required>
          <el-input
            v-model="form.code"
            type="textarea"
            rows="15"
            placeholder="import backtrader as bt&#10;&#10;class MyStrategy(bt.Strategy):&#10;    ..."
            class="font-mono"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveStrategy" :loading="saving">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
    
    <!-- 查看策略对话框 -->
    <el-dialog v-model="viewDialogVisible" title="策略详情" width="800px">
      <div v-if="currentStrategy" class="space-y-4">
        <div class="flex justify-between items-center">
          <h2 class="text-xl font-bold">{{ currentStrategy.name }}</h2>
          <el-tag>{{ getCategoryLabel(currentStrategy.category) }}</el-tag>
        </div>
        <p class="text-gray-500">{{ currentStrategy.description }}</p>
        <el-divider />
        <pre class="bg-gray-100 p-4 rounded-lg overflow-auto max-h-96"><code>{{ currentStrategy.code }}</code></pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useStrategyStore } from '@/stores/strategy'
import type { Strategy, StrategyTemplate } from '@/types'

const strategyStore = useStrategyStore()

const categoryFilter = ref('')
const dialogVisible = ref(false)
const viewDialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const editingId = ref('')
const currentStrategy = ref<Strategy | null>(null)

const form = reactive({
  name: '',
  description: '',
  code: '',
  category: 'custom',
})

const strategies = computed(() => strategyStore.strategies)
const templates = computed(() => strategyStore.templates)
const loading = computed(() => strategyStore.loading)

function getCategoryLabel(category: string) {
  const labels: Record<string, string> = {
    trend: '趋势策略',
    mean_reversion: '均值回归',
    volatility: '波动率',
    custom: '自定义',
  }
  return labels[category] || category
}

function showCreateDialog() {
  isEdit.value = false
  editingId.value = ''
  Object.assign(form, {
    name: '',
    description: '',
    code: '',
    category: 'custom',
  })
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
  isEdit.value = false
  editingId.value = ''
  Object.assign(form, {
    name: template.name + ' (副本)',
    description: template.description,
    code: template.code,
    category: template.category,
  })
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

watch(categoryFilter, (val) => {
  strategyStore.fetchStrategies(20, 0, val || undefined)
})

onMounted(async () => {
  await Promise.all([
    strategyStore.fetchStrategies(),
    strategyStore.fetchTemplates(),
  ])
})
</script>
