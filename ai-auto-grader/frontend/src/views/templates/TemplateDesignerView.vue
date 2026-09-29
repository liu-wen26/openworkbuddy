<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div class="title">
        <h2>{{ tpl.name || '答题卡模板' }}</h2>
        <el-tag size="small">{{ tpl.paper_size }}</el-tag>
        <el-tag size="small" :type="tpl.duplex ? 'warning' : 'info'">{{ tpl.duplex ? '双面' : '单面' }}</el-tag>
      </div>
      <div>
        <el-button @click="router.push('/templates')">返回模板库</el-button>
        <el-button :loading="prechecking" @click="runPrecheck">预校验</el-button>
        <el-button type="success" @click="exportPdf">导出空白答题卡 PDF</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存模板</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ---------------- 设计器 ---------------- -->
      <el-tab-pane label="答题卡设计" name="design">
        <div class="design-tab">
          <!-- 左侧：基本设置 -->
          <aside class="side left">
            <h3>基本设置</h3>
            <el-form label-width="82px" size="small">
              <el-form-item label="模板名称"><el-input v-model="tpl.name" /></el-form-item>
              <el-form-item label="学科"><el-input v-model="tpl.subject" /></el-form-item>
              <el-form-item label="卡面标题"><el-input v-model="tpl.title" /></el-form-item>
              <el-form-item label="纸张大小">
                <el-radio-group v-model="tpl.paper_size">
                  <el-radio-button value="A4">A4</el-radio-button>
                  <el-radio-button value="A3">A3</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="印刷方式">
                <el-radio-group v-model="tpl.duplex">
                  <el-radio-button :value="false">单面</el-radio-button>
                  <el-radio-button :value="true">双面</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="页数">
                <el-input-number v-model="tpl.page_count" :min="1" :max="8" style="width: 100%" />
              </el-form-item>
              <el-form-item label="页边距(mm)">
                <div class="margins">
                  <el-input-number v-model="tpl.margin_top" :min="0" :max="50" controls-position="right" />
                  <el-input-number v-model="tpl.margin_bottom" :min="0" :max="50" controls-position="right" />
                  <el-input-number v-model="tpl.margin_left" :min="0" :max="50" controls-position="right" />
                  <el-input-number v-model="tpl.margin_right" :min="0" :max="50" controls-position="right" />
                  <span class="margins-tip">上 / 下 / 左 / 右</span>
                </div>
              </el-form-item>
            </el-form>

            <h3>考号与姓名</h3>
            <el-form label-width="82px" size="small">
              <el-form-item label="考号位数">
                <el-input-number v-model="tpl.exam_number_digits" :min="4" :max="16" style="width: 100%" />
              </el-form-item>
              <el-form-item label="考号模式">
                <el-radio-group v-model="tpl.exam_number_mode">
                  <el-radio-button value="omr">OMR 填涂</el-radio-button>
                  <el-radio-button value="ocr">手写 OCR</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="班级前缀">
                <el-switch v-model="tpl.class_prefix_enabled" />
              </el-form-item>
              <el-form-item label="姓名 OCR">
                <el-switch v-model="tpl.name_ocr_enabled" />
              </el-form-item>
            </el-form>

            <h3>图像预处理</h3>
            <el-form label-width="82px" size="small">
              <el-form-item label="倾斜阈值">
                <el-input-number v-model="tpl.tilt_threshold" :min="0" :max="45" style="width: 100%" />
              </el-form-item>
              <el-form-item label="透视矫正"><el-switch v-model="tpl.perspective_enabled" /></el-form-item>
              <el-form-item label="自动纠偏"><el-switch v-model="tpl.deskew_enabled" /></el-form-item>
            </el-form>

            <h3>样卷框选（可选）</h3>
            <p class="tip">上传真实答题卡图片作为底图，便于精准框选区域。样卷仅本地预览，不会上传服务器。</p>
            <el-upload
              :show-file-list="false"
              :before-upload="beforeUploadSample"
              :http-request="handleSample"
              accept="image/*"
            >
              <el-button size="small">上传样卷图片（第 {{ currentPage + 1 }} 页）</el-button>
            </el-upload>
            <el-button v-if="bgImage" size="small" type="danger" plain @click="clearSample">清除底图</el-button>
          </aside>

          <!-- 中间：画布 -->
          <section class="canvas-wrap">
            <div class="canvas-toolbar">
              <el-radio-group v-model="drawType" size="small">
                <el-radio-button value="">选择/移动</el-radio-button>
                <el-radio-button value="exam_number">考号区</el-radio-button>
                <el-radio-button value="name">姓名区</el-radio-button>
                <el-radio-button value="choice">选择题区</el-radio-button>
                <el-radio-button value="subjective">非选择题框</el-radio-button>
              </el-radio-group>
              <div class="page-nav" v-if="tpl.page_count > 1">
                <el-button size="small" :disabled="currentPage === 0" @click="currentPage--">上一页</el-button>
                <span>第 {{ currentPage + 1 }} / {{ tpl.page_count }} 页</span>
                <el-button size="small" :disabled="currentPage >= tpl.page_count - 1" @click="currentPage++">下一页</el-button>
              </div>
            </div>

            <div
              ref="canvasRef"
              class="canvas"
              :style="canvasStyle"
              @mousedown="onCanvasMouseDown"
            >
              <img v-if="bgImage" :src="bgImage" class="bg" alt="样卷底图" />
              <div class="margin-guide" :style="marginStyle"></div>
              <div
                v-for="item in pageRegions"
                :key="item.i"
                class="region"
                :class="[`t-${item.r.region_type}`, { selected: item.i === selectedIndex }]"
                :style="regionStyle(item.r)"
                @mousedown.stop="onRegionMouseDown($event, item.i)"
              >
                <span class="region-label">{{ regionLabel(item.r) }}</span>
                <template v-if="item.r.region_type === 'choice'">
                  <span v-for="(l, k) in optionLetters(item.r)" :key="k" class="bubble">{{ l }}</span>
                </template>
                <span
                  v-if="item.i === selectedIndex"
                  class="handle"
                  @mousedown.stop="onHandleMouseDown($event, item.i)"
                ></span>
              </div>
            </div>
            <p class="tip">按住拖拽绘制「{{ drawTypeText }}」；点击区域可整体移动，拖动右下角小方块可缩放。</p>
          </section>

          <!-- 右侧：区域属性 -->
          <aside class="side right">
            <h3>区域属性</h3>
            <div v-if="selectedRegion" class="region-form">
              <el-form label-width="76px" size="small">
                <el-form-item label="类型">
                  <el-tag>{{ regionTypeText(selectedRegion.region_type) }}</el-tag>
                </el-form-item>
                <el-form-item v-if="selectedRegion.region_type !== 'name'" label="题号">
                  <el-input v-model="selectedRegion.question_number" @input="onQuestionNumberInput(selectedRegion)" />
                </el-form-item>
                <el-form-item v-if="selectedRegion.region_type === 'subjective'" label="子题号">
                  <el-input v-model="selectedRegion.sub_question_number" />
                </el-form-item>
                <el-form-item v-if="selectedRegion.region_type !== 'name'" label="分值">
                  <el-input-number v-model="selectedRegion.max_score" :min="0" :step="0.5" style="width: 100%" />
                </el-form-item>
                <template v-if="selectedRegion.region_type === 'choice'">
                  <el-form-item label="选项数">
                    <el-input-number v-model="selectedRegion.options_count" :min="2" :max="10" style="width: 100%" />
                  </el-form-item>
                  <el-form-item label="多选"><el-switch v-model="selectedRegion.allow_multiple" /></el-form-item>
                  <el-form-item label="标准答案">
                    <el-input v-model="choiceAnswerMap[selectedRegion.question_number || '']" placeholder="如 A / ABD" />
                  </el-form-item>
                </template>
                <el-form-item v-if="selectedRegion.region_type === 'exam_number'" label="填涂位数">
                  <el-input-number v-model="tpl.exam_number_digits" :min="4" :max="16" style="width: 100%" />
                </el-form-item>
                <el-form-item label="知识点">
                  <el-select
                    v-model="selectedRegion.knowledge_tags"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    placeholder="输入后回车添加"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-form>
              <el-button size="small" type="danger" plain @click="removeRegion(selectedIndex)">删除该区域</el-button>
            </div>
            <p v-else class="tip">点击画布中的区域以编辑属性。</p>

            <h3>区域列表（共 {{ pageRegions.length }} 个）</h3>
            <ul class="region-list">
              <li
                v-for="item in pageRegions"
                :key="item.i"
                :class="{ active: item.i === selectedIndex }"
                @click="selectedIndex = item.i"
              >
                <span class="dot" :class="`t-${item.r.region_type}`"></span>
                {{ regionLabel(item.r) }}
                <el-icon class="del" @click.stop="removeRegion(item.i)"><Delete /></el-icon>
              </li>
            </ul>
          </aside>
        </div>
      </el-tab-pane>

      <!-- ---------------- 选择题答案 ---------------- -->
      <el-tab-pane label="选择题答案" name="choice">
        <ChoiceAnswerPanel :template-id="templateId" />
      </el-tab-pane>

      <!-- ---------------- AI 评分规则 ---------------- -->
      <el-tab-pane label="AI 评分规则" name="ai">
        <AIConfigPanel :template-id="templateId" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="precheckVisible" title="模板预校验结果" width="620px">
      <div v-if="precheckResult" class="precheck">
        <el-alert
          :type="precheckResult.passed ? 'success' : 'error'"
          :closable="false"
          show-icon
          :title="precheckResult.passed ? '校验通过（可正常打印与导入）' : '校验未通过，请先修复错误项'"
          :description="`错误 ${precheckResult.error_count} 项，警告 ${precheckResult.warning_count} 项`"
        />
        <ul v-if="precheckResult.issues.length" class="issue-list">
          <li v-for="(issue, i) in precheckResult.issues" :key="i">
            <el-tag :type="issue.level === 'error' ? 'danger' : 'warning'" size="small">
              {{ issue.level === 'error' ? '错误' : '警告' }}
            </el-tag>
            <span>{{ issue.message }}</span>
          </li>
        </ul>
        <p v-else class="tip">未发现任何问题。</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import {
  getTemplate,
  updateTemplate,
  replaceRegions,
  getChoiceAnswers,
  replaceChoiceAnswers,
  exportTemplatePdf,
  precheckTemplate,
  type RegionType,
  type TemplateRegion,
  type PrecheckResult,
} from '@/api/templates'
import ChoiceAnswerPanel from './components/ChoiceAnswerPanel.vue'
import AIConfigPanel from './components/AIConfigPanel.vue'

const route = useRoute()
const router = useRouter()
const templateId = route.params.id as string

const loading = ref(false)
const saving = ref(false)
const prechecking = ref(false)
const precheckVisible = ref(false)
const precheckResult = ref<PrecheckResult | null>(null)
const activeTab = ref('design')

const tpl = reactive({
  name: '',
  subject: '',
  title: '答题卡',
  paper_size: 'A4' as 'A3' | 'A4',
  duplex: false,
  page_count: 1,
  margin_top: 10,
  margin_bottom: 10,
  margin_left: 10,
  margin_right: 10,
  exam_number_digits: 9,
  exam_number_mode: 'omr' as 'omr' | 'ocr',
  class_prefix_enabled: false,
  name_ocr_enabled: false,
  tilt_threshold: 5,
  perspective_enabled: true,
  deskew_enabled: true,
  description: '',
})

const regions = ref<TemplateRegion[]>([])
const currentPage = ref(0)
const drawType = ref<RegionType | ''>('')
const selectedIndex = ref(-1)

const bgImages = reactive<Record<number, string>>({})
const bgImage = computed(() => bgImages[currentPage.value] || '')

const choiceAnswerMap = reactive<Record<string, string>>({})

// ---------- 画布尺寸 ----------
const CANVAS_WIDTH = 560
const PAGE_MM = { A4: { w: 210, h: 297 }, A3: { w: 297, h: 420 } }
const paperMm = computed(() => PAGE_MM[tpl.paper_size])
const canvasHeight = computed(() => Math.round((CANVAS_WIDTH * paperMm.value.h) / paperMm.value.w))
const canvasStyle = computed(() => ({
  width: `${CANVAS_WIDTH}px`,
  height: `${canvasHeight.value}px`,
}))
const marginStyle = computed(() => {
  const mm = paperMm.value
  return {
    left: `${(tpl.margin_left / mm.w) * 100}%`,
    right: `${(tpl.margin_right / mm.w) * 100}%`,
    top: `${(tpl.margin_top / mm.h) * 100}%`,
    bottom: `${(tpl.margin_bottom / mm.h) * 100}%`,
  }
})

const canvasRef = ref<HTMLElement | null>(null)

// ---------- 区域派生数据 ----------
const pageRegions = computed(() =>
  regions.value.map((r, i) => ({ r, i })).filter(({ r }) => r.page_index === currentPage.value)
)
const selectedRegion = computed(() =>
  selectedIndex.value >= 0 ? regions.value[selectedIndex.value] : null
)

function regionStyle(r: TemplateRegion) {
  return {
    left: `${r.x / 10}%`,
    top: `${r.y / 10}%`,
    width: `${r.width / 10}%`,
    height: `${r.height / 10}%`,
  }
}

function optionLetters(r: TemplateRegion) {
  const n = Math.min(r.options_count || 4, 6)
  return Array.from({ length: n }, (_, i) => String.fromCharCode(65 + i))
}

const REGION_TEXT: Record<string, string> = {
  exam_number: '考号区',
  name: '姓名区',
  choice: '选择题区',
  subjective: '非选择题框',
}
function regionTypeText(t: string) {
  return REGION_TEXT[t] || t
}
function regionLabel(r: TemplateRegion) {
  const base = REGION_TEXT[r.region_type] || r.region_type
  if (!r.question_number) return base
  const sub = r.sub_question_number ? `-${r.sub_question_number}` : ''
  return `${base} ${r.question_number}${sub}`
}
const drawTypeText = computed(() => (drawType.value ? regionTypeText(drawType.value) : '区域'))

// ---------- 坐标换算 ----------
function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), max)
}
function toRel(e: MouseEvent) {
  const el = canvasRef.value!
  const rect = el.getBoundingClientRect()
  return {
    x: clamp(((e.clientX - rect.left) / rect.width) * 1000, 0, 1000),
    y: clamp(((e.clientY - rect.top) / rect.height) * 1000, 0, 1000),
  }
}

// ---------- 拖拽状态机 ----------
type DragMode = 'none' | 'draw' | 'move' | 'resize'
let dragMode: DragMode = 'none'
let startRel = { x: 0, y: 0 }
let originRegion: TemplateRegion | null = null

function addListeners() {
  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
}
function removeListeners() {
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
}

function onCanvasMouseDown(e: MouseEvent) {
  const type = drawType.value
  if (!type) return
  const rel = toRel(e)
  startRel = rel
  dragMode = 'draw'
  regions.value.push({
    page_index: currentPage.value,
    region_type: type,
    question_number: '',
    sub_question_number: '',
    max_score: 0,
    x: rel.x,
    y: rel.y,
    width: 0,
    height: 0,
    options_count: 4,
    allow_multiple: false,
    knowledge_tags: [],
    partial_score_rules: null,
    config: null,
  })
  selectedIndex.value = regions.value.length - 1
  addListeners()
}

function onRegionMouseDown(e: MouseEvent, index: number) {
  selectedIndex.value = index
  if (dragMode !== 'none') return
  startRel = toRel(e)
  originRegion = { ...regions.value[index] }
  dragMode = 'move'
  addListeners()
}

function onHandleMouseDown(e: MouseEvent, index: number) {
  selectedIndex.value = index
  startRel = toRel(e)
  originRegion = { ...regions.value[index] }
  dragMode = 'resize'
  addListeners()
}

function onWindowMouseMove(e: MouseEvent) {
  if (dragMode === 'none') return
  const rel = toRel(e)
  const r = regions.value[selectedIndex.value]
  if (!r) return
  if (dragMode === 'draw') {
    r.x = clamp(Math.min(startRel.x, rel.x), 0, 1000)
    r.y = clamp(Math.min(startRel.y, rel.y), 0, 1000)
    r.width = clamp(Math.abs(rel.x - startRel.x), 0, 1000 - r.x)
    r.height = clamp(Math.abs(rel.y - startRel.y), 0, 1000 - r.y)
  } else if (dragMode === 'move' && originRegion) {
    const dx = rel.x - startRel.x
    const dy = rel.y - startRel.y
    r.x = clamp(originRegion.x + dx, 0, 1000 - originRegion.width)
    r.y = clamp(originRegion.y + dy, 0, 1000 - originRegion.height)
  } else if (dragMode === 'resize' && originRegion) {
    r.width = clamp(rel.x - r.x, 5, 1000 - r.x)
    r.height = clamp(rel.y - r.y, 5, 1000 - r.y)
  }
}

function onWindowMouseUp() {
  if (dragMode === 'draw') {
    const r = regions.value[selectedIndex.value]
    if (r && (r.width < 8 || r.height < 8)) {
      regions.value.splice(selectedIndex.value, 1)
      selectedIndex.value = -1
    } else if (r) {
      autoNumber(r)
    }
  }
  dragMode = 'none'
  originRegion = null
  removeListeners()
}

function autoNumber(r: TemplateRegion) {
  if (r.region_type !== 'choice' && r.region_type !== 'subjective') return
  const nums = regions.value
    .filter((x) => x !== r && x.region_type === r.region_type && /^\d+$/.test(x.question_number || ''))
    .map((x) => parseInt(x.question_number as string, 10))
  r.question_number = String((nums.length ? Math.max(...nums) : 0) + 1)
}

function removeRegion(index: number) {
  regions.value.splice(index, 1)
  selectedIndex.value = -1
}

function onQuestionNumberInput(r: TemplateRegion) {
  // 选择题区域题号变化时，同步标准答案映射
  const key = r.question_number || ''
  if (r.region_type === 'choice' && key && !(key in choiceAnswerMap)) {
    choiceAnswerMap[key] = ''
  }
}

// ---------- 样卷底图 ----------
function beforeUploadSample(file: File) {
  if (!file.type.startsWith('image/')) {
    ElMessage.error('请上传图片格式的样卷')
    return false
  }
  return true
}
function handleSample(options: any) {
  bgImages[currentPage.value] = URL.createObjectURL(options.file)
}

function clearSample() {
  const url = bgImages[currentPage.value]
  if (url) URL.revokeObjectURL(url)
  delete bgImages[currentPage.value]
}

// ---------- 数据加载与保存 ----------
async function load() {
  loading.value = true
  try {
    const [tplRes, choiceRes] = await Promise.all([getTemplate(templateId), getChoiceAnswers(templateId)])
    const d = tplRes.data
    Object.assign(tpl, {
      name: d.name,
      subject: d.subject || '',
      title: d.title,
      paper_size: d.paper_size,
      duplex: d.duplex,
      page_count: d.page_count,
      margin_top: Number(d.margin_top),
      margin_bottom: Number(d.margin_bottom),
      margin_left: Number(d.margin_left),
      margin_right: Number(d.margin_right),
      exam_number_digits: d.exam_number_digits,
      exam_number_mode: d.exam_number_mode,
      class_prefix_enabled: d.class_prefix_enabled,
      name_ocr_enabled: d.name_ocr_enabled,
      tilt_threshold: Number(d.tilt_threshold),
      perspective_enabled: d.perspective_enabled,
      deskew_enabled: d.deskew_enabled,
      description: d.description || '',
    })
    regions.value = (d.regions || []).map((r) => ({
      ...r,
      page_index: Number(r.page_index),
      x: Number(r.x),
      y: Number(r.y),
      width: Number(r.width),
      height: Number(r.height),
      max_score: Number(r.max_score),
      options_count: Number(r.options_count),
      knowledge_tags: r.knowledge_tags || [],
    }))
    for (const a of choiceRes.data) {
      choiceAnswerMap[a.question_number] = a.correct_options
    }
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!tpl.name) {
    ElMessage.warning('请填写模板名称')
    return
  }
  saving.value = true
  try {
    await updateTemplate(templateId, { ...tpl })
    await replaceRegions(templateId, regions.value)
    await saveChoiceAnswersFromMap()
    ElMessage.success('模板已保存')
  } finally {
    saving.value = false
  }
}

async function saveChoiceAnswersFromMap() {
  const entries = Object.entries(choiceAnswerMap).filter(([q, a]) => q && a)
  if (!entries.length) return
  const existing = await getChoiceAnswers(templateId)
  const scoreMap = new Map(existing.data.map((a) => [a.question_number, Number(a.score)]))
  await replaceChoiceAnswers(
    templateId,
    entries.map(([question_number, correct_options]) => ({
      question_number,
      correct_options: correct_options.toUpperCase(),
      score: scoreMap.get(question_number) ?? 5,
    }))
  )
}

async function exportPdf() {
  const res = await exportTemplatePdf(templateId, tpl.title)
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${tpl.name || 'answer_card'}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

async function runPrecheck() {
  if (!tpl.name) {
    ElMessage.warning('请填写模板名称')
    return
  }
  prechecking.value = true
  try {
    // 预校验基于服务端最新配置，先静默保存当前改动
    await updateTemplate(templateId, { ...tpl })
    await replaceRegions(templateId, regions.value)
    const res = await precheckTemplate(templateId)
    precheckResult.value = res.data
    precheckVisible.value = true
  } finally {
    prechecking.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => {
  removeListeners()
  Object.values(bgImages).forEach((u) => URL.revokeObjectURL(u))
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.title h2 {
  margin: 0;
}
.design-tab {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.side {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
}
.side.left {
  width: 320px;
  flex-shrink: 0;
}
.side.right {
  width: 300px;
  flex-shrink: 0;
}
.side h3 {
  font-size: 14px;
  margin: 14px 0 8px;
  color: #303133;
}
.side h3:first-child {
  margin-top: 0;
}
.margins {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.margins-tip {
  grid-column: 1 / -1;
  font-size: 12px;
  color: #909399;
}
.canvas-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.canvas-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  margin-bottom: 10px;
  gap: 12px;
  flex-wrap: wrap;
}
.page-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}
.canvas {
  position: relative;
  background: #fff;
  border: 1px solid #dcdfe6;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  cursor: crosshair;
  user-select: none;
}
.bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
  opacity: 0.65;
  pointer-events: none;
}
.margin-guide {
  position: absolute;
  border: 1px dashed #c0c4cc;
  pointer-events: none;
}
.region {
  position: absolute;
  box-sizing: border-box;
  border: 1.5px solid #909399;
  background: rgba(64, 158, 255, 0.08);
  font-size: 11px;
  overflow: hidden;
  cursor: move;
}
.region.selected {
  border-width: 2px;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.35);
}
.region.t-exam_number {
  border-color: #1890ff;
  background: rgba(24, 144, 255, 0.1);
}
.region.t-name {
  border-color: #13c2c2;
  background: rgba(19, 194, 194, 0.1);
}
.region.t-choice {
  border-color: #fa8c16;
  background: rgba(250, 140, 22, 0.1);
}
.region.t-subjective {
  border-color: #eb2f96;
  background: rgba(235, 47, 150, 0.08);
}
.region-label {
  position: absolute;
  top: 1px;
  left: 3px;
  color: #606266;
  white-space: nowrap;
}
.bubble {
  display: inline-block;
  margin: 16px 2px 0 2px;
  font-size: 10px;
  color: #909399;
}
.handle {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 10px;
  height: 10px;
  background: #409eff;
  border: 1px solid #fff;
  border-radius: 2px;
  cursor: nwse-resize;
}
.region-form {
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 10px;
}
.region-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.region-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 6px;
  font-size: 13px;
  border-radius: 4px;
  cursor: pointer;
}
.region-list li.active {
  background: #ecf5ff;
}
.region-list .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.t-exam_number {
  background: #1890ff;
}
.dot.t-name {
  background: #13c2c2;
}
.dot.t-choice {
  background: #fa8c16;
}
.dot.t-subjective {
  background: #eb2f96;
}
.region-list .del {
  margin-left: auto;
  color: #c0c4cc;
}
.region-list .del:hover {
  color: #f56c6c;
}
.tip {
  font-size: 12px;
  color: #909399;
  margin: 8px 0;
}
.precheck .issue-list {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
  max-height: 340px;
  overflow-y: auto;
}
.precheck .issue-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  font-size: 13px;
  border-bottom: 1px solid #f5f7fa;
}
</style>