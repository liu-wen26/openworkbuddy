<template>
  <div>
    <div class="toolbar">
      <h2>考试管理</h2>
      <el-button type="primary" @click="goCreate" v-if="canManage">新建考试</el-button>
    </div>
    <el-table :data="exams" v-loading="loading" border>
      <el-table-column prop="name" label="考试名称" />
      <el-table-column prop="subject" label="学科" width="100" />
      <el-table-column prop="grade" label="年级" width="100" />
      <el-table-column prop="exam_type" label="类型" width="120">
        <template #default="{ row }">
          {{ typeText(row.exam_type) }}
        </template>
      </el-table-column>
      <el-table-column prop="total_score" label="总分" width="80" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="原试卷" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.original_paper_path" type="success">已上传</el-tag>
          <el-tag v-else type="info">未上传</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button link type="primary" @click="goDetail(row.id)">详情</el-button>
          <el-button link type="primary" @click="goEdit(row.id)" v-if="canManage && row.status !== 'locked' && row.status !== 'archived'">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)" v-if="canManage && row.status !== 'locked' && row.status !== 'archived'">删除</el-button>
          <el-button link type="warning" @click="handleCopy(row.id)" v-if="canManage">复制</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getExams, deleteExam, copyExam, type Exam } from '@/api/exams'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const exams = ref<Exam[]>([])
const loading = ref(false)

const canManage = computed(() => ['super_admin', 'exam_admin'].includes(auth.user?.role || ''))

async function load() {
  loading.value = true
  const res = await getExams()
  exams.value = res.data
  loading.value = false
}

function goCreate() {
  router.push('/exams/create')
}
function goEdit(id: string) {
  router.push(`/exams/${id}/edit`)
}
function goDetail(id: string) {
  router.push(`/exams/${id}`)
}

async function handleCopy(id: string) {
  await copyExam(id)
  ElMessage.success('复制成功')
  load()
}

async function handleDelete(row: Exam) {
  await ElMessageBox.confirm(`确定删除考试「${row.name}」吗？`, '提示', { type: 'warning' })
  await deleteExam(row.id)
  ElMessage.success('删除成功')
  load()
}

function typeText(type: string) {
  const map: Record<string, string> = {
    weekly: '周测', monthly: '月考', midterm: '期中', final: '期末', mock: '模拟',
  }
  return map[type] || type
}

function statusText(status: string) {
  const map: Record<string, string> = {
    draft: '草稿', ready: '就绪', importing: '导入中', grading: '阅卷中', locked: '已锁定', archived: '已归档',
  }
  return map[status] || status
}

function statusType(status: string) {
  const map: Record<string, any> = {
    draft: 'info', ready: 'primary', importing: 'warning', grading: 'success', locked: 'danger', archived: '',
  }
  return map[status] || ''
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
