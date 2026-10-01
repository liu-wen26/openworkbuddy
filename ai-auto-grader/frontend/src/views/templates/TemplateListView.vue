<template>
  <div>
    <div class="toolbar">
      <h2>答题卡模板库</h2>
      <div class="actions">
        <el-input
          v-model="keyword"
          placeholder="搜索模板名称"
          clearable
          style="width: 240px"
          @keyup.enter="load"
          @clear="load"
        >
          <template #append>
            <el-button :icon="Search" @click="load" />
          </template>
        </el-input>
        <el-upload
          :show-file-list="false"
          :before-upload="beforeImport"
          :http-request="handleImport"
          accept=".json"
        >
          <el-button :icon="Upload">导入备份</el-button>
        </el-upload>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建模板</el-button>
      </div>
    </div>

    <el-table :data="templates" v-loading="loading" border>
      <el-table-column prop="name" label="模板名称" min-width="180" />
      <el-table-column label="卡面来源" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source_type === 'annotated' ? 'success' : 'info'">
            {{ row.source_type === 'annotated' ? '原版答题卡标注' : '系统生成卡面' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="subject" label="学科" width="100" />
      <el-table-column prop="title" label="卡面标题" width="140" />
      <el-table-column label="纸张" width="100">
        <template #default="{ row }">{{ row.paper_size }}</template>
      </el-table-column>
      <el-table-column label="页数" width="80">
        <template #default="{ row }">{{ row.page_count }}</template>
      </el-table-column>
      <el-table-column label="印刷" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.duplex ? 'warning' : 'info'">
            {{ row.duplex ? '双面' : '单面' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="考号" width="120">
        <template #default="{ row }">
          {{ row.exam_number_digits }}位 / {{ row.exam_number_mode === 'omr' ? 'OMR' : 'OCR' }}
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="180">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="330" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="goDesign(row.id)">设计</el-button>
          <el-button link type="primary" @click="handleCopy(row)">复制</el-button>
          <el-button link type="success" @click="handleExportPdf(row)">导出PDF</el-button>
          <el-button link type="info" @click="handleBackup(row)">备份</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="新建答题卡模板" width="520px">
      <el-form :model="createForm" label-width="90px">
        <el-form-item label="模板名称">
          <el-input v-model="createForm.name" placeholder="如：初三数学月考答题卡" />
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="createForm.subject" />
        </el-form-item>
        <el-form-item label="纸张大小">
          <el-radio-group v-model="createForm.paper_size">
            <el-radio-button value="A4">A4</el-radio-button>
            <el-radio-button value="A3">A3</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="印刷方式">
          <el-radio-group v-model="createForm.duplex">
            <el-radio-button :value="false">单面</el-radio-button>
            <el-radio-button :value="true">双面</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="页数">
          <el-input-number v-model="createForm.page_count" :min="1" :max="8" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建并设计</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Upload } from '@element-plus/icons-vue'
import {
  getTemplates,
  createTemplate,
  deleteTemplate,
  copyTemplate,
  backupTemplate,
  importTemplateBackup,
  exportTemplatePdf,
  type Template,
  type TemplateForm,
} from '@/api/templates'

const router = useRouter()
const templates = ref<Template[]>([])
const loading = ref(false)
const keyword = ref('')

const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive<Partial<TemplateForm>>({
  name: '',
  subject: '',
  paper_size: 'A4',
  duplex: false,
  page_count: 1,
})

async function load() {
  loading.value = true
  try {
    const res = await getTemplates(keyword.value || undefined)
    templates.value = res.data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.name = ''
  createForm.subject = ''
  createForm.paper_size = 'A4'
  createForm.duplex = false
  createForm.page_count = 1
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.name) {
    ElMessage.warning('请输入模板名称')
    return
  }
  creating.value = true
  try {
    const res = await createTemplate(createForm)
    ElMessage.success('创建成功')
    createVisible.value = false
    router.push(`/templates/${res.data.id}/design`)
  } finally {
    creating.value = false
  }
}

function goDesign(id: string) {
  router.push(`/templates/${id}/design`)
}

async function handleCopy(row: Template) {
  const res = await copyTemplate(row.id)
  ElMessage.success('复制成功')
  load()
  router.push(`/templates/${res.data.id}/design`)
}

async function handleDelete(row: Template) {
  await ElMessageBox.confirm(`确定删除模板「${row.name}」吗？`, '提示', { type: 'warning' })
  await deleteTemplate(row.id)
  ElMessage.success('删除成功')
  load()
}

async function handleExportPdf(row: Template) {
  const res = await exportTemplatePdf(row.id)
  downloadBlob(res.data, `${row.name}.pdf`)
}

async function handleBackup(row: Template) {
  const res = await backupTemplate(row.id)
  const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
  downloadBlob(blob, `${row.name}-backup.json`)
}

function beforeImport(file: File) {
  if (!file.name.toLowerCase().endsWith('.json')) {
    ElMessage.error('仅支持 JSON 备份文件')
    return false
  }
  return true
}

async function handleImport(options: any) {
  const text = await options.file.text()
  let payload: any
  try {
    payload = JSON.parse(text)
  } catch {
    ElMessage.error('备份文件解析失败')
    return
  }
  const res = await importTemplateBackup(payload)
  ElMessage.success('导入成功')
  load()
  router.push(`/templates/${res.data.id}/design`)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function formatTime(value: string) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
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
.actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>