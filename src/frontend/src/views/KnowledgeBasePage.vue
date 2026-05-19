<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-2xl font-semibold text-slate-900">知识库</h2>
      <p class="mt-1 text-sm text-slate-500">
        按知识库、文档结构与索引状态浏览内容，并提供更接近 ReqDocs 的树形工作台、节点菜单、批量操作和表格管理。
      </p>
    </div>

    <div class="grid gap-4 xl:grid-cols-[280px_minmax(0,560px)_minmax(0,1fr)]">
      <el-card>
        <template #header>
          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium">知识库列表</div>
              <span class="text-xs text-slate-400">{{ filteredKnowledgeBases.length }} 个</span>
            </div>
            <input
              v-model="knowledgeBaseSearch"
              class="w-full rounded border px-3 py-2 text-sm"
              placeholder="搜索知识库..."
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
                <div class="font-medium text-slate-900">{{ kb.name }}</div>
                <span class="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{{ kb.document_count }} 篇</span>
              </div>
              <div class="mt-1 text-xs text-slate-500">{{ kb.description || '暂无描述' }}</div>
            </button>

            <div class="absolute right-2 top-2 hidden items-center gap-1 rounded bg-white/95 p-1 shadow-sm group-hover:flex">
              <span class="rounded px-2 py-1 text-xs text-slate-400">⋯</span>
              <button
                type="button"
                class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
                title="重命名知识库"
                @click.stop="openKnowledgeBaseRenameDialog(kb)"
              >
                重命名
              </button>
              <button
                type="button"
                class="rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-50"
                title="删除知识库"
                @click.stop="openKnowledgeBaseDeleteDialog(kb)"
              >
                删除
              </button>
            </div>
          </div>

          <div v-if="filteredKnowledgeBases.length === 0" class="text-sm text-slate-500">未找到匹配的知识库</div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="font-medium">{{ store.currentKnowledgeBase?.name || '文档工作台' }}</div>
              <div class="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  class="rounded border px-2 py-1"
                  :class="viewMode === 'tree' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-slate-200 text-slate-500'"
                  @click="viewMode = 'tree'"
                >
                  树视图
                </button>
                <button
                  type="button"
                  class="rounded border px-2 py-1"
                  :class="viewMode === 'table' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-slate-200 text-slate-500'"
                  @click="viewMode = 'table'"
                >
                  表格视图
                </button>
              </div>
            </div>

            <div class="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
              <input
                v-model="documentSearch"
                class="w-full rounded border px-3 py-2 text-sm"
                placeholder="搜索标题、正文或路径..."
              >
              <select v-model="sortKey" class="rounded border px-3 py-2 text-sm text-slate-600">
                <option value="sort_order">按排序</option>
                <option value="title">按标题</option>
                <option value="updated_at">按更新时间</option>
                <option value="status">按状态</option>
              </select>
              <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50" @click="openImportDialog">
                导入文档
              </button>
              <button
                type="button"
                class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                :disabled="!store.currentKnowledgeBase"
                @click="openKnowledgeBaseSettingsDialog"
              >
                检索配置
              </button>
              <div class="flex gap-2">
                <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50" @click="openCreateDialog(false)">
                  新建文档
                </button>
                <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50" @click="openCreateDialog(true)">
                  新建文件夹
                </button>
              </div>
            </div>

            <div v-if="store.currentKnowledgeBase" class="grid gap-2 sm:grid-cols-4">
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">文档总数</div>
                <div class="mt-1 text-sm font-medium text-slate-700">{{ store.documents.length }}</div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">已索引</div>
                <div class="mt-1 text-sm font-medium text-slate-700">{{ indexedDocumentCount }}</div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">文件夹</div>
                <div class="mt-1 text-sm font-medium text-slate-700">{{ folderCount }}</div>
              </div>
              <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <div class="text-xs text-slate-400">检索策略</div>
                <div class="mt-1 text-sm font-medium text-slate-700">{{ retrievalProfileLabel(currentKnowledgeBaseSettings.retrieval_profile) }}</div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ currentKnowledgeBaseSettings.search_mode }} / top_k {{ currentKnowledgeBaseSettings.default_top_k }}
                </div>
              </div>
            </div>

            <div v-if="visibleRows.length" class="rounded border border-slate-200 bg-slate-50 px-3 py-3 text-sm">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                  <label class="inline-flex items-center gap-2 text-slate-600">
                    <input
                      :checked="allVisibleSelected"
                      type="checkbox"
                      @change="toggleSelectAllVisible($event)"
                    >
                    <span>全选当前视图</span>
                  </label>
                  <span class="text-xs text-slate-400">已选 {{ selectedDocumentIds.size }} 项</span>
                </div>
                <div class="flex flex-wrap gap-2 text-xs">
                  <button type="button" class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50" @click="clearSelection">
                    清空选择
                  </button>
                  <button type="button" class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50" @click="openBulkActionDialog('publish')">
                    批量发布
                  </button>
                  <button type="button" class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50" @click="openBulkActionDialog('draft')">
                    设为草稿
                  </button>
                  <button type="button" class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50" @click="openBulkActionDialog('move_root')">
                    移到根目录
                  </button>
                  <button type="button" class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50" @click="handleBatchCopyTitles">
                    批量复制标题
                  </button>
                  <button type="button" class="rounded border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50" @click="openBulkActionDialog('mark_not_indexed')">
                    标记未索引
                  </button>
                  <button type="button" class="rounded border border-rose-200 bg-white px-2 py-1 text-rose-600 hover:bg-rose-50" @click="openBulkActionDialog('delete')">
                    批量删除
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <div v-if="visibleRows.length === 0" class="text-sm text-slate-500">暂无文档</div>

        <div v-else-if="viewMode === 'tree'" class="space-y-2">
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
              <div class="flex min-w-0 flex-1 items-start gap-2" :style="{ paddingLeft: `${row.depth * 16}px` }">
                <input :checked="selectedDocumentIds.has(row.id)" type="checkbox" class="mt-1" @change="toggleDocumentSelection(row.id)">
                <button
                  v-if="row.is_folder"
                  type="button"
                  class="mt-0.5 rounded px-1 text-xs text-slate-400 hover:bg-slate-100"
                  @click.stop="toggleFolder(row.id)"
                >
                  {{ expandedFolderIds.has(row.id) ? '▾' : '▸' }}
                </button>
                <span v-else class="mt-0.5 w-4 text-center text-xs text-slate-300">·</span>
                <button type="button" class="min-w-0 flex-1 text-left" @click="selectedDocumentId = row.id">
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
                    <span class="rounded px-2 py-0.5" :class="statusClass(row.status)">{{ row.status }}</span>
                    <span class="rounded px-2 py-0.5" :class="indexClass(row.index_status)">{{ row.index_status }}</span>
                  </div>
                  <div class="mt-2 text-xs text-slate-500">{{ documentInsight(row) }}</div>
                </button>
              </div>

              <el-dropdown trigger="click" class="shrink-0">
                <button type="button" class="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-white">操作</button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="!row.is_folder"><button type="button" class="w-full text-left" @click="openDocument(row)">打开</button></el-dropdown-item>
                    <el-dropdown-item><button type="button" class="w-full text-left" @click="openRenameDialog(row)">重命名</button></el-dropdown-item>
                    <el-dropdown-item><button type="button" class="w-full text-left" @click="openCreateChildDialog(row)">创建子项</button></el-dropdown-item>
                    <el-dropdown-item><button type="button" class="w-full text-left" @click="handleCopyNodeTitle(row)">复制标题</button></el-dropdown-item>
                    <el-dropdown-item><button type="button" class="w-full text-left" @click="handleMoveToRoot(row)">移到根目录</button></el-dropdown-item>
                    <el-dropdown-item><button type="button" class="w-full text-left text-rose-600" @click="openDeleteDialog(row)">删除</button></el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>

        <div v-else class="space-y-3">
          <div class="overflow-hidden rounded border border-slate-200">
            <table class="min-w-full divide-y divide-slate-200 text-sm">
              <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th class="px-3 py-2"></th>
                  <th class="px-3 py-2">标题</th>
                  <th class="px-3 py-2">类型</th>
                  <th class="px-3 py-2">路径</th>
                  <th class="px-3 py-2">更新时间</th>
                  <th class="px-3 py-2">洞察</th>
                  <th class="px-3 py-2">状态</th>
                  <th class="px-3 py-2">索引</th>
                  <th class="px-3 py-2">操作</th>
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
                    <input :checked="selectedDocumentIds.has(row.id)" type="checkbox" @change="toggleDocumentSelection(row.id)">
                  </td>
                  <td class="px-3 py-3">
                    <button type="button" class="text-left" @click="selectedDocumentId = row.id">
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
                      <div class="mt-1 text-xs text-slate-500">{{ documentInsight(row) }}</div>
                    </button>
                  </td>
                  <td class="px-3 py-3 text-slate-600">{{ row.is_folder ? 'folder' : row.content_type }}</td>
                  <td class="px-3 py-3 text-xs text-slate-500">{{ row.file_path || '-' }}</td>
                  <td class="px-3 py-3 text-xs text-slate-500">{{ formatDate(row.updated_at) }}</td>
                  <td class="px-3 py-3"><span class="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{{ insightChip(row) }}</span></td>
                  <td class="px-3 py-3"><span class="rounded px-2 py-0.5 text-[11px]" :class="statusClass(row.status)">{{ row.status }}</span></td>
                  <td class="px-3 py-3"><span class="rounded px-2 py-0.5 text-[11px]" :class="indexClass(row.index_status)">{{ row.index_status }}</span></td>
                  <td class="px-3 py-3">
                    <el-dropdown trigger="click">
                      <button type="button" class="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50">操作</button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item v-if="!row.is_folder"><button type="button" class="w-full text-left" @click="openDocument(row)">打开</button></el-dropdown-item>
                          <el-dropdown-item><button type="button" class="w-full text-left" @click="openRenameDialog(row)">重命名</button></el-dropdown-item>
                          <el-dropdown-item><button type="button" class="w-full text-left" @click="handleCopyNodeTitle(row)">复制标题</button></el-dropdown-item>
                          <el-dropdown-item><button type="button" class="w-full text-left" @click="handleMoveToRoot(row)">移到根目录</button></el-dropdown-item>
                          <el-dropdown-item><button type="button" class="w-full text-left text-rose-600" @click="openDeleteDialog(row)">删除</button></el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex items-center justify-between gap-3 text-sm text-slate-500">
            <div>第 {{ currentPage }} / {{ totalPages }} 页</div>
            <div class="flex items-center gap-2">
              <select v-model.number="pageSize" class="rounded border px-2 py-1 text-sm">
                <option :value="8">8 / 页</option>
                <option :value="12">12 / 页</option>
                <option :value="20">20 / 页</option>
              </select>
              <button type="button" class="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50" :disabled="currentPage <= 1" @click="currentPage -= 1">上一页</button>
              <button type="button" class="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-50" :disabled="currentPage >= totalPages" @click="currentPage += 1">下一页</button>
            </div>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium">{{ selectedDocument?.title || '文档详情' }}</div>
            <div v-if="selectedDocument" class="flex items-center gap-2 text-xs">
              <span class="rounded px-2 py-0.5" :class="statusClass(selectedDocument.status)">{{ selectedDocument.status }}</span>
              <span class="rounded px-2 py-0.5" :class="indexClass(selectedDocument.index_status)">{{ selectedDocument.index_status }}</span>
            </div>
          </div>
        </template>

        <div v-if="!selectedDocument" class="text-sm text-slate-500">请选择左侧文档查看详情</div>

        <div v-else class="space-y-4">
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">状态</div>
              <div class="mt-1 text-sm font-medium text-slate-700">{{ selectedDocument.status }}</div>
            </div>
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">索引</div>
              <div class="mt-1 text-sm font-medium text-slate-700">{{ selectedDocument.index_status }}</div>
            </div>
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">类型</div>
              <div class="mt-1 text-sm font-medium text-slate-700">{{ selectedDocument.is_folder ? 'folder' : selectedDocument.content_type }}</div>
            </div>
            <div class="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <div class="text-xs text-slate-400">洞察</div>
              <div class="mt-1 text-sm font-medium text-slate-700">{{ documentInsight(selectedDocument) }}</div>
            </div>
          </div>

          <div class="flex flex-wrap gap-2 text-xs">
            <span class="rounded bg-slate-100 px-2 py-1 text-slate-600">排序 {{ selectedDocument.sort_order }}</span>
            <span v-if="selectedDocument.parent_id" class="rounded bg-slate-100 px-2 py-1 text-slate-600">存在父节点</span>
            <span v-if="selectedDocument.indexed_at" class="rounded bg-slate-100 px-2 py-1 text-slate-600">最近索引 {{ formatDate(selectedDocument.indexed_at) }}</span>
            <span class="rounded bg-slate-100 px-2 py-1 text-slate-600">{{ insightChip(selectedDocument) }}</span>
          </div>

          <div v-if="selectedDocument.file_path" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600">
            <div class="text-xs text-slate-400">来源路径</div>
            <div class="mt-1 break-all">{{ selectedDocument.file_path }}</div>
          </div>

          <div v-if="selectedDocument.metadata" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600">
            <div class="text-xs text-slate-400">元数据</div>
            <pre class="mt-1 overflow-auto whitespace-pre-wrap break-all text-xs">{{ formattedMetadata }}</pre>
          </div>

          <div class="rounded border border-slate-200 px-4 py-3">
            <div class="mb-2 text-xs text-slate-400">正文预览</div>
            <div class="max-h-[640px] overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
              {{ selectedDocument.content || '暂无内容' }}
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <el-dialog v-if="createDialog.open" model-value="true">
      <div class="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">{{ createDialog.isFolder ? '新建文件夹' : '新建文档' }}</div>
          <button type="button" class="text-slate-400" @click="closeCreateDialog">✕</button>
        </div>
        <div class="mt-4 space-y-3">
          <input v-model="createDialog.title" class="w-full rounded border px-3 py-2 text-sm" :placeholder="createDialog.isFolder ? '文件夹名称' : '文档标题'">
          <textarea v-if="!createDialog.isFolder" v-model="createDialog.content" rows="8" class="w-full rounded border px-3 py-2 text-sm" placeholder="输入文档正文..." />
          <div class="text-xs text-slate-400">{{ createDialog.parentId ? '将创建在当前选中文件夹下。' : '将创建在当前知识库根目录。' }}</div>
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeCreateDialog">取消</button>
          <button type="button" class="rounded bg-blue-600 px-3 py-2 text-sm text-white" @click="submitCreateDialog">确定</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="renameDialog.open && renameDialog.target" model-value="true">
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">重命名</div>
          <button type="button" class="text-slate-400" @click="closeRenameDialog">✕</button>
        </div>
        <input v-model="renameDialog.title" class="mt-4 w-full rounded border px-3 py-2 text-sm" placeholder="输入新的名称">
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeRenameDialog">取消</button>
          <button type="button" class="rounded bg-blue-600 px-3 py-2 text-sm text-white" @click="submitRenameDialog">确定</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="importDialog.open" model-value="true">
      <div class="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">导入文档</div>
          <button type="button" class="text-slate-400" @click="closeImportDialog">✕</button>
        </div>
        <div class="mt-4 grid gap-3">
          <input v-model="importDialog.title" class="w-full rounded border px-3 py-2 text-sm" placeholder="导入文档标题">
          <textarea v-model="importDialog.content" rows="12" class="w-full rounded border px-3 py-2 text-sm" placeholder="粘贴需要导入的文档正文..." />
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeImportDialog">取消</button>
          <button type="button" class="rounded bg-blue-600 px-3 py-2 text-sm text-white" @click="submitImportDialog">导入</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="bulkDialog.open" model-value="true">
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">批量操作</div>
          <button type="button" class="text-slate-400" @click="closeBulkDialog">✕</button>
        </div>
        <div class="mt-4 text-sm text-slate-600">
          {{ bulkDialogMessage }}
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeBulkDialog">取消</button>
          <button type="button" class="rounded px-3 py-2 text-sm text-white" :class="bulkDialog.mode === 'delete' ? 'bg-rose-600' : 'bg-blue-600'" @click="submitBulkDialog">确定</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="deleteDialog.open && deleteDialog.target" model-value="true">
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">删除确认</div>
          <button type="button" class="text-slate-400" @click="closeDeleteDialog">✕</button>
        </div>
        <div class="mt-4 text-sm text-slate-600">确认删除「{{ deleteDialog.target.title }}」吗？</div>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeDeleteDialog">取消</button>
          <button type="button" class="rounded bg-rose-600 px-3 py-2 text-sm text-white" @click="submitDeleteDialog">删除</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="knowledgeBaseRenameDialog.open && knowledgeBaseRenameDialog.target" model-value="true">
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">重命名知识库</div>
          <button type="button" class="text-slate-400" @click="closeKnowledgeBaseRenameDialog">✕</button>
        </div>
        <input v-model="knowledgeBaseRenameDialog.name" class="mt-4 w-full rounded border px-3 py-2 text-sm" placeholder="输入新的知识库名称">
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeKnowledgeBaseRenameDialog">取消</button>
          <button type="button" class="rounded bg-blue-600 px-3 py-2 text-sm text-white" @click="submitKnowledgeBaseRenameDialog">确定</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="knowledgeBaseDeleteDialog.open && knowledgeBaseDeleteDialog.target" model-value="true">
      <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div class="text-lg font-semibold text-slate-900">删除知识库</div>
          <button type="button" class="text-slate-400" @click="closeKnowledgeBaseDeleteDialog">✕</button>
        </div>
        <div class="mt-4 text-sm text-slate-600">确认删除知识库「{{ knowledgeBaseDeleteDialog.target.name }}」吗？</div>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeKnowledgeBaseDeleteDialog">取消</button>
          <button type="button" class="rounded bg-rose-600 px-3 py-2 text-sm text-white" @click="submitKnowledgeBaseDeleteDialog">删除</button>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-if="knowledgeBaseSettingsDialog.open" model-value="true">
      <div class="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl mx-auto">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-lg font-semibold text-slate-900">检索配置</div>
            <div class="mt-1 text-sm text-slate-500">
              为当前知识库配置 AI 检索和会话记忆策略
            </div>
          </div>
          <button type="button" class="text-slate-400" @click="closeKnowledgeBaseSettingsDialog">✕</button>
        </div>
        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <label class="text-sm text-slate-600">
            <div class="mb-1">检索画像</div>
            <select v-model="knowledgeBaseSettingsDialog.form.retrieval_profile" class="w-full rounded border px-3 py-2 text-sm">
              <option value="quant_research">量化研究平衡</option>
              <option value="precision">高精度引用</option>
              <option value="exploration">探索式阅读</option>
            </select>
          </label>
          <label class="text-sm text-slate-600">
            <div class="mb-1">搜索模式</div>
            <select v-model="knowledgeBaseSettingsDialog.form.search_mode" class="w-full rounded border px-3 py-2 text-sm">
              <option value="hybrid">混合检索</option>
              <option value="keyword">关键词优先</option>
            </select>
          </label>
          <label class="text-sm text-slate-600">
            <div class="mb-1">默认 top_k</div>
            <input v-model.number="knowledgeBaseSettingsDialog.form.default_top_k" type="number" min="1" max="20" class="w-full rounded border px-3 py-2 text-sm">
          </label>
          <label class="text-sm text-slate-600">
            <div class="mb-1">最低相似度</div>
            <input v-model.number="knowledgeBaseSettingsDialog.form.min_similarity" type="number" min="0" max="1" step="0.01" class="w-full rounded border px-3 py-2 text-sm">
          </label>
          <label class="text-sm text-slate-600">
            <div class="mb-1">最大上下文块数</div>
            <input v-model.number="knowledgeBaseSettingsDialog.form.max_context_chunks" type="number" min="1" max="12" class="w-full rounded border px-3 py-2 text-sm">
          </label>
          <label class="text-sm text-slate-600">
            <div class="mb-1">量化重点</div>
            <select v-model="knowledgeBaseSettingsDialog.form.quant_focus" class="w-full rounded border px-3 py-2 text-sm">
              <option value="strategy_research">策略研究</option>
              <option value="strategy_review">策略审查</option>
              <option value="implementation">实现落地</option>
              <option value="general">通用问答</option>
            </select>
          </label>
        </div>
        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <label class="inline-flex items-center gap-2 text-sm text-slate-600">
            <input v-model="knowledgeBaseSettingsDialog.form.use_conversation_memory" type="checkbox">
            <span>启用会话记忆检索</span>
          </label>
          <label class="text-sm text-slate-600">
            <div class="mb-1">会话回看条数</div>
            <input v-model.number="knowledgeBaseSettingsDialog.form.conversation_lookback_messages" type="number" min="0" max="20" class="w-full rounded border px-3 py-2 text-sm">
          </label>
        </div>
        <div class="mt-4">
          <label class="text-sm text-slate-600">
            <div class="mb-1">系统补充提示</div>
            <textarea
              v-model="knowledgeBaseSettingsDialog.form.system_prompt_suffix"
              rows="4"
              class="w-full rounded border px-3 py-2 text-sm"
              placeholder="例如：优先按 A 股日线策略研究口径回答。"
            />
          </label>
        </div>
        <div class="mt-4 rounded border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          当前配置会影响 AI 助手的检索查询改写、文档排序、上下文拼装和量化场景提示词。
        </div>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded border border-slate-200 px-3 py-2 text-sm text-slate-600" @click="closeKnowledgeBaseSettingsDialog">取消</button>
          <button type="button" class="rounded bg-blue-600 px-3 py-2 text-sm text-white" @click="submitKnowledgeBaseSettingsDialog">保存配置</button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import type {
  KBDocumentItem,
  KnowledgeBaseItem,
  KnowledgeBaseSettings,
} from '@/api/knowledgeBase'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

type ViewMode = 'tree' | 'table'
type SortKey = 'sort_order' | 'title' | 'updated_at' | 'status'
type BulkMode = 'publish' | 'draft' | 'move_root' | 'mark_not_indexed' | 'delete'
type TreeRow = KBDocumentItem & { depth: number }

const route = useRoute()
const router = useRouter()
const store = useKnowledgeBaseStore()

const knowledgeBaseSearch = ref('')
const documentSearch = ref('')
const selectedDocumentId = ref<string | null>(null)
const viewMode = ref<ViewMode>('tree')
const sortKey = ref<SortKey>('sort_order')
const currentPage = ref(1)
const pageSize = ref(12)
const expandedFolderIds = ref<Set<string>>(new Set())
const selectedDocumentIds = ref<Set<string>>(new Set())

const createDialog = reactive({
  open: false,
  isFolder: false,
  title: '',
  content: '',
  parentId: null as string | null,
})

const renameDialog = reactive({
  open: false,
  target: null as KBDocumentItem | null,
  title: '',
})

const importDialog = reactive({
  open: false,
  title: '',
  content: '',
})

const bulkDialog = reactive({
  open: false,
  mode: 'publish' as BulkMode,
})

const deleteDialog = reactive({
  open: false,
  target: null as KBDocumentItem | null,
})

const knowledgeBaseRenameDialog = reactive({
  open: false,
  target: null as KnowledgeBaseItem | null,
  name: '',
})

const knowledgeBaseDeleteDialog = reactive({
  open: false,
  target: null as KnowledgeBaseItem | null,
})

function createDefaultKnowledgeBaseSettings(): KnowledgeBaseSettings {
  return {
    retrieval_profile: 'quant_research',
    search_mode: 'hybrid',
    default_top_k: 8,
    min_similarity: 0.08,
    title_weight: 0.35,
    keyword_weight: 0.35,
    phrase_weight: 0.2,
    recency_weight: 0.1,
    max_context_chunks: 6,
    use_conversation_memory: true,
    conversation_lookback_messages: 6,
    prioritize_title_matches: true,
    prefer_recent_documents: true,
    quant_focus: 'strategy_research',
    system_prompt_suffix: '',
  }
}

const knowledgeBaseSettingsDialog = reactive({
  open: false,
  form: createDefaultKnowledgeBaseSettings(),
})

const draggedDocumentId = ref<string | null>(null)

const filteredKnowledgeBases = computed(() => {
  const keyword = knowledgeBaseSearch.value.trim().toLowerCase()
  if (!keyword) return store.knowledgeBases
  return store.knowledgeBases.filter(kb => [kb.name, kb.description ?? ''].some(value => value.toLowerCase().includes(keyword)))
})

const sortedDocuments = computed(() => {
  const keyword = documentSearch.value.trim().toLowerCase()
  const filtered = !keyword
    ? store.documents
    : store.documents.filter(doc => [doc.title, doc.content ?? '', doc.file_path ?? ''].some(value => value.toLowerCase().includes(keyword)))

  return [...filtered].sort((a, b) => {
    if (sortKey.value === 'title') return a.title.localeCompare(b.title)
    if (sortKey.value === 'updated_at') return (b.updated_at ?? '').localeCompare(a.updated_at ?? '')
    if (sortKey.value === 'status') return a.status.localeCompare(b.status)
    return a.sort_order - b.sort_order
  })
})

const indexedDocumentCount = computed(() => store.documents.filter(doc => doc.index_status === 'indexed').length)
const folderCount = computed(() => store.documents.filter(doc => doc.is_folder).length)
const currentKnowledgeBaseSettings = computed<KnowledgeBaseSettings>(() => ({
  ...createDefaultKnowledgeBaseSettings(),
  ...(store.currentKnowledgeBase?.settings ?? {}),
}))

const displayRows = computed<TreeRow[]>(() => {
  const byParent = new Map<string | null, KBDocumentItem[]>()
  for (const doc of sortedDocuments.value) {
    const key = doc.parent_id ?? null
    const bucket = byParent.get(key) ?? []
    bucket.push(doc)
    byParent.set(key, bucket)
  }

  const rows: TreeRow[] = []
  const visited = new Set<string>()
  const walk = (parentId: string | null, depth: number) => {
    const children = byParent.get(parentId) ?? []
    for (const child of children) {
      if (visited.has(child.id)) continue
      visited.add(child.id)
      rows.push({ ...child, depth })
      if (!child.is_folder || expandedFolderIds.value.has(child.id)) {
        walk(child.id, depth + 1)
      }
    }
  }
  walk(null, 0)
  for (const doc of sortedDocuments.value) {
    if (!visited.has(doc.id)) rows.push({ ...doc, depth: 0 })
  }
  return rows
})

const totalPages = computed(() => Math.max(1, Math.ceil(displayRows.value.length / pageSize.value)))
const visibleRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return displayRows.value.slice(start, start + pageSize.value)
})
const selectedDocument = computed(() => displayRows.value.find(doc => doc.id === selectedDocumentId.value) ?? visibleRows.value[0] ?? null)
const formattedMetadata = computed(() => (selectedDocument.value?.metadata ? JSON.stringify(selectedDocument.value.metadata, null, 2) : ''))
const allVisibleSelected = computed(() => visibleRows.value.length > 0 && visibleRows.value.every(doc => selectedDocumentIds.value.has(doc.id)))
const bulkDialogMessage = computed(() => {
  const count = selectedDocumentIds.value.size
  if (bulkDialog.mode === 'publish') return `确认将 ${count} 项设为 published 吗？`
  if (bulkDialog.mode === 'draft') return `确认将 ${count} 项设为 draft 吗？`
  if (bulkDialog.mode === 'move_root') return `确认将 ${count} 项移动到根目录吗？`
  if (bulkDialog.mode === 'mark_not_indexed') return `确认将 ${count} 项标记为 not_indexed 吗？`
  return `确认删除 ${count} 项吗？`
})

function statusClass(status: string) {
  if (status === 'published') return 'bg-emerald-100 text-emerald-700'
  if (status === 'draft') return 'bg-amber-100 text-amber-700'
  return 'bg-slate-100 text-slate-600'
}

function indexClass(status: string) {
  if (status === 'indexed') return 'bg-blue-100 text-blue-700'
  if (status === 'not_indexed') return 'bg-slate-100 text-slate-600'
  return 'bg-amber-100 text-amber-700'
}

function formatDate(value?: string | null) {
  if (!value) return '未知时间'
  return value.replace('T', ' ').slice(0, 16)
}

function retrievalProfileLabel(profile?: string | null) {
  if (profile === 'precision') return '高精度引用'
  if (profile === 'exploration') return '探索式阅读'
  return '量化研究平衡'
}

function documentInsight(doc: KBDocumentItem) {
  if (doc.is_folder) return '文件夹'
  const length = (doc.content ?? '').length
  if (length > 4000) return '长文档'
  if (length > 0) return '正文已迁移'
  return '等待补充内容'
}

function insightChip(doc: KBDocumentItem) {
  if (doc.is_folder) return '📁 结构'
  if (doc.index_status === 'indexed') return '✨ 已索引'
  if ((doc.content ?? '').length > 4000) return '📚 长文'
  if ((doc.content ?? '').length > 0) return '📝 正文'
  return '⏳ 待补充'
}

function toggleFolder(folderId: string) {
  const next = new Set(expandedFolderIds.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  expandedFolderIds.value = next
}

function toggleDocumentSelection(documentId: string) {
  const next = new Set(selectedDocumentIds.value)
  if (next.has(documentId)) next.delete(documentId)
  else next.add(documentId)
  selectedDocumentIds.value = next
}

function toggleSelectAllVisible(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  const next = new Set(selectedDocumentIds.value)
  if (checked) visibleRows.value.forEach(doc => next.add(doc.id))
  else visibleRows.value.forEach(doc => next.delete(doc.id))
  selectedDocumentIds.value = next
}

function clearSelection() {
  selectedDocumentIds.value = new Set()
}

function openDocument(document: KBDocumentItem) {
  router.push({
    name: 'KnowledgeBaseDocument',
    params: {
      kbId: document.knowledge_base_id,
      docId: document.id,
    },
  })
}

function handleDragStart(documentId: string) {
  draggedDocumentId.value = documentId
}

async function handleDrop(target: KBDocumentItem) {
  const sourceId = draggedDocumentId.value
  draggedDocumentId.value = null
  if (!sourceId || sourceId === target.id) return
  const source = store.documents.find(doc => doc.id === sourceId)
  if (!source) return
  const parentId = target.parent_id ?? null
  const siblings = store.documents
    .filter(doc => (doc.parent_id ?? null) === parentId)
    .sort((a, b) => a.sort_order - b.sort_order)
  const sourceIndex = siblings.findIndex(doc => doc.id === sourceId)
  const targetIndex = siblings.findIndex(doc => doc.id === target.id)
  if (sourceIndex === -1 || targetIndex === -1) return
  const reordered = [...siblings]
  const [moved] = reordered.splice(sourceIndex, 1)
  reordered.splice(targetIndex, 0, moved)
  for (const [index, doc] of reordered.entries()) {
    await store.updateDocument(doc.id, { sort_order: index, parent_id: parentId })
  }
  ElMessage.success('已更新树节点顺序')
}

function openCreateDialog(isFolder: boolean, parentId: string | null = null) {
  createDialog.open = true
  createDialog.isFolder = isFolder
  createDialog.title = ''
  createDialog.content = ''
  createDialog.parentId = parentId
}

function closeCreateDialog() {
  createDialog.open = false
}

async function submitCreateDialog() {
  if (!store.currentKnowledgeBase) {
    ElMessage.warning('请先选择知识库')
    return
  }
  if (!createDialog.title.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  const created = await store.createDocument({
    title: createDialog.title.trim(),
    content: createDialog.isFolder ? '' : createDialog.content,
    content_type: 'markdown',
    is_folder: createDialog.isFolder,
    parent_id: createDialog.parentId,
  })
  if (created) {
    selectedDocumentId.value = created.id
    if (created.is_folder) expandedFolderIds.value = new Set([...expandedFolderIds.value, created.id])
    ElMessage.success(created.is_folder ? '文件夹已创建' : '文档已创建')
    closeCreateDialog()
  }
}

function openRenameDialog(target: KBDocumentItem) {
  renameDialog.open = true
  renameDialog.target = target
  renameDialog.title = target.title
}

function closeRenameDialog() {
  renameDialog.open = false
  renameDialog.target = null
  renameDialog.title = ''
}

async function submitRenameDialog() {
  if (!renameDialog.target || !renameDialog.title.trim()) {
    ElMessage.warning('请输入新的名称')
    return
  }
  await store.updateDocument(renameDialog.target.id, { title: renameDialog.title.trim() })
  ElMessage.success('名称已更新')
  closeRenameDialog()
}

function openImportDialog() {
  importDialog.open = true
  importDialog.title = ''
  importDialog.content = ''
}

function closeImportDialog() {
  importDialog.open = false
}

async function submitImportDialog() {
  if (!store.currentKnowledgeBase) {
    ElMessage.warning('请先选择知识库')
    return
  }
  if (!importDialog.title.trim()) {
    ElMessage.warning('请输入导入文档标题')
    return
  }
  const created = await store.createDocument({
    title: importDialog.title.trim(),
    content: importDialog.content,
    content_type: 'markdown',
    is_folder: false,
    parent_id: selectedDocument.value?.is_folder ? selectedDocument.value.id : null,
  })
  if (created) {
    selectedDocumentId.value = created.id
    ElMessage.success('文档已导入到当前知识库')
    closeImportDialog()
  }
}

function openBulkActionDialog(mode: BulkMode) {
  if (!selectedDocumentIds.value.size) {
    ElMessage.warning('请先选择文档')
    return
  }
  bulkDialog.open = true
  bulkDialog.mode = mode
}

function closeBulkDialog() {
  bulkDialog.open = false
}

async function submitBulkDialog() {
  const ids = [...selectedDocumentIds.value]
  if (!ids.length) {
    ElMessage.warning('请先选择文档')
    return
  }
  if (bulkDialog.mode === 'publish') {
    for (const id of ids) {
      await store.updateDocument(id, { status: 'published' })
    }
    ElMessage.success(`已发布 ${ids.length} 项`)
  } else if (bulkDialog.mode === 'draft') {
    for (const id of ids) {
      await store.updateDocument(id, { status: 'draft' })
    }
    ElMessage.success(`已设为草稿 ${ids.length} 项`)
  } else if (bulkDialog.mode === 'move_root') {
    for (const id of ids) {
      await store.updateDocument(id, { parent_id: null })
    }
    ElMessage.success(`已移动 ${ids.length} 项到根目录`)
  } else if (bulkDialog.mode === 'mark_not_indexed') {
    for (const id of ids) {
      await store.updateDocument(id, { index_status: 'not_indexed' })
    }
    ElMessage.success(`已标记 ${ids.length} 项为未索引`)
  } else {
    for (const id of ids) {
      await store.deleteDocument(id)
    }
    clearSelection()
    ElMessage.success(`已删除 ${ids.length} 项`)
  }
  closeBulkDialog()
}

function openDeleteDialog(target: KBDocumentItem) {
  deleteDialog.open = true
  deleteDialog.target = target
}

function closeDeleteDialog() {
  deleteDialog.open = false
  deleteDialog.target = null
}

async function submitDeleteDialog() {
  if (!deleteDialog.target) return
  await store.deleteDocument(deleteDialog.target.id)
  selectedDocumentIds.value.delete(deleteDialog.target.id)
  if (selectedDocumentId.value === deleteDialog.target.id) selectedDocumentId.value = null
  ElMessage.success('文档已删除')
  closeDeleteDialog()
}

async function handleBatchCopyTitles() {
  if (!sortedDocuments.value.length) {
    ElMessage.warning('当前没有可复制的文档标题')
    return
  }
  try {
    await navigator.clipboard.writeText(sortedDocuments.value.map(doc => doc.title).join('\n'))
    ElMessage.success(`已复制 ${sortedDocuments.value.length} 条文档标题`)
  } catch {
    ElMessage.warning('复制失败，请检查浏览器剪贴板权限')
  }
}

function openCreateChildDialog(row: KBDocumentItem) {
  openCreateDialog(false, row.is_folder ? row.id : row.parent_id ?? null)
}

async function handleCopyNodeTitle(row: KBDocumentItem) {
  try {
    await navigator.clipboard.writeText(row.title)
    ElMessage.success('已复制文档标题')
  } catch {
    ElMessage.warning('复制失败，请检查浏览器剪贴板权限')
  }
}

function openKnowledgeBaseRenameDialog(kb: KnowledgeBaseItem) {
  knowledgeBaseRenameDialog.open = true
  knowledgeBaseRenameDialog.target = kb
  knowledgeBaseRenameDialog.name = kb.name
}

function closeKnowledgeBaseRenameDialog() {
  knowledgeBaseRenameDialog.open = false
  knowledgeBaseRenameDialog.target = null
  knowledgeBaseRenameDialog.name = ''
}

async function submitKnowledgeBaseRenameDialog() {
  if (!knowledgeBaseRenameDialog.target || !knowledgeBaseRenameDialog.name.trim()) {
    ElMessage.warning('请输入新的知识库名称')
    return
  }
  await store.updateKnowledgeBase(knowledgeBaseRenameDialog.target.id, {
    name: knowledgeBaseRenameDialog.name.trim(),
  })
  ElMessage.success('知识库名称已更新')
  closeKnowledgeBaseRenameDialog()
}

function openKnowledgeBaseDeleteDialog(kb: KnowledgeBaseItem) {
  knowledgeBaseDeleteDialog.open = true
  knowledgeBaseDeleteDialog.target = kb
}

function openKnowledgeBaseSettingsDialog() {
  knowledgeBaseSettingsDialog.open = true
  knowledgeBaseSettingsDialog.form = {
    ...createDefaultKnowledgeBaseSettings(),
    ...(store.currentKnowledgeBase?.settings ?? {}),
    system_prompt_suffix: store.currentKnowledgeBase?.settings?.system_prompt_suffix ?? '',
  }
}

function closeKnowledgeBaseSettingsDialog() {
  knowledgeBaseSettingsDialog.open = false
}

async function submitKnowledgeBaseSettingsDialog() {
  if (!store.currentKnowledgeBase) {
    ElMessage.warning('请先选择知识库')
    return
  }
  const settingsPayload = {
    ...knowledgeBaseSettingsDialog.form,
    default_top_k: Math.min(20, Math.max(1, Number(knowledgeBaseSettingsDialog.form.default_top_k) || 8)),
    min_similarity: Math.min(1, Math.max(0, Number(knowledgeBaseSettingsDialog.form.min_similarity) || 0)),
    max_context_chunks: Math.min(12, Math.max(1, Number(knowledgeBaseSettingsDialog.form.max_context_chunks) || 6)),
    conversation_lookback_messages: Math.min(
      20,
      Math.max(0, Number(knowledgeBaseSettingsDialog.form.conversation_lookback_messages) || 0),
    ),
    system_prompt_suffix: knowledgeBaseSettingsDialog.form.system_prompt_suffix?.trim() || null,
  }
  await store.updateKnowledgeBase(store.currentKnowledgeBase.id, {
    settings: settingsPayload,
  })
  ElMessage.success('检索配置已更新')
  closeKnowledgeBaseSettingsDialog()
}

function closeKnowledgeBaseDeleteDialog() {
  knowledgeBaseDeleteDialog.open = false
  knowledgeBaseDeleteDialog.target = null
}

async function submitKnowledgeBaseDeleteDialog() {
  if (!knowledgeBaseDeleteDialog.target) {
    return
  }
  const deletedId = knowledgeBaseDeleteDialog.target.id
  await store.deleteKnowledgeBase(deletedId)
  ElMessage.success('知识库已删除')
  if (selectedDocumentId.value && !store.currentKnowledgeBase) {
    selectedDocumentId.value = null
  }
  closeKnowledgeBaseDeleteDialog()
}

async function handleMoveToRoot(row: KBDocumentItem) {
  await store.updateDocument(row.id, { parent_id: null })
  ElMessage.success('已移动到根目录')
}

async function handleSelectKnowledgeBase(id: string) {
  documentSearch.value = ''
  selectedDocumentId.value = null
  clearSelection()
  currentPage.value = 1
  await store.selectKnowledgeBase(id)
  expandedFolderIds.value = new Set(store.documents.filter(doc => doc.is_folder && !doc.parent_id).map(doc => doc.id))
  if (route.query.kbId === id && typeof route.query.docId === 'string') {
    selectedDocumentId.value = route.query.docId
  }
}

watch([sortKey, pageSize], () => {
  currentPage.value = 1
})

watch(
  () => displayRows.value,
  (rows) => {
    if (!rows.length) {
      selectedDocumentId.value = null
      return
    }
    if (!rows.some(doc => doc.id === selectedDocumentId.value)) {
      selectedDocumentId.value = rows[0]?.id ?? null
    }
    if (currentPage.value > totalPages.value) currentPage.value = totalPages.value
  },
  { immediate: true },
)

onMounted(async () => {
  await store.fetchKnowledgeBases()
  const requestedKbId = typeof route.query.kbId === 'string' ? route.query.kbId : undefined
  const firstId = requestedKbId || store.knowledgeBases[0]?.id
  if (firstId) {
    await store.selectKnowledgeBase(firstId)
    expandedFolderIds.value = new Set(store.documents.filter(doc => doc.is_folder && !doc.parent_id).map(doc => doc.id))
    if (typeof route.query.docId === 'string') selectedDocumentId.value = route.query.docId
  }
})
</script>
