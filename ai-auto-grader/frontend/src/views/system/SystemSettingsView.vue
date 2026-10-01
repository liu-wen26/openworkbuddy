<template>
  <div>
    <div class="toolbar">
      <h2>系统设置</h2>
    </div>

    <el-tabs v-model="activeTab" class="tabs">
      <!-- F11-01 大模型配置 -->
      <el-tab-pane label="大模型配置" name="llm">
        <el-card shadow="never" v-loading="loading.llm" class="panel">
          <el-form :model="llm" label-width="140px" style="max-width: 640px">
            <el-form-item label="启用 AI 评分">
              <el-switch v-model="llm.enabled" />
            </el-form-item>
            <el-form-item label="服务提供方">
              <el-select v-model="llm.provider" style="width: 100%">
                <el-option label="OpenAI 兼容（云端）" value="openai" />
                <el-option label="本地私有化模型" value="local" />
                <el-option label="Mock（无凭证兜底）" value="mock" />
              </el-select>
            </el-form-item>
            <el-form-item label="API 地址">
              <el-input v-model="llm.api_base" placeholder="留空使用提供方默认地址" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="llm.api_key" type="password" show-password placeholder="已配置则显示 ******，保持不变即可" />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="llm.model" placeholder="如 gpt-4o / qwen-vl-max" />
            </el-form-item>
            <el-form-item label="置信度阈值">
              <el-input-number v-model="llm.confidence_threshold" :min="0" :max="1" :step="0.05" />
              <span class="hint">低于该值的 AI 评分将转为异常复核</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving.llm" @click="saveLlm">保存</el-button>
              <el-button :loading="testing" @click="testLlm">测试连接</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- F11-03 水印 -->
      <el-tab-pane label="全局水印" name="watermark">
        <el-card shadow="never" v-loading="loading.watermark" class="panel">
          <el-form :model="watermark" label-width="140px" style="max-width: 640px">
            <el-form-item label="启用水印">
              <el-switch v-model="watermark.enabled" />
            </el-form-item>
            <el-form-item label="水印文字">
              <el-input v-model="watermark.text" />
            </el-form-item>
            <el-form-item label="透明度">
              <el-slider v-model="watermark.opacity" :min="0.02" :max="0.5" :step="0.02" style="width: 320px" />
            </el-form-item>
            <el-form-item label="颜色">
              <el-color-picker v-model="watermark.color" />
            </el-form-item>
            <el-form-item label="字号">
              <el-input-number v-model="watermark.font_size" :min="10" :max="60" />
            </el-form-item>
            <el-form-item label="旋转角度">
              <el-input-number v-model="watermark.rotate" :min="-90" :max="90" />
            </el-form-item>
            <el-form-item label="排布方式">
              <el-radio-group v-model="watermark.position">
                <el-radio value="center">居中单个</el-radio>
                <el-radio value="tile">平铺</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving.watermark" @click="saveWatermark">保存</el-button>
            </el-form-item>
          </el-form>

          <el-divider />
          <div class="preview-title">预览</div>
          <div class="wm-preview">
            <div v-if="watermark.enabled" class="wm-layer">
              <span
                v-for="i in previewCount"
                :key="i"
                class="wm-text"
                :style="wmStyle"
              >{{ watermark.text }}</span>
            </div>
            <div class="wm-placeholder">答卷 / 报表预览区域</div>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- F11-04 消息通知 -->
      <el-tab-pane label="消息通知" name="notification">
        <el-card shadow="never" v-loading="loading.notification" class="panel">
          <el-form :model="notification" label-width="140px" style="max-width: 640px">
            <el-form-item label="启用通知">
              <el-switch v-model="notification.enabled" />
            </el-form-item>
            <el-form-item label="通知渠道">
              <el-checkbox-group v-model="notification.channels">
                <el-checkbox value="in_app">站内消息</el-checkbox>
                <el-checkbox value="email">邮件</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="通知事件">
              <el-checkbox-group v-model="notification.events">
                <el-checkbox v-for="ev in eventOptions" :key="ev.key" :value="ev.key">{{ ev.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="额外收件人">
              <el-select
                v-model="notification.recipients"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="输入邮箱后回车添加"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving.notification" @click="saveNotification">保存</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- F11-02 阅卷界面偏好 -->
      <el-tab-pane label="阅卷偏好" name="preferences">
        <el-card shadow="never" v-loading="loading.preferences" class="panel">
          <el-form :model="preferences" label-width="160px" style="max-width: 640px">
            <el-form-item label="默认缩放">
              <el-input-number v-model="preferences.default_zoom" :min="0.5" :max="3" :step="0.1" />
            </el-form-item>
            <el-form-item label="图片适应方式">
              <el-select v-model="preferences.image_fit" style="width: 200px">
                <el-option label="适应宽度" value="width" />
                <el-option label="适应高度" value="height" />
                <el-option label="完整显示" value="contain" />
              </el-select>
            </el-form-item>
            <el-form-item label="快捷打分步长">
              <el-input-number v-model="preferences.score_step" :min="0.1" :max="5" :step="0.5" />
            </el-form-item>
            <el-form-item label="启用键盘快捷键">
              <el-switch v-model="preferences.keyboard_shortcuts" />
            </el-form-item>
            <el-form-item label="打分后自动下一份">
              <el-switch v-model="preferences.auto_next" />
            </el-form-item>
            <el-form-item label="显示 AI 评语">
              <el-switch v-model="preferences.show_ai_comment" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving.preferences" @click="savePreferences">保存</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getLlmConfig, updateLlmConfig, testLlmConfig,
  getWatermark, updateWatermark,
  getNotification, updateNotification,
  getPreferences, updatePreferences,
  type LLMConfig, type WatermarkConfig, type NotificationConfig, type PreferenceConfig,
  type NotificationEvent,
} from '@/api/system'

const activeTab = ref('llm')

const llm = reactive<LLMConfig>({
  provider: 'openai', api_base: null, api_key: '', model: 'gpt-4o',
  confidence_threshold: 0.7, enabled: true,
})
const watermark = reactive<WatermarkConfig>({
  enabled: false, text: 'AI自动阅卷系统 机密', opacity: 0.12,
  color: '#909399', font_size: 16, rotate: -25, position: 'center',
})
const notification = reactive<NotificationConfig>({
  enabled: true, channels: ['in_app'], events: [], recipients: [],
})
const preferences = reactive<PreferenceConfig>({
  default_zoom: 1, image_fit: 'width', keyboard_shortcuts: true,
  auto_next: true, show_ai_comment: true, score_step: 0.5,
})
const eventOptions = ref<NotificationEvent[]>([])

const loading = reactive({ llm: false, watermark: false, notification: false, preferences: false })
const saving = reactive({ llm: false, watermark: false, notification: false, preferences: false })
const testing = ref(false)

const wmStyle = computed(() => ({
  color: watermark.color,
  opacity: String(watermark.opacity),
  fontSize: `${watermark.font_size}px`,
  transform: `rotate(${watermark.rotate}deg)`,
}))
const previewCount = computed(() => (watermark.position === 'tile' ? 12 : 1))

async function loadAll() {
  loading.llm = true
  loading.watermark = true
  loading.notification = true
  loading.preferences = true
  try {
    const [l, w, n, p] = await Promise.all([
      getLlmConfig(), getWatermark(), getNotification(), getPreferences(),
    ])
    Object.assign(llm, l.data)
    Object.assign(watermark, w.data)
    Object.assign(notification, n.data.config)
    eventOptions.value = n.data.events
    Object.assign(preferences, p.data)
  } finally {
    loading.llm = loading.watermark = loading.notification = loading.preferences = false
  }
}

async function saveLlm() {
  saving.llm = true
  try {
    const res = await updateLlmConfig({ ...llm })
    Object.assign(llm, res.data)
    ElMessage.success('大模型配置已保存')
  } finally {
    saving.llm = false
  }
}

async function testLlm() {
  testing.value = true
  try {
    const res = await testLlmConfig()
    if (res.data.success) ElMessage.success(`连接成功：${res.data.message}`)
    else ElMessage.warning(`连接失败：${res.data.message}`)
  } finally {
    testing.value = false
  }
}

async function saveWatermark() {
  saving.watermark = true
  try {
    const res = await updateWatermark({ ...watermark })
    Object.assign(watermark, res.data)
    ElMessage.success('水印设置已保存')
  } finally {
    saving.watermark = false
  }
}

async function saveNotification() {
  saving.notification = true
  try {
    const res = await updateNotification({ ...notification })
    Object.assign(notification, res.data)
    ElMessage.success('通知设置已保存')
  } finally {
    saving.notification = false
  }
}

async function savePreferences() {
  saving.preferences = true
  try {
    const res = await updatePreferences({ ...preferences })
    Object.assign(preferences, res.data)
    ElMessage.success('阅卷偏好已保存')
  } finally {
    saving.preferences = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel {
  max-width: 900px;
}
.hint {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}
.preview-title {
  margin-bottom: 8px;
  color: #606266;
}
.wm-preview {
  position: relative;
  height: 220px;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
  background: #fafafa;
}
.wm-layer {
  position: absolute;
  inset: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 40px 60px;
  pointer-events: none;
}
.wm-text {
  font-weight: bold;
  white-space: nowrap;
  user-select: none;
}
.wm-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}
</style>