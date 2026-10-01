<template>
  <div class="precheck-view">
    <div class="toolbar">
      <h2>预阅卷预览</h2>
      <div class="toolbar-right">
        <el-select
          v-model="examId"
          placeholder="请选择考试"
          filterable
          style="width: 320px"
          @change="loadSession"
        >
          <el-option v-for="e in exams" :key="e.id" :label="e.name" :value="e.id">
            <span>{{ e.name }}</span>
            <span class="option-sub">{{ e.subject }} · {{ e.grade }}</span>
          </el-option>
        </el-select>
        <el-button v-if="sessionId" :disabled="!sessionId" :loading="loading" @click="fetchDetail(sessionId)">
          刷新
        </el-button>
        <el-button v-if="sessionId" type="danger" plain :disabled="!canRun" :loading="clearing" @click="onClear">
          清空预阅卷
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="!examId"
      type="info"
      :closable="false"
      show-icon
      title="请选择考试后开始预阅卷。"
    />
    <el-alert
      v-else-if="!sessionId"
      type="info"
      :closable="false"
      show-icon
      title="该考试尚未创建预阅卷会话。预阅卷用少量样卷试跑模板与 AI 效果，数据与正式阅卷完全隔离。"
    />

    <template v-if="examId && !sessionId">
      <el-card shadow="never" class="start-card">
        <el-button type="primary" :disabled="!canRun" :loading="opening" @click="startSession">
          开始预阅卷
        </el-button>
        <span class="hint">创建后即可上传样卷（最多 20 份）并执行试跑。</span>
      </el-card>
    </template>

    <template v-if="session">
      <el-alert
        v-if="session.message"
        class="msg"
        type="warning"
        :closable="false"
        show-icon
        :title="session.message"
      />

      <!-- 样卷上传 -->
      <el-card shadow="never" class="upload-card">
        <template #header>
          <div class="card-header">
            <span>
              样卷上传（{{ session.sample_count }} / {{ MAX_SAMPLES }} 份，共 {{ session.page_count }} 页）
              <el-tag :type="sessionStatusType" size="small" style="margin-left: 8px">
                {{ sessionStatusText }}
              </el-tag>
            </span>
            <div>
              <el-button
                type="primary"
                :disabled="!canRun || !uploadFiles.length || session.status === 'running'"
                :loading="uploading"
                @click="submitUpload"
              >
                上传样卷
              </el-button>
              <el-button
                type="success"
                :disabled="!canRun || !session.page_count || session.status === 'running'"
                :loading="running"
                @click="onRun"
              >
                执行预阅卷
              </el-button>
            </div>
          </div>
        </template>
        <el-upload
          drag
          multiple
          :auto-upload="false"
          :file-list="uploadFiles"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
          :disabled="session.status === 'running' || session.sample_count >= MAX_SAMPLES"
          accept=".pdf,.jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">将样卷拖到此处，或 <em>点击选择文件</em></div>
          <template #tip>
            <div class="upload-tip">支持 PDF / jpg / png / bmp / tif / webp，最多 {{ MAX_SAMPLES }} 份。</div>
          </template>
        </el-upload>
      </el-card>

      <!-- 汇总 -->
      <div class="stat-row">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.pages }}</div>
          <div class="stat-label">已处理页数</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.cut_blocks - summary.cut_failed }} / {{ summary.cut_blocks }}</div>
          <div class="stat-label">阅卷题块切割成功</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.exam_number_matched }} / {{ summary.exam_number_found }}</div>
          <div class="stat-label">考号匹配花名册</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.cut_positioning }}</div>
          <div class="stat-label">定位区（不计分）</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.choice_correct }} / {{ summary.choice_total }}</div>
          <div class="stat-label">选择题正确</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.choice_exception }}</div>
          <div class="stat-label">选择题异常</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.ai_scored }} / {{ summary.subjective_total }}</div>
          <div class="stat-label">非选择题 AI 已评</div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ summary.ai_low_confidence }}</div>
          <div class="stat-label">AI 低置信度</div>
        </el-card>
      </div>
      <div class="provider-line">
        AI 提供方：<el-tag size="small" type="info">{{ summary.provider || '未配置' }}</el-tag>
      </div>

      <el-tabs v-model="activeTab" class="tabs">
        <!-- 样卷预览 -->
        <el-tab-pane :label="`样卷预览（${session.pages.length}）`" name="preview">
          <el-card shadow="never">
            <el-table v-loading="loading" :data="session.pages" border>
              <el-table-column label="样卷页" width="110">
                <template #default="{ row }">第 {{ (row.original_page_index || 0) + 1 }} 页</template>
              </el-table-column>
              <el-table-column label="类型" width="90">
                <template #default="{ row }">{{ row.source_type === 'pdf' ? 'PDF' : '图片' }}</template>
              </el-table-column>
              <el-table-column label="识别考号" width="130">
                <template #default="{ row }">
                  <span v-if="row.exam_number_ocr">{{ row.exam_number_ocr }}</span>
                  <el-tag v-else size="small" type="warning">未识别</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="花名册" width="110">
                <template #default="{ row }">
                  <el-tag v-if="matchState(row) === 'matched'" size="small" type="success">已匹配</el-tag>
                  <el-tag v-else-if="matchState(row) === 'unmatched'" size="small" type="danger">不在花名册</el-tag>
                  <span v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column label="倾斜角" width="90">
                <template #default="{ row }">
                  {{ row.tilt_angle != null ? Number(row.tilt_angle).toFixed(2) + '°' : '—' }}
                </template>
              </el-table-column>
              <el-table-column label="题块" width="130">
                <template #default="{ row }">
                  {{ (row.cut_result || []).length }} 块 / {{ failedBlocks(row) }} 失败
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="pageStatusType(row.status)" size="small">
                    {{ pageStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }">
                  <el-button
                    link
                    type="primary"
                    :disabled="!row.preprocessed_image_path"
                    @click="openPageDialog(row)"
                  >
                    查看结果
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!session.pages.length" description="尚未上传样卷" />
          </el-card>
        </el-tab-pane>

        <!-- 选择题识别 -->
        <el-tab-pane :label="`选择题识别（${choiceRows.length}）`" name="choice">
          <el-card shadow="never">
            <el-table v-loading="loading" :data="choiceRows" border>
              <el-table-column label="页" width="80">
                <template #default="{ row }">第 {{ (row.page_index || 0) + 1 }} 页</template>
              </el-table-column>
              <el-table-column prop="exam_number" label="考号" width="120">
                <template #default="{ row }">{{ row.exam_number || '—' }}</template>
              </el-table-column>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="识别结果" width="110">
                <template #default="{ row }">{{ row.recognized_options || '未填涂' }}</template>
              </el-table-column>
              <el-table-column label="标准答案" width="100">
                <template #default="{ row }">{{ row.correct_options || '—' }}</template>
              </el-table-column>
              <el-table-column label="判定" width="90">
                <template #default="{ row }">
                  <el-tag v-if="row.status === 'no_answer_key'" size="small" type="info">未配置</el-tag>
                  <el-tag v-else-if="row.is_correct" size="small" type="success">正确</el-tag>
                  <el-tag v-else size="small" type="danger">错误</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="得分" width="100">
                <template #default="{ row }">{{ row.score }} / {{ row.max_score }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'ok' ? 'success' : 'warning'" size="small">
                    {{ omrStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="填涂占比" min-width="200">
                <template #default="{ row }">
                  <span v-for="(r, i) in row.fill_ratios || []" :key="i" class="ratio">
                    {{ letter(i) }}:{{ Number(r).toFixed(2) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!choiceRows.length" description="暂无选择题识别结果" />
          </el-card>
        </el-tab-pane>

        <!-- 非选择题 AI 预评 -->
        <el-tab-pane :label="`非选择题 AI 预评（${aiRows.length}）`" name="ai">
          <el-card shadow="never">
            <el-table v-loading="loading" :data="aiRows" border>
              <el-table-column label="页" width="80">
                <template #default="{ row }">第 {{ (row.page_index || 0) + 1 }} 页</template>
              </el-table-column>
              <el-table-column prop="exam_number" label="考号" width="120">
                <template #default="{ row }">{{ row.exam_number || '—' }}</template>
              </el-table-column>
              <el-table-column prop="question_number" label="题号" width="80" />
              <el-table-column label="AI 评分" width="110">
                <template #default="{ row }">
                  <span v-if="row.ai_score != null">{{ row.ai_score }} / {{ row.max_score }}</span>
                  <span v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column label="置信度" width="100">
                <template #default="{ row }">
                  <span v-if="row.ai_confidence != null">
                    {{ (row.ai_confidence * 100).toFixed(0) }}%
                  </span>
                  <span v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column label="低置信" width="90">
                <template #default="{ row }">
                  <el-tag v-if="row.low_confidence" size="small" type="warning">需复核</el-tag>
                  <span v-else>—</span>
                </template>
              </el-table-column>
              <el-table-column prop="ai_model" label="模型" width="140" />
              <el-table-column prop="ai_comment" label="AI 评语" min-width="260" show-overflow-tooltip />
            </el-table>
            <el-empty v-if="!aiRows.length" description="暂无 AI 预评结果" />
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 单页结果弹窗 -->
    <el-dialog v-model="pageDialogVisible" title="样卷页预阅卷结果" width="900px" @closed="clearPageDialog">
      <div v-if="pageDialogTarget" class="page-dialog">
        <div class="page-image-wrap">
          <img v-if="pageDialogImage" :src="pageDialogImage" class="page-image" />
          <el-empty v-else description="预处理图像加载中或不存在" />
        </div>
        <el-table :data="pageDialogTarget.cut_result || []" border size="small" class="block-table">
          <el-table-column prop="index" label="#" width="50" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              {{ regionTypeText(row.region_type) }}
              <el-tag v-if="row.grading === false" size="small" type="info" style="margin-left: 4px">仅定位</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="question_number" label="题号" width="80" />
          <el-table-column label="题块组" width="110">
            <template #default="{ row }">
              <span v-if="row.group_key">〔组{{ row.group_key }}〕×{{ row.region_count || 1 }}</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="尺寸(px)" width="120">
            <template #default="{ row }">{{ row.width_px }} × {{ row.height_px }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">
                {{ row.status === 'ok' ? '正常' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="row.status !== 'ok'"
                @click="openBlockImage(pageDialogTarget.id, row)"
              >
                题块图
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <el-dialog v-model="blockDialogVisible" :title="blockDialogTitle" width="560px" @closed="blockDialogImage = ''">
      <div class="block-dialog">
        <img v-if="blockDialogImage" :src="blockDialogImage" class="block-image" />
        <el-empty v-else description="题块图像加载中或不存在" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type UploadUserFile } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { getExams, getExamStudents, type Exam } from '@/api/exams'
import { useAuthStore } from '@/stores/auth'
import {
  OMR_STATUS_LABELS,
  PRECHECK_PAGE_STATUS_LABELS,
  PRECHECK_PAGE_STATUS_TYPES,
  clearPrecheckSession,
  getPrecheckBlockImageUrl,
  getPrecheckPageImageUrl,
  getPrecheckSession,
  listPrecheckSessions,
  openPrecheckSession,
  runPrecheck,
  uploadPrecheckSamples,
  type PrecheckCutBlock,
  type PrecheckPage,
  type PrecheckSessionDetail,
} from '@/api/precheck'

const MAX_SAMPLES = 20

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exams = ref<Exam[]>([])
const examId = ref('')
const rosterNumbers = ref<Set<string>>(new Set())
const sessionId = ref('')
const session = ref<PrecheckSessionDetail | null>(null)
const loading = ref(false)
const opening = ref(false)
const uploading = ref(false)
const running = ref(false)
const clearing = ref(false)
const activeTab = ref('preview')

const uploadFiles = ref<UploadUserFile[]>([])
const pageImages = ref<Record<string, string>>({})
const pageDialogVisible = ref(false)
const pageDialogTarget = ref<PrecheckPage | null>(null)
const pageDialogImage = ref('')
const blockDialogVisible = ref(false)
const blockDialogImage = ref('')
const blockDialogTitle = ref('')

const canRun = computed(() =>
  ['super_admin', 'exam_admin', 'group_leader'].includes(auth.user?.role || ''),
)

const sessionStatusText = computed(() => {
  const map: Record<string, string> = { active: '待运行', running: '运行中', done: '已完成', cleared: '已清空' }
  return map[session.value?.status || ''] || session.value?.status || ''
})
const sessionStatusType = computed(() => {
  const map: Record<string, string> = { active: 'info', running: 'warning', done: 'success', cleared: 'danger' }
  return map[session.value?.status || ''] || 'info'
})

const summary = computed(() => ({
  pages: session.value?.summary?.pages ?? 0,
  cut_blocks: session.value?.summary?.cut_blocks ?? 0,
  cut_failed: session.value?.summary?.cut_failed ?? 0,
  cut_positioning: session.value?.summary?.cut_positioning ?? 0,
  exam_number_found: session.value?.summary?.exam_number_found ?? 0,
  exam_number_matched: session.value?.summary?.exam_number_matched ?? 0,
  choice_total: session.value?.summary?.choice_total ?? 0,
  choice_correct: session.value?.summary?.choice_correct ?? 0,
  choice_exception: session.value?.summary?.choice_exception ?? 0,
  subjective_total: session.value?.summary?.subjective_total ?? 0,
  ai_scored: session.value?.summary?.ai_scored ?? 0,
  ai_low_confidence: session.value?.summary?.ai_low_confidence ?? 0,
  provider: session.value?.summary?.provider ?? null,
}))

const choiceRows = computed(() => {
  const rows: Array<Record<string, any>> = []
  for (const page of session.value?.pages || []) {
    for (const item of page.omr_result || []) {
      rows.push({ ...item, page_id: page.id, exam_number: page.exam_number_ocr, page_index: page.original_page_index })
    }
  }
  return rows
})

const aiRows = computed(() => {
  const rows: Array<Record<string, any>> = []
  for (const page of session.value?.pages || []) {
    for (const item of page.ai_result || []) {
      rows.push({ ...item, page_id: page.id, exam_number: page.exam_number_ocr, page_index: page.original_page_index })
    }
  }
  return rows
})

function letter(i: number) {
  return String.fromCharCode(65 + i)
}
function pageStatusText(s: string) {
  return PRECHECK_PAGE_STATUS_LABELS[s] || s
}
function pageStatusType(s: string) {
  return PRECHECK_PAGE_STATUS_TYPES[s] || 'info'
}
function omrStatusText(s: string) {
  return OMR_STATUS_LABELS[s] || s
}
function regionTypeText(t: string) {
  return { choice: '选择题', subjective: '非选择题', exam_number: '考号区', name: '姓名区' }[t] || t
}
function failedBlocks(page: PrecheckPage) {
  return (page.cut_result || []).filter((b) => b.status !== 'ok').length
}
function matchState(page: PrecheckPage): 'matched' | 'unmatched' | 'none' {
  if (!page.exam_number_ocr) return 'none'
  if (!rosterNumbers.value.size) return 'none'
  return rosterNumbers.value.has(page.exam_number_ocr) ? 'matched' : 'unmatched'
}

async function loadRoster() {
  rosterNumbers.value = new Set()
  if (!examId.value) return
  try {
    const res = await getExamStudents(examId.value)
    rosterNumbers.value = new Set(res.data.map((s) => s.exam_number).filter(Boolean))
  } catch {
    /* 花名册加载失败不阻断预阅卷查看 */
  }
}

async function loadExams() {
  const res = await getExams()
  exams.value = res.data
  const q = route.query.exam_id as string | undefined
  if (q && exams.value.some((e) => e.id === q)) examId.value = q
  else if (exams.value.length) examId.value = exams.value[0].id
  if (examId.value) await loadSession()
}

async function loadSession() {
  sessionId.value = ''
  session.value = null
  uploadFiles.value = []
  if (!examId.value) return
  router.replace({ query: { exam_id: examId.value } })
  loading.value = true
  try {
    await loadRoster()
    const res = await listPrecheckSessions(examId.value)
    const current = res.data.find((s) => ['active', 'running', 'done'].includes(s.status))
    if (current) {
      await fetchDetail(current.id)
    }
  } catch (e) {
    ElMessage.error('加载预阅卷会话失败')
  } finally {
    loading.value = false
  }
}

async function fetchDetail(id: string) {
  sessionId.value = id
  const res = await getPrecheckSession(id)
  session.value = res.data
  await loadPageImages(res.data.pages)
}

async function loadPageImages(pages: PrecheckPage[]) {
  for (const page of pages) {
    if (page.preprocessed_image_path && !pageImages.value[page.id]) {
      try {
        pageImages.value[page.id] = await getPrecheckPageImageUrl(page.id)
      } catch {
        /* 忽略单页图像加载失败 */
      }
    }
  }
}

async function startSession() {
  if (!examId.value) return
  opening.value = true
  try {
    const res = await openPrecheckSession(examId.value)
    await fetchDetail(res.data.id)
    ElMessage.success('预阅卷会话已就绪')
  } finally {
    opening.value = false
  }
}

function onFileChange(_file: unknown, fileList: UploadUserFile[]) {
  uploadFiles.value = fileList
}
function onFileRemove(_file: unknown, fileList: UploadUserFile[]) {
  uploadFiles.value = fileList
}

async function submitUpload() {
  if (!sessionId.value) return
  const files = uploadFiles.value.map((f) => f.raw).filter(Boolean) as File[]
  if (!files.length) {
    ElMessage.warning('请先选择样卷文件')
    return
  }
  uploading.value = true
  try {
    const res = await uploadPrecheckSamples(sessionId.value, files)
    uploadFiles.value = []
    await fetchDetail(sessionId.value)
    ElMessage.success(`已上传 ${res.data.added} 份样卷`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '样卷上传失败')
  } finally {
    uploading.value = false
  }
}

async function onRun() {
  if (!sessionId.value) return
  running.value = true
  try {
    await runPrecheck(sessionId.value)
    await pollUntilDone()
    ElMessage.success('预阅卷执行完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '预阅卷执行失败')
  } finally {
    running.value = false
  }
}

async function pollUntilDone() {
  for (let i = 0; i < 90; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    const res = await getPrecheckSession(sessionId.value)
    session.value = res.data
    const pending = res.data.pages.some((p) => p.status === 'pending')
    // 会话状态由 running 变为 done（或页面无 pending）即认为执行结束
    if (res.data.status !== 'running' && !pending) {
      await loadPageImages(res.data.pages)
      return
    }
  }
}

async function onClear() {
  if (!sessionId.value) return
  try {
    await ElMessageBox.confirm('清空后该考试的预阅卷样卷与结果将被删除，是否继续？', '清空预阅卷', {
      type: 'warning',
    })
  } catch {
    return
  }
  clearing.value = true
  try {
    const res = await clearPrecheckSession(sessionId.value)
    ElMessage.success(`已清空 ${res.data.cleared_samples} 份样卷、${res.data.cleared_pages} 页结果`)
    sessionId.value = ''
    session.value = null
    pageImages.value = {}
  } finally {
    clearing.value = false
  }
}

async function openPageDialog(page: PrecheckPage) {
  pageDialogTarget.value = page
  pageDialogVisible.value = true
  pageDialogImage.value = pageImages.value[page.id] || ''
  if (!pageDialogImage.value && page.preprocessed_image_path) {
    try {
      pageDialogImage.value = await getPrecheckPageImageUrl(page.id)
      pageImages.value[page.id] = pageDialogImage.value
    } catch {
      pageDialogImage.value = ''
    }
  }
}

function clearPageDialog() {
  pageDialogTarget.value = null
  pageDialogImage.value = ''
}

async function openBlockImage(pageId: string, block: PrecheckCutBlock) {
  blockDialogTitle.value = `题块 #${block.index} · ${regionTypeText(block.region_type)}${
    block.question_number ? ' · 第 ' + block.question_number + ' 题' : ''
  }`
  blockDialogVisible.value = true
  blockDialogImage.value = ''
  try {
    blockDialogImage.value = await getPrecheckBlockImageUrl(pageId, block.index)
  } catch {
    blockDialogImage.value = ''
  }
}

onMounted(loadExams)
</script>

<style scoped>
.precheck-view {
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
.start-card {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint {
  color: #909399;
  font-size: 13px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.upload-icon {
  font-size: 44px;
  color: #c0c4cc;
}
.upload-text {
  color: #606266;
}
.upload-text em {
  color: #409eff;
  font-style: normal;
}
.upload-tip {
  color: #909399;
  font-size: 12px;
}
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}
.stat-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}
.provider-line {
  color: #606266;
  font-size: 13px;
}
.ratio {
  display: inline-block;
  margin-right: 12px;
  font-size: 12px;
  color: #606266;
}
.page-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-image-wrap {
  max-height: 420px;
  overflow: auto;
  text-align: center;
  background: #f5f7fa;
  border-radius: 4px;
}
.page-image {
  max-width: 100%;
}
.block-dialog {
  text-align: center;
}
.block-image {
  max-width: 100%;
}
.msg {
  margin-bottom: 0;
}
</style>