<template>
  <div>
    <h2>{{ isEdit ? '编辑考试' : '新建考试' }}</h2>
    <el-form :model="form" label-width="100px" style="max-width: 600px; margin-top: 20px;">
      <el-form-item label="考试名称">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="学科">
        <el-input v-model="form.subject" />
      </el-form-item>
      <el-form-item label="年级">
        <el-input v-model="form.grade" />
      </el-form-item>
      <el-form-item label="考试类型">
        <el-select v-model="form.exam_type" style="width: 100%">
          <el-option label="周测" value="weekly" />
          <el-option label="月考" value="monthly" />
          <el-option label="期中" value="midterm" />
          <el-option label="期末" value="final" />
          <el-option label="模拟" value="mock" />
        </el-select>
      </el-form-item>
      <el-form-item label="总分">
        <el-input-number v-model="form.total_score" :min="1" style="width: 100%" />
      </el-form-item>
      <el-form-item label="及格线">
        <el-input-number v-model="form.pass_score" :min="0" style="width: 100%" />
      </el-form-item>
      <el-form-item label="优秀线">
        <el-input-number v-model="form.excellent_score" :min="0" style="width: 100%" />
      </el-form-item>
      <el-form-item label="答题卡模板">
        <el-select v-model="form.answer_card_template_id" placeholder="请选择（可选）" clearable style="width: 100%">
          <el-option v-for="tpl in templates" :key="tpl.id" :label="tpl.name" :value="tpl.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="阅卷开始">
        <el-date-picker v-model="form.grading_start_at" type="datetime" style="width: 100%" />
      </el-form-item>
      <el-form-item label="阅卷结束">
        <el-date-picker v-model="form.grading_end_at" type="datetime" style="width: 100%" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="submit" :loading="saving">保存</el-button>
        <el-button @click="router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createExam, updateExam, getExam, type ExamForm } from '@/api/exams'
import request from '@/api/request'

const route = useRoute()
const router = useRouter()
const isEdit = ref(!!route.params.id)
const saving = ref(false)
const templates = ref<Array<{ id: string; name: string }>>([])

const form = reactive<ExamForm>({
  name: '',
  subject: '',
  grade: '',
  exam_type: 'monthly',
  total_score: 100,
  pass_score: 60,
  excellent_score: 85,
  answer_card_template_id: undefined,
  grading_start_at: undefined,
  grading_end_at: undefined,
})

async function loadTemplates() {
  const res = await request.get('/templates')
  templates.value = res.data
}

async function loadExam() {
  if (!isEdit.value) return
  const res = await getExam(route.params.id as string)
  const data = res.data
  Object.assign(form, {
    name: data.name,
    subject: data.subject,
    grade: data.grade,
    exam_type: data.exam_type,
    total_score: data.total_score,
    pass_score: data.pass_score,
    excellent_score: data.excellent_score,
    answer_card_template_id: data.answer_card_template_id,
    grading_start_at: data.grading_start_at,
    grading_end_at: data.grading_end_at,
  })
}

async function submit() {
  saving.value = true
  try {
    if (isEdit.value) {
      await updateExam(route.params.id as string, form)
    } else {
      await createExam(form)
    }
    ElMessage.success('保存成功')
    router.push('/exams')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadTemplates()
  loadExam()
})
</script>
