<template>
  <div>
    <div class="toolbar">
      <h2>考试归档</h2>
      <div class="toolbar-right">
        <el-checkbox v-model="includeRestored" @change="load">显示已恢复</el-checkbox>
        <el-button type="primary" @click="openCreate">归档考试</el-button>
      </div>
    </div>

    <el-table :data="archives" v-loading="loading" border>
      <el-table-column prop="exam_name" label="考试名称" min-width="200" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'archived' ? 'info' : 'success'">
            {{ row.status === 'archived' ? '已归档' : '已恢复' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="含原试卷" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.original_paper_included ? 'success' : 'info'">
            {{ row.original_paper_included ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="归档包大小" width="130">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="归档时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="恢复时间" width="180">
        <template #default="{ row }">{{ row.restored_at ? formatTime(row.restored_at) : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="230">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleDownload(row)">下载</el-button>
          <el-button v-if="row.status === 'archived'" link type="warning" @click="handleRestore(row)">恢复</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="归档考试" width="480px">
      <el-form label-width="90px">
        <el-form-item label="选择考试">
          <el-select v-model="selectedExamId" filterable placeholder="请选择要归档的考试" style="width: 100%">
            <el-option v-for="e in archivableExams" :key="e.id" :label="e.name" :value="e.id">
              <span>{{ e.name }}</span>
              <span class="option-sub">{{ e.subject }} · {{ e.grade }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-alert
          title="归档将打包原试卷、成绩明细与学情报告，并把考试状态置为「已归档」。"
          type="info"
          :closable="false"
          show-icon
        />
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="!selectedExamId" @click="handleCreate">确定归档</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listArchives, createArchive, restoreArchive, deleteArchive, downloadArchive, type ExamArchive } from '@/api/archives'
import { getExams, type Exam } from '@/api/exams'

const archives = ref<ExamArchive[]>([])
const exams = ref<Exam[]>([])
const loading = ref(false)
const includeRestored = ref(true)
const createVisible = ref(false)
const creating = ref(false)
const selectedExamId = ref('')

const archivableExams = computed(() => exams.value.filter((e) => e.status !== 'archived'))

function formatSize(bytes: number) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let i = 0
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function formatTime(value: string) {
  const d = new Date(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function load() {
  loading.value = true
  try {
    const [a, e] = await Promise.all([listArchives(includeRestored.value), getExams()])
    archives.value = a.data
    exams.value = e.data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  selectedExamId.value = ''
  createVisible.value = true
}

async function handleCreate() {
  creating.value = true
  try {
    await createArchive(selectedExamId.value)
    ElMessage.success('归档完成')
    createVisible.value = false
    load()
  } finally {
    creating.value = false
  }
}

async function handleDownload(row: ExamArchive) {
  await downloadArchive(row.id, row.exam_name)
}

async function handleRestore(row: ExamArchive) {
  await ElMessageBox.confirm(`确定恢复考试「${row.exam_name}」吗？恢复后可继续编辑。`, '提示', { type: 'warning' })
  await restoreArchive(row.id)
  ElMessage.success('已恢复')
  load()
}

async function handleDelete(row: ExamArchive) {
  await ElMessageBox.confirm(`确定删除归档包「${row.exam_name}」吗？此操作不可撤销。`, '警告', { type: 'warning' })
  await deleteArchive(row.id)
  ElMessage.success('已删除')
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
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.option-sub {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}
</style>