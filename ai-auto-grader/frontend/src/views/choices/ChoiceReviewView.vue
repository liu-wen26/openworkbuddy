<template>
  <div class="choice-center">
    <div class="toolbar">
      <h2>选择题判分</h2>
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
        <el-button v-if="canGrade" type="primary" :disabled="!examId" :loading="grading" @click="runGrade">
          重新判分
        </el-button>
        <el-button :disabled="!examId" :loading="loading" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="!examId" type="info" :closable="false" show-icon title="请选择考试后查看选择题判分结果。" />

    <template v-else>
      <div class="stat-row">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ overall.total_results }}</div>
          <div class="stat-label">判分记录</div>
        </el-card>
        <el-card shadow="never" class="stat-card pending">
          <div class="stat-value">{{ overall.exception }}</div>
          <div class="stat-label">异常待复核</div>
        </el-card>
        <el-card shadow="never" class="stat-card resolved">
          <div class="stat-value">{{ overall.reviewed }}</div>
          <div class="stat-label">已人工复核</div>
        </el-card>
        <el-card shadow="never" class="stat-card rate">
          <div class="stat-value">{{ (overall.correct_rate * 100).toFixed(1) }}%</div>
          <div class="stat-label">选择题正确率</div>
        </el-card>
      </div>

      <el-tabs v-model="activeTab" class="tabs">
        <el-tab-pane :label="`异常复核（${exceptionRows.length}）`" name="exception">
          <el-card shadow="never">
            <div class="filters">
              <el-select v-model="filterQuestion" placeholder="全部题号" clearable style="width: 140px" @change="loadExceptions">
                <el-option v-for="q in questions" :key="q.question_number" :label="`第 ${q.question_number} 题`" :value="q.question_number" />
              </el-select>
            </div>
            <el-table v-loading="loading" :data="exceptionRows" border>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="考号" width="110">
                <template #default="{ row }">{{ row.exam_number || '—' }}</template>
              </el-table-column>
              <el-table-column label="考生" width="110">
                <template #default="{ row }">{{ row.student_name || '—' }}</template>
              </el-table-column>
              <el-table-column label="识别结果" width="110">
                <template #default="{ row }">{{ row.recognized_options || '未填涂' }}</template>
              </el-table-column>
              <el-table-column label="标准答案" width="100">
                <template #default="{ row }">{{ row.correct_options || '—' }}</template>
              </el-table-column>
              <el-table-column label="异常类型" width="130">
                <template #default="{ row }">
                  <el-tag type="warning" size="small">{{ typeLabel(row.exception_type) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="填涂占比" min-width="200">
                <template #default="{ row }">
                  <span v-for="(r, i) in row.fill_ratios || []" :key="i" class="ratio">
                    {{ letter(i) }}:{{ r.toFixed(2) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openReview(row)">复核</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!loading && !exceptionRows.length" description="暂无待复核异常" />
          </el-card>
        </el-tab-pane>

        <el-tab-pane label="统计面板" name="statistics">
          <el-card shadow="never">
            <el-table :data="questions" border>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column prop="max_score" label="满分" width="80" />
              <el-table-column label="作答/总数" width="110">
                <template #default="{ row }">{{ row.graded }} / {{ row.total }}</template>
              </el-table-column>
              <el-table-column label="正确数" prop="correct" width="90" />
              <el-table-column label="正确率" width="180">
                <template #default="{ row }">
                  <el-progress :percentage="Math.round(row.correct_rate * 100)" :stroke-width="12" />
                </template>
              </el-table-column>
              <el-table-column label="异常" prop="exception" width="80" />
              <el-table-column label="平均分" prop="avg_score" width="90" />
              <el-table-column label="选项分布" min-width="240">
                <template #default="{ row }">
                  <div class="dist">
                    <div v-for="(count, opt) in row.distribution" :key="opt" class="dist-item">
                      <span class="dist-label">{{ opt }}</span>
                      <div class="dist-bar">
                        <div class="dist-fill" :style="{ width: barWidth(count) }"></div>
                      </div>
                      <span class="dist-count">{{ count }}</span>
                    </div>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!questions.length" description="暂无统计数据" />
          </el-card>
        </el-tab-pane>

        <el-tab-pane label="结果明细" name="detail">
          <el-card shadow="never">
            <div class="filters">
              <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 130px" @change="loadDetail">
                <el-option label="已判分" value="scored" />
                <el-option label="异常" value="exception" />
                <el-option label="已复核" value="reviewed" />
              </el-select>
              <el-select v-model="filterQuestion" placeholder="全部题号" clearable style="width: 140px" @change="loadDetail">
                <el-option v-for="q in questions" :key="q.question_number" :label="`第 ${q.question_number} 题`" :value="q.question_number" />
              </el-select>
            </div>
            <el-table v-loading="loading" :data="detailRows" border>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="考号" width="110">
                <template #default="{ row }">{{ row.exam_number || '—' }}</template>
              </el-table-column>
              <el-table-column label="考生" width="110">
                <template #default="{ row }">{{ row.student_name || '—' }}</template>
              </el-table-column>
              <el-table-column label="识别结果" width="100">
                <template #default="{ row }">{{ row.recognized_options || '未填涂' }}</template>
              </el-table-column>
              <el-table-column label="标准答案" width="100">
                <template #default="{ row }">{{ row.correct_options || '—' }}</template>
              </el-table-column>
              <el-table-column label="判定" width="90">
                <template #default="{ row }">
                  <el-tag v-if="row.status === 'exception'" type="warning" size="small">待复核</el-tag>
                  <el-tag v-else-if="row.is_correct" type="success" size="small">正确</el-tag>
                  <el-tag v-else type="danger" size="small">错误</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="得分" width="100">
                <template #default="{ row }">{{ row.score }} / {{ row.max_score }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="置信度" width="90">
                <template #default="{ row }">{{ row.confidence != null ? (row.confidence * 100).toFixed(0) + '%' : '—' }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <el-tab-pane :label="`标准答案（${answerRows.length}）`" name="answer">
          <el-card shadow="never">
            <div class="filters answer-actions">
              <span class="hint">按题录入标准答案；多选题可勾选多个选项。保存后可选择立即重新判分。</span>
              <div>
                <el-button v-if="canGrade" :loading="savingAnswer" @click="submitAnswers(false)">保存</el-button>
                <el-button v-if="canGrade" type="primary" :loading="savingAnswer" @click="submitAnswers(true)">
                  保存并重新判分
                </el-button>
              </div>
            </div>
            <el-table v-loading="loading" :data="answerRows" border>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="题型" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.allow_multiple ? 'warning' : 'info'">
                    {{ row.allow_multiple ? '多选' : '单选' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="满分" width="80">
                <template #default="{ row }">{{ row.max_score }}</template>
              </el-table-column>
              <el-table-column label="标准答案" min-width="260">
                <template #default="{ row }">
                  <el-radio-group v-if="!row.allow_multiple" v-model="row.single" :disabled="!canGrade">
                    <el-radio-button v-for="l in answerLetters(row)" :key="l" :value="l">{{ l }}</el-radio-button>
                  </el-radio-group>
                  <el-checkbox-group v-else v-model="row.selected" :disabled="!canGrade">
                    <el-checkbox-button v-for="l in answerLetters(row)" :key="l" :value="l">{{ l }}</el-checkbox-button>
                  </el-checkbox-group>
                </template>
              </el-table-column>
              <el-table-column label="来源" width="120">
                <template #default="{ row }">
                  <el-tag size="small" :type="sourceType(row.source)">{{ sourceText(row.source) }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!loading && !answerRows.length" description="该模板未配置选择题区域" />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 复核弹窗 -->
    <el-dialog v-model="reviewVisible" title="选择题人工复核" width="560px" @closed="clearReviewImage">
      <div v-if="reviewTarget" class="review-body">
        <div class="review-meta">
          第 {{ reviewTarget.question_number }} 题 ·
          考号 {{ reviewTarget.exam_number || '—' }} ·
          标准答案 <strong>{{ reviewTarget.correct_options || '未配置' }}</strong>
        </div>
        <div class="review-img-wrap">
          <img v-if="reviewImage" :src="reviewImage" class="review-img" />
          <el-empty v-else description="题块图像加载中或不存在" />
        </div>
        <div class="review-controls">
          <span class="label">识别结果：{{ reviewTarget.recognized_options || '未填涂' }}</span>
          <span class="label">机器置信度：{{ reviewTarget.confidence != null ? (reviewTarget.confidence * 100).toFixed(0) + '%' : '—' }}</span>
        </div>
        <el-checkbox-group v-model="reviewOptions" class="option-group">
          <el-checkbox-button v-for="l in optionLetters" :key="l" :value="l">{{ l }}</el-checkbox-button>
        </el-checkbox-group>
        <el-input v-model="reviewNote" type="textarea" :rows="2" placeholder="复核备注（选填）" style="margin-top: 12px" />
      </div>
      <template #footer>
        <el-button @click="reviewOptions = []">清空</el-button>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="primary" :loading="reviewing" @click="submitReview">确认复核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getExams, type Exam } from '@/api/exams'
import { getBlockImageUrl } from '@/api/imports'
import { useAuthStore } from '@/stores/auth'
import {
  CHOICE_EXCEPTION_LABELS,
  getChoiceAnswers,
  getChoiceStatistics,
  gradeChoices,
  listChoiceResults,
  reviewChoiceResult,
  saveChoiceAnswers,
  type ChoiceAnswerItem,
  type ChoiceQuestionStat,
  type ChoiceResult,
  type ChoiceStatus,
} from '@/api/choices'

type AnswerRow = ChoiceAnswerItem & { selected: string[]; single: string }

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exams = ref<Exam[]>([])
const examId = ref('')
const loading = ref(false)
const grading = ref(false)
const activeTab = ref('exception')

const questions = ref<ChoiceQuestionStat[]>([])
const overall = ref({
  total_questions: 0,
  total_results: 0,
  graded: 0,
  exception: 0,
  reviewed: 0,
  correct: 0,
  correct_rate: 0,
  avg_score: 0,
})

const exceptionRows = ref<ChoiceResult[]>([])
const detailRows = ref<ChoiceResult[]>([])
const filterQuestion = ref<string>('')
const filterStatus = ref<ChoiceStatus | ''>('')

const answerRows = ref<AnswerRow[]>([])
const savingAnswer = ref(false)

const reviewVisible = ref(false)
const reviewing = ref(false)
const reviewTarget = ref<ChoiceResult | null>(null)
const reviewOptions = ref<string[]>([])
const reviewNote = ref('')
const reviewImage = ref('')

const canGrade = computed(() => ['super_admin', 'exam_admin', 'group_leader'].includes(auth.user?.role || ''))
const optionLetters = computed(() => {
  if (!reviewTarget.value) return []
  const meta = questions.value.find((q) => q.question_number === reviewTarget.value?.question_number)
  const count = meta?.options_count || 4
  return Array.from({ length: count }, (_, i) => String.fromCharCode(65 + i))
})

function letter(i: number) {
  return String.fromCharCode(65 + i)
}
function typeLabel(t?: string) {
  return t ? CHOICE_EXCEPTION_LABELS[t] || t : '—'
}
function statusText(s: string) {
  return { scored: '已判分', exception: '异常', reviewed: '已复核' }[s] || s
}
function statusType(s: string) {
  return ({ scored: 'success', exception: 'warning', reviewed: 'primary' } as Record<string, any>)[s] || ''
}
function barWidth(count: number) {
  const max = Math.max(1, ...questions.value.flatMap((q) => Object.values(q.distribution)))
  return `${Math.round((count / max) * 100)}%`
}
function answerLetters(row: AnswerRow) {
  return Array.from({ length: row.options_count }, (_, i) => String.fromCharCode(65 + i))
}
function sourceText(s: string) {
  return { exam: '考试级', template: '模板级', none: '未配置' }[s] || s
}
function sourceType(s: string) {
  return ({ exam: 'success', template: 'info', none: 'danger' } as Record<string, any>)[s] || ''
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
  router.replace({ query: { exam_id: examId.value } })
  refreshAll()
}

async function refreshAll() {
  if (!examId.value) return
  loading.value = true
  try {
    const statRes = await getChoiceStatistics(examId.value)
    questions.value = statRes.data.questions
    overall.value = statRes.data.overall
    await Promise.all([loadExceptions(), loadDetail(), loadAnswers()])
  } finally {
    loading.value = false
  }
}

async function loadAnswers() {
  if (!examId.value) return
  const res = await getChoiceAnswers(examId.value)
  answerRows.value = res.data.items.map((it) => {
    const letters = (it.correct_options || '').split('').filter(Boolean)
    return { ...it, selected: letters, single: letters[0] || '' }
  })
}

async function submitAnswers(regrade: boolean) {
  if (!examId.value) return
  savingAnswer.value = true
  try {
    const items = answerRows.value.map((row) => ({
      question_number: row.question_number,
      correct_options: row.allow_multiple ? [...row.selected].sort().join('') : row.single,
      score: row.score,
    }))
    const res = await saveChoiceAnswers(examId.value, items, regrade)
    const g = res.data.grade
    ElMessage.success(
      regrade && g ? `已保存并重新判分：正常 ${g.scored} 题，异常 ${g.exception} 题` : '标准答案已保存',
    )
    await refreshAll()
  } catch {
    // 错误由拦截器提示
  } finally {
    savingAnswer.value = false
  }
}

async function loadExceptions() {
  if (!examId.value) return
  const res = await listChoiceResults({
    exam_id: examId.value,
    status: 'exception',
    question_number: filterQuestion.value || undefined,
  })
  exceptionRows.value = res.data
}

async function loadDetail() {
  if (!examId.value) return
  const res = await listChoiceResults({
    exam_id: examId.value,
    status: (filterStatus.value || undefined) as ChoiceStatus | undefined,
    question_number: filterQuestion.value || undefined,
  })
  detailRows.value = res.data
}

async function runGrade() {
  if (!examId.value) return
  grading.value = true
  try {
    const res = await gradeChoices(examId.value)
    ElMessage.success(`判分完成：正常 ${res.data.scored} 题，异常 ${res.data.exception} 题`)
    await refreshAll()
  } catch {
    // 错误由拦截器提示
  } finally {
    grading.value = false
  }
}

async function openReview(row: ChoiceResult) {
  reviewTarget.value = row
  reviewOptions.value = (row.recognized_options || '').split('').filter(Boolean)
  reviewNote.value = ''
  reviewImage.value = ''
  reviewVisible.value = true
  try {
    reviewImage.value = await getBlockImageUrl(row.block_id)
  } catch {
    reviewImage.value = ''
  }
}

function clearReviewImage() {
  if (reviewImage.value) URL.revokeObjectURL(reviewImage.value)
  reviewImage.value = ''
}

async function submitReview() {
  if (!reviewTarget.value) return
  reviewing.value = true
  try {
    await reviewChoiceResult(reviewTarget.value.id, {
      options: reviewOptions.value.join(''),
      note: reviewNote.value || undefined,
    })
    ElMessage.success('复核完成')
    reviewVisible.value = false
    await refreshAll()
  } catch {
    // 错误由拦截器提示
  } finally {
    reviewing.value = false
  }
}

onMounted(loadExams)
</script>

<style scoped>
.choice-center {
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
  color: #409eff;
}
.stat-card.rate .stat-value {
  color: #67c23a;
}
.stat-label {
  margin-top: 4px;
  color: #909399;
  font-size: 13px;
}
.filters {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.answer-actions {
  justify-content: space-between;
  align-items: center;
}
.answer-actions .hint {
  color: #909399;
  font-size: 13px;
}
.ratio {
  display: inline-block;
  margin-right: 10px;
  color: #606266;
  font-size: 12px;
}
.dist-item {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.dist-label {
  width: 14px;
  color: #606266;
  font-size: 12px;
}
.dist-bar {
  flex: 1;
  height: 10px;
  background: #f0f2f5;
  border-radius: 5px;
  overflow: hidden;
  min-width: 60px;
}
.dist-fill {
  height: 100%;
  background: #409eff;
}
.dist-count {
  width: 28px;
  text-align: right;
  color: #909399;
  font-size: 12px;
}
.review-meta {
  color: #606266;
  margin-bottom: 10px;
}
.review-img-wrap {
  text-align: center;
  min-height: 120px;
  margin-bottom: 12px;
}
.review-img {
  max-width: 100%;
  max-height: 320px;
  border: 1px solid #ebeef5;
}
.review-controls {
  display: flex;
  gap: 20px;
  margin-bottom: 10px;
}
.review-controls .label {
  color: #606266;
  font-size: 13px;
}
</style>