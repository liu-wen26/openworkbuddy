<template>
  <div v-loading="loading">
    <div class="panel-toolbar">
      <div>
        <el-button type="primary" :icon="Plus" @click="addRow">添加题目</el-button>
        <el-button :icon="DocumentCopy" @click="pasteVisible = true">批量粘贴</el-button>
        <span class="hint">多选答案连写，如 ABD</span>
      </div>
      <el-button type="success" :loading="saving" @click="save">保存答案</el-button>
    </div>

    <el-table :data="answers" border>
      <el-table-column label="题号" width="160">
        <template #default="{ row }">
          <el-input v-model="row.question_number" placeholder="如 1" />
        </template>
      </el-table-column>
      <el-table-column label="正确答案">
        <template #default="{ row }">
          <el-input v-model="row.correct_options" placeholder="如 A / ABD" />
        </template>
      </el-table-column>
      <el-table-column label="分值" width="170">
        <template #default="{ row }">
          <el-input-number v-model="row.score" :min="0" :step="0.5" style="width: 100%" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ $index }">
          <el-button link type="danger" @click="answers.splice($index, 1)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无答案解析，请点击「添加题目」或「批量粘贴」</template>
    </el-table>

    <el-dialog v-model="pasteVisible" title="批量粘贴答案" width="560px">
      <p class="hint">
        每行一题，格式：<b>题号 答案 分值</b>（分值为可选项），例如
        <code>1 A 3</code>、<code>12 ABD 5</code>
      </p>
      <el-input
        v-model="pasteText"
        type="textarea"
        :rows="10"
        placeholder="1 A 3&#10;2 B 3&#10;3 ABD 5"
      />
      <template #footer>
        <el-button @click="pasteVisible = false">取消</el-button>
        <el-button type="primary" @click="applyPaste">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, DocumentCopy } from '@element-plus/icons-vue'
import {
  getChoiceAnswers,
  replaceChoiceAnswers,
  type ChoiceAnswer,
} from '@/api/templates'

const props = defineProps<{ templateId: string }>()

const answers = ref<ChoiceAnswer[]>([])
const loading = ref(false)
const saving = ref(false)
const pasteVisible = ref(false)
const pasteText = ref('')

async function load() {
  loading.value = true
  try {
    const res = await getChoiceAnswers(props.templateId)
    answers.value = res.data.map((a) => ({ ...a, score: Number(a.score) }))
  } finally {
    loading.value = false
  }
}

function addRow() {
  answers.value.push({
    question_number: String(answers.value.length + 1),
    correct_options: '',
    score: 5,
  })
}

function applyPaste() {
  const rows: ChoiceAnswer[] = []
  for (const line of pasteText.value.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const parts = trimmed.split(/[\s,，:：\t]+/)
    const [q, opt, score] = parts
    if (!q || !opt) continue
    rows.push({
      question_number: q,
      correct_options: opt.toUpperCase(),
      score: Number(score) || 0,
    })
  }
  if (!rows.length) {
    ElMessage.warning('未解析到有效数据')
    return
  }
  answers.value = rows
  pasteVisible.value = false
  pasteText.value = ''
  ElMessage.success(`已导入 ${rows.length} 道题`)
}

async function save() {
  const invalid = answers.value.find((a) => !a.question_number || !a.correct_options)
  if (invalid) {
    ElMessage.warning('存在题号或答案为空的行')
    return
  }
  saving.value = true
  try {
    await replaceChoiceAnswers(props.templateId, answers.value)
    ElMessage.success('答案已保存')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
code {
  background: #f5f7fa;
  padding: 1px 5px;
  border-radius: 3px;
  color: #e6a23c;
}
</style>