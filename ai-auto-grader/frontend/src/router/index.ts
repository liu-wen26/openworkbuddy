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
import GradingWorkbenchView from '@/views/grading/GradingWorkbenchView.vue'
import PrecheckView from '@/views/precheck/PrecheckView.vue'
import AnalyticsView from '@/views/analytics/AnalyticsView.vue'
import ExportCenterView from '@/views/exports/ExportCenterView.vue'
import ArchiveListView from '@/views/archives/ArchiveListView.vue'
import MonitorView from '@/views/monitor/MonitorView.vue'
import UserManageView from '@/views/users/UserManageView.vue'
import SystemSettingsView from '@/views/system/SystemSettingsView.vue'
import RolePermissionView from '@/views/system/RolePermissionView.vue'
import AuditLogView from '@/views/system/AuditLogView.vue'

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
        { path: 'grading', name: 'GradingWorkbench', component: GradingWorkbenchView },
        { path: 'precheck', name: 'Precheck', component: PrecheckView },
        { path: 'analytics', name: 'Analytics', component: AnalyticsView },
        { path: 'exports', name: 'ExportCenter', component: ExportCenterView },
        { path: 'archives', name: 'ArchiveList', component: ArchiveListView },
        { path: 'monitor', name: 'Monitor', component: MonitorView },
        { path: 'users', name: 'UserManage', component: UserManageView },
        { path: 'system/settings', name: 'SystemSettings', component: SystemSettingsView },
        { path: 'system/roles', name: 'RolePermission', component: RolePermissionView },
        { path: 'system/audit', name: 'AuditLog', component: AuditLogView },
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
