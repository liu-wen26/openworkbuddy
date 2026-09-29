<template>
  <div>
    <h2>欢迎使用 AI自动阅卷系统</h2>
    <p>当前用户：{{ auth.user?.real_name }}，角色：{{ roleText }}</p>
    <p>请从左侧菜单进入对应功能模块。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const roleText = computed(() => {
  const map: Record<string, string> = {
    super_admin: '超级管理员',
    exam_admin: '教务管理员',
    group_leader: '教研组长',
    teacher: '阅卷教师',
  }
  return map[auth.user?.role || ''] || auth.user?.role
})
</script>
