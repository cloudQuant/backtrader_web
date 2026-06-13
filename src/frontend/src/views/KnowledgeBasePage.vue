<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-semibold text-slate-900">
        {{ t('kb.pageTitle') }}
      </h2>
      <p class="mt-1 text-sm text-slate-500">
        {{ t('kb.pageSubtitle') }}
      </p>
    </div>

    <div class="grid gap-4 xl:grid-cols-[280px_minmax(0,560px)_minmax(0,1fr)]">
      <el-card>
        <template #header>
          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium">
                {{ t('kb.kbList') }}
              </div>
              <span class="text-xs text-slate-400">{{ t('kb.kbCounter', { count: filteredKnowledgeBases.length }) }}</span>
            </div>
            <input
              v-model="knowledgeBaseSearch"
              class="w-full rounded border px-3 py-2 text-sm"
              :placeholder="t('kb.searchKbPlaceholder')"
              :aria-label="t('kb.searchKb')"
            >
          </div>
        </template>

        <div class="space-y-2">
          <div
            v-for="kb in filteredKnowledgeBases"
            :key="kb.id"
            class="group relative"
          >
            <button
              type="button"
              class="block w-full rounded border px-3 py-2 pr-12 text-left text-sm transition"
              :class="kb.id === store.currentKnowledgeBase?.id ? 'border-blue-500 bg-blue-50' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'"
              @click="handleSelectKnowledgeBase(kb.id)"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="font-medium text-slate-900">
                  {{ kb.name }}
                </div>
                <span class="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{{ t('kb.kbCounterDocs', { count: kb.document_count }) }}</span>
              </div>
              <div class="mt-1 text-xs text-slate-500">
                {{ kb.description || t('kb.noDescription') }}
              </div>
            </button>

            <div class="absolute right-2 top-2 hidden items-center gap-1 rounded bg-white/95 p-1 shadow-sm group-hover:flex">
              <span class="rounded px-2 py-1 text-xs text-slate-400">⋯</span>
              <button
                type="button"
                class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
                :title="t('kb.renameKb')"
                @click.stop="openKnowledgeBaseRenameDialog(kb)"
              >
                {{ t('kb.rename') }}
              </button>
              <button
                type="button"
                class="rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-50"
                :title="t('kb.deleteKb')"
                @click.stop="openKnowledgeBaseDeleteDialog(kb)"
              >
                {{ t('kb.delete') }}
              </button>
            </div>
          </div>

          <div
            v-if="filteredKnowledgeBases.length === 0"
            class="text-sm text-slate-500"
          >
            {{ t('kb.noMatchKb') }}
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium">
                {{ store.currentKnowledgeBase?.name || t('kb.workbench') }}
              </div>
              <div class="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  class="rounded border px-2 py-1"
                  :class="viewMode === 'tree' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-slate-200 text-slate-500'"
                  @click="viewMode = 'tree'"
                >
                  {{ t('kb.treeView') }}
                </button>
                <button
                  type="button"
                  class="rounded border px-2 py-1"
                  :class="viewMode === 'table' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-slate-200 text-slate-500'"
                  @click="viewMode = 'table'"
                >
                  {{ t('kb.tableView') }}
                </button>
              </div>
            </div>

            <div class="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
              <input
                v-model="documentSearch"
                class="w-full rounded border px-3 py-2 text-sm"
                :placeholder="t('kb.searchDocsPlaceholder')"
                :aria-label="t('kb.searchDocs')"
              >
              <select
                v-model="sortKey"
                class="rounded border px-3 py-2 text-sm text-slate-600"
                :aria-label="t('kb.sortDocsBy')"
              >
                <option value="sort_order">
                  {{ t('kb.sortBy') }}
                </option>
                <option value="title">
                  {{ t('kb.sortByTitle') }}
                </option>
                <option value="updated_at">
                  {{ t('kb.sortByUpdated') }}
                </option>
                <option value="status">
                  {{ t('kb.sortByStatus') }}
                </option>
              </select>
              <button
                type="button"
                class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                @click="openImportDialog"
              >
                {{ t('kb.importDocs') }}
              </button>
              <button
                type="button"
                class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                :disabled="!store.currentKnowledgeBase"
                @click="openKnowledgeBaseSettingsDialog"
              >
                {{ t('kb.retrievalConfig') }}
              </button>
              <div class="flex gap-2">
                <button
                  type="button"
                  class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  @click="openCreateDialog(false)"
                >
                  {{ t('kb.createDoc') }}
                </button>
                <button
                  type="button"
                  class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  @click="openCreateDialog(true)"
                >
                  {{ t('kb.createFolder') }}
                </button>
              </div>
            </div>

            <div
              v-if="store.currentKnowledgeBase"
              class="grid gap-2 sm:grid-cols-4"
            >
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">
                  {{ t('kb.statTotal') }}
                </div>
                <div class="mt-1 text-sm font-medium text-slate-700">
                  {{ store.documents.length }}
                </div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">
                  {{ t('kb.statIndexed') }}
                </div>
                <div class="mt-1 text-sm font-medium text-slate-700">
                  {{ indexedDocumentCount }}
                </div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">
                  {{ t('kb.statFolders') }}
                </div>
                <div class="mt-1 text-sm font-medium text-slate-700">
                  {{ folderCount }}
                </div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">
                  {{ t('kb.retrievalStrategy') }}
                </div>
                <div class="mt-1 text-sm font-medium text-slate-700">
                  {{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ currentKnowledgeBaseSettings.search_mode }} / top_k {{ currentKnowledgeBaseSettings.default_top_k }}
                </div>
              </div>
            </div>

            <div
              v-if="visibleRows.length"
              class="rounded border border-slate-200 bg-slate-50 px-3 py-3 text-sm"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                  <label class="inline-flex items-center gap-2 text-slate-600">
                    <input
                      :checked="allVisibleSelected"
                      type="checkbox"
                      @change="toggleSelectAllVisible($event)"
                    >
                    <span>{{ t('kb.selectAll') }}</span>
                  </label>
                  <span class="text-xs text-slate-400">{{ t('kb.selectedCount', { count: selectedDocumentIds.size }) }}</span>
                </div>
                <div class="flex flex-wrap gap-2 text-xs">
                  <button
                    type="button"
                    class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
                    @click="clearSelection"
                  >
                    {{ t('kb.clearSelection') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
                    @click="openBulkActionDialog('publish')"
                  >
                    {{ t('kb.batchPublish') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
                    @click="openBulkActionDialog('draft')"
                  >
                    {{ t('kb.setDraft') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
                    @click="openBulkActionDialog('move_root')"
                  >
                    {{ t('kb.moveToRoot') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
                    @click="handleBatchCopyTitles"
                  >
                    {{ t('kb.batchCopyTitles') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
                    @click="openBulkActionDialog('mark_not_indexed')"
                  >
                    {{ t('kb.markUnindexed') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-rose-200 bg-white px-2 py-1 text-rose-600 hover:bg-rose-50"
                    @click="openBulkActionDialog('delete')"
                  >
                    {{ t('kb.batchDelete') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <div
          v-if="visibleRows.length === 0"
          class="text-sm text-slate-500"
        >
          {{ t('kb.emptyDocs') }}
        </div>

        <div
          v-else-if="viewMode === 'tree'"
          class="space-y-2"
        >
          <div
            v-for="row in visibleRows"
            :key="row.id"
            class="rounded border px-3 py-3 transition"
            :class="row.id === selectedDocument?.id ? 'border-blue-500 bg-blue-50' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'"
            draggable="true"
            @dragstart="handleDragStart(row.id)"
            @dragover.prevent
            @drop="handleDrop(row)"
          >
            <div class="flex items-start justify-between gap-3">
              <div
                class="flex min-w-0 flex-1 items-start gap-2"
                :style="{ paddingLeft: `${row.depth * 16}px` }"
              >
                <input
                  :checked="selectedDocumentIds.has(row.id)"
                  type="checkbox"
                  class="mt-1"
                  :aria-label="t('kb.selectDocAria', { title: row.title })"
                  @change="toggleDocumentSelection(row.id)"
                >
                <button
                  v-if="row.is_folder"
                  type="button"
                  class="mt-0.5 rounded px-1 text-xs text-slate-400 hover:bg-slate-100"
                  @click.stop="toggleFolder(row.id)"
                >
                  {{ expandedFolderIds.has(row.id) ? '▾' : '▸' }}
                </button>
                <span
                  v-else
                  class="mt-0.5 w-4 text-center text-xs text-slate-300"
                >·</span>
                <button
                  type="button"
                  class="min-w-0 flex-1 text-left"
                  @click="selectedDocumentId = row.id"
                >
                  <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400">{{ row.is_folder ? '📁' : '📄' }}</span>
                    <div
                      class="truncate font-medium text-slate-900"
                    >
                      <button
                        v-if="!row.is_folder"
                        type="button"
                        class="truncate text-left hover:text-blue-700"
                        @click.stop="openDocument(row)"
                      >
                        {{ row.title }}
                      </button>
                      <span v-else>{{ row.title }}</span>
                    </div>
                  </div>
                  <div class="mt-2 flex flex-wrap gap-2 text-[11px]">
                    <span class="rounded bg-slate-100 px-2 py-0.5 text-slate-600">{{ insightChip(row) }}</span>
                    <span
                      class="rounded px-2 py-0.5"
                      :class="statusClass(row.status)"
                    >{{ row.status }}</span>
                    <span
                      class="rounded px-2 py-0.5"
                      :class="indexClass(row.index_status)"
                    >{{ row.index_status }}</span>
                  </div>
                  <div class="mt-2 text-xs text-slate-500">
                    {{ documentInsight(row) }}
                  </div>
                </button>
              </div>

              <el-dropdown
                trigger="click"
                class="shrink-0"
              >
                <button
                  type="button"
                  class="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-white"
                >
                  {{ t('kb.actions') }}
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="!row.is_folder">
                      <button
                        type="button"
                        class="w-full text-left"
                        @click="openDocument(row)"
                      >
                        {{ t('kb.open') }}
                      </button>
                    </el-dropdown-item>
                    <el-dropdown-item>
                      <button
                        type="button"
                        class="w-full text-left"
                        @click="openRenameDialog(row)"
                      >
                        {{ t('kb.rename') }}
                      </button>
                    </el-dropdown-item>
                    <el-dropdown-item>
                      <button
                        type="button"
                        class="w-full text-left"
                        @click="openCreateChildDialog(row)"
                      >
                        {{ t('kb.createChild') }}
                      </button>
                    </el-dropdown-item>
                    <el-dropdown-item>
                      <button
                        type="button"
                        class="w-full text-left"
                        @click="handleCopyNodeTitle(row)"
                      >
                        {{ t('kb.copyTitle') }}
                      </button>
                    </el-dropdown-item>
                    <el-dropdown-item>
                      <button
                        type="button"
                        class="w-full text-left"
                        @click="handleMoveToRoot(row)"
                      >
                        {{ t('kb.moveToRoot') }}
                      </button>
                    </el-dropdown-item>
                    <el-dropdown-item>
                      <button
                        type="button"
                        class="w-full text-left text-rose-600"
                        @click="openDeleteDialog(row)"
                      >
                        {{ t('kb.delete') }}
                      </button>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <div class="overflow-hidden rounded border border-slate-200">
            <table class="min-w-full divide-y divide-slate-200 text-sm">
              <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th class="px-3 py-2" />
                  <th class="px-3 py-2">
                    {{ t('kb.title') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.type') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.path') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.updatedAt') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.insights') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.status') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.indexCol') }}
                  </th>
                  <th class="px-3 py-2">
                    {{ t('kb.actions') }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-200 bg-white">
                <tr
                  v-for="row in visibleRows"
                  :key="row.id"
                  class="hover:bg-slate-50"
                  :class="row.id === selectedDocument?.id ? 'bg-blue-50' : ''"
                >
                  <td class="px-3 py-3">
                    <input
                      :checked="selectedDocumentIds.has(row.id)"
                      type="checkbox"
                      :aria-label="t('kb.selectDocAria', { title: row.title })"
                      @change="toggleDocumentSelection(row.id)"
                    >
                  </td>
                  <td class="px-3 py-3">
                    <button
                      type="button"
                      class="text-left"
                      @click="selectedDocumentId = row.id"
                    >
                      <div class="font-medium text-slate-800">
                        <button
                          v-if="!row.is_folder"
                          type="button"
                          class="text-left hover:text-blue-700"
                          @click.stop="openDocument(row)"
                        >
                          {{ row.title }}
                        </button>
                        <span v-else>{{ row.title }}</span>
                      </div>
                      <div class="mt-1 text-xs text-slate-500">
                        {{ documentInsight(row) }}
                      </div>
                    </button>
                  </td>
                  <td class="px-3 py-3 text-slate-600">
                    {{ row.is_folder ? 'folder' : row.content_type }}
                  </td>
                  <td class="px-3 py-3 text-xs text-slate-500">
                    {{ row.file_path || '-' }}
                  </td>
                  <td class="px-3 py-3 text-xs text-slate-500">
                    {{ formatDate(row.updated_at) }}
                  </td>
                  <td class="px-3 py-3">
                    <span class="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{{ insightChip(row) }}</span>
                  </td>
                  <td class="px-3 py-3">
                    <span
                      class="rounded px-2 py-0.5 text-[11px]"
                      :class="statusClass(row.status)"
                    >{{ row.status }}</span>
                  </td>
                  <td class="px-3 py-3">
                    <span
                      class="rounded px-2 py-0.5 text-[11px]"
                      :class="indexClass(row.index_status)"
                    >{{ row.index_status }}</span>
                  </td>
                  <td class="px-3 py-3">
                    <el-dropdown trigger="click">
                      <button
                        type="button"
                        class="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                      >
                        {{ t('kb.actions') }}
                      </button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item v-if="!row.is_folder">
                            <button
                              type="button"
                              class="w-full text-left"
                              @click="openDocument(row)"
                            >
                              {{ t('kb.open') }}
                            </button>
                          </el-dropdown-item>
                          <el-dropdown-item>
                            <button
                              type="button"
                              class="w-full text-left"
                              @click="openRenameDialog(row)"
                            >
                              {{ t('kb.rename') }}
                            </button>
                          </el-dropdown-item>
                          <el-dropdown-item>
                            <button
                              type="button"
                              class="w-full text-left"
                              @click="handleCopyNodeTitle(row)"
                            >
                              {{ t('kb.copyTitle') }}
                            </button>
                          </el-dropdown-item>
                          <el-dropdown-item>
                            <button
                              type="button"
                              class="w-full text-left"
                              @click="handleMoveToRoot(row)"
                            >
                              {{ t('kb.moveToRoot') }}
                            </button>
                          </el-dropdown-item>
                          <el-dropdown-item>
                            <button
                              type="button"
                              class="w-full text-left text-rose-600"
                              @click="openDeleteDialog(row)"
                            >
                              {{ t('kb.delete') }}
                            </button>
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex items-center justify-between gap-3 text-sm text-slate-500">
            <div>{{ t('kb.pageStatus', { current: currentPage, total: totalPages }) }}</div>
            <div class="flex items-center gap-2">
              <select
                v-model.number="pageSize"
                class="rounded border px-2 py-1 text-sm"
                :aria-label="t('kb.perPageAria')"
              >
                <option :value="8">
                  {{ t('kb.perPage', { n: 8 }) }}
                </option>
                <option :value="12">
                  {{ t('kb.perPage', { n: 12 }) }}
                </option>
                <option :value="20">
                  {{ t('kb.perPage', { n: 20 }) }}
                </option>
              </select>
              <button
                type="button"
                class="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
                :disabled="currentPage <= 1"
                @click="currentPage -= 1"
              >
                {{ t('kb.pagePrev') }}
              </button>
              <button
                type="button"
                class="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
                :disabled="currentPage >= totalPages"
                @click="currentPage += 1"
              >
                {{ t('kb.pageNext') }}
              </button>
            </div>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium">
              {{ selectedDocument?.title || t('kb.docDetail') }}
            </div>
            <div
              v-if="selectedDocument"
              class="flex items-center gap-2 text-xs"
            >
              <span
                class="rounded px-2 py-0.5"
                :class="statusClass(selectedDocument.status)"
              >{{ selectedDocument.status }}</span>
              <span
                class="rounded px-2 py-0.5"
                :class="indexClass(selectedDocument.index_status)"
              >{{ selectedDocument.index_status }}</span>
            </div>
          </div>
        </template>

        <div
          v-if="!selectedDocument"
          class="text-sm text-slate-500"
        >
          {{ t('kb.selectDocPrompt') }}
        </div>

        <div
          v-else
          class="space-y-4"
        >
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">
                {{ t('kb.status') }}
              </div>
              <div class="mt-1 text-sm font-medium text-slate-700">
                {{ selectedDocument.status }}
              </div>
            </div>
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">
                {{ t('kb.indexCol') }}
              </div>
              <div class="mt-1 text-sm font-medium text-slate-700">
                {{ selectedDocument.index_status }}
              </div>
            </div>
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">
                {{ t('kb.type') }}
              </div>
              <div class="mt-1 text-sm font-medium text-slate-700">
                {{ selectedDocument.is_folder ? 'folder' : selectedDocument.content_type }}
              </div>
            </div>
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">
                {{ t('kb.insights') }}
              </div>
              <div class="mt-1 text-sm font-medium text-slate-700">
                {{ documentInsight(selectedDocument) }}
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2 text-xs">
            <span class="rounded bg-slate-100 px-2 py-1 text-slate-600">{{ t('kb.sortOrder') }} {{ selectedDocument.sort_order }}</span>
            <span
              v-if="selectedDocument.parent_id"
              class="rounded bg-slate-100 px-2 py-1 text-slate-600"
            >{{ t('kb.hasParent') }}</span>
            <span
              v-if="selectedDocument.indexed_at"
              class="rounded bg-slate-100 px-2 py-1 text-slate-600"
            >{{ t('kb.lastIndexed') }} {{ formatDate(selectedDocument.indexed_at) }}</span>
            <span class="rounded bg-slate-100 px-2 py-1 text-slate-600">{{ insightChip(selectedDocument) }}</span>
          </div>

          <div
            v-if="selectedDocument.file_path"
            class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          >
            <div class="text-xs text-slate-400">
              {{ t('kb.sourcePath') }}
            </div>
            <div class="mt-1 break-all">
              {{ selectedDocument.file_path }}
            </div>
          </div>

          <div
            v-if="selectedDocument.metadata"
            class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600"
          >
            <div class="text-xs text-slate-400">
              {{ t('kb.metadata') }}
            </div>
            <pre class="mt-1 overflow-auto whitespace-pre-wrap break-all text-xs">{{ formattedMetadata }}</pre>
          </div>

          <div class="rounded border border-slate-200 px-4 py-3">
            <div class="mb-2 text-xs text-slate-400">
              {{ t('kb.contentPreview') }}
            </div>
            <div class="max-h-[640px] overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
              {{ selectedDocumentContent }}
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <el-dialog
      v-if="createDialog.open"
      :model-value="true"
    >
      <div class="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
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
      <div class="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl mx-auto">
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
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useKnowledgeBasePage } from '@/composables/useKnowledgeBasePage'

const { t } = useI18n()
const {
  store,
  knowledgeBaseSearch,
  documentSearch,
  selectedDocumentId,
  viewMode,
  sortKey,
  currentPage,
  pageSize,
  expandedFolderIds,
  selectedDocumentIds,
  createDialog,
  renameDialog,
  importDialog,
  bulkDialog,
  deleteDialog,
  knowledgeBaseRenameDialog,
  knowledgeBaseDeleteDialog,
  knowledgeBaseSettingsDialog,
  filteredKnowledgeBases,
  indexedDocumentCount,
  folderCount,
  currentKnowledgeBaseSettings,
  totalPages,
  visibleRows,
  selectedDocument,
  formattedMetadata,
  selectedDocumentContent,
  allVisibleSelected,
  bulkDialogMessage,
  statusClass,
  indexClass,
  formatDate,
  retrievalProfileLabel,
  documentInsight,
  insightChip,
  toggleFolder,
  toggleDocumentSelection,
  toggleSelectAllVisible,
  clearSelection,
  openDocument,
  handleDragStart,
  handleDrop,
  openCreateDialog,
  closeCreateDialog,
  submitCreateDialog,
  openRenameDialog,
  closeRenameDialog,
  submitRenameDialog,
  openImportDialog,
  closeImportDialog,
  submitImportDialog,
  openBulkActionDialog,
  closeBulkDialog,
  submitBulkDialog,
  openDeleteDialog,
  closeDeleteDialog,
  submitDeleteDialog,
  handleBatchCopyTitles,
  openCreateChildDialog,
  handleCopyNodeTitle,
  openKnowledgeBaseRenameDialog,
  closeKnowledgeBaseRenameDialog,
  submitKnowledgeBaseRenameDialog,
  openKnowledgeBaseDeleteDialog,
  openKnowledgeBaseSettingsDialog,
  closeKnowledgeBaseSettingsDialog,
  submitKnowledgeBaseSettingsDialog,
  closeKnowledgeBaseDeleteDialog,
  submitKnowledgeBaseDeleteDialog,
  handleMoveToRoot,
  handleSelectKnowledgeBase,
} = useKnowledgeBasePage()
</script>
