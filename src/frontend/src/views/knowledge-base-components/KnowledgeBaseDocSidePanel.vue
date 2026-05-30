<template>
  <div class="space-y-4">
    <!-- Document summary card -->
    <el-card>
      <template #header>
        <div class="font-medium">
          {{ t('kbDoc.summaryTitle') }}
        </div>
      </template>
      <div class="space-y-3 text-sm">
        <div class="leading-6 text-slate-700">
          {{ documentSummary }}
        </div>
        <div
          v-if="sourceFileName"
          class="flex flex-wrap gap-2"
        >
          <button
            v-if="sourceMimeType === 'application/pdf' || isOfficeFile"
            type="button"
            class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            @click="emit('navigate', 'source')"
          >
            {{ t('kbDoc.btnPreviewSource') }}
          </button>
          <button
            v-if="hasContent"
            type="button"
            class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            @click="emit('navigate', 'markdown')"
          >
            {{ t('kbDoc.btnReadMd') }}
          </button>
          <button
            v-if="sourcePreviewUrl"
            type="button"
            class="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            @click="emit('download')"
          >
            {{ t('kbDoc.btnDownloadOriginal') }}
          </button>
        </div>
      </div>
    </el-card>

    <!-- Reading tips -->
    <el-card>
      <template #header>
        <div class="font-medium">
          {{ t('kbDoc.readingTipsTitle') }}
        </div>
      </template>
      <ul class="space-y-2 text-sm text-slate-600">
        <li v-if="sourceMimeType === 'application/pdf' || isOfficeFile">
          {{ t('kbDoc.tipPreferSource') }}
        </li>
        <li v-if="hasContent">
          {{ t('kbDoc.tipUseMarkdown') }}
        </li>
        <li v-if="!isIndexed">
          {{ t('kbDoc.tipNotIndexed') }}
        </li>
        <li v-else>
          {{ t('kbDoc.tipIndexed') }}
        </li>
      </ul>
    </el-card>

    <!-- Quick AI Q&A entry -->
    <el-card>
      <template #header>
        <div class="font-medium">
          {{ t('kbDoc.quickAiTitle') }}
        </div>
      </template>
      <div class="space-y-2 text-sm">
        <button
          v-for="prompt in quickPrompts"
          :key="prompt"
          type="button"
          class="block w-full rounded border border-slate-200 px-3 py-2 text-left text-slate-600 hover:bg-slate-50"
          @click="emit('quickChat', prompt)"
        >
          {{ prompt }}
        </button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  documentSummary: string
  sourceFileName: string
  sourceMimeType: string
  sourcePreviewUrl: string
  isOfficeFile: boolean
  hasContent: boolean
  isIndexed: boolean
  quickPrompts: string[]
}>()

const emit = defineEmits<{
  (e: 'navigate', tab: 'source' | 'markdown'): void
  (e: 'download'): void
  (e: 'quickChat', prompt: string): void
}>()
</script>
