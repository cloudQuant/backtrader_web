<template>
  <div class="kb-doc-source-view">
    <!-- PDF preview -->
    <div
      v-if="sourceMimeType === 'application/pdf' && sourcePreviewUrl"
      :class="['kb-doc-source-frame', pdfFullscreen ? 'kb-doc-source-frame-fullscreen' : '']"
    >
      <iframe
        :src="pdfEmbedUrl"
        :class="['kb-doc-source-iframe', pdfFullscreen ? 'kb-doc-source-iframe-fullscreen' : '']"
        :title="t('kbDoc.pdfTitle')"
      />
    </div>

    <!-- Office files (docx/xlsx/pptx) via Office Online Viewer -->
    <div
      v-else-if="isOfficeFile && sourcePreviewUrl"
      class="kb-doc-source-frame"
    >
      <iframe
        :src="officeViewerUrl"
        class="kb-doc-source-iframe"
        :title="t('kbDoc.officeTitle')"
      />
    </div>

    <!-- Other unsupported files -->
    <div
      v-else-if="sourceFileName"
      class="kb-doc-source-empty"
    >
      <div class="kb-doc-source-empty-icon">
        PDF
      </div>
      <div class="kb-doc-source-empty-title">
        {{ sourceFileName }}
      </div>
      <div class="kb-doc-source-empty-desc">
        {{ t('kbDoc.notInlinePreview') }}
      </div>
      <div class="kb-doc-source-actions">
        <button
          type="button"
          class="kb-doc-source-button kb-doc-source-button-primary"
          @click="emit('download')"
        >
          {{ t('kbDoc.btnDownloadOriginal') }}
        </button>
        <button
          v-if="hasContent"
          type="button"
          class="kb-doc-source-button"
          @click="emit('read-markdown')"
        >
          {{ t('kbDoc.btnReadMarkdown') }}
        </button>
      </div>
    </div>

    <!-- No source file -->
    <div
      v-else
      class="kb-doc-source-empty"
    >
      <div class="kb-doc-source-empty-icon">
        DOC
      </div>
      <div class="kb-doc-source-empty-title">
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

<style scoped>
.kb-doc-source-view {
  min-height: 60vh;
}

.kb-doc-source-frame {
  overflow: hidden;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.kb-doc-source-frame-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100vw;
  height: 100vh;
  border-radius: 0;
}

.kb-doc-source-iframe {
  width: 100%;
  height: 72vh;
  background: var(--fill-color-light);
}

.kb-doc-source-iframe-fullscreen {
  height: 100vh;
}

.kb-doc-source-empty {
  display: grid;
  place-items: center;
  gap: 10px;
  min-height: 360px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--fill-color-lighter);
  padding: 42px 20px;
  color: var(--text-color-secondary);
  text-align: center;
}

.kb-doc-source-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 32%, var(--border-color) 68%);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-color) 84%, var(--primary-color) 16%);
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 760;
  letter-spacing: 0;
}

.kb-doc-source-empty-title {
  max-width: 100%;
  color: var(--text-color-primary);
  font-size: 15px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.kb-doc-source-empty-desc {
  color: var(--text-color-placeholder);
  font-size: 12px;
  line-height: 1.5;
}

.kb-doc-source-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 6px;
}

.kb-doc-source-button {
  min-height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-color);
  padding: 8px 12px;
  color: var(--text-color-regular);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.kb-doc-source-button:hover {
  border-color: color-mix(in srgb, var(--primary-color) 42%, var(--border-color) 58%);
  background: color-mix(in srgb, var(--bg-color) 82%, var(--primary-color) 18%);
  color: var(--primary-color);
}

.kb-doc-source-button-primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--el-color-white);
}

.kb-doc-source-button-primary:hover {
  background: var(--primary-color-dark);
  color: var(--el-color-white);
}
</style>
