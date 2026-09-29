import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LoginView from '@/views/auth/LoginView.vue'
import MainLayout from '@/layouts/MainLayout.vue'
import DashboardView from '@/views/dashboard/DashboardView.vue'
import ExamListView from '@/views/exams/ExamListView.vue'
import ExamFormView from '@/views/exams/ExamFormView.vue'
import ExamDetailView from '@/views/exams/ExamDetailView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: LoginView,
      meta: { public: true },
    },
    {
      path: '/',
      component: MainLayout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'Dashboard', component: DashboardView },
        { path: 'exams', name: 'ExamList', component: ExamListView },
        { path: 'exams/create', name: 'ExamCreate', component: ExamFormView },
        { path: 'exams/:id/edit', name: 'ExamEdit', component: ExamFormView },
        { path: 'exams/:id', name: 'ExamDetail', component: ExamDetailView },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()
  if (!auth.isLoggedIn && auth.token) {
    await auth.fetchUser()
  }
  if (to.meta.public) {
    next()
  } else if (!auth.isLoggedIn) {
    next('/login')
  } else {
    next()
  }
})

export default router
