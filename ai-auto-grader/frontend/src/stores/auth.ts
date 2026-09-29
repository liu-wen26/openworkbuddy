import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import Cookies from 'js-cookie'
import { login as loginApi, getMe, type User, type LoginForm } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string>(Cookies.get('access_token') || '')

  const isLoggedIn = computed(() => !!token.value && !!user.value)

  async function login(form: LoginForm) {
    const res = await loginApi(form)
    token.value = res.data.access_token
    user.value = res.data.user
    Cookies.set('access_token', res.data.access_token, { expires: 7 })
    return res.data.user
  }

  async function fetchUser() {
    if (!token.value) return null
    try {
      const res = await getMe()
      user.value = res.data
      return res.data
    } catch {
      logout()
      return null
    }
  }

  function logout() {
    user.value = null
    token.value = ''
    Cookies.remove('access_token')
  }

  const menus = computed(() => {
    const role = user.value?.role
    const base = [
      { path: '/', title: '首页', icon: 'HomeFilled' },
    ]
    if (role === 'super_admin' || role === 'exam_admin') {
      base.push({ path: '/exams', title: '考试管理', icon: 'Document' })
      base.push({ path: '/templates', title: '答题卡模板', icon: 'Grid' })
      base.push({ path: '/imports', title: '答卷导入', icon: 'UploadFilled' })
      base.push({ path: '/exceptions', title: '异常中心', icon: 'Warning' })
    }
    if (role === 'group_leader' || role === 'teacher') {
      base.push({ path: '/exams', title: '考试列表', icon: 'Document' })
    }
    if (role === 'group_leader') {
      base.push({ path: '/imports', title: '答卷导入', icon: 'UploadFilled' })
      base.push({ path: '/exceptions', title: '异常中心', icon: 'Warning' })
    }
    return base
  })

  return { user, token, isLoggedIn, login, fetchUser, logout, menus }
})
