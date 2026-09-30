<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">AI阅卷系统</div>
      <el-menu
        :default-active="$route.path"
        router
        class="menu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <el-menu-item v-for="menu in auth.menus" :key="menu.path" :index="menu.path">
          <el-icon><component :is="menu.icon" /></el-icon>
          <span>{{ menu.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-right">
          <span>{{ auth.user?.real_name }} ({{ roleText }})</span>
          <el-button type="primary" link @click="logout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
    <div v-if="watermark.enabled" class="global-watermark">
      <span v-for="i in 120" :key="i" class="wm-text" :style="wmStyle">{{ watermark.text }}</span>
    </div>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getPublicWatermark, type WatermarkConfig } from '@/api/system'

const auth = useAuthStore()
const router = useRouter()

const watermark = reactive<WatermarkConfig>({
  enabled: false, text: '', opacity: 0.12, color: '#909399',
  font_size: 16, rotate: -25, position: 'center',
})

const wmStyle = computed(() => ({
  color: watermark.color,
  opacity: String(watermark.opacity),
  fontSize: `${watermark.font_size}px`,
  transform: `rotate(${watermark.rotate}deg)`,
}))

onMounted(async () => {
  try {
    const res = await getPublicWatermark()
    Object.assign(watermark, res.data)
  } catch {
    // 水印为可选功能，获取失败时静默忽略
  }
})

const roleText = computed(() => {
  const map: Record<string, string> = {
    super_admin: '超级管理员',
    exam_admin: '教务管理员',
    group_leader: '教研组长',
    teacher: '阅卷教师',
  }
  return map[auth.user?.role || ''] || auth.user?.role
})

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background-color: #304156;
}
.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #fff;
  font-size: 18px;
  font-weight: bold;
  border-bottom: 1px solid #1f2d3d;
}
.menu {
  border-right: none;
}
.header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.main {
  background-color: #f0f2f5;
  padding: 20px;
}
.global-watermark {
  position: fixed;
  inset: 0;
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 48px 72px;
  padding: 40px;
  overflow: hidden;
  pointer-events: none;
  user-select: none;
  z-index: 9999;
}
.wm-text {
  font-weight: bold;
  white-space: nowrap;
}
</style>
