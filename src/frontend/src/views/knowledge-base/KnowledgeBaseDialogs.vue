<template>
  <el-dialog
    v-if="createDialog.open"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-lg rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ createDialog.isFolder ? t('kb.createFolder') : t('kb.createDoc') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeCreateDialog"
        >
          ✕
        </button>
      </div>
      <div class="mt-4 space-y-3">
        <input
          v-model="createDialog.title"
          class="w-full rounded border px-3 py-2 text-sm"
          :placeholder="createDialog.isFolder ? t('kb.folderName') : t('kb.docTitle')"
        >
        <textarea
          v-if="!createDialog.isFolder"
          v-model="createDialog.content"
          rows="8"
          class="w-full rounded border px-3 py-2 text-sm"
          :placeholder="t('kb.docContentPlaceholder')"
        />
        <div class="text-xs text-slate-400">
          {{ createDialog.parentId ? t('kb.childOfFolder') : t('kb.childOfRoot') }}
        </div>
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeCreateDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-blue-600 px-3 py-2 text-sm text-white"
          @click="submitCreateDialog"
        >
          {{ t('kb.confirm') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="renameDialog.open && renameDialog.target"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ t('kb.rename') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeRenameDialog"
        >
          ✕
        </button>
      </div>
      <input
        v-model="renameDialog.title"
        class="mt-4 w-full rounded border px-3 py-2 text-sm"
        :placeholder="t('kb.newNamePlaceholder')"
      >
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeRenameDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-blue-600 px-3 py-2 text-sm text-white"
          @click="submitRenameDialog"
        >
          {{ t('kb.confirm') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="importDialog.open"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ t('kb.importDocs') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeImportDialog"
        >
          ✕
        </button>
      </div>
      <div class="mt-4 grid gap-3">
        <input
          v-model="importDialog.title"
          class="w-full rounded border px-3 py-2 text-sm"
          :placeholder="t('kb.importTitlePlaceholder')"
        >
        <textarea
          v-model="importDialog.content"
          rows="12"
          class="w-full rounded border px-3 py-2 text-sm"
          :placeholder="t('kb.importBodyPlaceholder')"
        />
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeImportDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-blue-600 px-3 py-2 text-sm text-white"
          @click="submitImportDialog"
        >
          {{ t('kb.import') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="bulkDialog.open"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ t('kb.bulkOperations') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeBulkDialog"
        >
          ✕
        </button>
      </div>
      <div class="mt-4 text-sm text-slate-600">
        {{ bulkDialogMessage }}
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeBulkDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded px-3 py-2 text-sm text-white"
          :class="bulkDialog.mode === 'delete' ? 'bg-rose-600' : 'bg-blue-600'"
          @click="submitBulkDialog"
        >
          {{ t('kb.confirm') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="deleteDialog.open && deleteDialog.target"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ t('kb.deleteConfirmTitle') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeDeleteDialog"
        >
          ✕
        </button>
      </div>
      <div class="mt-4 text-sm text-slate-600">
        {{ t('kb.deleteConfirmText', { title: deleteDialog.target.title }) }}
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeDeleteDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-rose-600 px-3 py-2 text-sm text-white"
          @click="submitDeleteDialog"
        >
          {{ t('kb.delete') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="knowledgeBaseRenameDialog.open && knowledgeBaseRenameDialog.target"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ t('kb.renameKb') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeKnowledgeBaseRenameDialog"
        >
          ✕
        </button>
      </div>
      <input
        v-model="knowledgeBaseRenameDialog.name"
        class="mt-4 w-full rounded border px-3 py-2 text-sm"
        :placeholder="t('kb.newKbNamePlaceholder')"
      >
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeKnowledgeBaseRenameDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-blue-600 px-3 py-2 text-sm text-white"
          @click="submitKnowledgeBaseRenameDialog"
        >
          {{ t('kb.confirm') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="knowledgeBaseDeleteDialog.open && knowledgeBaseDeleteDialog.target"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div class="text-lg font-semibold text-slate-900">
          {{ t('kb.deleteKb') }}
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeKnowledgeBaseDeleteDialog"
        >
          ✕
        </button>
      </div>
      <div class="mt-4 text-sm text-slate-600">
        {{ t('kb.deleteKbConfirmText', { name: knowledgeBaseDeleteDialog.target.name }) }}
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeKnowledgeBaseDeleteDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-rose-600 px-3 py-2 text-sm text-white"
          @click="submitKnowledgeBaseDeleteDialog"
        >
          {{ t('kb.delete') }}
        </button>
      </div>
    </div>
  </el-dialog>

  <el-dialog
    v-if="knowledgeBaseSettingsDialog.open"
    :model-value="true"
  >
    <div class="kb-dialog-card w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl mx-auto">
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="text-lg font-semibold text-slate-900">
            {{ t('kb.retrievalConfig') }}
          </div>
          <div class="mt-1 text-sm text-slate-500">
            {{ t('kb.settingsHint') }}
          </div>
        </div>
        <button
          type="button"
          class="text-slate-400"
          :aria-label="t('kb.closeDialog')"
          @click="closeKnowledgeBaseSettingsDialog"
        >
          ✕
        </button>
      </div>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.profileLabel') }}</div>
          <select
            v-model="knowledgeBaseSettingsDialog.form.retrieval_profile"
            class="w-full rounded border px-3 py-2 text-sm"
          >
            <option value="quant_research">{{ t('kb.profileQuantBalance') }}</option>
            <option value="precision">{{ t('kb.profilePrecision') }}</option>
            <option value="exploration">{{ t('kb.profileExploration') }}</option>
          </select>
        </label>
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.searchMode') }}</div>
          <select
            v-model="knowledgeBaseSettingsDialog.form.search_mode"
            class="w-full rounded border px-3 py-2 text-sm"
          >
            <option value="hybrid">{{ t('kb.searchModeHybrid') }}</option>
            <option value="keyword">{{ t('kb.searchModeKeyword') }}</option>
          </select>
        </label>
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.defaultTopK') }}</div>
          <input
            v-model.number="knowledgeBaseSettingsDialog.form.default_top_k"
            type="number"
            min="1"
            max="20"
            class="w-full rounded border px-3 py-2 text-sm"
          >
        </label>
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.minSimilarity') }}</div>
          <input
            v-model.number="knowledgeBaseSettingsDialog.form.min_similarity"
            type="number"
            min="0"
            max="1"
            step="0.01"
            class="w-full rounded border px-3 py-2 text-sm"
          >
        </label>
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.maxChunks') }}</div>
          <input
            v-model.number="knowledgeBaseSettingsDialog.form.max_context_chunks"
            type="number"
            min="1"
            max="12"
            class="w-full rounded border px-3 py-2 text-sm"
          >
        </label>
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.quantFocus') }}</div>
          <select
            v-model="knowledgeBaseSettingsDialog.form.quant_focus"
            class="w-full rounded border px-3 py-2 text-sm"
          >
            <option value="strategy_research">{{ t('kb.quantStrategyResearch') }}</option>
            <option value="strategy_review">{{ t('kb.quantStrategyReview') }}</option>
            <option value="implementation">{{ t('kb.quantImplementation') }}</option>
            <option value="general">{{ t('kb.quantGeneral') }}</option>
          </select>
        </label>
      </div>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <label class="inline-flex items-center gap-2 text-sm text-slate-600">
          <input
            v-model="knowledgeBaseSettingsDialog.form.use_conversation_memory"
            type="checkbox"
          >
          <span>{{ t('kb.enableConvMemory') }}</span>
        </label>
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.convMemoryWindow') }}</div>
          <input
            v-model.number="knowledgeBaseSettingsDialog.form.conversation_lookback_messages"
            type="number"
            min="0"
            max="20"
            class="w-full rounded border px-3 py-2 text-sm"
          >
        </label>
      </div>
      <div class="mt-4">
        <label class="text-sm text-slate-600">
          <div class="mb-1">{{ t('kb.systemPrompt') }}</div>
          <textarea
            v-model="knowledgeBaseSettingsDialog.form.system_prompt_suffix"
            rows="4"
            class="w-full rounded border px-3 py-2 text-sm"
            :placeholder="t('kb.systemPromptExample')"
          />
        </label>
      </div>
      <div class="mt-4 rounded border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
        {{ t('kb.settingsImpact') }}
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          @click="closeKnowledgeBaseSettingsDialog"
        >
          {{ t('kb.cancel') }}
        </button>
        <button
          type="button"
          class="rounded bg-blue-600 px-3 py-2 text-sm text-white"
          @click="submitKnowledgeBaseSettingsDialog"
        >
          {{ t('kb.saveConfig') }}
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  KnowledgeBaseBulkDialogState,
  KnowledgeBaseCreateDialogState,
  KnowledgeBaseDeleteCollectionDialogState,
  KnowledgeBaseDeleteDialogState,
  KnowledgeBaseImportDialogState,
  KnowledgeBaseRenameCollectionDialogState,
  KnowledgeBaseRenameDialogState,
  KnowledgeBaseSettingsDialogState,
} from '@/composables/useKnowledgeBasePage'

type DialogAction = () => void | Promise<void>

const props = defineProps<{
  bulkDialog: KnowledgeBaseBulkDialogState
  bulkDialogMessage: string
  closeBulkDialog: DialogAction
  closeCreateDialog: DialogAction
  closeDeleteDialog: DialogAction
  closeImportDialog: DialogAction
  closeKnowledgeBaseDeleteDialog: DialogAction
  closeKnowledgeBaseRenameDialog: DialogAction
  closeKnowledgeBaseSettingsDialog: DialogAction
  closeRenameDialog: DialogAction
  createDialog: KnowledgeBaseCreateDialogState
  deleteDialog: KnowledgeBaseDeleteDialogState
  importDialog: KnowledgeBaseImportDialogState
  knowledgeBaseDeleteDialog: KnowledgeBaseDeleteCollectionDialogState
  knowledgeBaseRenameDialog: KnowledgeBaseRenameCollectionDialogState
  knowledgeBaseSettingsDialog: KnowledgeBaseSettingsDialogState
  renameDialog: KnowledgeBaseRenameDialogState
  submitBulkDialog: DialogAction
  submitCreateDialog: DialogAction
  submitDeleteDialog: DialogAction
  submitImportDialog: DialogAction
  submitKnowledgeBaseDeleteDialog: DialogAction
  submitKnowledgeBaseRenameDialog: DialogAction
  submitKnowledgeBaseSettingsDialog: DialogAction
  submitRenameDialog: DialogAction
}>()

// Dialog forms are shared reactive models from the page composable. Local refs
// keep child form bindings explicit without replacing the parent-owned state.
const createDialog = ref(props.createDialog)
const renameDialog = ref(props.renameDialog)
const importDialog = ref(props.importDialog)
const bulkDialog = ref(props.bulkDialog)
const deleteDialog = ref(props.deleteDialog)
const knowledgeBaseRenameDialog = ref(props.knowledgeBaseRenameDialog)
const knowledgeBaseDeleteDialog = ref(props.knowledgeBaseDeleteDialog)
const knowledgeBaseSettingsDialog = ref(props.knowledgeBaseSettingsDialog)

const { t } = useI18n()
</script>

<style scoped>
.kb-dialog-card {
  --kb-surface: var(--bg-color);
  --kb-surface-soft: var(--fill-color-lighter);
  --kb-surface-muted: var(--fill-color-light);
  --kb-border: var(--border-color);
  width: min(100%, 720px);
  border: 1px solid var(--kb-border);
  border-radius: 8px;
  background: var(--kb-surface);
  color: var(--text-color-primary);
  box-shadow: 0 18px 60px color-mix(in srgb, var(--shadow-color, black) 24%, transparent);
}

.kb-dialog-card input,
.kb-dialog-card select,
.kb-dialog-card textarea {
  border-color: var(--kb-border) !important;
  background: var(--kb-surface) !important;
  color: var(--text-color-primary) !important;
}

.kb-dialog-card .text-slate-900,
.kb-dialog-card .text-slate-800,
.kb-dialog-card .text-slate-700 {
  color: var(--text-color-primary) !important;
}

.kb-dialog-card .text-slate-600,
.kb-dialog-card .text-slate-500 {
  color: var(--text-color-secondary) !important;
}

.kb-dialog-card .text-slate-400 {
  color: var(--text-color-placeholder) !important;
}

.kb-dialog-card .bg-white,
.kb-dialog-card .bg-slate-50 {
  background: var(--kb-surface-soft) !important;
}

.kb-dialog-card .border-slate-200 {
  border-color: var(--kb-border) !important;
}

</style>
