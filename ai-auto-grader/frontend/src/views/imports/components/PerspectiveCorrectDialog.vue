<template>
  <el-dialog
    :model-value="modelValue"
    title="手动四点透视矫正"
    width="820px"
    top="4vh"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="reset"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="请依次点击答卷原图的四个角点：左上 → 右上 → 右下 → 左下。至少选择 4 个点后可应用矫正。"
      style="margin-bottom: 12px"
    />

    <div v-loading="loading" class="canvas-wrap">
      <div v-if="imageUrl" ref="stageRef" class="stage" @click="onStageClick">
        <img :src="imageUrl" class="stage-img" @load="onImageLoad" draggable="false" />
        <svg class="overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polygon
            v-if="points.length >= 2"
            :points="polygonPoints"
            fill="rgba(64, 158, 255, 0.15)"
            stroke="#409eff"
            stroke-width="1.5"
            vector-effect="non-scaling-stroke"
          />
        </svg>
        <div
          v-for="(p, i) in points"
          :key="i"
          class="marker"
          :style="{ left: pct(p[0], naturalWidth), top: pct(p[1], naturalHeight) }"
        >
          {{ i + 1 }}
        </div>
      </div>
      <el-empty v-else-if="!loading" description="无法加载答卷原图" />
    </div>

    <div class="hint">
      已选 {{ points.length }} / 4 个点
      <span v-if="points.length === 4" class="ok">（可应用矫正）</span>
    </div>

    <template #footer>
      <el-button :disabled="!points.length" @click="undo">撤销上一点</el-button>
      <el-button :disabled="!points.length" @click="points = []">重选</el-button>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="points.length !== 4" :loading="applying" @click="apply">
        应用矫正
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getPageSourceImageUrl, recutPage } from '@/api/imports'

const props = defineProps<{
  modelValue: boolean
  pageId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'applied'): void
}>()

const stageRef = ref<HTMLElement | null>(null)
const imageUrl = ref('')
const loading = ref(false)
const applying = ref(false)
const points = ref<number[][]>([])
const naturalWidth = ref(0)
const naturalHeight = ref(0)

function pct(value: number, total: number) {
  return total ? `${(value / total) * 100}%` : '0%'
}

const polygonPoints = ref('')

watch(
  () => props.modelValue,
  async (visible) => {
    if (visible && props.pageId) {
      await loadImage()
    }
  },
)

watch(
  points,
  (pts) => {
    polygonPoints.value = pts.map((p) => `${(p[0] / (naturalWidth.value || 1)) * 100},${(p[1] / (naturalHeight.value || 1)) * 100}`).join(' ')
  },
  { deep: true },
)

async function loadImage() {
  loading.value = true
  imageUrl.value = ''
  points.value = []
  try {
    imageUrl.value = await getPageSourceImageUrl(props.pageId)
  } catch {
    imageUrl.value = ''
  } finally {
    loading.value = false
  }
}

function onImageLoad(e: Event) {
  const img = e.target as HTMLImageElement
  naturalWidth.value = img.naturalWidth
  naturalHeight.value = img.naturalHeight
}

function onStageClick(e: MouseEvent) {
  if (!stageRef.value || points.value.length >= 4) return
  const rect = stageRef.value.getBoundingClientRect()
  const x = Math.round(((e.clientX - rect.left) / rect.width) * naturalWidth.value)
  const y = Math.round(((e.clientY - rect.top) / rect.height) * naturalHeight.value)
  if (x < 0 || y < 0 || x > naturalWidth.value || y > naturalHeight.value) return
  points.value = [...points.value, [x, y]]
}

function undo() {
  points.value = points.value.slice(0, -1)
}

async function apply() {
  if (points.value.length !== 4) return
  applying.value = true
  try {
    await recutPage(props.pageId, points.value)
    ElMessage.success('已完成透视矫正并重新切割')
    emit('applied')
    emit('update:modelValue', false)
  } catch {
    // 错误由拦截器提示
  } finally {
    applying.value = false
  }
}

function reset() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
  points.value = []
  polygonPoints.value = ''
  naturalWidth.value = 0
  naturalHeight.value = 0
}
</script>

<style scoped>
.canvas-wrap {
  min-height: 200px;
}
.stage {
  position: relative;
  display: inline-block;
  max-width: 100%;
  cursor: crosshair;
  user-select: none;
  border: 1px solid #ebeef5;
}
.stage-img {
  display: block;
  max-width: 100%;
  max-height: 62vh;
}
.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.marker {
  position: absolute;
  width: 24px;
  height: 24px;
  margin-left: -12px;
  margin-top: -12px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 13px;
  line-height: 24px;
  text-align: center;
  pointer-events: none;
  box-shadow: 0 0 0 2px #fff;
}
.hint {
  margin-top: 10px;
  color: #909399;
  font-size: 13px;
}
.hint .ok {
  color: #67c23a;
}
</style>