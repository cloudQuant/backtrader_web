<template>
  <div class="space-y-6 prompt-templates-page">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">
          Prompt 模板治理
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          管理 AI Prompt 模板版本、active 激活与灰度发布比例。
        </p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        @click="loadTemplates"
      >
        刷新
      </el-button>
    </div>

    <el-card>
      <template #header>
        <span class="font-bold">新建模板版本</span>
      </template>
      <el-form label-width="110px">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <el-form-item label="模板名">
            <el-input
              v-model="form.name"
              placeholder="knowledge_qa"
            />
          </el-form-item>
          <el-form-item label="版本">
            <el-input
              v-model="form.version"
              placeholder="v1 / canary"
            />
          </el-form-item>
        </div>
        <el-form-item label="变量">
          <el-input
            v-model="form.variablesText"
            placeholder="question, context_text"
          />
        </el-form-item>
        <el-form-item label="模板内容">
          <el-input
            v-model="form.content"
            type="textarea"
            placeholder="灰度模板 {{question}}"
          />
        </el-form-item>
        <el-form-item label="灰度比例">
          <div class="w-full">
            <el-slider
              v-model="form.rollout_percentage"
              :min="0"
              :max="100"
              :step="5"
            />
            <div class="text-sm text-gray-500 mt-1">
              当前灰度比例：{{ form.rollout_percentage }}%
            </div>
          </div>
        </el-form-item>
        <el-button
          type="primary"
          :loading="saving"
          @click="createTemplate"
        >
          新建模板
        </el-button>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <span class="font-bold">模板版本列表</span>
      </template>
      <div class="space-y-3">
        <div
          v-for="template in templates"
          :key="template.id"
          class="border rounded p-3 bg-white"
        >
          <div class="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <div class="font-bold">
                {{ template.name }} / {{ template.version }}
              </div>
              <div class="text-sm text-gray-500">
                状态：{{ template.status }} · 灰度比例：{{ template.rollout_percentage }}%
              </div>
            </div>
            <el-button
              size="small"
              :disabled="template.status === 'active'"
              @click="activateTemplate(template.id)"
            >
              激活
            </el-button>
          </div>
          <pre class="text-xs bg-gray-50 rounded p-2 mt-2 whitespace-pre-wrap">{{ template.content }}</pre>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { promptTemplatesApi, type PromptTemplate } from '@/api/promptTemplates'

const loading = ref(false)
const saving = ref(false)
const templates = ref<PromptTemplate[]>([])
const form = reactive({
  name: '',
  version: '',
  content: '',
  variablesText: '',
  rollout_percentage: 0,
})

function parseVariables(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

async function loadTemplates() {
  loading.value = true
  try {
    const result = await promptTemplatesApi.list()
    templates.value = result.items
  } finally {
    loading.value = false
  }
}

async function createTemplate() {
  saving.value = true
  try {
    await promptTemplatesApi.create({
      name: form.name,
      version: form.version,
      content: form.content,
      variables: parseVariables(form.variablesText),
      rollout_percentage: form.rollout_percentage,
    })
    ElMessage.success('Prompt 模板已创建')
    await loadTemplates()
  } finally {
    saving.value = false
  }
}

async function activateTemplate(id: string) {
  await promptTemplatesApi.activate(id)
  ElMessage.success('Prompt 模板版本已激活')
  await loadTemplates()
}

onMounted(loadTemplates)
</script>
