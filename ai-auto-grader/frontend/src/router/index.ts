import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LoginView from '@/views/auth/LoginView.vue'
import MainLayout from '@/layouts/MainLayout.vue'
import DashboardView from '@/views/dashboard/DashboardView.vue'
import ExamListView from '@/views/exams/ExamListView.vue'
import ExamFormView from '@/views/exams/ExamFormView.vue'
import ExamDetailView from '@/views/exams/ExamDetailView.vue'
import TemplateListView from '@/views/templates/TemplateListView.vue'
import TemplateDesignerView from '@/views/templates/TemplateDesignerView.vue'
import ImportCenterView from '@/views/imports/ImportCenterView.vue'
import ExceptionCenterView from '@/views/exceptions/ExceptionCenterView.vue'
import ChoiceReviewView from '@/views/choices/ChoiceReviewView.vue'

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
        { path: 'templates', name: 'TemplateList', component: TemplateListView },
        { path: 'templates/:id/design', name: 'TemplateDesigner', component: TemplateDesignerView },
        { path: 'imports', name: 'ImportCenter', component: ImportCenterView },
        { path: 'exceptions', name: 'ExceptionCenter', component: ExceptionCenterView },
        { path: 'choices', name: 'ChoiceReview', component: ChoiceReviewView },
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
