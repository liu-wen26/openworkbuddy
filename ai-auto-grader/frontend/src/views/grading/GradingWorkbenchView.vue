<template>
  <div class="grading-center">
    <div class="toolbar">
      <h2>非选择题阅卷</h2>
      <div class="toolbar-right">
        <el-select
          v-model="examId"
          placeholder="请选择考试"
          filterable
          style="width: 300px"
          @change="onExamChange"
        >
          <el-option v-for="e in exams" :key="e.id" :label="e.name" :value="e.id">
            <span>{{ e.name }}</span>
            <span class="option-sub">{{ e.subject }} · {{ e.grade }}</span>
          </el-option>
        </el-select>
        <el-button v-if="canDistribute" :disabled="!examId" @click="openDistribute">任务分发</el-button>
        <el-button v-if="canAI" type="success" :disabled="!examId" :loading="aiRunning" @click="runAI">
          AI 预评
        </el-button>
        <el-button :disabled="!examId" :loading="loading" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="!examId" type="info" :closable="false" show-icon title="请选择考试后进入阅卷工作台。" />

    <template v-else>
      <div class="stat-row">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ progress.total }}</div>
          <div class="stat-label">任务总数</div>
        </el-card>
        <el-card shadow="never" class="stat-card pending">
          <div class="stat-value">{{ progress.by_status.pending || 0 }}</div>
          <div class="stat-label">待评分</div>
        </el-card>
        <el-card shadow="never" class="stat-card ai">
          <div class="stat-value">{{ progress.by_status.ai_scored || 0 }}</div>
          <div class="stat-label">AI 已评</div>
        </el-card>
        <el-card shadow="never" class="stat-card done">
          <div class="stat-value">{{ progress.done }}</div>
          <div class="stat-label">已完成</div>
        </el-card>
        <el-card shadow="never" class="stat-card arb">
          <div class="stat-value">{{ progress.by_status.arbitrating || 0 }}</div>
          <div class="stat-label">待仲裁</div>
        </el-card>
      </div>

      <el-tabs v-model="activeTab" class="tabs">
        <el-tab-pane label="阅卷工作台" name="workbench">
          <div class="workbench">
            <el-card shadow="never" class="queue">
              <div class="queue-filters">
                <el-select v-model="filterQuestion" placeholder="全部题号" clearable size="small" @change="loadTasks">
                  <el-option
                    v-for="q in questionOptions"
                    :key="q"
                    :label="`第 ${q} 题`"
                    :value="q"
                  />
                </el-select>
                <el-select v-model="filterStatus" placeholder="全部状态" clearable size="small" @change="loadTasks">
                  <el-option v-for="(label, key) in GRADING_STATUS_LABELS" :key="key" :label="label" :value="key" />
                </el-select>
                <el-checkbox v-model="onlyMine" size="small" @change="loadTasks">仅我的任务</el-checkbox>
              </div>
              <div v-loading="tasksLoading" class="queue-list">
                <div
                  v-for="task in tasks"
                  :key="task.id"
                  class="queue-item"
                  :class="{ active: current && current.id === task.id }"
                  @click="selectTask(task)"
                >
                  <div class="queue-main">
                    <span class="q-no">第 {{ task.question_number || '-' }} 题</span>
                    <el-tag :type="GRADING_STATUS_TYPES[task.status]" size="small">{{ statusLabel(task.status) }}</el-tag>
                  </div>
                  <div class="queue-sub">
                    {{ task.student_name || '未知考生' }} · {{ task.exam_number || '未识别考号' }}
                  </div>
                  <div class="queue-score">
                    <span v-if="task.final_score != null" class="final">终评 {{ task.final_score }}</span>
                    <span v-else-if="task.ai_score != null" class="ai">AI {{ task.ai_score }}</span>
                    <span class="max">/ {{ task.max_score }}</span>
                  </div>
                </div>
                <el-empty v-if="!tasksLoading && !tasks.length" description="暂无待处理任务" :image-size="80" />
              </div>
            </el-card>

            <el-card shadow="never" class="panel">
              <template v-if="current">
                <div class="panel-header">
                  <div class="panel-title">第 {{ current.question_number || '-' }} 题</div>
                  <div class="panel-tags">
                    <el-tag size="small" type="info">{{ GRADING_MODE_LABELS[current.grading_mode] }}</el-tag>
                    <el-tag size="small" :type="GRADING_STATUS_TYPES[current.status]">{{ statusLabel(current.status) }}</el-tag>
                    <el-button size="small" @click="openPagePreview">整卷预览</el-button>
                  </div>
                </div>
                <div class="panel-meta">
                  <span>考生：{{ current.student_name || '—' }}</span>
                  <span>考号：{{ current.exam_number || '—' }}</span>
                  <span>班级：{{ current.class_name || '—' }}</span>
                  <span>满分：{{ current.max_score }}</span>
                </div>

                <div class="panel-body">
                  <div class="image-col">
                    <div class="zoom-bar">
                      <el-button-group size="small">
                        <el-button :disabled="blockZoom <= 0.5" @click="zoomBlock(-0.25)">缩小</el-button>
                        <el-button :disabled="blockZoom >= 4" @click="zoomBlock(0.25)">放大</el-button>
                        <el-button @click="blockZoom = 1">重置</el-button>
                      </el-button-group>
                      <span class="zoom-value">{{ Math.round(blockZoom * 100) }}%</span>
                    </div>
                    <div class="image-wrap" v-loading="imageLoading" @wheel.ctrl.prevent="onBlockWheel">
                      <img
                        v-if="imageUrl"
                        :src="imageUrl"
                        class="block-img"
                        :style="{ transform: `scale(${blockZoom})` }"
                      />
                      <el-empty v-else :image-size="70" description="题块图像不存在" />
                    </div>
                  </div>

                  <div class="form-col">
                    <div class="ai-card" :class="{ 'ai-card--low': isLowConfidence }">
                      <div class="ai-head">
                        <span>AI 预评</span>
                        <el-tag v-if="current.ai_score != null" size="small" type="success">
                          {{ current.ai_score }} / {{ current.max_score }}
                        </el-tag>
                        <el-tag v-else size="small" type="info">未预评</el-tag>
                      </div>
                      <div v-if="current.ai_score != null" class="ai-body">
                        <div class="ai-line">
                          <span class="ai-label">置信度</span>
                          <el-progress
                            :percentage="Math.round((current.ai_confidence || 0) * 100)"
                            :stroke-width="10"
                            :status="isLowConfidence ? 'exception' : 'success'"
                          />
                        </div>
                        <div class="ai-line"><span class="ai-label">批注</span>{{ current.ai_comment || '—' }}</div>
                        <div class="ai-line muted">
                          <span class="ai-label">模型</span>{{ current.ai_provider || '—' }} / {{ current.ai_model || '—' }}
                        </div>
                      </div>
                      <div v-else class="ai-empty">尚未执行 AI 预评，可人工直接评分。</div>
                    </div>

                    <div v-if="hasHumanScore" class="human-card">
                      <div v-if="current.first_score != null">
                        一评：<strong>{{ current.first_score }}</strong>
                        <span v-if="current.first_comment" class="muted"> · {{ current.first_comment }}</span>
                      </div>
                      <div v-if="current.second_score != null">
                        二评：<strong>{{ current.second_score }}</strong>
                        <span v-if="current.second_comment" class="muted"> · {{ current.second_comment }}</span>
                      </div>
                      <div v-if="current.final_score != null">
                        终评：<strong>{{ current.final_score }}</strong>
                        <span v-if="current.arbitration_note" class="muted"> · {{ current.arbitration_note }}</span>
                      </div>
                    </div>

                    <div class="grade-form">
                      <div class="grade-row">
                        <span class="label">评分</span>
                        <el-input-number
                          v-model="scoreInput"
                          :min="0"
                          :max="current.max_score"
                          :step="0.5"
                          :precision="1"
                          :disabled="!canGrade"
                        />
                        <el-button-group class="quick">
                          <el-button size="small" :disabled="!canGrade" @click="quickScore(0)">0</el-button>
                          <el-button size="small" :disabled="!canGrade" @click="quickScore(current.max_score / 2)">
                            半分
                          </el-button>
                          <el-button size="small" :disabled="!canGrade" @click="quickScore(current.max_score)">
                            满分
                          </el-button>
                        </el-button-group>
                        <el-button
                          v-if="current.ai_score != null"
                          size="small"
                          :disabled="!canGrade"
                          @click="quickScore(current.ai_score)"
                        >
                          采纳 AI
                        </el-button>
                      </div>
                      <div class="grade-row">
                        <span class="label">批注</span>
                        <el-input
                          v-model="commentInput"
                          type="textarea"
                          :rows="2"
                          :disabled="!canGrade"
                          placeholder="评分说明 / 扣分要点（选填）"
                        />
                      </div>
                      <div class="grade-row">
                        <span class="label">标记</span>
                        <el-select v-model="markInput" :disabled="!canGrade" style="width: 160px">
                          <el-option
                            v-for="(label, key) in ANSWER_MARK_LABELS"
                            :key="key"
                            :label="label"
                            :value="key"
                          />
                        </el-select>
                        <el-button
                          type="primary"
                          class="submit"
                          :disabled="!canGrade || scoreInput === undefined"
                          :loading="submitting"
                          @click="submitGrade(false)"
                        >
                          提交评分
                        </el-button>
                        <el-button
                          :disabled="!canGrade || scoreInput === undefined"
                          :loading="submitting"
                          @click="submitGrade(true)"
                        >
                          提交并下一题
                        </el-button>
                      </div>
                      <div class="shortcut-hint">
                        快捷键：<kbd>Enter</kbd> 提交评分 · <kbd>Shift</kbd>+<kbd>Enter</kbd> 提交并下一题 ·
                        <kbd>↑</kbd>/<kbd>↓</kbd> 加减 0.5 分 · <kbd>F</kbd> 满分 · <kbd>H</kbd> 半分 ·
                        <kbd>0</kbd> 零分 · <kbd>A</kbd> 采纳 AI
                      </div>
                      <el-alert
                        v-if="!canGrade"
                        type="warning"
                        :closable="false"
                        show-icon
                        title="当前账号没有评分权限，仅可查看。"
                      />
                    </div>
                  </div>
                </div>
              </template>
              <el-empty v-else description="请从左侧选择一份阅卷任务" />
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="`仲裁中心（${arbitrationRows.length}）`" name="arbitration">
          <el-card shadow="never">
            <el-table v-loading="loading" :data="arbitrationRows" border>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="考号" width="120">
                <template #default="{ row }">{{ row.exam_number || '—' }}</template>
              </el-table-column>
              <el-table-column label="考生" width="110">
                <template #default="{ row }">{{ row.student_name || '—' }}</template>
              </el-table-column>
              <el-table-column label="满分" width="80" prop="max_score" />
              <el-table-column label="一评" width="80">
                <template #default="{ row }">{{ row.first_score ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="二评" width="80">
                <template #default="{ row }">{{ row.second_score ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="分差" width="80">
                <template #default="{ row }">{{ scoreDiff(row) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button v-if="canArbitrate" link type="primary" @click="openArbitration(row)">仲裁</el-button>
                  <span v-else class="muted">无权限</span>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!loading && !arbitrationRows.length" description="暂无待仲裁任务" />
          </el-card>
        </el-tab-pane>

        <el-tab-pane label="进度看板" name="progress">
          <el-card shadow="never" class="progress-card">
            <div class="progress-head">
              <el-progress
                type="dashboard"
                :percentage="Math.round(progress.completion_rate * 100)"
                :width="140"
              />
              <div class="progress-status">
                <div v-for="(label, key) in GRADING_STATUS_LABELS" :key="key" class="status-line">
                  <el-tag size="small" :type="GRADING_STATUS_TYPES[key]">{{ label }}</el-tag>
                  <span class="status-count">{{ progress.by_status[key] || 0 }}</span>
                </div>
              </div>
            </div>
            <el-table :data="progress.by_question" border style="margin-top: 16px">
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column prop="max_score" label="满分" width="80" />
              <el-table-column label="已评 / 总数" width="120">
                <template #default="{ row }">{{ row.graded }} / {{ row.total }}</template>
              </el-table-column>
              <el-table-column label="待仲裁" width="90" prop="arbitrating" />
              <el-table-column label="完成度" min-width="220">
                <template #default="{ row }">
                  <el-progress :percentage="Math.round((row.graded / (row.total || 1)) * 100)" :stroke-width="12" />
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!progress.by_question.length" description="暂无进度数据" />
          </el-card>
        </el-tab-pane>

        <el-tab-pane label="阅卷痕迹" name="logs">
          <el-card shadow="never">
            <el-table v-loading="loading" :data="logs" border>
              <el-table-column label="时间" width="180">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="动作" width="120">
                <template #default="{ row }">
                  <el-tag size="small">{{ actionLabel(row.action) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作人" width="130">
                <template #default="{ row }">{{ row.operator_name || '系统' }}</template>
              </el-table-column>
              <el-table-column label="分数变化" width="130">
                <template #default="{ row }">
                  <span v-if="row.score_before != null || row.score_after != null">
                    {{ row.score_before ?? '—' }} → {{ row.score_after ?? '—' }}
                  </span>
                  <span v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column label="说明" min-width="260" prop="note" />
            </el-table>
            <el-empty v-if="!loading && !logs.length" description="暂无阅卷痕迹" />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 任务分发 -->
    <el-dialog v-model="distributeVisible" title="阅卷任务分发" width="480px">
      <el-form label-width="90px">
        <el-form-item label="阅卷模式">
          <el-radio-group v-model="distributeForm.mode">
            <el-radio-button value="manual">人工阅卷</el-radio-button>
            <el-radio-button value="ai_assist">AI 辅助</el-radio-button>
            <el-radio-button value="double">双评模式</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="题号范围">
          <el-select
            v-model="distributeForm.question_numbers"
            multiple
            clearable
            placeholder="不选则全部题号"
            style="width: 100%"
          >
            <el-option v-for="q in questionOptions" :key="q" :label="`第 ${q} 题`" :value="q" />
          </el-select>
        </el-form-item>
        <el-form-item label="指定阅卷人">
          <el-select v-model="distributeForm.assign_to" clearable filterable placeholder="不选则不指定" style="width: 100%">
            <el-option
              v-for="u in users"
              :key="u.id"
              :label="`${u.real_name || u.username}（${roleLabel(u.role)}）`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="distributeVisible = false">取消</el-button>
        <el-button type="primary" :loading="distributing" @click="submitDistribute">确认分发</el-button>
      </template>
    </el-dialog>

    <!-- 整卷预览 -->
    <el-dialog v-model="pagePreviewVisible" title="整卷预览" width="720px" @closed="clearPageImage">
      <div class="zoom-bar">
        <el-button-group size="small">
          <el-button :disabled="pageZoom <= 0.5" @click="zoomPage(-0.25)">缩小</el-button>
          <el-button :disabled="pageZoom >= 4" @click="zoomPage(0.25)">放大</el-button>
          <el-button @click="pageZoom = 1">重置</el-button>
        </el-button-group>
        <span class="zoom-value">{{ Math.round(pageZoom * 100) }}%</span>
      </div>
      <div v-loading="pageImageLoading" class="page-preview-wrap" @wheel.ctrl.prevent="onPageWheel">
        <img
          v-if="pageImageUrl"
          :src="pageImageUrl"
          class="page-img"
          :style="{ transform: `scale(${pageZoom})` }"
        />
        <el-empty v-else :image-size="70" description="整卷图像不存在或尚未预处理" />
      </div>
    </el-dialog>

    <!-- 仲裁 -->
    <el-dialog v-model="arbitrationVisible" title="仲裁终评" width="520px">
      <div v-if="arbitrationTarget" class="arb-body">
        <div class="panel-meta">
          <span>第 {{ arbitrationTarget.question_number || '-' }} 题</span>
          <span>考生：{{ arbitrationTarget.student_name || '—' }}</span>
          <span>满分：{{ arbitrationTarget.max_score }}</span>
        </div>
        <div class="arb-scores">
          <div>一评：<strong>{{ arbitrationTarget.first_score ?? '—' }}</strong></div>
          <div>二评：<strong>{{ arbitrationTarget.second_score ?? '—' }}</strong></div>
          <div>分差：<strong>{{ scoreDiff(arbitrationTarget) }}</strong></div>
        </div>
        <div class="image-wrap small">
          <img v-if="imageUrl" :src="imageUrl" class="block-img" />
          <el-empty v-else :image-size="60" description="题块图像不存在" />
        </div>
        <el-form label-width="80px" style="margin-top: 12px">
          <el-form-item label="终评分数">
            <el-input-number
              v-model="finalScoreInput"
              :min="0"
              :max="arbitrationTarget.max_score"
              :step="0.5"
              :precision="1"
            />
          </el-form-item>
          <el-form-item label="仲裁说明">
            <el-input v-model="arbitrationNote" type="textarea" :rows="2" placeholder="仲裁理由（选填）" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="arbitrationVisible = false">取消</el-button>
        <el-button type="primary" :loading="arbitrating" @click="submitArbitration">提交终评</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getExams, type Exam } from '@/api/exams'
import { getBlockImageUrl, getPageImageUrl } from '@/api/imports'
import { listUsers, type User } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import {
  ANSWER_MARK_LABELS,
  GRADING_ACTION_LABELS,
  GRADING_MODE_LABELS,
  GRADING_STATUS_LABELS,
  GRADING_STATUS_TYPES,
  arbitrateTask,
  distributeGrading,
  getGradingProgress,
  gradeTask,
  listArbitration,
  listGradingLogs,
  listGradingTasks,
  runAIGrading,
  type AnswerMark,
  type GradingLog,
  type GradingMode,
  type GradingProgress,
  type GradingStatus,
  type GradingTask,
} from '@/api/grading'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exams = ref<Exam[]>([])
const users = ref<User[]>([])
const examId = ref('')
const loading = ref(false)
const activeTab = ref('workbench')

const progress = ref<GradingProgress>({
  total: 0,
  done: 0,
  completion_rate: 0,
  by_status: {},
  by_question: [],
})

const tasks = ref<GradingTask[]>([])
const tasksLoading = ref(false)
const filterQuestion = ref<string>('')
const filterStatus = ref<GradingStatus | ''>('')
const onlyMine = ref(false)

const current = ref<GradingTask | null>(null)
const imageUrl = ref('')
const imageLoading = ref(false)
const blockZoom = ref(1)

const pagePreviewVisible = ref(false)
const pageImageUrl = ref('')
const pageImageLoading = ref(false)
const pageZoom = ref(1)

const scoreInput = ref<number>()
const commentInput = ref('')
const markInput = ref<AnswerMark>('none')
const submitting = ref(false)

const arbitrationRows = ref<GradingTask[]>([])
const logs = ref<GradingLog[]>([])

const aiRunning = ref(false)
const distributeVisible = ref(false)
const distributing = ref(false)
const distributeForm = ref<{ mode: GradingMode; question_numbers: string[]; assign_to?: string }>({
  mode: 'manual',
  question_numbers: [],
  assign_to: undefined,
})

const arbitrationVisible = ref(false)
const arbitrating = ref(false)
const arbitrationTarget = ref<GradingTask | null>(null)
const finalScoreInput = ref<number>()
const arbitrationNote = ref('')

const role = auth.user?.role || ''
const canGrade = computed(() => ['super_admin', 'exam_admin', 'group_leader', 'teacher'].includes(role))
const canDistribute = computed(() => ['super_admin', 'exam_admin', 'group_leader'].includes(role))
const canArbitrate = computed(() => ['super_admin', 'exam_admin', 'group_leader'].includes(role))
const canAI = computed(() => ['super_admin', 'exam_admin', 'group_leader'].includes(role))

const questionOptions = computed(() => progress.value.by_question.map((q) => q.question_number))
const isLowConfidence = computed(() => {
  if (!current.value || current.value.ai_confidence == null) return false
  return current.value.ai_confidence < 0.6
})
const hasHumanScore = computed(() => {
  const c = current.value
  return !!c && (c.first_score != null || c.second_score != null || c.final_score != null)
})

function statusLabel(s: string) {
  return GRADING_STATUS_LABELS[s] || s
}
function actionLabel(a: string) {
  return GRADING_ACTION_LABELS[a] || a
}
function roleLabel(r: string) {
  return { super_admin: '管理员', exam_admin: '教务', group_leader: '组长', teacher: '教师' }[r] || r
}
function formatTime(t: string) {
  return t ? t.replace('T', ' ').slice(0, 19) : '—'
}
function scoreDiff(row: GradingTask) {
  if (row.first_score == null || row.second_score == null) return '—'
  return Math.abs(row.first_score - row.second_score).toFixed(1)
}

async function loadExams() {
  const res = await getExams()
  exams.value = res.data
  const q = route.query.exam_id as string | undefined
  if (q && exams.value.some((e) => e.id === q)) examId.value = q
  else if (exams.value.length) examId.value = exams.value[0].id
  if (examId.value) await refreshAll()
}

function onExamChange() {
  filterQuestion.value = ''
  filterStatus.value = ''
  onlyMine.value = false
  current.value = null
  clearImage()
  router.replace({ query: { exam_id: examId.value } })
  refreshAll()
}

async function refreshAll() {
  if (!examId.value) return
  loading.value = true
  try {
    await loadProgress()
    await Promise.all([loadTasks(), loadArbitration(), loadLogs()])
  } finally {
    loading.value = false
  }
}

async function loadProgress() {
  if (!examId.value) return
  const res = await getGradingProgress(examId.value)
  progress.value = res.data
}

async function loadTasks() {
  if (!examId.value) return
  tasksLoading.value = true
  try {
    const res = await listGradingTasks({
      exam_id: examId.value,
      status: (filterStatus.value || undefined) as GradingStatus | undefined,
      question_number: filterQuestion.value || undefined,
      mine: onlyMine.value || undefined,
    })
    tasks.value = res.data
  } finally {
    tasksLoading.value = false
  }
}

async function loadArbitration() {
  if (!examId.value) return
  const res = await listArbitration(examId.value)
  arbitrationRows.value = res.data
}

async function loadLogs() {
  if (!examId.value) return
  const res = await listGradingLogs(examId.value)
  logs.value = res.data
}

async function selectTask(task: GradingTask) {
  current.value = task
  scoreInput.value = task.ai_score ?? undefined
  commentInput.value = ''
  markInput.value = task.mark || 'none'
  blockZoom.value = 1
  await loadImage(task.block_id)
}

async function loadImage(blockId: string) {
  clearImage()
  imageLoading.value = true
  try {
    imageUrl.value = await getBlockImageUrl(blockId)
  } catch {
    imageUrl.value = ''
  } finally {
    imageLoading.value = false
  }
}

function clearImage() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
}

function clampZoom(v: number) {
  return Math.min(4, Math.max(0.5, Math.round(v * 100) / 100))
}

function zoomBlock(delta: number) {
  blockZoom.value = clampZoom(blockZoom.value + delta)
}

function onBlockWheel(e: WheelEvent) {
  zoomBlock(e.deltaY < 0 ? 0.1 : -0.1)
}

function zoomPage(delta: number) {
  pageZoom.value = clampZoom(pageZoom.value + delta)
}

function onPageWheel(e: WheelEvent) {
  zoomPage(e.deltaY < 0 ? 0.1 : -0.1)
}

async function openPagePreview() {
  if (!current.value) return
  pagePreviewVisible.value = true
  pageZoom.value = 1
  if (pageImageUrl.value) return
  pageImageLoading.value = true
  try {
    pageImageUrl.value = await getPageImageUrl(current.value.page_id)
  } catch {
    pageImageUrl.value = ''
  } finally {
    pageImageLoading.value = false
  }
}

function clearPageImage() {
  if (pageImageUrl.value) URL.revokeObjectURL(pageImageUrl.value)
  pageImageUrl.value = ''
}

function quickScore(v: number) {
  scoreInput.value = Math.round(v * 10) / 10
}

function adjustScore(delta: number) {
  if (!current.value) return
  const base = scoreInput.value ?? 0
  scoreInput.value = Math.min(current.value.max_score, Math.max(0, Math.round((base + delta) * 10) / 10))
}

function onKeydown(e: KeyboardEvent) {
  if (activeTab.value !== 'workbench') return
  const target = e.target as HTMLElement | null
  const tag = target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return
  if (!current.value || !canGrade.value) return

  if (e.key === 'Enter') {
    if (submitting.value) return
    e.preventDefault()
    submitGrade(e.shiftKey)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    adjustScore(0.5)
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    adjustScore(-0.5)
  } else if (e.key === '0') {
    quickScore(0)
  } else if (e.key === 'f' || e.key === 'F') {
    quickScore(current.value.max_score)
  } else if (e.key === 'h' || e.key === 'H') {
    quickScore(current.value.max_score / 2)
  } else if (e.key === 'a' || e.key === 'A') {
    if (current.value.ai_score != null) quickScore(current.value.ai_score)
  }
}

async function submitGrade(next: boolean) {
  if (!current.value || scoreInput.value === undefined) return
  submitting.value = true
  const gradedId = current.value.id
  try {
    await gradeTask(gradedId, {
      score: scoreInput.value,
      comment: commentInput.value || undefined,
      mark: markInput.value,
    })
    ElMessage.success('评分已提交')
    await Promise.all([loadProgress(), loadTasks(), loadArbitration(), loadLogs()])
    if (next) {
      const idx = tasks.value.findIndex((t) => t.id === gradedId)
      const remaining = tasks.value.filter((t) => t.id !== gradedId)
      const candidate = remaining[Math.min(idx, remaining.length - 1)]
      if (candidate) await selectTask(candidate)
      else {
        current.value = null
        clearImage()
      }
    } else {
      const refreshed = tasks.value.find((t) => t.id === gradedId)
      if (refreshed) current.value = refreshed
      else current.value = null
    }
  } catch {
    // 错误由拦截器提示
  } finally {
    submitting.value = false
  }
}

async function runAI() {
  if (!examId.value) return
  aiRunning.value = true
  try {
    const res = await runAIGrading(examId.value)
    ElMessage.success(
      `AI 预评完成：已评 ${res.data.scored} 题，低置信度 ${res.data.low_confidence} 题（模型 ${res.data.provider}）`,
    )
    await Promise.all([loadProgress(), loadTasks(), loadLogs()])
  } catch {
    // 错误由拦截器提示
  } finally {
    aiRunning.value = false
  }
}

async function openDistribute() {
  distributeVisible.value = true
  if (users.value.length) return
  try {
    const res = await listUsers()
    users.value = res.data
  } catch {
    users.value = []
  }
}

async function submitDistribute() {
  if (!examId.value) return
  distributing.value = true
  try {
    const res = await distributeGrading(examId.value, {
      mode: distributeForm.value.mode,
      assign_to: distributeForm.value.assign_to || undefined,
      question_numbers: distributeForm.value.question_numbers.length
        ? distributeForm.value.question_numbers
        : undefined,
    })
    ElMessage.success(`已按「${GRADING_MODE_LABELS[res.data.mode]}」分发 ${res.data.assigned} 个任务`)
    distributeVisible.value = false
    await refreshAll()
  } catch {
    // 错误由拦截器提示
  } finally {
    distributing.value = false
  }
}

async function openArbitration(row: GradingTask) {
  arbitrationTarget.value = row
  finalScoreInput.value = row.second_score ?? row.first_score ?? undefined
  arbitrationNote.value = ''
  arbitrationVisible.value = true
  await loadImage(row.block_id)
}

async function submitArbitration() {
  if (!arbitrationTarget.value || finalScoreInput.value === undefined) return
  arbitrating.value = true
  try {
    await arbitrateTask(arbitrationTarget.value.id, {
      final_score: finalScoreInput.value,
      note: arbitrationNote.value || undefined,
    })
    ElMessage.success('仲裁终评已提交')
    arbitrationVisible.value = false
    await Promise.all([loadProgress(), loadTasks(), loadArbitration(), loadLogs()])
  } catch {
    // 错误由拦截器提示
  } finally {
    arbitrating.value = false
  }
}

onMounted(() => {
  loadExams()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  clearImage()
  clearPageImage()
})
</script>

<style scoped>
.grading-center {
  max-width: 1440px;
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
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-card .stat-value {
  font-size: 26px;
  font-weight: 600;
  color: #303133;
}
.stat-card.pending .stat-value {
  color: #e6a23c;
}
.stat-card.ai .stat-value {
  color: #409eff;
}
.stat-card.done .stat-value {
  color: #67c23a;
}
.stat-card.arb .stat-value {
  color: #f56c6c;
}
.stat-label {
  margin-top: 4px;
  color: #909399;
  font-size: 13px;
}
.workbench {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  align-items: start;
}
.queue-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.queue-filters :deep(.el-select) {
  width: 120px;
}
.queue-list {
  max-height: 620px;
  overflow-y: auto;
}
.queue-item {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.queue-item:hover {
  border-color: #c6e2ff;
  background: #f5faff;
}
.queue-item.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.queue-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.q-no {
  font-weight: 600;
  color: #303133;
}
.queue-sub {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}
.queue-score {
  margin-top: 4px;
  font-size: 12px;
}
.queue-score .final {
  color: #67c23a;
  font-weight: 600;
}
.queue-score .ai {
  color: #409eff;
}
.queue-score .max {
  color: #c0c4cc;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-title {
  font-size: 16px;
  font-weight: 600;
}
.panel-tags {
  display: flex;
  gap: 6px;
}
.panel-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin: 10px 0;
  color: #606266;
  font-size: 13px;
}
.panel-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.zoom-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.zoom-value {
  color: #909399;
  font-size: 12px;
}
.image-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  padding: 8px;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  background: #fafafa;
  overflow: auto;
  max-height: 560px;
}
.image-wrap.small {
  min-height: 120px;
}
.block-img {
  max-width: 100%;
  max-height: 520px;
  transform-origin: center center;
}
.page-preview-wrap {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  min-height: 200px;
  max-height: 70vh;
  padding: 8px;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  background: #fafafa;
  overflow: auto;
}
.page-img {
  max-width: 100%;
  transform-origin: top center;
}
.shortcut-hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.8;
}
.shortcut-hint kbd {
  display: inline-block;
  padding: 0 5px;
  border: 1px solid #dcdfe6;
  border-bottom-width: 2px;
  border-radius: 3px;
  background: #f5f7fa;
  font-family: inherit;
  font-size: 11px;
  color: #606266;
}
.ai-card {
  border: 1px solid #b3e19d;
  background: #f0f9eb;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}
.ai-card--low {
  border-color: #f3d19e;
  background: #fdf6ec;
}
.ai-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.ai-body .ai-line {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
  align-items: center;
}
.ai-line .ai-label {
  color: #909399;
  flex-shrink: 0;
}
.ai-line.muted {
  color: #909399;
}
.ai-empty {
  color: #909399;
  font-size: 13px;
}
.human-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.muted {
  color: #909399;
}
.grade-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.grade-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.grade-row .label {
  width: 42px;
  color: #606266;
  font-size: 13px;
  flex-shrink: 0;
}
.grade-row :deep(.el-textarea) {
  flex: 1;
}
.grade-row .submit {
  margin-left: auto;
}
.progress-head {
  display: flex;
  align-items: center;
  gap: 40px;
}
.progress-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
}
.status-count {
  font-weight: 600;
  color: #303133;
}
.arb-scores {
  display: flex;
  gap: 24px;
  margin: 10px 0;
  color: #606266;
}
</style>