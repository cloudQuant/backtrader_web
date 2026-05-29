<template>
  <div class="space-y-6 prompt-templates-page">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">
          {{ t('promptTpl.headerTitle') }}
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          {{ t('promptTpl.headerDesc') }}
        </p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        @click="loadTemplates"
      >
        {{ t('promptTpl.btnRefresh') }}
      </el-button>
    </div>

    <el-card>
      <template #header>
        <span class="font-bold">{{ t('promptTpl.cardCreate') }}</span>
      </template>
      <el-form label-width="110px">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <el-form-item :label="t('promptTpl.formName')">
            <el-input
              v-model="form.name"
              placeholder="knowledge_qa"
            />
          </el-form-item>
          <el-form-item :label="t('promptTpl.formVersion')">
            <el-input
              v-model="form.version"
              placeholder="v1 / canary"
            />
          </el-form-item>
        </div>
        <el-form-item :label="t('promptTpl.formVariables')">
          <el-input
            v-model="form.variablesText"
            placeholder="question, context_text"
          />
        </el-form-item>
        <el-form-item :label="t('promptTpl.formContent')">
          <el-input
            v-model="form.content"
            type="textarea"
            :placeholder="t('promptTpl.formContentPlaceholder', { var: '{{question}}' })"
          />
        </el-form-item>
        <el-form-item :label="t('promptTpl.formRollout')">
          <div class="w-full">
            <el-slider
              v-model="form.rollout_percentage"
              :min="0"
              :max="100"
              :step="5"
            />
            <div class="text-sm text-gray-500 mt-1">
              {{ t('promptTpl.rolloutCurrent', { pct: form.rollout_percentage }) }}
            </div>
          </div>
        </el-form-item>
        <el-button
          type="primary"
          :loading="saving"
          @click="createTemplate"
        >
          {{ t('promptTpl.btnCreate') }}
        </el-button>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <span class="font-bold">{{ t('promptTpl.cardList') }}</span>
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
                {{ t('promptTpl.statusLabel', { status: template.status, pct: template.rollout_percentage }) }}
              </div>
            </div>
            <el-button
              size="small"
              :disabled="template.status === 'active'"
              @click="activateTemplate(template.id)"
            >
              {{ t('promptTpl.btnActivate') }}
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
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'

import { promptTemplatesApi, type PromptTemplate } from '@/api/promptTemplates'

const { t } = useI18n()

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
    ElMessage.success(t('promptTpl.msgCreated'))
    await loadTemplates()
  } finally {
    saving.value = false
  }
}

async function activateTemplate(id: string) {
  await promptTemplatesApi.activate(id)
  ElMessage.success(t('promptTpl.msgActivated'))
  await loadTemplates()
}

onMounted(loadTemplates)
</script>
