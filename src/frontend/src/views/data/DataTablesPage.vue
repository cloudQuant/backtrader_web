<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="page-title">数据表</div>
          <div class="page-subtitle">查看已落盘数据表、更新状态和表详情预览。</div>
        </div>
        <el-tag type="info">共 {{ total }} 张</el-tag>
      </div>
    </template>

    <div class="toolbar">
      <el-input
        v-model="search"
        clearable
        placeholder="按表名或备注搜索"
        class="toolbar-search"
        @keyup.enter="reloadFirstPage"
        @clear="reloadFirstPage"
      />
      <el-button
        type="primary"
        @click="reloadFirstPage"
      >
        查询
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="tables"
      stripe
    >
      <el-table-column
        prop="table_name"
        label="表名"
        min-width="220"
      />
      <el-table-column
        prop="table_comment"
        label="备注"
        min-width="180"
      />
      <el-table-column
        prop="row_count"
        label="行数"
        width="120"
      >
        <template #default="{ row }">
          {{ compactCount(row.row_count) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="last_update_status"
        label="最近状态"
        width="110"
      >
        <template #default="{ row }">
          <el-tag :type="row.last_update_status === 'success' ? 'success' : 'info'">
            {{ row.last_update_status || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="data_start_date"
        label="数据起始"
        width="120"
      >
        <template #default="{ row }">
          {{ formatShortDate(row.data_start_date) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="data_end_date"
        label="数据结束"
        width="120"
      >
        <template #default="{ row }">
          {{ formatShortDate(row.data_end_date) }}
        </template>
      </el-table-column>
      <el-table-column
        prop="updated_at"
        label="更新时间"
        width="180"
      >
        <template #default="{ row }">
          {{ formatDateTime(row.updated_at) }}
        </template>
      </el-table-column>
      <el-table-column
        label="操作"
        width="100"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            @click="goDetail(row.id)"
          >
            详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadTables"
        @size-change="handleSizeChange"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { akshareTablesApi } from '@/api/akshare'
import { getErrorMessage } from '@/api/index'
import type { DataTable } from '@/types'
import { compactCount, formatDateTime, formatShortDate } from '@/views/data/utils'

const router = useRouter()

const loading = ref(false)
const tables = ref<DataTable[]>([])
const search = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

async function loadTables() {
  loading.value = true
  try {
    const response = await akshareTablesApi.list({
      search: search.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    tables.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '加载数据表失败'))
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  page.value = 1
  void loadTables()
}

function handleSizeChange() {
  page.value = 1
  void loadTables()
}

function goDetail(tableId: number) {
  void router.push({ name: 'DataTableDetail', params: { id: tableId } })
}

onMounted(() => {
  void loadTables()
})
</script>

<style scoped>
.header-row,
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
}

.page-subtitle {
  margin-top: 4px;
  color: #64748b;
}

.toolbar {
  margin-bottom: 16px;
  justify-content: flex-start;
}

.toolbar-search {
  max-width: 320px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
