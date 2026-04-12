<template>
  <div class="space-y-6">
    <el-page-header
      title="返回"
      @back="goBack"
    >
      <template #content>
        <span>{{ table?.table_name || '数据表详情' }}</span>
      </template>
    </el-page-header>

    <el-card v-loading="loading">
      <el-descriptions
        v-if="table"
        :column="2"
        border
      >
        <el-descriptions-item label="表名">
          {{ table.table_name }}
        </el-descriptions-item>
        <el-descriptions-item label="行数">
          {{ compactCount(table.row_count) }}
        </el-descriptions-item>
        <el-descriptions-item label="脚本 ID">
          {{ table.script_id || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="最近状态">
          {{ table.last_update_status || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="数据起始">
          {{ formatShortDate(table.data_start_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="数据结束">
          {{ formatShortDate(table.data_end_date) }}
        </el-descriptions-item>
      </el-descriptions>

      <el-tabs
        v-model="activeTab"
        class="detail-tabs"
        @tab-change="handleTabChange"
      >
        <el-tab-pane
          label="表结构"
          name="schema"
        >
          <el-table
            :data="schema?.columns || []"
            stripe
          >
            <el-table-column
              prop="name"
              label="列名"
              min-width="180"
            />
            <el-table-column
              prop="type"
              label="类型"
              width="180"
            />
            <el-table-column
              label="可空"
              width="100"
            >
              <template #default="{ row }">
                <el-tag :type="row.nullable ? 'success' : 'danger'">
                  {{ row.nullable ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="default"
              label="默认值"
              min-width="140"
            />
          </el-table>
        </el-tab-pane>

        <el-tab-pane
          label="数据预览"
          name="rows"
        >
          <el-table
            :data="rows.rows"
            stripe
            max-height="520"
          >
            <el-table-column
              v-for="column in rows.columns"
              :key="column"
              :prop="column"
              :label="column"
              min-width="160"
              show-overflow-tooltip
            />
          </el-table>

          <div class="pagination-wrap">
            <el-pagination
              v-model:current-page="rowsPage"
              v-model:page-size="rowsPageSize"
              :page-sizes="[20, 50, 100, 200]"
              :total="rows.total"
              layout="total, sizes, prev, pager, next, jumper"
              @current-change="loadRows"
              @size-change="handleRowsSizeChange"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { akshareTablesApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import type { DataTable, DataTableRowsResponse, DataTableSchemaResponse } from '@/types'
import { compactCount, formatShortDate } from '@/views/data/utils'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const activeTab = ref('schema')
const rowsPage = ref(1)
const rowsPageSize = ref(50)
const table = ref<DataTable | null>(null)
const schema = ref<DataTableSchemaResponse | null>(null)
const rows = reactive<DataTableRowsResponse>({
  table_name: '',
  columns: [],
  rows: [],
  page: 1,
  page_size: 50,
  total: 0,
})

const tableId = Number(route.params.id)

function goBack() {
  void router.back()
}

async function loadBase() {
  loading.value = true
  try {
    const [tableDetail, schemaDetail] = await Promise.all([
      akshareTablesApi.getDetail(tableId),
      akshareTablesApi.getSchema(tableId),
    ])
    table.value = tableDetail
    schema.value = schemaDetail
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载表详情失败'))
  } finally {
    loading.value = false
  }
}

async function loadRows() {
  try {
    const response = await akshareTablesApi.getRows(tableId, {
      page: rowsPage.value,
      page_size: rowsPageSize.value,
    })
    Object.assign(rows, response)
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载表预览失败'))
  }
}

function handleTabChange(tabName: string | number) {
  if (String(tabName) === 'rows' && rows.columns.length === 0) {
    void loadRows()
  }
}

function handleRowsSizeChange() {
  rowsPage.value = 1
  void loadRows()
}

onMounted(() => {
  void loadBase()
})
</script>

<style scoped>
.detail-tabs {
  margin-top: 24px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
