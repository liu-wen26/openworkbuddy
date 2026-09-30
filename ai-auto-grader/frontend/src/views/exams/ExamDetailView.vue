<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h2>{{ exam?.name }}</h2>
      <div>
        <el-button v-if="canManage && exam?.status === 'grading'" type="warning" @click="lock">锁定成绩</el-button>
        <el-button v-if="canManage && exam?.status === 'locked'" type="success" @click="unlock">解锁</el-button>
        <el-button @click="router.back()">返回</el-button>
      </div>
    </div>

    <el-descriptions :column="3" border>
      <el-descriptions-item label="学科">{{ exam?.subject }}</el-descriptions-item>
      <el-descriptions-item label="年级">{{ exam?.grade }}</el-descriptions-item>
      <el-descriptions-item label="类型">{{ typeText }}</el-descriptions-item>
      <el-descriptions-item label="总分">{{ exam?.total_score }}</el-descriptions-item>
      <el-descriptions-item label="及格线">{{ exam?.pass_score }}</el-descriptions-item>
      <el-descriptions-item label="优秀线">{{ exam?.excellent_score }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="statusType">{{ statusText }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="原试卷">
        <el-tag v-if="exam?.original_paper_path" type="success">已上传</el-tag>
        <el-tag v-else type="info">未上传</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <el-tabs v-model="activeTab" style="margin-top: 20px;">
      <el-tab-pane label="原试卷" name="paper">
        <div v-if="canManage && exam?.status !== 'locked' && exam?.status !== 'archived'">
          <el-upload
            :show-file-list="false"
            :before-upload="beforeUploadPaper"
            :http-request="uploadPaper"
            accept=".pdf"
          >
            <el-button type="primary">上传/替换原试卷 PDF</el-button>
          </el-upload>
          <el-button
            v-if="exam?.original_paper_path"
            type="danger"
            style="margin-top: 10px"
            @click="deletePaper"
          >删除原试卷</el-button>
        </div>
        <div v-if="exam?.original_paper_path" style="margin-top: 16px;">
          <el-button type="primary" @click="previewPaper">在线预览原试卷</el-button>
          <a :href="downloadUrl" target="_blank" download>
            <el-button style="margin-left: 10px">下载原试卷</el-button>
          </a>
        </div>
        <div v-else style="margin-top: 16px; color: #909399;">尚未上传原试卷</div>
      </el-tab-pane>

      <el-tab-pane label="考生花名册" name="students">
        <div v-if="canManage && exam?.status !== 'locked' && exam?.status !== 'archived'">
          <el-upload
            :show-file-list="false"
            :before-upload="beforeUploadStudent"
            :http-request="importStudent"
            accept=".xlsx,.xls"
          >
            <el-button type="primary">导入 Excel 花名册</el-button>
          </el-upload>
          <p style="color: #909399; font-size: 12px; margin-top: 8px;">Excel 表头必须为：考号、姓名、班级</p>
        </div>
        <el-table :data="students" border style="margin-top: 16px;">
          <el-table-column prop="exam_number" label="考号" />
          <el-table-column prop="name" label="姓名" />
          <el-table-column prop="class_name" label="班级" />
          <el-table-column label="总分" width="100">
            <template #default="{ row }">
              <span v-if="row.total_score != null">{{ row.total_score }}</span>
              <span v-else style="color: #c0c4cc;">—</span>
            </template>
          </el-table-column>
          <el-table-column label="年级排名" width="100">
            <template #default="{ row }">
              <span v-if="row.rank_in_grade != null">{{ row.rank_in_grade }}</span>
              <span v-else style="color: #c0c4cc;">—</span>
            </template>
          </el-table-column>
          <el-table-column label="班级排名" width="100">
            <template #default="{ row }">
              <span v-if="row.rank_in_class != null">{{ row.rank_in_class }}</span>
              <span v-else style="color: #c0c4cc;">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_absent" label="缺考" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_absent ? 'danger' : 'success'">{{ row.is_absent ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="previewVisible" title="原试卷预览" width="80%" top="5vh">
      <iframe v-if="previewUrl" :src="previewUrl" style="width: 100%; height: 70vh; border: none;"></iframe>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getExam,
  uploadOriginalPaper,
  deleteOriginalPaper,
  importStudents,
  getExamStudents,
  lockExam,
  unlockExam,
  type Exam,
} from '@/api/exams'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const examId = route.params.id as string

const loading = ref(false)
const exam = ref<Exam | null>(null)
const activeTab = ref('paper')
const students = ref<Array<any>>([])
const previewVisible = ref(false)
const previewUrl = ref('')

const canManage = computed(() => ['super_admin', 'exam_admin'].includes(auth.user?.role || ''))
const typeText = computed(() => {
  const map: Record<string, string> = {
    weekly: '周测', monthly: '月考', midterm: '期中', final: '期末', mock: '模拟',
  }
  return map[exam.value?.exam_type || ''] || exam.value?.exam_type
})
const statusText = computed(() => {
  const map: Record<string, string> = {
    draft: '草稿', ready: '就绪', importing: '导入中', grading: '阅卷中', locked: '已锁定', archived: '已归档',
  }
  return map[exam.value?.status || ''] || exam.value?.status
})
const statusType = computed(() => {
  const map: Record<string, any> = {
    draft: 'info', ready: 'primary', importing: 'warning', grading: 'success', locked: 'danger', archived: '',
  }
  return map[exam.value?.status || ''] || ''
})
const downloadUrl = computed(() => `/api/v1/exams/${examId}/original-paper/download`)

async function load() {
  loading.value = true
  const [examRes, studentRes] = await Promise.all([getExam(examId), getExamStudents(examId)])
  exam.value = examRes.data
  students.value = studentRes.data
  loading.value = false
}

function beforeUploadPaper(file: File) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('仅支持 PDF 格式')
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

async function uploadPaper(options: any) {
  const res = await uploadOriginalPaper(examId, options.file)
  exam.value = res.data
  ElMessage.success('原试卷上传成功')
}

async function deletePaper() {
  const res = await deleteOriginalPaper(examId)
  exam.value = res.data
  ElMessage.success('原试卷已删除')
}

function previewPaper() {
  previewUrl.value = downloadUrl.value
  previewVisible.value = true
}

function beforeUploadStudent(file: File) {
  if (!file.name.toLowerCase().endsWith('.xlsx') && !file.name.toLowerCase().endsWith('.xls')) {
    ElMessage.error('仅支持 Excel 文件')
    return false
  }
  return true
}

async function importStudent(options: any) {
  const res = await importStudents(examId, options.file)
  const result = res.data
  ElMessage.success(`导入完成：成功 ${result.success} 条，失败 ${result.failed} 条`)
  if (result.errors.length) {
    result.errors.forEach((e) => ElMessage.warning(e))
  }
  const studentRes = await getExamStudents(examId)
  students.value = studentRes.data
}

async function lock() {
  const res = await lockExam(examId)
  exam.value = res.data
  ElMessage.success('考试已锁定')
}

async function unlock() {
  const res = await unlockExam(examId)
  exam.value = res.data
  ElMessage.success('考试已解锁')
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
</style>
