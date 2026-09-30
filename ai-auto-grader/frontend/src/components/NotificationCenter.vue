<template>
  <div class="notification-center">
    <el-badge :value="unread" :hidden="unread === 0" :max="99" class="bell-badge">
      <el-button text circle @click="open = true">
        <el-icon :size="20"><Bell /></el-icon>
      </el-button>
    </el-badge>

    <el-drawer v-model="open" title="消息中心" size="380px" @open="load">
      <template #header>
        <div class="drawer-header">
          <span>消息中心</span>
          <el-button v-if="unread > 0" type="primary" link @click="readAll">全部已读</el-button>
        </div>
      </template>

      <div v-loading="loading" class="list">
        <el-empty v-if="!items.length" description="暂无消息" :image-size="80" />
        <div
          v-for="item in items"
          :key="item.id"
          class="item"
          :class="{ unread: !item.is_read }"
          @click="handleClick(item)"
        >
          <div class="item-head">
            <span class="dot" :class="`level-${item.level}`" />
            <span class="title">{{ item.title }}</span>
            <span class="time">{{ formatTime(item.created_at) }}</span>
          </div>
          <div class="content">{{ item.content }}</div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from '@/api/notifications'
import { useRealtime } from '@/composables/useRealtime'

const router = useRouter()
const realtime = useRealtime()

const open = ref(false)
const loading = ref(false)
const unread = ref(0)
const items = ref<NotificationItem[]>([])

async function load() {
  loading.value = true
  try {
    const res = await listNotifications({ limit: 50 })
    items.value = res.data.items
    unread.value = res.data.unread
  } finally {
    loading.value = false
  }
}

async function refreshUnread() {
  try {
    const res = await getUnreadCount()
    unread.value = res.data.unread
  } catch {
    // 静默忽略
  }
}

async function readAll() {
  await markAllNotificationsRead()
  items.value = items.value.map((i) => ({ ...i, is_read: true }))
  unread.value = 0
}

async function handleClick(item: NotificationItem) {
  if (!item.is_read) {
    await markNotificationRead(item.id)
    item.is_read = true
    unread.value = Math.max(0, unread.value - 1)
  }
  if (item.link) {
    open.value = false
    router.push(item.link)
  }
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const diff = Date.now() - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${date.getMonth() + 1}-${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}

// 实时接收：新消息置顶并弹出提醒
let stopRealtime: (() => void) | null = null
function handleRealtime(data: Record<string, unknown>) {
  const item = data as unknown as NotificationItem
  items.value = [item, ...items.value]
  unread.value += 1
  ElNotification({
    title: item.title || '新消息',
    message: item.content || '',
    type: item.level === 'danger' ? 'error' : item.level === 'warning' ? 'warning' : item.level === 'success' ? 'success' : 'info',
    duration: 4000,
    onClick: () => {
      open.value = true
    },
  })
}

onMounted(() => {
  realtime.connect()
  refreshUnread()
  stopRealtime = realtime.on('notification', handleRealtime)
})

onUnmounted(() => {
  stopRealtime?.()
})

// 供外部（如删除后）调用刷新
defineExpose({ refreshUnread })
</script>

<style scoped>
.bell-badge {
  margin-right: 8px;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 12px;
  font-weight: 600;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.item {
  padding: 10px 12px;
  border-radius: 6px;
  background: #f7f8fa;
  cursor: pointer;
  transition: background 0.2s;
}
.item:hover {
  background: #eef2f7;
}
.item.unread {
  background: #ecf5ff;
}
.item-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
  flex-shrink: 0;
}
.dot.level-success {
  background: #67c23a;
}
.dot.level-warning {
  background: #e6a23c;
}
.dot.level-danger {
  background: #f56c6c;
}
.title {
  font-size: 14px;
  font-weight: 600;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.time {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}
.content {
  margin-top: 4px;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
</style>