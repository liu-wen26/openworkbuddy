<template>
  <div v-loading="loading">
    <div class="panel-toolbar">
      <div>
        <el-button type="primary" :icon="Plus" @click="openEditor(-1)">添加评分规则</el-button>
        <span class="hint">用于非选择题 AI 预评与辅助阅卷</span>
      </div>
      <el-button type="success" :loading="saving" @click="save">保存配置</el-button>
    </div>

    <el-table :data="configs" border>
      <el-table-column prop="question_number" label="题号" width="120" />
      <el-table-column label="标准答案" min-width="200">
        <template #default="{ row }">
          <span class="ellipsis">{{ row.standard_answer || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="采分点" width="100">
        <template #default="{ row }">{{ (row.scoring_points || []).length }} 项</template>
      </el-table-column>
      <el-table-column label="置信阈值" width="110">
        <template #default="{ row }">{{ Number(row.confidence_threshold).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="误差阈值" width="110">
        <template #default="{ row }">{{ Number(row.score_tolerance) }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90">
        <template #default="{ row }">
          <el-switch v-model="row.enabled" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ $index }">
          <el-button link type="primary" @click="openEditor($index)">编辑</el-button>
          <el-button link type="danger" @click="configs.splice($index, 1)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无 AI 评分规则</template>
    </el-table>

    <el-dialog v-model="editVisible" :title="editIndex < 0 ? '新增评分规则' : '编辑评分规则'" width="640px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="题号">
          <el-input v-model="editForm.question_number" placeholder="如 21 或 21-1" />
        </el-form-item>
        <el-form-item label="标准答案">
          <el-input v-model="editForm.standard_answer" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="采分点">
          <el-input
            v-model="editForm.scoring_points_text"
            type="textarea"
            :rows="5"
            placeholder="每行一个采分点，例如：&#10;写出光合作用的反应式（2分）&#10;说明影响因素（3分）"
          />
        </el-form-item>
        <el-form-item label="扣分说明">
          <el-input v-model="editForm.deduction_notes" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="Prompt 模板">
          <el-input
            v-model="editForm.prompt_template"
            type="textarea"
            :rows="4"
            placeholder="留空则使用系统默认评卷提示词，可用 {{answer}} {{standard}} {{points}} 占位符"
          />
        </el-form-item>
        <el-form-item label="置信阈值">
          <el-input-number v-model="editForm.confidence_threshold" :min="0" :max="1" :step="0.05" />
          <span class="hint">低于该置信度的 AI 结果将转为人工复核</span>
        </el-form-item>
        <el-form-item label="误差阈值">
          <el-input-number v-model="editForm.score_tolerance" :min="0" :step="0.5" />
          <span class="hint">双评差值超过该值时进入仲裁</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="editForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEditor">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getAIConfigs,
  replaceAIConfigs,
  type AIScoringConfig,
} from '@/api/templates'

const props = defineProps<{ templateId: string }>()

const configs = ref<AIScoringConfig[]>([])
const loading = ref(false)
const saving = ref(false)

const editVisible = ref(false)
const editIndex = ref(-1)
const editForm = reactive({
  question_number: '',
  standard_answer: '',
  scoring_points_text: '',
  deduction_notes: '',
  prompt_template: '',
  confidence_threshold: 0.7,
  score_tolerance: 0,
  enabled: true,
})

async function load() {
  loading.value = true
  try {
    const res = await getAIConfigs(props.templateId)
    configs.value = res.data.map((c) => ({
      ...c,
      confidence_threshold: Number(c.confidence_threshold),
      score_tolerance: Number(c.score_tolerance),
      scoring_points: c.scoring_points || [],
    }))
  } finally {
    loading.value = false
  }
}

function openEditor(index: number) {
  editIndex.value = index
  const src = index >= 0 ? configs.value[index] : null
  editForm.question_number = src?.question_number || ''
  editForm.standard_answer = src?.standard_answer || ''
  editForm.scoring_points_text = (src?.scoring_points || []).join('\n')
  editForm.deduction_notes = src?.deduction_notes || ''
  editForm.prompt_template = src?.prompt_template || ''
  editForm.confidence_threshold = src ? Number(src.confidence_threshold) : 0.7
  editForm.score_tolerance = src ? Number(src.score_tolerance) : 0
  editForm.enabled = src ? src.enabled : true
  editVisible.value = true
}

function confirmEditor() {
  if (!editForm.question_number) {
    ElMessage.warning('请填写题号')
    return
  }
  const data: AIScoringConfig = {
    question_number: editForm.question_number,
    standard_answer: editForm.standard_answer || null,
    scoring_points: editForm.scoring_points_text
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean),
    deduction_notes: editForm.deduction_notes || null,
    prompt_template: editForm.prompt_template || null,
    confidence_threshold: editForm.confidence_threshold,
    score_tolerance: editForm.score_tolerance,
    enabled: editForm.enabled,
  }
  if (editIndex.value >= 0) {
    configs.value[editIndex.value] = { ...configs.value[editIndex.value], ...data }
  } else {
    configs.value.push(data)
  }
  editVisible.value = false
}

async function save() {
  const invalid = configs.value.find((c) => !c.question_number)
  if (invalid) {
    ElMessage.warning('存在题号为空的规则')
    return
  }
  saving.value = true
  try {
    await replaceAIConfigs(props.templateId, configs.value)
    ElMessage.success('AI 评分规则已保存')
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
.ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
</style>