<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div class="title">
        <h2>{{ tpl.name || '答题卡模板' }}</h2>
        <el-tag size="small" :type="isAnnotated ? 'success' : 'info'">
          {{ isAnnotated ? '原版答题卡标注' : '系统生成卡面' }}
        </el-tag>
        <el-tag v-if="!isAnnotated" size="small">{{ tpl.paper_size }}</el-tag>
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
          <!-- 左侧：基本设置与底图 -->
          <aside class="side left">
            <h3>模板信息</h3>
            <el-form label-width="82px" size="small">
              <el-form-item label="模板名称"><el-input v-model="tpl.name" /></el-form-item>
              <el-form-item label="学科"><el-input v-model="tpl.subject" /></el-form-item>
              <el-form-item label="卡面标题"><el-input v-model="tpl.title" /></el-form-item>
              <template v-if="!isAnnotated">
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
              </template>
            </el-form>

            <h3>原版答题卡底图</h3>
            <p class="tip">
              上传真实答题卡（图片或 PDF）。PDF 自动读取页数并逐页登记，空白页自动标识；
              原图按上传尺寸原样保存，不做缩放。
            </p>
            <el-upload
              :show-file-list="false"
              multiple
              :before-upload="beforeUploadBase"
              :http-request="handleBaseUpload"
              accept="image/*,.pdf"
            >
              <el-button size="small" type="primary" :loading="uploading">上传答题卡（可多选 / PDF）</el-button>
            </el-upload>

            <div v-if="pages.length" class="page-cards">
              <div
                v-for="(p, i) in pages"
                :key="p.id"
                class="page-card"
                :class="{ active: i === activePageIdx }"
                @click="activePageIdx = i"
              >
                <div class="page-card-head">
                  <span>第 {{ p.page_index + 1 }} 页</span>
                  <el-tag size="small" :type="p.is_blank ? 'warning' : 'success'">
                    {{ p.is_blank ? '空白页' : '有效页' }}
                  </el-tag>
                </div>
                <div class="page-card-meta">
                  {{ p.orientation === 'landscape' ? '横向' : '纵向' }} · {{ p.width_px }}×{{ p.height_px }}px
                </div>
                <div class="page-card-actions" @click.stop>
                  <el-switch
                    v-model="p.is_blank"
                    size="small"
                    active-text="空白"
                    @change="(v: boolean) => toggleBlank(p, v)"
                  />
                  <el-icon class="del" @click="removePage(p)"><Delete /></el-icon>
                </div>
              </div>
            </div>
            <p v-else class="tip">尚未上传底图，可先上传原版答题卡再进行框选。</p>

            <h3>识别与预处理</h3>
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
              <el-form-item label="班级前缀"><el-switch v-model="tpl.class_prefix_enabled" /></el-form-item>
              <el-form-item label="姓名 OCR"><el-switch v-model="tpl.name_ocr_enabled" /></el-form-item>
              <el-form-item label="倾斜阈值">
                <el-input-number v-model="tpl.tilt_threshold" :min="0" :max="45" style="width: 100%" />
              </el-form-item>
              <el-form-item label="透视矫正"><el-switch v-model="tpl.perspective_enabled" /></el-form-item>
              <el-form-item label="自动纠偏"><el-switch v-model="tpl.deskew_enabled" /></el-form-item>
            </el-form>

            <template v-if="!isAnnotated">
              <h3>本地样卷（仅预览）</h3>
              <p class="tip">未上传底图时，可临时载入一张本地样卷图片辅助框选，不会上传服务器。</p>
              <el-upload
                :show-file-list="false"
                :before-upload="beforeUploadSample"
                :http-request="handleSample"
                accept="image/*"
              >
                <el-button size="small">载入本地样卷图片</el-button>
              </el-upload>
              <el-button v-if="localSample" size="small" type="danger" plain @click="clearSample">清除本地样卷</el-button>
            </template>
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
              <div class="page-nav" v-if="pages.length > 1">
                <el-button size="small" :disabled="activePageIdx === 0" @click="activePageIdx--">上一页</el-button>
                <span>第 {{ activePageIdx + 1 }} / {{ pages.length }} 页</span>
                <el-button size="small" :disabled="activePageIdx >= pages.length - 1" @click="activePageIdx++">下一页</el-button>
              </div>
              <span v-if="currentPageMeta" class="tip">
                底图原始尺寸 {{ currentPageMeta.width_px }}×{{ currentPageMeta.height_px }}px（画布按比例显示，坐标与分辨率无关）
              </span>
            </div>

            <div
              ref="canvasRef"
              class="canvas"
              :style="canvasStyle"
              @mousedown="onCanvasMouseDown"
            >
              <img v-if="bgImage" :src="bgImage" class="bg" alt="答题卡底图" />
              <div v-if="!isAnnotated" class="margin-guide" :style="marginStyle"></div>
              <div
                v-for="item in pageRegions"
                :key="item.i"
                class="region"
                :class="[`t-${item.r.region_type}`, { selected: item.i === selectedIndex }]"
                :style="regionStyle(item.r)"
                @mousedown.stop="onRegionMouseDown($event, item.i)"
              >
                <span class="region-label">{{ regionLabel(item.r) }}</span>
                <span
                  v-for="(m, k) in regionMarkers(item.r)"
                  :key="k"
                  class="marker"
                  :style="{ left: `${m.left}px`, top: `${m.top}px`, width: `${m.size}px`, height: `${m.size}px` }"
                >{{ m.label }}</span>
                <span
                  v-if="item.i === selectedIndex"
                  class="handle"
                  @mousedown.stop="onHandleMouseDown($event, item.i)"
                ></span>
              </div>
            </div>
            <p class="tip">
              按住拖拽绘制「{{ drawTypeText }}」；点击区域可整体移动，拖动右下角小方块可缩放。
              选择题 / 考号区框选后会弹出切格设置，自动生成气泡坐标。
            </p>
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
                  <el-input v-model="selectedRegion.question_number" />
                </el-form-item>
                <el-form-item v-if="selectedRegion.region_type === 'subjective'" label="子题号">
                  <el-input v-model="selectedRegion.sub_question_number" placeholder="如 (1)" />
                </el-form-item>
                <el-form-item v-if="selectedRegion.region_type === 'subjective'" label="题块组">
                  <el-input v-model="selectedRegion.group_key" placeholder="同一题跨区域时填写相同值，如 17" />
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
                  <el-form-item label="切格">
                    <el-button size="small" @click="openChoiceGrid(selectedIndex)">重新生成题目网格</el-button>
                  </el-form-item>
                </template>

                <template v-if="selectedRegion.region_type === 'exam_number'">
                  <el-form-item label="填涂格">
                    <el-button size="small" @click="openDigitGrid(selectedIndex)">
                      {{ hasDigitSpec(selectedRegion) ? '重新生成填涂格' : '生成填涂格' }}
                    </el-button>
                  </el-form-item>
                </template>

                <el-form-item v-if="hasOptionSpec(selectedRegion)" label="对齐">
                  <el-button size="small" type="primary" plain @click="openTune(selectedIndex)">气泡对齐微调</el-button>
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

            <h3>区域列表（本页 {{ pageRegions.length }} 个 / 共 {{ regions.length }} 个）</h3>
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

    <!-- 选择题切格设置 -->
    <el-dialog v-model="choiceGridVisible" title="选择题自动切格" width="520px">
      <p class="tip">
        把刚框选的大区按「题数 × 选项数 × 栏数」自动切成一题一区域，并生成气泡坐标，
        用于后续 OMR 自动判分。取消则保留为单个区域。
      </p>
      <el-form label-width="90px" size="small">
        <el-form-item label="起始题号">
          <el-input-number v-model="choiceForm.start_question" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="题目数量">
          <el-input-number v-model="choiceForm.question_count" :min="1" :max="200" style="width: 100%" />
        </el-form-item>
        <el-form-item label="每题选项数">
          <el-input-number v-model="choiceForm.options_count" :min="2" :max="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="栏数">
          <el-input-number v-model="choiceForm.columns" :min="1" :max="8" style="width: 100%" />
        </el-form-item>
        <el-form-item label="排列方向">
          <el-radio-group v-model="choiceForm.direction">
            <el-radio-button value="horizontal">横向（选项左右排列）</el-radio-button>
            <el-radio-button value="vertical">纵向（选项上下排列）</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="每题分值">
          <el-input-number v-model="choiceForm.score" :min="0" :step="0.5" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelChoiceGrid">保留为单区域</el-button>
        <el-button type="primary" :loading="gridBusy" @click="confirmChoiceGrid">生成网格</el-button>
      </template>
    </el-dialog>

    <!-- 考号填涂格设置 -->
    <el-dialog v-model="digitGridVisible" title="考号区填涂格" width="460px">
      <p class="tip">按考号位数生成「位数 × 10 行（0~9）」的填涂格坐标，用于精确识别学生填涂的考号。</p>
      <el-form label-width="90px" size="small">
        <el-form-item label="考号位数">
          <el-input-number v-model="digitForm.digits" :min="4" :max="16" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="digitGridVisible = false">取消</el-button>
        <el-button type="primary" :loading="gridBusy" @click="confirmDigitGrid">生成填涂格</el-button>
      </template>
    </el-dialog>

    <!-- 气泡对齐微调 -->
    <el-dialog v-model="tuneVisible" title="气泡对齐微调" width="560px">
      <p class="tip">下方为该区域在底图上的实际裁剪。若圆点未对准气泡，用按钮整体平移 / 缩放对齐。</p>
      <div class="tune-stage" :style="{ width: `${tuneBox.w}px`, height: `${tuneBox.h}px` }">
        <img v-if="tuneCropUrl" :src="tuneCropUrl" class="tune-img" alt="区域裁剪" />
        <span
          v-for="(m, k) in tuneMarkers"
          :key="k"
          class="marker tune-marker"
          :style="{ left: `${m.left}px`, top: `${m.top}px`, width: `${m.size}px`, height: `${m.size}px` }"
        >{{ m.label }}</span>
      </div>
      <div class="tune-controls">
        <div class="tune-group">
          <span>平移</span>
          <el-button size="small" @click="nudge(-5, 0)">←</el-button>
          <el-button size="small" @click="nudge(5, 0)">→</el-button>
          <el-button size="small" @click="nudge(0, -5)">↑</el-button>
          <el-button size="small" @click="nudge(0, 5)">↓</el-button>
        </div>
        <div class="tune-group">
          <span>缩放</span>
          <el-button size="small" @click="scaleSpec(0.95)">缩小</el-button>
          <el-button size="small" @click="scaleSpec(1.05)">放大</el-button>
        </div>
        <el-button size="small" type="warning" plain @click="resetTune">还原</el-button>
      </div>
      <template #footer>
        <el-button @click="tuneVisible = false">完成</el-button>
      </template>
    </el-dialog>

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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import {
  getTemplate,
  updateTemplate,
  replaceRegions,
  getChoiceAnswers,
  replaceChoiceAnswers,
  exportTemplatePdf,
  precheckTemplate,
  uploadTemplatePages,
  getTemplatePages,
  updateTemplatePage,
  deleteTemplatePage,
  getTemplatePageImageUrl,
  getTemplatePageCropUrl,
  buildChoiceGrid,
  buildDigitGrid,
  type RegionType,
  type TemplateRegion,
  type TemplatePage,
  type PrecheckResult,
} from '@/api/templates'
import ChoiceAnswerPanel from './components/ChoiceAnswerPanel.vue'
import AIConfigPanel from './components/AIConfigPanel.vue'

const route = useRoute()
const router = useRouter()
const templateId = route.params.id as string

const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const prechecking = ref(false)
const gridBusy = ref(false)
const precheckVisible = ref(false)
const precheckResult = ref<PrecheckResult | null>(null)
const activeTab = ref('design')

const tpl = reactive({
  name: '',
  subject: '',
  title: '答题卡',
  source_type: 'generated' as 'generated' | 'annotated',
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

const isAnnotated = computed(() => tpl.source_type === 'annotated' || pages.value.length > 0)

const regions = ref<TemplateRegion[]>([])
const drawType = ref<RegionType | ''>('')
const selectedIndex = ref(-1)

// ---------- 底图页 ----------
const pages = ref<TemplatePage[]>([])
const pageImages = reactive<Record<number, string>>({})
const activePageIdx = ref(0)
const currentPageMeta = computed<TemplatePage | null>(() => pages.value[activePageIdx.value] || null)
const currentPage = computed(() => currentPageMeta.value?.page_index ?? 0)

const localSamples = reactive<Record<number, string>>({})
const localSample = computed(() => localSamples[currentPage.value] || '')

const bgImage = computed(() => pageImages[currentPage.value] || localSample.value)

const choiceAnswerMap = reactive<Record<string, string>>({})

// ---------- 画布尺寸 ----------
const CANVAS_WIDTH = 620
const PAGE_MM = { A4: { w: 210, h: 297 }, A3: { w: 297, h: 420 } }
const paperMm = computed(() => PAGE_MM[tpl.paper_size])
const pageRatio = computed(() => {
  const p = currentPageMeta.value
  if (p && p.width_px && p.height_px) return p.height_px / p.width_px
  return paperMm.value.h / paperMm.value.w
})
const canvasHeight = computed(() => Math.max(240, Math.round(CANVAS_WIDTH * pageRatio.value)))
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
  const grouped = r.group_key ? `〔组${r.group_key}〕` : ''
  return `${base} ${r.question_number}${sub}${grouped}`
}
const drawTypeText = computed(() => (drawType.value ? regionTypeText(drawType.value) : '区域'))

// ---------- 气泡 / 填涂格标记 ----------
interface Marker {
  left: number
  top: number
  size: number
  label: string
}
function buildMarkers(r: TemplateRegion, rw: number, rh: number): Marker[] {
  const spec = r.option_spec
  if (!spec || typeof spec !== 'object') return []
  const out: Marker[] = []
  if (Array.isArray(spec.bubbles)) {
    const rad = Math.max(2, Number(spec.radius || 0.05) * rh)
    for (const b of spec.bubbles) {
      out.push({
        left: (Number(b.cx) / 1000) * rw,
        top: (Number(b.cy) / 1000) * rh,
        size: rad * 2,
        label: String(b.label ?? ''),
      })
    }
    return out
  }
  if (spec.kind === 'digit' && Array.isArray(spec.columns) && Array.isArray(spec.rows)) {
    const rad = Math.max(1.5, Number(spec.radius || 0.02) * rh)
    for (const c of spec.columns) {
      for (const y of spec.rows) {
        out.push({
          left: (Number(c) / 1000) * rw,
          top: (Number(y) / 1000) * rh,
          size: rad * 2,
          label: '',
        })
      }
    }
  }
  return out
}
function regionMarkers(r: TemplateRegion): Marker[] {
  const rw = (r.width / 1000) * CANVAS_WIDTH
  const rh = (r.height / 1000) * canvasHeight.value
  return buildMarkers(r, rw, rh)
}
function hasOptionSpec(r: TemplateRegion) {
  const spec = r.option_spec
  return !!spec && (Array.isArray(spec.bubbles) || spec.kind === 'digit')
}
function hasDigitSpec(r: TemplateRegion) {
  return !!r.option_spec && r.option_spec.kind === 'digit'
}

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

function newRegion(type: RegionType, rel: { x: number; y: number }): TemplateRegion {
  return {
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
    group_key: null,
    option_spec: null,
  }
}

function onCanvasMouseDown(e: MouseEvent) {
  const type = drawType.value
  if (!type) return
  const rel = toRel(e)
  startRel = rel
  dragMode = 'draw'
  regions.value.push(newRegion(type, rel))
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
    const idx = selectedIndex.value
    const r = regions.value[idx]
    if (r && (r.width < 8 || r.height < 8)) {
      regions.value.splice(idx, 1)
      selectedIndex.value = -1
    } else if (r) {
      if (r.region_type === 'choice') {
        openChoiceGrid(idx)
      } else if (r.region_type === 'exam_number') {
        openDigitGrid(idx)
      } else {
        autoNumber(r)
      }
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

// ---------- 选择题切格 ----------
const choiceGridVisible = ref(false)
const choiceGridIndex = ref(-1)
const choiceForm = reactive({
  start_question: 1,
  question_count: 10,
  options_count: 4,
  columns: 1,
  direction: 'horizontal' as 'horizontal' | 'vertical',
  score: 0,
})

function nextChoiceQuestion(): number {
  const nums = regions.value
    .filter((x) => x.region_type === 'choice' && /^\d+$/.test(x.question_number || ''))
    .map((x) => parseInt(x.question_number as string, 10))
  return nums.length ? Math.max(...nums) + 1 : 1
}

function openChoiceGrid(index: number) {
  choiceGridIndex.value = index
  choiceForm.start_question = nextChoiceQuestion()
  choiceForm.question_count = 10
  choiceForm.options_count = 4
  choiceForm.columns = 1
  choiceForm.direction = 'horizontal'
  choiceForm.score = 0
  choiceGridVisible.value = true
}

function cancelChoiceGrid() {
  const r = regions.value[choiceGridIndex.value]
  if (r) autoNumber(r)
  choiceGridVisible.value = false
}

async function confirmChoiceGrid() {
  const r = regions.value[choiceGridIndex.value]
  if (!r) return
  gridBusy.value = true
  try {
    const res = await buildChoiceGrid(templateId, {
      page_index: r.page_index,
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      start_question: choiceForm.start_question,
      question_count: choiceForm.question_count,
      options_count: choiceForm.options_count,
      columns: choiceForm.columns,
      direction: choiceForm.direction,
      score: choiceForm.score,
    })
    const generated = res.data.regions.map((x) => ({
      ...x,
      question_number: x.question_number ?? '',
      sub_question_number: x.sub_question_number ?? '',
      knowledge_tags: x.knowledge_tags || [],
    }))
    for (const g of generated) {
      const q = g.question_number || ''
      if (q && !(q in choiceAnswerMap)) choiceAnswerMap[q] = ''
    }
    regions.value.splice(choiceGridIndex.value, 1, ...generated)
    selectedIndex.value = -1
    choiceGridVisible.value = false
    ElMessage.success(`已生成 ${generated.length} 道选择题区域`)
  } finally {
    gridBusy.value = false
  }
}

// ---------- 考号填涂格 ----------
const digitGridVisible = ref(false)
const digitGridIndex = ref(-1)
const digitForm = reactive({ digits: 9 })

function openDigitGrid(index: number) {
  digitGridIndex.value = index
  digitForm.digits = Number(tpl.exam_number_digits) || 9
  digitGridVisible.value = true
}

async function confirmDigitGrid() {
  const r = regions.value[digitGridIndex.value]
  if (!r) return
  gridBusy.value = true
  try {
    const res = await buildDigitGrid(templateId, {
      page_index: r.page_index,
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      digits: digitForm.digits,
    })
    r.option_spec = res.data.option_spec
    tpl.exam_number_digits = digitForm.digits
    digitGridVisible.value = false
    ElMessage.success('已生成考号填涂格')
  } finally {
    gridBusy.value = false
  }
}

// ---------- 气泡对齐微调 ----------
const TUNE_WIDTH = 480
const tuneVisible = ref(false)
const tuneIndex = ref(-1)
const tuneCropUrl = ref('')
const tuneOrigin = ref<Record<string, any> | null>(null)

const tuneRegion = computed(() => (tuneIndex.value >= 0 ? regions.value[tuneIndex.value] : null))
const tuneBox = computed(() => {
  const r = tuneRegion.value
  const p = currentPageMeta.value
  if (!r || !p || !r.width) return { w: TUNE_WIDTH, h: 200 }
  const rpxW = (r.width / 1000) * p.width_px
  const rpxH = (r.height / 1000) * p.height_px
  const h = rpxW > 0 ? Math.round((TUNE_WIDTH * rpxH) / rpxW) : 200
  return { w: TUNE_WIDTH, h: Math.max(60, h) }
})
const tuneMarkers = computed<Marker[]>(() => {
  const r = tuneRegion.value
  if (!r) return []
  return buildMarkers(r, tuneBox.value.w, tuneBox.value.h)
})

async function openTune(index: number) {
  const r = regions.value[index]
  if (!r) return
  tuneIndex.value = index
  tuneOrigin.value = r.option_spec ? JSON.parse(JSON.stringify(r.option_spec)) : null
  tuneCropUrl.value = ''
  tuneVisible.value = true
  tuneCropUrl.value = await getTemplatePageCropUrl(templateId, r.page_index, {
    x: r.x,
    y: r.y,
    width: r.width,
    height: r.height,
  })
}

function nudge(dx: number, dy: number) {
  const r = tuneRegion.value
  if (!r || !r.option_spec) return
  const spec = JSON.parse(JSON.stringify(r.option_spec))
  if (Array.isArray(spec.bubbles)) {
    spec.bubbles.forEach((b: any) => {
      b.cx = clamp(Number(b.cx) + dx, 0, 1000)
      b.cy = clamp(Number(b.cy) + dy, 0, 1000)
    })
  }
  if (Array.isArray(spec.columns)) spec.columns = spec.columns.map((c: number) => clamp(c + dx, 0, 1000))
  if (Array.isArray(spec.rows)) spec.rows = spec.rows.map((y: number) => clamp(y + dy, 0, 1000))
  r.option_spec = spec
}

function scaleSpec(factor: number) {
  const r = tuneRegion.value
  if (!r || !r.option_spec) return
  const spec = JSON.parse(JSON.stringify(r.option_spec))
  const scaleArr = (arr: number[]) => {
    const c = arr.reduce((a, b) => a + b, 0) / arr.length
    return arr.map((v) => clamp(c + (v - c) * factor, 0, 1000))
  }
  if (Array.isArray(spec.bubbles)) {
    const xs = spec.bubbles.map((b: any) => Number(b.cx))
    const ys = spec.bubbles.map((b: any) => Number(b.cy))
    const sx = scaleArr(xs)
    const sy = scaleArr(ys)
    spec.bubbles.forEach((b: any, i: number) => {
      b.cx = sx[i]
      b.cy = sy[i]
    })
  }
  if (Array.isArray(spec.columns)) spec.columns = scaleArr(spec.columns)
  if (Array.isArray(spec.rows)) spec.rows = scaleArr(spec.rows)
  if (spec.radius) spec.radius = Math.min(0.5, Number(spec.radius) * factor)
  r.option_spec = spec
}

function resetTune() {
  const r = tuneRegion.value
  if (r && tuneOrigin.value) r.option_spec = JSON.parse(JSON.stringify(tuneOrigin.value))
}

// ---------- 底图页上传与管理 ----------
function beforeUploadBase(file: File) {
  const name = file.name.toLowerCase()
  const ok = file.type.startsWith('image/') || name.endsWith('.pdf')
  if (!ok) {
    ElMessage.error('仅支持图片或 PDF 答题卡')
    return false
  }
  return true
}

async function handleBaseUpload(options: any) {
  uploading.value = true
  try {
    const res = await uploadTemplatePages(templateId, [options.file])
    const added = res.data.pages
    if (added.length) {
      ElMessage.success(`已添加 ${added.length} 页底图`)
      await reloadAfterPageChange()
    }
  } finally {
    uploading.value = false
  }
}

async function toggleBlank(p: TemplatePage, value: boolean) {
  await updateTemplatePage(templateId, p.page_index, value)
  p.is_blank = value
  ElMessage.success(value ? '已标记为空白页' : '已标记为有效页')
}

async function removePage(p: TemplatePage) {
  await ElMessageBox.confirm(`确定删除第 ${p.page_index + 1} 页底图吗？（该页已框选的区域需自行清理）`, '提示', {
    type: 'warning',
  })
  await deleteTemplatePage(templateId, p.page_index)
  await reloadAfterPageChange()
}

async function reloadAfterPageChange() {
  await loadPages(true)
  await refreshTemplate()
}

// ---------- 本地样卷 ----------
function beforeUploadSample(file: File) {
  if (!file.type.startsWith('image/')) {
    ElMessage.error('请上传图片格式的样卷')
    return false
  }
  return true
}
function handleSample(options: any) {
  localSamples[currentPage.value] = URL.createObjectURL(options.file)
}
function clearSample() {
  const url = localSamples[currentPage.value]
  if (url) URL.revokeObjectURL(url)
  delete localSamples[currentPage.value]
}

// ---------- 数据加载与保存 ----------
async function refreshTemplate() {
  const d = (await getTemplate(templateId)).data
  Object.assign(tpl, {
    name: d.name,
    subject: d.subject || '',
    title: d.title,
    source_type: d.source_type || 'generated',
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
    group_key: r.group_key ?? null,
    option_spec: r.option_spec ?? null,
  }))
  return d
}

async function loadPages(force = false) {
  const res = await getTemplatePages(templateId)
  pages.value = res.data
  if (force) {
    Object.values(pageImages).forEach((u) => URL.revokeObjectURL(u))
    Object.keys(pageImages).forEach((k) => delete pageImages[Number(k)])
  }
  if (activePageIdx.value >= pages.value.length) activePageIdx.value = 0
  for (const p of pages.value) {
    if (!pageImages[p.page_index]) {
      pageImages[p.page_index] = await getTemplatePageImageUrl(templateId, p.page_index, true)
    }
  }
}

async function load() {
  loading.value = true
  try {
    const [, choiceRes] = await Promise.all([refreshTemplate(), getChoiceAnswers(templateId)])
    await loadPages()
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
  Object.values(pageImages).forEach((u) => URL.revokeObjectURL(u))
  Object.values(localSamples).forEach((u) => URL.revokeObjectURL(u))
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
  width: 330px;
  flex-shrink: 0;
}
.side.right {
  width: 300px;
  flex-shrink: 0;
}
.side h3 {
  font-size: 14px;
  margin: 16px 0 8px;
  color: #303133;
}
.side h3:first-child {
  margin-top: 0;
}
.page-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}
.page-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: all 0.15s;
}
.page-card.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.page-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
}
.page-card-meta {
  font-size: 12px;
  color: #909399;
  margin: 4px 0 6px;
}
.page-card-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.page-card-actions .del {
  color: #c0c4cc;
  cursor: pointer;
}
.page-card-actions .del:hover {
  color: #f56c6c;
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
  overflow: visible;
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
  z-index: 2;
}
.marker {
  position: absolute;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(250, 140, 22, 0.9);
  border-radius: 50%;
  background: rgba(250, 140, 22, 0.18);
  font-size: 8px;
  line-height: 1;
  color: #d46b08;
  text-align: center;
  pointer-events: none;
}
.t-exam_number .marker {
  border-color: rgba(24, 144, 255, 0.9);
  background: rgba(24, 144, 255, 0.18);
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
  z-index: 3;
}
.region-form {
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 10px;
}
.region-list {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 260px;
  overflow-y: auto;
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
.tune-stage {
  position: relative;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
  background: #fafafa;
  margin: 0 auto;
}
.tune-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
}
.tune-marker {
  z-index: 2;
}
.tune-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.tune-group {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #606266;
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