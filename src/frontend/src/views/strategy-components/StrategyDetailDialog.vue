<template>
  <el-dialog
    :model-value="visible"
    :title="template?.name"
    width="900px"
    top="5vh"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div
      v-if="template"
      class="space-y-4"
    >
      <div class="flex items-center gap-3 flex-wrap">
        <el-tag :type="getCategoryType(template.category)">
          {{ getCategoryLabel(template.category) }}
        </el-tag>
        <span class="text-gray-400 text-sm">{{ template.id }}</span>
      </div>
      <p class="text-gray-600">
        {{ stripMeta(template.description) }}
      </p>

      <div v-if="Object.keys(template.params).length">
        <h4 class="font-bold text-sm mb-2">
          {{ t('strategy.params') }}
        </h4>
        <el-table
          :data="paramTableData"
          size="small"
          border
          stripe
        >
          <el-table-column
            prop="name"
            :label="t('strategy.paramName')"
            width="180"
          />
          <el-table-column
            prop="default"
            :label="t('strategy.paramDefault')"
            width="120"
          />
          <el-table-column
            prop="type"
            :label="t('strategy.paramType')"
            width="80"
          />
          <el-table-column
            prop="description"
            :label="t('strategy.paramDescription')"
          />
        </el-table>
      </div>

      <el-tabs :model-value="detailTab" @update:model-value="(v) => emit('update:detailTab', String(v))">
        <el-tab-pane
          :label="t('strategy.docs')"
          name="readme"
        >
          <div
            v-if="readmeLoading"
            class="flex justify-center py-8"
          >
            <el-icon class="is-loading text-2xl">
              <Loading />
            </el-icon>
          </div>
          <!-- eslint-disable vue/no-v-html -- Strategy readme Markdown; consider sanitizing with DOMPurify -->
          <div
            v-else-if="readmeContent"
            class="prose prose-sm max-w-none readme-content"
            v-html="renderedReadme"
          />
          <!-- eslint-enable vue/no-v-html -->
          <el-empty
            v-else
            :description="t('strategy.docsEmpty')"
          />
        </el-tab-pane>
        <el-tab-pane
          :label="t('strategy.strategyCode')"
          name="code"
        >
          <MonacoEditor
            v-model="template.code"
            language="python"
            :height="450"
            :read-only="true"
            theme="vs"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">
        {{ t('strategy.close') }}
      </el-button>
      <el-button @click="template && emit('use', template)">
        {{ t('strategy.actionCopy') }}
      </el-button>
      <el-button
        type="primary"
        @click="template && emit('backtest', template)"
      >
        {{ t('strategy.actionRunBacktest') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import MonacoEditor from '@/components/common/MonacoEditor.vue'
import { getCategoryLabel, getCategoryType } from '@/constants/strategy'
import type { StrategyTemplate } from '@/types'

const { t } = useI18n()

interface ParamRow {
  name: string
  default: unknown
  type: string
  description: string
}

defineProps<{
  visible: boolean
  template: StrategyTemplate | null
  detailTab: string
  paramTableData: ParamRow[]
  readmeLoading: boolean
  readmeContent: string
  renderedReadme: string
  stripMeta: (description?: string) => string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'update:detailTab', value: string): void
  (e: 'use', template: StrategyTemplate): void
  (e: 'backtest', template: StrategyTemplate): void
}>()
</script>
