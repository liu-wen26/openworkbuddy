<template>
  <div>
    <div class="toolbar">
      <h2>阅卷进度监控</h2>
      <div class="toolbar-right">
        <el-tag :type="connected ? 'success' : 'info'" size="small" effect="plain">
          {{ connected ? '实时已连接' : '实时未连接' }}
        </el-tag>
        <el-select v-model="statusFilter" clearable placeholder="全部状态" style="width: 160px" @change="load">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summaries.length }}</div>
          <div class="stat-label">考试总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ avgCompletion }}</div>
          <div class="stat-label">平均阅卷完成度</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value warn">{{ totalArbitrating }}</div>
          <div class="stat-label">待仲裁</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value danger">{{ totalException }}</div>
          <div class="stat-label">待处理异常</div>
        </el-card>
      </el-col>
    </el-row>

    <el-table :data="summaries" v-loading="loading" border>
      <el-table-column prop="exam_name" label="考试名称" min-width="200" />
      <el-table-column prop="subject" label="学科" width="90" />
      <el-table-column prop="grade" label="年级" width="90" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="整体完成度" min-width="200">
        <template #default="{ row }">
          <el-progress :percentage="pctNum(row.overall_completion)" :stroke-width="14" :text-inside="true" />
        </template>
      </el-table-column>
      <el-table-column label="选择题" width="130">
        <template #default="{ row }">{{ row.choice_graded }}/{{ row.choice_total }}</template>
      </el-table-column>
      <el-table-column label="非选择题" width="130">
        <template #default="{ row }">{{ row.subjective_done }}/{{ row.subjective_total }}</template>
      </el-table-column>
      <el-table-column label="待仲裁" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.arbitrating" size="small" type="warning">{{ row.arbitrating }}</el-tag>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column label="待处理异常" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.exception_pending" size="small" type="danger">{{ row.exception_pending }}</el-tag>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row.exam_id)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="detailVisible" :title="detail?.exam_name || '阅卷进度详情'" width="720px">
      <div v-if="detail" class="detail-body">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="学科">{{ detail.subject }}</el-descriptions-item>
          <el-descriptions-item label="年级">{{ detail.grade }}</el-descriptions-item>
          <el-descriptions-item label="导入批次">{{ detail.imports.batch_count }}</el-descriptions-item>
          <el-descriptions-item label="答卷页数">{{ detail.imports.processed_pages }}/{{ detail.imports.page_count }}</el-descriptions-item>
        </el-descriptions>

        <div class="progress-block">
          <div class="block-title">选择题判分</div>
          <el-progress :percentage="pctNum(detail.choice.completion_rate)" :stroke-width="16" :text-inside="true" />
          <div class="block-meta">
            已判 {{ detail.choice.graded }}/{{ detail.choice.total }} · 异常 {{ detail.choice.exception }} ·
            正确率 {{ pct(detail.choice.correct_rate) }}
          </div>
        </div>

        <div class="progress-block">
          <div class="block-title">非选择题阅卷</div>
          <el-progress :percentage="pctNum(detail.subjective.completion_rate)" :stroke-width="16" :text-inside="true" color="#67c23a" />
          <div class="block-meta">
            已完成 {{ detail.subjective.done }}/{{ detail.subjective.total }} · 待仲裁 {{ detail.subjective.arbitrating }}
          </div>
          <div class="status-chips">
            <el-tag v-for="(count, status) in detail.subjective.by_status" :key="status" size="small" type="info">
              {{ subjectiveStatusText(status) }}：{{ count }}
            </el-tag>
          </div>
        </div>

        <div class="progress-block">
          <div class="block-title">异常处理</div>
          <el-progress :percentage="pctNum(detail.exception.completion_rate)" :stroke-width="16" :text-inside="true" color="#e6a23c" />
          <div class="block-meta">
            已处理 {{ detail.exception.resolved }}/{{ detail.exception.total }} · 待处理 {{ detail.exception.pending }}
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { listMonitorExams, getMonitorExam, type ExamProgressSummary, type ExamProgressDetail } from '@/api/system'
import { useRealtime } from '@/composables/useRealtime'

const { connected, subscribe, unsubscribe, on } = useRealtime()

const summaries = ref<ExamProgressSummary[]>([])
const loading = ref(false)
const statusFilter = ref('')
const detailVisible = ref(false)
const detail = ref<ExamProgressDetail | null>(null)

const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'ready', label: '就绪' },
  { value: 'importing', label: '导入中' },
  { value: 'grading', label: '阅卷中' },
  { value: 'locked', label: '已锁定' },
  { value: 'archived', label: '已归档' },
]

const avgCompletion = computed(() => {
  if (!summaries.value.length) return '0%'
  const avg = summaries.value.reduce((s, e) => s + e.overall_completion, 0) / summaries.value.length
  return `${Math.round(avg * 100)}%`
})
const totalArbitrating = computed(() => summaries.value.reduce((s, e) => s + e.arbitrating, 0))
const totalException = computed(() => summaries.value.reduce((s, e) => s + e.exception_pending, 0))

function pctNum(v: number) {
  return Math.round((v || 0) * 100)
}
function pct(v: number) {
  return `${Math.round((v || 0) * 100)}%`
}

function statusText(status: string) {
  return statusOptions.find((s) => s.value === status)?.label || status
}
function statusType(status: string) {
  const map: Record<string, string> = {
    draft: 'info', ready: 'primary', importing: 'warning', grading: 'success', locked: 'danger', archived: '',
  }
  return map[status] || ''
}
function subjectiveStatusText(status: string) {
  const map: Record<string, string> = {
    pending: '待阅', ai_scored: 'AI已评', graded: '已阅', graded_pending_second: '待二评',
    arbitrating: '仲裁中', arbitrated: '已仲裁',
  }
  return map[status] || status
}

async function load() {
  loading.value = true
  try {
    const res = await listMonitorExams(statusFilter.value || undefined)
    summaries.value = res.data
  } finally {
    loading.value = false
  }
}

async function openDetail(examId: string) {
  const res = await getMonitorExam(examId)
  detail.value = res.data
  detailVisible.value = true
}

const stops: Array<() => void> = []
let refreshTimer: ReturnType<typeof setTimeout> | null = null

/** 实时事件到达时合并刷新，避免频繁请求。 */
function scheduleReload() {
  if (refreshTimer) return
  refreshTimer = setTimeout(async () => {
    refreshTimer = null
    await load()
    if (detailVisible.value && detail.value) {
      try {
        const res = await getMonitorExam(detail.value.exam_id)
        detail.value = res.data
      } catch {
        // 详情刷新失败时静默
      }
    }
  }, 800)
}

onMounted(() => {
  subscribe('exams')
  ;['import_progress', 'choice_graded', 'grading_progress'].forEach((type) => {
    stops.push(on(type, scheduleReload))
  })
  load()
})

onUnmounted(() => {
  stops.forEach((stop) => stop())
  if (refreshTimer) clearTimeout(refreshTimer)
  unsubscribe('exams')
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-right {
  display: flex;
  gap: 12px;
}
.stat-row {
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: 26px;
  font-weight: 600;
  color: #409eff;
}
.stat-value.warn {
  color: #e6a23c;
}
.stat-value.danger {
  color: #f56c6c;
}
.stat-label {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
.detail-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.progress-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.block-title {
  font-weight: 600;
  color: #303133;
}
.block-meta {
  color: #909399;
  font-size: 13px;
}
.status-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>