<template>
  <div class="exception-center">
    <div class="toolbar">
      <h2>异常中心</h2>
      <div class="toolbar-right">
        <el-select
          v-model="examId"
          placeholder="请选择考试"
          filterable
          style="width: 320px"
          @change="onExamChange"
        >
          <el-option v-for="e in exams" :key="e.id" :label="e.name" :value="e.id">
            <span>{{ e.name }}</span>
            <span class="option-sub">{{ e.subject }} · {{ e.grade }}</span>
          </el-option>
        </el-select>
        <el-button :disabled="!examId" :loading="loading" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="!examId"
      type="info"
      :closable="false"
      show-icon
      title="请选择考试后查看异常记录。"
    />

    <template v-else>
      <!-- 概览卡片 -->
      <div class="stat-row">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.total }}</div>
          <div class="stat-label">异常总数</div>
        </el-card>
        <el-card shadow="never" class="stat-card pending">
          <div class="stat-value">{{ summary.by_status.pending || 0 }}</div>
          <div class="stat-label">待处理</div>
        </el-card>
        <el-card shadow="never" class="stat-card resolved">
          <div class="stat-value">{{ summary.by_status.resolved || 0 }}</div>
          <div class="stat-label">已处理</div>
        </el-card>
        <el-card shadow="never" class="stat-card ignored">
          <div class="stat-value">{{ summary.by_status.ignored || 0 }}</div>
          <div class="stat-label">已忽略</div>
        </el-card>
      </div>

      <!-- 按类型分布 -->
      <el-card v-if="typeStats.length" shadow="never" style="margin-bottom: 16px">
        <template #header><span>异常类型分布</span></template>
        <div class="type-chips">
          <div
            v-for="ts in typeStats"
            :key="ts.type"
            class="type-chip"
            :class="{ active: filters.exception_type === ts.type }"
            @click="toggleType(ts.type)"
          >
            <span class="type-name">{{ typeLabel(ts.type) }}</span>
            <el-tag size="small" type="warning" effect="dark">{{ ts.pending }}</el-tag>
            <span class="type-total">/ {{ ts.total }}</span>
          </div>
        </div>
      </el-card>

      <!-- 筛选 -->
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>异常列表</span>
            <div class="filters">
              <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px" @change="loadExceptions">
                <el-option label="待处理" value="pending" />
                <el-option label="已处理" value="resolved" />
                <el-option label="已忽略" value="ignored" />
              </el-select>
              <el-select v-model="filters.exception_type" placeholder="全部类型" clearable style="width: 170px" @change="loadExceptions">
                <el-option v-for="(label, key) in EXCEPTION_TYPE_LABELS" :key="key" :label="label" :value="key" />
              </el-select>
              <el-button link type="primary" @click="resetFilters">重置</el-button>
            </div>
          </div>
        </template>

        <el-table v-loading="loading" :data="exceptions" border>
          <el-table-column label="类型" width="150">
            <template #default="{ row }">
              <el-tag size="small" type="warning">{{ typeLabel(row.exception_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" prop="description" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.description || '—' }}</template>
          </el-table-column>
          <el-table-column label="考号" width="110">
            <template #default="{ row }">{{ row.exam_number_ocr || '—' }}</template>
          </el-table-column>
          <el-table-column label="考生" width="110">
            <template #default="{ row }">{{ row.student_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="来源" width="80">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row.source === 'image' ? '图片' : 'PDF' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.snapshot_path" link type="primary" @click="viewSnapshot(row)">查看</el-button>
              <el-button
                v-if="row.page_id"
                link
                type="primary"
                @click="openPagePreview(row)"
              >定位答卷页</el-button>
              <el-button
                v-if="row.status === 'pending' && canResolve"
                link
                type="success"
                @click="openHandle(row, 'resolved')"
              >处理</el-button>
              <el-button
                v-if="row.status === 'pending' && canResolve"
                link
                type="info"
                @click="openHandle(row, 'ignored')"
              >忽略</el-button>
              <el-button
                v-if="row.status !== 'pending' && canResolve"
                link
                type="warning"
                @click="reopen(row)"
              >重新打开</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager">
          <el-pagination
            layout="total, prev, pager, next"
            :total="pagination.total"
            :page-size="pagination.pageSize"
            :current-page="pagination.page"
            @current-change="onPageChange"
          />
        </div>
      </el-card>
    </template>

    <!-- 处理弹窗 -->
    <el-dialog v-model="handleVisible" :title="handleTitle" width="480px">
      <el-form label-width="90px">
        <el-form-item label="处理动作">
          <el-select v-model="handleForm.action" placeholder="请选择" style="width: 100%">
            <el-option v-for="a in actionOptions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="处理备注">
          <el-input v-model="handleForm.note" type="textarea" :rows="3" placeholder="选填，记录处理说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleVisible = false">取消</el-button>
        <el-button type="primary" :loading="handling" @click="submitHandle">确认</el-button>
      </template>
    </el-dialog>

    <!-- 快照预览 -->
    <el-dialog v-model="snapshotVisible" title="异常快照" width="60%" top="6vh" @closed="clearSnapshot">
      <div v-loading="snapshotLoading" class="snapshot-wrap">
        <img v-if="snapshotUrl" :src="snapshotUrl" class="snapshot-img" />
        <el-empty v-else description="快照加载中或不存在" />
      </div>
    </el-dialog>

    <!-- 定位答卷页 -->
    <el-dialog v-model="pageVisible" title="答卷页题块" width="70%" top="6vh">
      <div v-loading="pageLoading">
        <p class="muted" v-if="currentException">
          考号：{{ currentException.exam_number_ocr || '—' }} ·
          考生：{{ currentException.student_name || '—' }}
        </p>
        <div class="block-grid">
          <div v-for="b in pageBlocks" :key="b.id" class="block-item">
            <img v-if="blockImages[b.id]" :src="blockImages[b.id]" />
            <div class="block-label">{{ blockLabel(b) }}</div>
          </div>
        </div>
        <el-empty v-if="!pageLoading && !pageBlocks.length" description="该页暂无题块图像" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getExams, type Exam } from '@/api/exams'
import { useAuthStore } from '@/stores/auth'
import {
  EXCEPTION_TYPE_LABELS,
  getExceptionSnapshotUrl,
  getBlockImageUrl,
  listExceptions,
  listPageBlocks,
  getExceptionSummary,
  updateException,
  type AnswerBlock,
  type ExamExceptionItem,
} from '@/api/imports'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exams = ref<Exam[]>([])
const examId = ref<string>('')
const loading = ref(false)
const exceptions = ref<ExamExceptionItem[]>([])
const summary = ref<{ total: number; by_status: Record<string, number>; by_type: Record<string, Record<string, number>> }>({
  total: 0,
  by_status: { pending: 0, resolved: 0, ignored: 0 },
  by_type: {},
})

const filters = ref<{ status?: string; exception_type?: string }>({ status: 'pending' })
const pagination = ref({ page: 1, pageSize: 20, total: 0 })

const handleVisible = ref(false)
const handling = ref(false)
const handleTarget = ref<ExamExceptionItem | null>(null)
const handleStatus = ref<'resolved' | 'ignored'>('resolved')
const handleForm = ref<{ action: string; note: string }>({ action: '', note: '' })

const snapshotVisible = ref(false)
const snapshotLoading = ref(false)
const snapshotUrl = ref('')

const pageVisible = ref(false)
const pageLoading = ref(false)
const currentException = ref<ExamExceptionItem | null>(null)
const pageBlocks = ref<AnswerBlock[]>([])
const blockImages = ref<Record<string, string>>({})

const canResolve = computed(() => {
  const role = auth.user?.role
  return ['super_admin', 'exam_admin', 'group_leader'].includes(role || '')
})

const typeStats = computed(() =>
  Object.entries(summary.value.by_type || {})
    .map(([type, cnt]) => ({
      type,
      pending: cnt.pending || 0,
      total: (cnt.pending || 0) + (cnt.resolved || 0) + (cnt.ignored || 0),
    }))
    .sort((a, b) => b.pending - a.pending || b.total - a.total),
)

const handleTitle = computed(() => (handleStatus.value === 'resolved' ? '处理异常' : '忽略异常'))
const actionOptions = computed(() =>
  handleStatus.value === 'resolved'
    ? [
        { label: '已手动指定考号', value: 'manual_exam_number' },
        { label: '已手动重框/重切', value: 'manual_recut' },
        { label: '已手动矫正', value: 'manual_perspective' },
        { label: '已人工复核', value: 'manual_review' },
        { label: '其他', value: 'other' },
      ]
    : [
        { label: '确认可忽略', value: 'ignore' },
        { label: '误报', value: 'false_positive' },
        { label: '其他', value: 'other' },
      ],
)

function typeLabel(t: string) {
  return EXCEPTION_TYPE_LABELS[t] || t
}
function statusText(s: string) {
  return { pending: '待处理', resolved: '已处理', ignored: '已忽略' }[s] || s
}
function statusType(s: string) {
  return ({ pending: 'warning', resolved: 'success', ignored: 'info' } as Record<string, any>)[s] || ''
}
function formatTime(t: string) {
  return t ? new Date(t).toLocaleString() : '—'
}
function blockLabel(b: AnswerBlock) {
  const t: Record<string, string> = { choice: '选择题', subjective: '非选择题', exam_number: '考号', name: '姓名' }
  return `${t[b.block_type] || b.block_type}${b.question_number ? ' ' + b.question_number : ''}`
}

async function loadExams() {
  const res = await getExams()
  exams.value = res.data
  const q = route.query.exam_id as string | undefined
  if (q && exams.value.some((e) => e.id === q)) {
    examId.value = q
  } else if (exams.value.length) {
    examId.value = exams.value[0].id
  }
  if (examId.value) await refreshAll()
}

function onExamChange() {
  pagination.value.page = 1
  router.replace({ query: { exam_id: examId.value } })
  refreshAll()
}

async function refreshAll() {
  if (!examId.value) return
  await Promise.all([loadSummary(), loadExceptions()])
}

async function loadSummary() {
  if (!examId.value) return
  const res = await getExceptionSummary(examId.value)
  summary.value = res.data
}

async function loadExceptions() {
  if (!examId.value) return
  loading.value = true
  try {
    const res = await listExceptions({
      exam_id: examId.value,
      status: filters.value.status || undefined,
      exception_type: filters.value.exception_type || undefined,
    })
    exceptions.value = res.data
    pagination.value.total = res.data.length
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.value = { status: 'pending' }
  pagination.value.page = 1
  loadExceptions()
}

function toggleType(type: string) {
  filters.value.exception_type = filters.value.exception_type === type ? undefined : type
  loadExceptions()
}

function onPageChange(page: number) {
  pagination.value.page = page
}

function openHandle(row: ExamExceptionItem, status: 'resolved' | 'ignored') {
  handleTarget.value = row
  handleStatus.value = status
  handleForm.value = { action: status === 'resolved' ? 'manual_exam_number' : 'ignore', note: '' }
  handleVisible.value = true
}

async function submitHandle() {
  if (!handleTarget.value) return
  handling.value = true
  try {
    await updateException(handleTarget.value.id, {
      status: handleStatus.value,
      resolution_action: handleForm.value.action || undefined,
      resolution_note: handleForm.value.note || undefined,
    })
    ElMessage.success(handleStatus.value === 'resolved' ? '异常已处理' : '异常已忽略')
    handleVisible.value = false
    await refreshAll()
  } catch {
    // 错误由拦截器提示
  } finally {
    handling.value = false
  }
}

async function reopen(row: ExamExceptionItem) {
  await updateException(row.id, { status: 'pending' })
  ElMessage.success('已重新打开')
  await refreshAll()
}

async function viewSnapshot(row: ExamExceptionItem) {
  snapshotVisible.value = true
  snapshotLoading.value = true
  snapshotUrl.value = ''
  try {
    snapshotUrl.value = await getExceptionSnapshotUrl(row.id)
  } catch {
    snapshotUrl.value = ''
  } finally {
    snapshotLoading.value = false
  }
}

function clearSnapshot() {
  if (snapshotUrl.value) URL.revokeObjectURL(snapshotUrl.value)
  snapshotUrl.value = ''
}

async function openPagePreview(row: ExamExceptionItem) {
  if (!row.page_id) return
  currentException.value = row
  pageVisible.value = true
  pageLoading.value = true
  pageBlocks.value = []
  blockImages.value = {}
  try {
    const res = await listPageBlocks(row.page_id)
    pageBlocks.value = res.data
    for (const b of pageBlocks.value) {
      if (b.image_path) {
        try {
          blockImages.value[b.id] = await getBlockImageUrl(b.id)
        } catch {
          // 忽略单个题块加载失败
        }
      }
    }
  } finally {
    pageLoading.value = false
  }
}

onMounted(loadExams)
</script>

<style scoped>
.exception-center {
  max-width: 1280px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-right {
  display: flex;
  gap: 8px;
}
.option-sub {
  float: right;
  color: #909399;
  font-size: 12px;
}
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-card .stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
}
.stat-card.pending .stat-value {
  color: #e6a23c;
}
.stat-card.resolved .stat-value {
  color: #67c23a;
}
.stat-card.ignored .stat-value {
  color: #909399;
}
.stat-label {
  margin-top: 4px;
  color: #909399;
  font-size: 13px;
}
.type-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.type-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #ebeef5;
  border-radius: 16px;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.type-chip:hover {
  border-color: #409eff;
}
.type-chip.active {
  border-color: #409eff;
  background-color: #ecf5ff;
}
.type-name {
  font-size: 13px;
  color: #606266;
}
.type-total {
  font-size: 12px;
  color: #909399;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
}
.pager {
  margin-top: 12px;
  text-align: right;
}
.muted {
  color: #909399;
  font-size: 13px;
}
.snapshot-wrap {
  display: flex;
  justify-content: center;
  min-height: 40vh;
}
.snapshot-img {
  max-width: 100%;
  max-height: 70vh;
}
.block-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 12px;
}
.block-item {
  border: 1px solid #ebeef5;
  padding: 4px;
  text-align: center;
}
.block-item img {
  max-width: 100%;
  max-height: 100px;
}
.block-label {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}
</style>