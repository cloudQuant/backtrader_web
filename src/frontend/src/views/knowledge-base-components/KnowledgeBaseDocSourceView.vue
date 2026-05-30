<template>
  <div class="min-h-[60vh]">
    <!-- PDF preview -->
    <div
      v-if="sourceMimeType === 'application/pdf' && sourcePreviewUrl"
      :class="['overflow-hidden rounded border border-slate-200 bg-slate-50', pdfFullscreen ? 'fixed inset-0 z-[9999] h-screen w-screen' : '']"
    >
      <iframe
        :src="pdfEmbedUrl"
        class="w-full bg-slate-100"
        :class="pdfFullscreen ? 'h-screen' : 'h-[72vh]'"
        :title="t('kbDoc.pdfTitle')"
      />
    </div>

    <!-- Office files (docx/xlsx/pptx) via Office Online Viewer -->
    <div
      v-else-if="isOfficeFile && sourcePreviewUrl"
      class="overflow-hidden rounded border border-slate-200"
    >
      <iframe
        :src="officeViewerUrl"
        class="h-[72vh] w-full bg-slate-100"
        :title="t('kbDoc.officeTitle')"
      />
    </div>

    <!-- Other unsupported files -->
    <div
      v-else-if="sourceFileName"
      class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
    >
      <div class="mb-4 text-4xl">
        📄
      </div>
      <div class="font-medium text-slate-700">
        {{ sourceFileName }}
      </div>
      <div class="mt-2 text-xs text-slate-400">
        {{ t('kbDoc.notInlinePreview') }}
      </div>
      <div class="mt-4 flex gap-2">
        <button
          type="button"
          class="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          @click="emit('download')"
        >
          {{ t('kbDoc.btnDownloadOriginal') }}
        </button>
        <button
          v-if="hasContent"
          type="button"
          class="rounded border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          @click="emit('read-markdown')"
        >
          {{ t('kbDoc.btnReadMarkdown') }}
        </button>
      </div>
    </div>

    <!-- No source file -->
    <div
      v-else
      class="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 py-16 text-sm text-slate-500"
    >
      <div class="text-4xl">
        📭
      </div>
      <div class="mt-2">
        {{ t('kbDoc.noSourceFile') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  sourceMimeType: string
  sourcePreviewUrl: string
  pdfFullscreen: boolean
  pdfEmbedUrl: string
  isOfficeFile: boolean
  officeViewerUrl: string
  sourceFileName: string
  hasContent: boolean
}>()

const emit = defineEmits<{
  (e: 'download'): void
  (e: 'read-markdown'): void
}>()

const { t } = useI18n()
</script>
