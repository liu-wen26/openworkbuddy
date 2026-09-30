<template>
  <div>
    <div class="toolbar">
      <h2>审计日志</h2>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item label="操作类型">
          <el-select v-model="filters.action" clearable placeholder="全部" style="width: 160px">
            <el-option v-for="a in actionOptions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-select v-model="filters.resource_type" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="r in resourceOptions" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="filters.role" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="(label, key) in ROLE_LABELS" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="filters.path" clearable placeholder="模糊匹配" style="width: 180px" />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="range"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            style="width: 360px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="items" v-loading="loading" border>
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="username" label="操作人" width="120">
        <template #default="{ row }">{{ row.username || '-' }}</template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="120">
        <template #default="{ row }">{{ ROLE_LABELS[row.role] || row.role || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="actionType(row.action)">{{ actionLabel(row.action) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="resource_type" label="资源" width="110">
        <template #default="{ row }">{{ resourceLabel(row.resource_type) }}</template>
      </el-table-column>
      <el-table-column prop="path" label="接口路径" min-width="220" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <span v-if="row.status_code" :class="row.status_code >= 400 ? 'fail' : 'ok'">{{ row.status_code }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="140" />
      <el-table-column label="详情" min-width="200">
        <template #default="{ row }">
          <span class="detail-text">{{ detailText(row.detail) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { listAuditLogs, type AuditLog } from '@/api/system'
import { ROLE_LABELS } from '@/api/users'

const items = ref<AuditLog[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const range = ref<[Date, Date] | null>(null)

const filters = reactive({
  action: '',
  resource_type: '',
  role: '',
  path: '',
})

const actionOptions = [
  { value: 'create', label: '新增' },
  { value: 'update', label: '修改' },
  { value: 'delete', label: '删除' },
  { value: 'create_failed', label: '新增失败' },
  { value: 'update_failed', label: '修改失败' },
  { value: 'delete_failed', label: '删除失败' },
  { value: 'export', label: '导出' },
  { value: 'archive', label: '归档' },
  { value: 'archive_restore', label: '恢复归档' },
  { value: 'archive_delete', label: '删除归档' },
  { value: 'role_update', label: '角色权限变更' },
  { value: 'system_update', label: '系统设置变更' },
  { value: 'system_test', label: '系统设置测试' },
]

const resourceOptions = [
  { value: 'exam', label: '考试' },
  { value: 'template', label: '模板' },
  { value: 'import', label: '导入' },
  { value: 'choice', label: '选择题' },
  { value: 'grading', label: '阅卷' },
  { value: 'precheck', label: '预阅卷' },
  { value: 'analytics', label: '学情分析' },
  { value: 'export', label: '导出' },
  { value: 'archive', label: '归档' },
  { value: 'system', label: '系统设置' },
  { value: 'user', label: '用户' },
  { value: 'auth', label: '认证' },
]

function actionLabel(action: string) {
  return actionOptions.find((a) => a.value === action)?.label || action
}

function actionType(action: string) {
  if (action.endsWith('_failed')) return 'danger'
  if (action === 'delete' || action === 'archive_delete') return 'warning'
  if (action === 'create' || action === 'archive') return 'success'
  return 'info'
}

function resourceLabel(type: string | null) {
  if (!type) return '-'
  return resourceOptions.find((r) => r.value === type)?.label || type
}

function detailText(detail: Record<string, unknown> | null) {
  if (!detail) return '-'
  const entries = Object.entries(detail).filter(([k]) => k !== 'timestamp')
  if (!entries.length) return '-'
  return entries.map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('，')
}

function formatTime(value: string) {
  const d = new Date(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    }
    if (filters.action) params.action = filters.action
    if (filters.resource_type) params.resource_type = filters.resource_type
    if (filters.role) params.role = filters.role
    if (filters.path) params.path = filters.path
    if (range.value) {
      params.start = range.value[0].toISOString()
      params.end = range.value[1].toISOString()
    }
    const res = await listAuditLogs(params)
    items.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function reset() {
  filters.action = ''
  filters.resource_type = ''
  filters.role = ''
  filters.path = ''
  range.value = null
  page.value = 1
  load()
}

function onPageChange(p: number) {
  page.value = p
  load()
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.filter-card {
  margin-bottom: 16px;
}
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.detail-text {
  color: #606266;
  font-size: 12px;
}
.ok {
  color: #67c23a;
}
.fail {
  color: #f56c6c;
}
</style>