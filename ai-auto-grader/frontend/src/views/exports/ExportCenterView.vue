<template>
  <div>
    <div class="toolbar">
      <h2>导出中心</h2>
    </div>

    <el-card shadow="never" class="panel">
      <el-form label-width="120px" style="max-width: 560px">
        <el-form-item label="选择考试">
          <el-select v-model="examId" filterable placeholder="请选择考试" style="width: 100%" @change="onExamChange">
            <el-option v-for="e in exams" :key="e.id" :label="e.name" :value="e.id">
              <span>{{ e.name }}</span>
              <span class="option-sub">{{ e.subject }} · {{ e.grade }}</span>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-empty v-if="!examId" description="请选择考试后进行导出" />

    <template v-else>
      <!-- F10-01 成绩明细 -->
      <el-card shadow="never" class="panel">
        <template #header><span>成绩明细表（Excel）</span></template>
        <p class="desc">导出含考号、姓名、班级、各题得分、总分与排名的成绩明细表。</p>
        <el-button type="primary" :loading="busy.grade" @click="doGradeDetail">导出成绩明细</el-button>
      </el-card>

      <!-- F10-03 学情报表 -->
      <el-card shadow="never" class="panel">
        <template #header><span>学情报表</span></template>
        <p class="desc">多维度学情分析（年级总览、班级对比、题目分析、知识点掌握）。Excel 便于二次加工，HTML 可直接打印或另存为 PDF。</p>
        <el-button type="primary" :loading="busy.reportXlsx" @click="doReport('xlsx')">导出 Excel</el-button>
        <el-button :loading="busy.reportHtml" @click="doReport('html')">导出可打印 HTML</el-button>
      </el-card>

      <!-- F10-02 答卷/错题图片 -->
      <el-card shadow="never" class="panel">
        <template #header><span>答卷 / 错题图片（ZIP）</span></template>
        <p class="desc">按题目或标记类别打包题块图片，压缩包内含 manifest.csv 索引。</p>
        <el-form :inline="true" style="margin-bottom: 12px">
          <el-form-item label="题目">
            <el-input v-model="images.question_number" clearable placeholder="如 21 或 21-1" style="width: 160px" />
          </el-form-item>
          <el-form-item label="标记类别">
            <el-select v-model="images.mark" clearable placeholder="全部" style="width: 160px">
              <el-option label="优秀作答" value="excellent" />
              <el-option label="典型错误" value="typical_error" />
              <el-option label="空白" value="blank" />
            </el-select>
          </el-form-item>
          <el-form-item label="学生">
            <el-select v-model="images.student_id" clearable filterable placeholder="全部" style="width: 200px">
              <el-option
                v-for="s in students"
                :key="s.student_id"
                :label="`${s.name}（${s.exam_number}）`"
                :value="s.student_id"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <el-button type="primary" :loading="busy.images" @click="doImages">导出图片包</el-button>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getExams, getExamStudents, type Exam } from '@/api/exams'
import { exportGradeDetail, exportReport, exportAnswerImages, type AnswerImagesQuery } from '@/api/exports'

interface StudentItem {
  student_id: string
  name: string
  exam_number: string
}

const exams = ref<Exam[]>([])
const students = ref<StudentItem[]>([])
const examId = ref('')
const images = reactive<AnswerImagesQuery>({ question_number: '', mark: undefined, student_id: undefined })
const busy = reactive({ grade: false, reportXlsx: false, reportHtml: false, images: false })

const currentExam = () => exams.value.find((e) => e.id === examId.value)

async function loadExams() {
  const res = await getExams()
  exams.value = res.data
}

async function onExamChange() {
  students.value = []
  images.question_number = ''
  images.mark = undefined
  images.student_id = undefined
  if (!examId.value) return
  const res = await getExamStudents(examId.value)
  students.value = res.data as unknown as StudentItem[]
}

async function doGradeDetail() {
  busy.grade = true
  try {
    const name = await exportGradeDetail(examId.value, currentExam()?.name)
    ElMessage.success(`已导出：${name}`)
  } finally {
    busy.grade = false
  }
}

async function doReport(format: 'xlsx' | 'html') {
  const key = format === 'xlsx' ? 'reportXlsx' : 'reportHtml'
  busy[key] = true
  try {
    const name = await exportReport(examId.value, format, currentExam()?.name)
    ElMessage.success(`已导出：${name}`)
  } finally {
    busy[key] = false
  }
}

async function doImages() {
  busy.images = true
  try {
    const params: AnswerImagesQuery = {}
    if (images.question_number) params.question_number = images.question_number
    if (images.mark) params.mark = images.mark
    if (images.student_id) params.student_id = images.student_id
    const name = await exportAnswerImages(examId.value, params, currentExam()?.name)
    ElMessage.success(`已导出：${name}`)
  } finally {
    busy.images = false
  }
}

onMounted(loadExams)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel {
  margin-bottom: 16px;
}
.desc {
  color: #909399;
  font-size: 13px;
  margin: 0 0 12px;
}
.option-sub {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}
</style>