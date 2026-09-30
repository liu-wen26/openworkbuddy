<template>
  <div class="import-center">
    <div class="toolbar">
      <h2>答卷导入</h2>
      <el-select
        v-model="examId"
        placeholder="请选择考试"
        filterable
        style="width: 320px"
        @change="onExamChange"
      >
        <el-option v-for="e in exams" :key="e.id" :label="e.name" :value="e.id">
          <span>{{ e.name }}</span>
          <span style="float: right; color: #909399; font-size: 12px">{{ e.subject }} · {{ e.grade }}</span>
        </el-option>
      </el-select>
    </div>

    <el-alert
      v-if="examId && selectedExam && !selectedExam.answer_card_template_id"
      type="warning"
      :closable="false"
      show-icon
      title="该考试尚未绑定答题卡模板，无法导入答卷，请先在考试设置中绑定模板。"
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" class="upload-card">
      <template #header>
        <div class="card-header">
          <span>上传答卷</span>
          <div>
            <el-radio-group v-model="importType">
              <el-radio-button value="pdf">PDF 文件（整卷/批量）</el-radio-button>
              <el-radio-button value="image">图片 / ZIP 图片包</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <el-upload
        drag
        multiple
        :auto-upload="false"
        :file-list="fileList"
        :accept="acceptTypes"
        :on-change="onFileChange"
        :on-remove="onFileRemove"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择文件</em></div>
        <template #tip>
          <div class="el-upload__tip">
            PDF 模式支持 .pdf；图片模式支持 jpg/png/bmp/tif 及 .zip 图片包。单个文件不超过 50MB。
          </div>
        </template>
      </el-upload>

      <div class="upload-actions">
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="!examId || !canImport || fileList.length === 0"
          @click="startImport"
        >
          开始导入（{{ fileList.length }} 个文件）
        </el-button>
        <el-button :disabled="fileList.length === 0 || uploading" @click="clearFiles">清空</el-button>
      </div>

      <div v-if="uploading" class="upload-progress">
        <el-progress :percentage="uploadPercent" :stroke-width="14" />
        <span class="muted">{{ uploadHint }}</span>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>导入批次</span>
          <el-button link type="primary" :disabled="!examId" @click="loadBatches">刷新</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="batches" border>
        <el-table-column label="批次" width="120">
          <template #default="{ row }">{{ row.id.slice(0, 8) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ row.import_type === 'pdf' ? 'PDF' : '图片' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="batchStatusType(row.status)" size="small">{{ batchStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="batchPercent(row)"
              :status="row.status === 'failed' ? 'exception' : undefined"
            />
            <span class="muted">{{ row.processed_pages }} / {{ row.total_pages }} 页</span>
          </template>
        </el-table-column>
        <el-table-column label="文件数" prop="total_files" width="80" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openPages(row)">答卷页</el-button>
            <el-button
              link
              type="primary"
              :disabled="row.status === 'processing'"
              @click="reprocess(row)"
            >重新处理</el-button>
            <el-button link type="danger" @click="removeBatch(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 答卷页抽屉 -->
    <el-drawer v-model="pagesVisible" title="答卷页处理结果" size="70%">
      <div style="margin-bottom: 12px">
        <el-button link type="primary" @click="loadPages">刷新</el-button>
        <span class="muted" style="margin-left: 12px">共 {{ pages.length }} 页</span>
      </div>
      <el-table v-loading="pagesLoading" :data="pages" border height="calc(100vh - 200px)">
        <el-table-column label="页" width="70">
          <template #default="{ row }">{{ (row.original_page_index ?? 0) + 1 }}</template>
        </el-table-column>
        <el-table-column label="识别考号" width="110" prop="exam_number_ocr" />
        <el-table-column label="考生" width="120">
          <template #default="{ row }">{{ row.student_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="班级" width="100">
          <template #default="{ row }">{{ row.class_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="倾斜角" width="90">
          <template #default="{ row }">{{ row.tilt_angle ?? 0 }}°</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="pageStatusType(row.status)" size="small">{{ pageStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="previewPage(row)">预览</el-button>
            <el-button link type="primary" @click="promptExamNumber(row)">指定考号</el-button>
            <el-button link type="primary" @click="openPerspective(row)">透视矫正</el-button>
            <el-button link type="warning" @click="recut(row)">重新切割</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <!-- 整卷/题块预览 -->
    <el-dialog v-model="previewVisible" title="答卷页预览" width="80%" top="5vh" @closed="clearPreview">
      <div v-loading="previewLoading" class="preview-wrap">
        <div class="preview-main">
          <img v-if="previewImageUrl" :src="previewImageUrl" class="preview-img" />
          <el-empty v-else description="暂无预处理图像" />
        </div>
        <div class="preview-side">
          <h4>切割题块（{{ previewBlocks.length }}）</h4>
          <div class="block-grid">
            <div v-for="b in previewBlocks" :key="b.id" class="block-item">
              <img v-if="blockImages[b.id]" :src="blockImages[b.id]" />
              <div class="block-label">{{ blockLabel(b) }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 手动四点透视矫正 -->
    <PerspectiveCorrectDialog
      v-model="perspectiveVisible"
      :page-id="perspectivePageId"
      @applied="onPerspectiveApplied"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getExams, type Exam } from '@/api/exams'
import { useAuthStore } from '@/stores/auth'
import {
  completeChunkUpload,
  createImportBatch,
  deleteImportBatch,
  getBlockImageUrl,
  getImportProgress,
  getPageImageUrl,
  initChunkUpload,
  listBatchPages,
  listImportBatches,
  listPageBlocks,
  processImportBatch,
  recutPage,
  setPageExamNumber,
  uploadChunk,
  uploadSourceFiles,
  type AnswerBlock,
  type ImportBatch,
  type ImportType,
  type ImportedPage,
} from '@/api/imports'
import PerspectiveCorrectDialog from './components/PerspectiveCorrectDialog.vue'
import { useRealtime } from '@/composables/useRealtime'

const LARGE_FILE_THRESHOLD = 10 * 1024 * 1024 // 10MB 以上走分片上传

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const realtime = useRealtime()

const exams = ref<Exam[]>([])
const examId = ref<string>('')
const importType = ref<ImportType>('pdf')
const fileList = ref<any[]>([])
const uploading = ref(false)
const uploadPercent = ref(0)
const uploadHint = ref('')
const loading = ref(false)
const batches = ref<ImportBatch[]>([])

const perspectiveVisible = ref(false)
const perspectivePageId = ref('')

const pagesVisible = ref(false)
const pagesLoading = ref(false)
const pages = ref<ImportedPage[]>([])
const activeBatch = ref<ImportBatch | null>(null)

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewImageUrl = ref('')
const previewBlocks = ref<AnswerBlock[]>([])
const blockImages = ref<Record<string, string>>({})

const canImport = computed(() => ['super_admin', 'exam_admin'].includes(auth.user?.role || ''))
const selectedExam = computed(() => exams.value.find((e) => e.id === examId.value) || null)
const acceptTypes = computed(() => (importType.value === 'pdf' ? '.pdf' : '.jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp,.zip'))

let pollTimer: ReturnType<typeof setInterval> | null = null

function batchPercent(row: ImportBatch) {
  if (row.status === 'completed') return 100
  if (!row.total_pages) return 0
  return Math.round((row.processed_pages / row.total_pages) * 100)
}
function batchStatusText(s: string) {
  return { pending: '待处理', processing: '处理中', completed: '已完成', failed: '失败' }[s] || s
}
function batchStatusType(s: string) {
  return ({ pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' } as Record<string, any>)[s] || ''
}
function pageStatusText(s: string) {
  return { pending: '待处理', matched: '已匹配', exception: '异常', processed: '已处理' }[s] || s
}
function pageStatusType(s: string) {
  return ({ pending: 'info', matched: 'warning', exception: 'danger', processed: 'success' } as Record<string, any>)[s] || ''
}
function blockLabel(b: AnswerBlock) {
  const t: Record<string, string> = { choice: '选择题', subjective: '非选择题', exam_number: '考号', name: '姓名' }
  return `${t[b.block_type] || b.block_type}${b.question_number ? ' ' + b.question_number : ''}`
}
function formatTime(t: string) {
  return t ? new Date(t).toLocaleString() : '—'
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
  if (examId.value) await loadBatches()
}

function onExamChange() {
  batches.value = []
  pagesVisible.value = false
  router.replace({ query: { exam_id: examId.value } })
  syncRealtimeTopic()
  loadBatches()
}

let realtimeTopic = ''
let stopImportProgress: (() => void) | null = null
const notifiedBatches = new Set<string>()

function syncRealtimeTopic() {
  if (realtimeTopic) realtime.unsubscribe(realtimeTopic)
  realtimeTopic = ''
  if (examId.value) {
    realtimeTopic = `exam:${examId.value}`
    realtime.subscribe(realtimeTopic)
  }
}

/** 实时进度回调：直接更新对应批次行，WebSocket 不可用时仍由轮询兜底。 */
function handleImportProgress(data: Record<string, unknown>) {
  const batchId = data.batch_id as string
  const row = batches.value.find((b) => b.id === batchId)
  if (!row) return
  row.processed_pages = (data.processed_pages as number) ?? row.processed_pages
  row.total_pages = (data.total_pages as number) ?? row.total_pages
  row.status = (data.status as ImportBatch['status']) ?? row.status
  row.message = (data.message as string | null) ?? row.message
  if (row.status === 'completed' && !notifiedBatches.has(batchId)) {
    notifiedBatches.add(batchId)
    ElMessage.success('答卷导入完成')
  } else if (row.status === 'failed' && !notifiedBatches.has(batchId)) {
    notifiedBatches.add(batchId)
    ElMessage.error(row.message || '答卷导入失败')
  }
  syncPolling()
}

async function loadBatches() {
  if (!examId.value) return
  loading.value = true
  try {
    const res = await listImportBatches({ exam_id: examId.value })
    batches.value = res.data
  } finally {
    loading.value = false
  }
  syncPolling()
}

function syncPolling() {
  const processing = batches.value.some((b) => b.status === 'processing' || b.status === 'pending')
  if (processing && !pollTimer) {
    pollTimer = setInterval(refreshProgress, 2000)
  } else if (!processing && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshProgress() {
  let anyProcessing = false
  for (const b of batches.value) {
    if (b.status === 'processing' || b.status === 'pending') {
      try {
        const res = await getImportProgress(b.id)
        b.processed_pages = res.data.processed_pages
        b.total_pages = res.data.total_pages
        b.status = res.data.status
      } catch {
        // ignore
      }
      if (b.status === 'processing' || b.status === 'pending') anyProcessing = true
    }
  }
  if (!anyProcessing) syncPolling()
}

function onFileChange(_file: any, list: any[]) {
  fileList.value = list
}
function onFileRemove(_file: any, list: any[]) {
  fileList.value = list
}
function clearFiles() {
  fileList.value = []
}

async function startImport() {
  if (!examId.value) return
  uploading.value = true
  uploadPercent.value = 0
  uploadHint.value = '正在创建导入批次…'
  try {
    const files = fileList.value.map((f) => f.raw as File).filter(Boolean)
    const totalBytes = files.reduce((sum, f) => sum + f.size, 0) || 1
    const createRes = await createImportBatch({ exam_id: examId.value, import_type: importType.value })
    const batchId = createRes.data.id

    let uploadedBytes = 0
    const updateProgress = (name: string) => {
      uploadPercent.value = Math.min(99, Math.round((uploadedBytes / totalBytes) * 100))
      uploadHint.value = `正在上传：${name}`
    }

    const small: File[] = []
    for (const f of files) {
      if (f.size > LARGE_FILE_THRESHOLD) {
        await uploadLargeFile(batchId, f, (done) => {
          updateProgress(f.name)
          uploadedBytes += done
        })
      } else {
        small.push(f)
      }
    }

    if (small.length) {
      uploadHint.value = `正在上传 ${small.length} 个小文件…`
      await uploadSourceFiles(batchId, small, false)
    }

    uploadPercent.value = 100
    uploadHint.value = '上传完成，正在后台处理…'
    await processImportBatch(batchId)
    ElMessage.success('上传成功，正在后台处理')
    clearFiles()
    await loadBatches()
  } catch {
    // 错误已由拦截器提示
  } finally {
    uploading.value = false
    uploadHint.value = ''
  }
}

/** 分片上传单个大文件，支持断点续传（跳过已接收分片）。 */
async function uploadLargeFile(batchId: string, file: File, onBytes: (bytes: number) => void) {
  const initRes = await initChunkUpload(batchId, { filename: file.name, total_size: file.size })
  const { upload_id, chunk_size, total_chunks, received } = initRes.data
  const done = new Set<number>(received)

  for (let i = 0; i < total_chunks; i++) {
    if (done.has(i)) continue
    const start = i * chunk_size
    const end = Math.min(start + chunk_size, file.size)
    const blob = file.slice(start, end)
    await uploadChunk(batchId, upload_id, i, blob)
    onBytes(end - start)
  }
  await completeChunkUpload(batchId, upload_id, false)
}

function openPerspective(row: ImportedPage) {
  perspectivePageId.value = row.id
  perspectiveVisible.value = true
}

async function onPerspectiveApplied() {
  await loadPages()
}

async function reprocess(row: ImportBatch) {
  await processImportBatch(row.id)
  ElMessage.success('已提交重新处理')
  loadBatches()
}

async function removeBatch(row: ImportBatch) {
  await ElMessageBox.confirm('删除该批次将同时删除其答卷页、题块与异常记录，确认继续？', '提示', { type: 'warning' })
  await deleteImportBatch(row.id)
  ElMessage.success('已删除')
  loadBatches()
}

async function openPages(row: ImportBatch) {
  activeBatch.value = row
  pagesVisible.value = true
  await loadPages()
}

async function loadPages() {
  if (!activeBatch.value) return
  pagesLoading.value = true
  try {
    const res = await listBatchPages(activeBatch.value.id)
    pages.value = res.data
  } finally {
    pagesLoading.value = false
  }
}

async function promptExamNumber(row: ImportedPage) {
  const { value } = await ElMessageBox.prompt('请输入该答卷对应的考号', '手动指定考号', {
    inputValue: row.exam_number_ocr || '',
    inputPattern: /^\S+$/,
    inputErrorMessage: '考号不能为空',
  })
  await setPageExamNumber(row.id, value.trim())
  ElMessage.success('考号已更新')
  await loadPages()
}

async function recut(row: ImportedPage) {
  await recutPage(row.id)
  ElMessage.success('已按模板重新切割')
  await loadPages()
}

async function previewPage(row: ImportedPage) {
  previewVisible.value = true
  previewLoading.value = true
  previewBlocks.value = []
  blockImages.value = {}
  previewImageUrl.value = ''
  try {
    if (row.preprocessed_image_path) {
      previewImageUrl.value = await getPageImageUrl(row.id)
    }
    const res = await listPageBlocks(row.id)
    previewBlocks.value = res.data
    for (const b of previewBlocks.value) {
      if (b.image_path) {
        try {
          blockImages.value[b.id] = await getBlockImageUrl(b.id)
        } catch {
          // ignore single block failure
        }
      }
    }
  } finally {
    previewLoading.value = false
  }
}

function clearPreview() {
  ;[previewImageUrl.value, ...Object.values(blockImages.value)].forEach((u) => u && URL.revokeObjectURL(u))
  previewImageUrl.value = ''
  blockImages.value = {}
  previewBlocks.value = []
}

onMounted(async () => {
  stopImportProgress = realtime.on('import_progress', handleImportProgress)
  await loadExams()
  syncRealtimeTopic()
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  stopImportProgress?.()
  if (realtimeTopic) realtime.unsubscribe(realtimeTopic)
  clearPreview()
})
</script>

<style scoped>
.import-center {
  max-width: 1200px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.upload-actions {
  margin-top: 16px;
}
.upload-progress {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.muted {
  color: #909399;
  font-size: 12px;
}
.preview-wrap {
  display: flex;
  gap: 16px;
  min-height: 60vh;
}
.preview-main {
  flex: 2;
  overflow: auto;
  border: 1px solid #ebeef5;
  display: flex;
  justify-content: center;
  align-items: flex-start;
}
.preview-img {
  max-width: 100%;
}
.preview-side {
  flex: 1;
  overflow: auto;
  border: 1px solid #ebeef5;
  padding: 12px;
}
.block-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.block-item {
  border: 1px solid #ebeef5;
  padding: 4px;
  text-align: center;
}
.block-item img {
  max-width: 100%;
  max-height: 90px;
}
.block-label {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}
</style>