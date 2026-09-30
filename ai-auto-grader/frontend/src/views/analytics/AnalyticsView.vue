<template>
  <div class="analytics-view">
    <div class="toolbar">
      <h2>学情分析</h2>
      <div class="toolbar-right">
        <el-select v-model="examId" placeholder="请选择考试" filterable style="width: 320px" @change="onExamChange">
          <el-option v-for="e in exams" :key="e.id" :label="e.name" :value="e.id">
            <span>{{ e.name }}</span>
            <span class="option-sub">{{ e.subject }} · {{ e.grade }}</span>
          </el-option>
        </el-select>
        <el-button :disabled="!examId" @click="openPaper">查看原试卷</el-button>
      </div>
    </div>

    <el-empty v-if="!examId" description="请选择考试以查看学情分析" />

    <template v-else>
      <el-tabs v-model="activeTab" class="tabs">
        <!-- F8-01 年级总览 -->
        <el-tab-pane label="年级总览" name="overview">
          <div v-loading="loading.overview">
            <div class="stat-row">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ overview?.appeared_count ?? 0 }}<span class="unit">/{{ overview?.roster_count ?? 0 }}</span></div>
                <div class="stat-label">实考 / 应考</div>
              </el-card>
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ overview?.avg_score ?? 0 }}<span class="unit">/{{ overview?.total_score ?? 0 }}</span></div>
                <div class="stat-label">平均分</div>
              </el-card>
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ overview?.max_score ?? 0 }}</div>
                <div class="stat-label">最高分</div>
              </el-card>
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ overview?.min_score ?? 0 }}</div>
                <div class="stat-label">最低分</div>
              </el-card>
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ pct(overview?.pass_rate) }}</div>
                <div class="stat-label">及格率（≥{{ overview?.pass_score }}）</div>
              </el-card>
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ pct(overview?.excellent_rate) }}</div>
                <div class="stat-label">优秀率（≥{{ overview?.excellent_score }}）</div>
              </el-card>
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ overview?.score_std ?? 0 }}</div>
                <div class="stat-label">标准差</div>
              </el-card>
            </div>

            <el-card shadow="never" class="chart-card">
              <template #header><span>分数分布直方图</span></template>
              <div class="histogram">
                <div v-for="bin in overview?.distribution || []" :key="bin.label" class="hist-col">
                  <div class="hist-count">{{ bin.count }}</div>
                  <div class="hist-bar-wrap">
                    <div class="hist-bar" :style="{ height: barHeight(bin.count) }" />
                  </div>
                  <div class="hist-label">{{ bin.label }}</div>
                </div>
              </div>
            </el-card>

            <el-card shadow="never" class="chart-card">
              <template #header><span>班级对比</span></template>
              <el-table :data="overview?.classes || []" border>
                <el-table-column prop="class_name" label="班级" width="140" />
                <el-table-column label="人数" width="80">
                  <template #default="{ row }">{{ row.appeared }}/{{ row.student_count }}</template>
                </el-table-column>
                <el-table-column label="平均分" min-width="180">
                  <template #default="{ row }">
                    <div class="bar-cell">
                      <div class="bar" :style="{ width: ratioWidth(row.avg_score, overview?.total_score) }" />
                      <span>{{ row.avg_score }}</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="median_score" label="中位数" width="90" />
                <el-table-column prop="max_score" label="最高" width="80" />
                <el-table-column prop="min_score" label="最低" width="80" />
                <el-table-column label="及格率" width="100">
                  <template #default="{ row }">{{ pct(row.pass_rate) }}</template>
                </el-table-column>
                <el-table-column label="优秀率" width="100">
                  <template #default="{ row }">{{ pct(row.excellent_rate) }}</template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- F8-02 班级学情 -->
        <el-tab-pane label="班级学情" name="classes">
          <el-card shadow="never" v-loading="loading.classes">
            <el-table :data="classReport?.classes || []" border>
              <el-table-column prop="class_name" label="班级" width="140" />
              <el-table-column label="实考/应考" width="110">
                <template #default="{ row }">{{ row.appeared }}/{{ row.student_count }}</template>
              </el-table-column>
              <el-table-column prop="avg_score" label="平均分" width="90" />
              <el-table-column prop="median_score" label="中位数" width="90" />
              <el-table-column label="及格率" width="120">
                <template #default="{ row }">
                  <div class="bar-cell">
                    <div class="bar" :style="{ width: `${row.pass_rate * 100}%` }" />
                    <span>{{ pct(row.pass_rate) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="优秀率" width="120">
                <template #default="{ row }">
                  <div class="bar-cell">
                    <div class="bar" :style="{ width: `${row.excellent_rate * 100}%` }" />
                    <span>{{ pct(row.excellent_rate) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="选择题得分率" width="130">
                <template #default="{ row }">{{ pct(row.choice_rate) }}</template>
              </el-table-column>
              <el-table-column label="非选择题得分率" width="140">
                <template #default="{ row }">{{ pct(row.subjective_rate) }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- F8-03 题目分析 -->
        <el-tab-pane label="题目分析" name="questions">
          <el-card shadow="never" v-loading="loading.questions">
            <el-alert
              v-if="questionReport?.high_error_questions?.length"
              type="warning"
              :closable="false"
              show-icon
              class="mb"
              :title="`高频错题：${questionReport.high_error_questions.map((q) => '第' + q.question_number + '题').join('、')}`"
            />
            <el-table :data="questionReport?.questions || []" border>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="题型" width="100">
                <template #default="{ row }">{{ row.question_type === 'choice' ? '选择题' : '非选择题' }}</template>
              </el-table-column>
              <el-table-column prop="max_score" label="满分" width="70" />
              <el-table-column prop="avg_score" label="平均分" width="90" />
              <el-table-column label="得分率" min-width="180">
                <template #default="{ row }">
                  <div class="bar-cell">
                    <div class="bar" :class="{ danger: row.score_rate < 0.5 }" :style="{ width: `${row.score_rate * 100}%` }" />
                    <span>{{ pct(row.score_rate) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="难度" width="90">
                <template #default="{ row }">{{ row.difficulty?.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="区分度" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.discrimination >= 0.3 ? 'success' : row.discrimination >= 0.2 ? 'warning' : 'info'" size="small">
                    {{ row.discrimination?.toFixed(2) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="正确率" width="90">
                <template #default="{ row }">{{ row.correct_rate != null ? pct(row.correct_rate) : '—' }}</template>
              </el-table-column>
              <el-table-column label="操作" width="90" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openQuestionDetail(row)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- F8-04 知识点掌握 -->
        <el-tab-pane label="知识点掌握" name="knowledge">
          <el-card shadow="never" v-loading="loading.knowledge">
            <el-alert
              v-if="!knowledgeReport?.tags?.length"
              type="info"
              :closable="false"
              show-icon
              title="尚未在答题卡模板中为题目配置知识点标签（knowledge_tags）。"
            />
            <el-table v-else :data="knowledgeReport?.tags || []" border>
              <el-table-column prop="knowledge_tag" label="知识点" width="200" />
              <el-table-column label="关联题目" min-width="140">
                <template #default="{ row }">{{ row.question_numbers.join('、') }}</template>
              </el-table-column>
              <el-table-column label="题目数" width="90" prop="question_count" />
              <el-table-column label="得分率" min-width="220">
                <template #default="{ row }">
                  <div class="bar-cell">
                    <div
                      class="bar"
                      :class="{ danger: row.mastery_level === 'weak', warn: row.mastery_level === 'basic' }"
                      :style="{ width: `${row.avg_score_rate * 100}%` }"
                    />
                    <span>{{ pct(row.avg_score_rate) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="掌握等级" width="120">
                <template #default="{ row }">
                  <el-tag :type="masteryType(row.mastery_level)" size="small">{{ masteryLabel(row.mastery_level) }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-tab-pane>

        <!-- F8-05 学生报告 -->
        <el-tab-pane label="学生报告" name="student">
          <el-card shadow="never">
            <div class="student-picker">
              <el-select
                v-model="studentId"
                placeholder="选择学生"
                filterable
                style="width: 320px"
                @change="loadStudentReport"
              >
                <el-option
                  v-for="s in students"
                  :key="s.student_id"
                  :label="`${s.name}（${s.class_name || '未分班'} · ${s.exam_number}）`"
                  :value="s.student_id"
                />
              </el-select>
            </div>

            <div v-if="studentReport" v-loading="loading.student" class="student-report">
              <div class="stat-row">
                <el-card shadow="never" class="stat-card">
                  <div class="stat-value">{{ studentReport.score }}<span class="unit">/{{ studentReport.total_score }}</span></div>
                  <div class="stat-label">总分</div>
                </el-card>
                <el-card shadow="never" class="stat-card">
                  <div class="stat-value">{{ studentReport.rank_in_grade ?? '—' }}<span class="unit">/{{ studentReport.grade_student_count }}</span></div>
                  <div class="stat-label">年级排名</div>
                </el-card>
                <el-card shadow="never" class="stat-card">
                  <div class="stat-value">{{ studentReport.rank_in_class ?? '—' }}<span class="unit">/{{ studentReport.class_student_count }}</span></div>
                  <div class="stat-label">班级排名</div>
                </el-card>
                <el-card shadow="never" class="stat-card">
                  <div class="stat-value">{{ studentReport.choice_score }}</div>
                  <div class="stat-label">选择题得分</div>
                </el-card>
                <el-card shadow="never" class="stat-card">
                  <div class="stat-value">{{ studentReport.subjective_score }}</div>
                  <div class="stat-label">非选择题得分</div>
                </el-card>
                <el-card shadow="never" class="stat-card">
                  <div class="stat-value">
                    <el-tag :type="studentReport.excellent ? 'success' : studentReport.passed ? 'warning' : 'danger'">
                      {{ studentReport.excellent ? '优秀' : studentReport.passed ? '及格' : '不及格' }}
                    </el-tag>
                  </div>
                  <div class="stat-label">等级</div>
                </el-card>
              </div>

              <el-row :gutter="16">
                <el-col :span="14">
                  <el-card shadow="never">
                    <template #header><span>逐题明细</span></template>
                    <el-table :data="studentReport.questions" border size="small">
                      <el-table-column prop="question_number" label="题号" width="70" />
                      <el-table-column label="题型" width="90">
                        <template #default="{ row }">{{ row.question_type === 'choice' ? '选择' : '主观' }}</template>
                      </el-table-column>
                      <el-table-column label="得分" width="90">
                        <template #default="{ row }">
                          <span v-if="row.score != null">{{ row.score }} / {{ row.max_score }}</span>
                          <span v-else class="muted">未评</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="作答" min-width="120">
                        <template #default="{ row }">
                          <span v-if="row.question_type === 'choice'">
                            {{ row.recognized_options || '未填涂' }}
                            <span class="muted">（答案 {{ row.correct_options || '—' }}）</span>
                          </span>
                          <el-tag v-else-if="row.mark && row.mark !== 'none'" size="small">{{ markLabel(row.mark) }}</el-tag>
                          <span v-else class="muted">—</span>
                        </template>
                      </el-table-column>
                      <el-table-column label="判定" width="90">
                        <template #default="{ row }">
                          <el-tag v-if="row.is_correct === true" type="success" size="small">正确</el-tag>
                          <el-tag v-else-if="row.is_correct === false" type="danger" size="small">错误</el-tag>
                          <span v-else class="muted">—</span>
                        </template>
                      </el-table-column>
                    </el-table>
                  </el-card>
                </el-col>
                <el-col :span="10">
                  <el-card shadow="never">
                    <template #header><span>知识点掌握</span></template>
                    <el-table :data="studentReport.knowledge" border size="small">
                      <el-table-column prop="knowledge_tag" label="知识点" />
                      <el-table-column label="得分率" width="90">
                        <template #default="{ row }">{{ pct(row.avg_score_rate) }}</template>
                      </el-table-column>
                      <el-table-column label="等级" width="100">
                        <template #default="{ row }">
                          <el-tag :type="masteryType(row.mastery_level)" size="small">{{ masteryLabel(row.mastery_level) }}</el-tag>
                        </template>
                      </el-table-column>
                    </el-table>
                  </el-card>
                  <el-card v-if="studentReport.marks.length" shadow="never" class="mt">
                    <template #header><span>作答标记</span></template>
                    <div v-for="(m, i) in studentReport.marks" :key="i" class="mark-item">
                      <el-tag size="small">{{ markLabel(m.mark) }}</el-tag>
                      <span>第 {{ m.question_number }} 题：{{ m.score }} / {{ m.max_score }}</span>
                      <span class="muted">{{ m.comment }}</span>
                    </div>
                  </el-card>
                </el-col>
              </el-row>
            </div>
            <el-empty v-else description="请选择学生查看个人报告" />
          </el-card>
        </el-tab-pane>

        <!-- F8-06 讲评素材 -->
        <el-tab-pane label="讲评素材" name="materials">
          <div v-loading="loading.materials">
            <el-card shadow="never">
              <template #header><span>高频错题</span></template>
              <el-table :data="materials?.high_error_questions || []" border size="small">
                <el-table-column prop="question_number" label="题号" width="80" />
                <el-table-column label="题型" width="100">
                  <template #default="{ row }">{{ row.question_type === 'choice' ? '选择题' : '非选择题' }}</template>
                </el-table-column>
                <el-table-column prop="avg_score" label="平均分" width="90" />
                <el-table-column label="得分率" width="100">
                  <template #default="{ row }">{{ pct(row.score_rate) }}</template>
                </el-table-column>
                <el-table-column label="常见错误" min-width="200">
                  <template #default="{ row }">
                    <span v-if="row.common_wrong?.length">
                      <el-tag v-for="w in row.common_wrong" :key="w.options" size="small" type="danger" class="mr">
                        {{ w.options }} × {{ w.count }}
                      </el-tag>
                    </span>
                    <span v-else class="muted">—</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>

            <el-card shadow="never" class="mt">
              <template #header><span>优秀作答（{{ materials?.excellent?.length || 0 }}）</span></template>
              <div class="material-grid">
                <div v-for="m in materials?.excellent || []" :key="m.result_id" class="material-card">
                  <img v-if="blockImages[m.result_id]" :src="blockImages[m.result_id]" class="material-img" />
                  <div v-else class="material-img placeholder">无作答图</div>
                  <div class="material-meta">
                    <div><b>{{ m.student_name || '未匹配' }}</b> · {{ m.class_name || '—' }}</div>
                    <div>第 {{ m.question_number }} 题 · {{ m.score }} / {{ m.max_score }}</div>
                    <div class="muted">{{ m.comment }}</div>
                  </div>
                </div>
                <el-empty v-if="!materials?.excellent?.length" description="暂无标记为优秀的作答" />
              </div>
            </el-card>

            <el-card shadow="never" class="mt">
              <template #header><span>典型错误（{{ materials?.typical_error?.length || 0 }}）</span></template>
              <div class="material-grid">
                <div v-for="m in materials?.typical_error || []" :key="m.result_id" class="material-card">
                  <img v-if="blockImages[m.result_id]" :src="blockImages[m.result_id]" class="material-img" />
                  <div v-else class="material-img placeholder">无作答图</div>
                  <div class="material-meta">
                    <div><b>{{ m.student_name || '未匹配' }}</b> · {{ m.class_name || '—' }}</div>
                    <div>第 {{ m.question_number }} 题 · {{ m.score }} / {{ m.max_score }}</div>
                    <div class="muted">{{ m.comment }}</div>
                  </div>
                </div>
                <el-empty v-if="!materials?.typical_error?.length" description="暂无标记为典型错误的作答" />
              </div>
            </el-card>

            <el-card v-if="materials?.blank?.length" shadow="never" class="mt">
              <template #header><span>空白卷（{{ materials?.blank?.length || 0 }}）</span></template>
              <div class="material-grid">
                <div v-for="m in materials?.blank || []" :key="m.result_id" class="material-card">
                  <img v-if="blockImages[m.result_id]" :src="blockImages[m.result_id]" class="material-img" />
                  <div v-else class="material-img placeholder">无作答图</div>
                  <div class="material-meta">
                    <div><b>{{ m.student_name || '未匹配' }}</b> · {{ m.class_name || '—' }}</div>
                    <div>第 {{ m.question_number }} 题</div>
                  </div>
                </div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 题目详情 -->
    <el-dialog v-model="questionDialogVisible" :title="`第 ${questionDetail?.question_number || ''} 题 · 作答分析`" width="620px">
      <div v-if="questionDetail">
        <div class="detail-row">
          <span>满分：{{ questionDetail.max_score }}</span>
          <span>平均分：{{ questionDetail.avg_score }}</span>
          <span>得分率：{{ pct(questionDetail.score_rate) }}</span>
          <span>难度：{{ questionDetail.difficulty?.toFixed(2) }}</span>
          <span>区分度：{{ questionDetail.discrimination?.toFixed(2) }}</span>
        </div>
        <template v-if="questionDetail.question_type === 'choice'">
          <h4>选项分布</h4>
          <div class="histogram compact">
            <div v-for="(count, letter) in questionDetail.option_distribution || {}" :key="letter" class="hist-col">
              <div class="hist-count">{{ count }}</div>
              <div class="hist-bar-wrap">
                <div class="hist-bar" :style="{ height: optBarHeight(count) }" />
              </div>
              <div class="hist-label">{{ letter }}</div>
            </div>
          </div>
          <h4>高频错误</h4>
          <el-tag v-for="w in questionDetail.common_wrong || []" :key="w.options" type="danger" class="mr">
            {{ w.options }} × {{ w.count }}
          </el-tag>
          <el-empty v-if="!questionDetail.common_wrong?.length" description="暂无错误作答" />
        </template>
        <template v-else>
          <h4>作答情况</h4>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="应阅份数">{{ questionDetail.total }}</el-descriptions-item>
            <el-descriptions-item label="已评分">{{ questionDetail.graded }}</el-descriptions-item>
            <el-descriptions-item label="平均得分率">{{ pct(questionDetail.score_rate) }}</el-descriptions-item>
            <el-descriptions-item label="区分度">{{ questionDetail.discrimination?.toFixed(2) }}</el-descriptions-item>
          </el-descriptions>
          <p class="muted">典型作答与错误样例请在「讲评素材」页签查看。</p>
          <div v-if="questionDetail.knowledge_tags?.length">
            <el-tag v-for="t in questionDetail.knowledge_tags" :key="t" size="small" class="mr">{{ t }}</el-tag>
          </div>
        </template>
      </div>
    </el-dialog>

    <!-- 原试卷预览 -->
    <el-dialog v-model="paperDialogVisible" title="原试卷预览" width="860px" @closed="closePaper">
      <div class="paper-wrap">
        <iframe v-if="paperUrl" :src="paperUrl" class="paper-frame" />
        <el-empty v-else description="正在加载原试卷或尚未上传" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getExams, type Exam } from '@/api/exams'
import { getBlockImageUrl } from '@/api/imports'
import {
  MASTERY_LABELS,
  MASTERY_TYPES,
  MARK_LABELS,
  getClassReport,
  getKnowledgeReport,
  getOriginalPaperPreviewUrl,
  getOverview,
  getQuestionReport,
  getReviewMaterials,
  getStudentReport,
  listAnalyticsStudents,
  type AnalyticsStudent,
  type ClassReport,
  type ExamOverview,
  type KnowledgeReport,
  type QuestionReport,
  type QuestionStat,
  type ReviewMaterial,
  type ReviewMaterials,
  type StudentReport,
} from '@/api/analytics'

const route = useRoute()
const router = useRouter()

const exams = ref<Exam[]>([])
const examId = ref('')
const activeTab = ref('overview')

const overview = ref<ExamOverview | null>(null)
const classReport = ref<ClassReport | null>(null)
const questionReport = ref<QuestionReport | null>(null)
const knowledgeReport = ref<KnowledgeReport | null>(null)
const students = ref<AnalyticsStudent[]>([])
const studentId = ref('')
const studentReport = ref<StudentReport | null>(null)
const materials = ref<ReviewMaterials | null>(null)

const loading = ref({
  overview: false,
  classes: false,
  questions: false,
  knowledge: false,
  student: false,
  materials: false,
})

const questionDialogVisible = ref(false)
const questionDetail = ref<QuestionStat | null>(null)
const paperDialogVisible = ref(false)
const paperUrl = ref('')
const blockImages = ref<Record<string, string>>({})

function pct(v?: number | null) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}
function masteryLabel(v: string) {
  return MASTERY_LABELS[v] || v
}
function masteryType(v: string) {
  return MASTERY_TYPES[v] || 'info'
}
function markLabel(v: string) {
  return MARK_LABELS[v] || v
}

const maxBinCount = computed(() => Math.max(1, ...(overview.value?.distribution || []).map((b) => b.count)))
function barHeight(count: number) {
  return `${Math.round((count / maxBinCount.value) * 160)}px`
}
const maxOptCount = computed(() => {
  const dist = questionDetail.value?.option_distribution || {}
  return Math.max(1, ...Object.values(dist))
})
function optBarHeight(count: number) {
  return `${Math.round((count / maxOptCount.value) * 120)}px`
}
function ratioWidth(value: number, total?: number) {
  if (!total) return '0%'
  return `${Math.min(100, Math.round((value / total) * 100))}%`
}

async function loadExams() {
  const res = await getExams()
  exams.value = res.data
  const q = route.query.exam_id as string | undefined
  if (q && exams.value.some((e) => e.id === q)) examId.value = q
  else if (exams.value.length) examId.value = exams.value[0].id
  if (examId.value) await onExamChange()
}

async function onExamChange() {
  router.replace({ query: { exam_id: examId.value } })
  studentId.value = ''
  studentReport.value = null
  blockImages.value = {}
  await Promise.all([loadOverview(), loadClasses(), loadQuestions(), loadKnowledge(), loadStudents()])
  await loadMaterials()
}

async function loadOverview() {
  loading.value.overview = true
  try {
    overview.value = (await getOverview(examId.value)).data
  } finally {
    loading.value.overview = false
  }
}
async function loadClasses() {
  loading.value.classes = true
  try {
    classReport.value = (await getClassReport(examId.value)).data
  } finally {
    loading.value.classes = false
  }
}
async function loadQuestions() {
  loading.value.questions = true
  try {
    questionReport.value = (await getQuestionReport(examId.value)).data
  } finally {
    loading.value.questions = false
  }
}
async function loadKnowledge() {
  loading.value.knowledge = true
  try {
    knowledgeReport.value = (await getKnowledgeReport(examId.value)).data
  } finally {
    loading.value.knowledge = false
  }
}
async function loadStudents() {
  students.value = (await listAnalyticsStudents(examId.value)).data
}
async function loadMaterials() {
  loading.value.materials = true
  try {
    materials.value = (await getReviewMaterials(examId.value)).data
    await loadMaterialImages()
  } finally {
    loading.value.materials = false
  }
}

async function loadMaterialImages() {
  const list: ReviewMaterial[] = [
    ...(materials.value?.excellent || []),
    ...(materials.value?.typical_error || []),
    ...(materials.value?.blank || []),
  ]
  for (const m of list) {
    if (m.block_id && !blockImages.value[m.result_id]) {
      try {
        blockImages.value[m.result_id] = await getBlockImageUrl(m.block_id)
      } catch {
        /* 忽略单张作答图加载失败 */
      }
    }
  }
}

async function loadStudentReport() {
  if (!studentId.value) return
  loading.value.student = true
  try {
    studentReport.value = (await getStudentReport(examId.value, studentId.value)).data
  } finally {
    loading.value.student = false
  }
}

function openQuestionDetail(row: QuestionStat) {
  questionDetail.value = row
  questionDialogVisible.value = true
}

async function openPaper() {
  if (!examId.value) return
  paperDialogVisible.value = true
  paperUrl.value = ''
  try {
    paperUrl.value = await getOriginalPaperPreviewUrl(examId.value)
  } catch {
    ElMessage.warning('该考试尚未上传原试卷')
    paperDialogVisible.value = false
  }
}
function closePaper() {
  if (paperUrl.value) {
    URL.revokeObjectURL(paperUrl.value)
    paperUrl.value = ''
  }
}

onMounted(loadExams)
</script>

<style scoped>
.analytics-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.toolbar h2 {
  margin: 0;
}
.toolbar-right {
  display: flex;
  gap: 12px;
}
.option-sub {
  float: right;
  color: #909399;
  font-size: 12px;
  margin-left: 12px;
}
.stat-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}
.stat-value .unit {
  font-size: 13px;
  color: #909399;
  font-weight: 400;
}
.stat-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}
.chart-card {
  margin-bottom: 16px;
}
.histogram {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  height: 220px;
  padding: 0 8px;
}
.histogram.compact {
  height: 170px;
}
.hist-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
}
.hist-count {
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
}
.hist-bar-wrap {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: flex-end;
  flex: 1;
}
.hist-bar {
  width: 70%;
  max-width: 48px;
  background: linear-gradient(180deg, #79bbff, #409eff);
  border-radius: 3px 3px 0 0;
  transition: height 0.3s;
}
.hist-label {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
  white-space: nowrap;
}
.bar-cell {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
}
.bar-cell .bar {
  height: 12px;
  min-width: 2px;
  background: #409eff;
  border-radius: 6px;
  transition: width 0.3s;
}
.bar-cell .bar.danger {
  background: #f56c6c;
}
.bar-cell .bar.warn {
  background: #e6a23c;
}
.bar-cell span {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}
.student-picker {
  margin-bottom: 16px;
}
.student-report {
  margin-top: 8px;
}
.detail-row {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  color: #606266;
  margin-bottom: 12px;
}
.material-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
.material-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}
.material-img {
  width: 100%;
  height: 150px;
  object-fit: contain;
  background: #f5f7fa;
  display: block;
}
.material-img.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 13px;
}
.material-meta {
  padding: 10px;
  font-size: 13px;
  color: #303133;
}
.muted {
  color: #909399;
  font-size: 12px;
}
.mt {
  margin-top: 16px;
}
.mb {
  margin-bottom: 12px;
}
.mr {
  margin-right: 8px;
}
.mark-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px dashed #ebeef5;
}
.paper-wrap {
  height: 70vh;
}
.paper-frame {
  width: 100%;
  height: 100%;
  border: none;
}
</style>