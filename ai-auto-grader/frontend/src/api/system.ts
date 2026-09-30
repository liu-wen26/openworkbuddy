import request from './request'

// ---------------- F11-01 大模型配置 ----------------

export interface LLMConfig {
  provider: string
  api_base: string | null
  api_key: string
  model: string
  confidence_threshold: number
  enabled: boolean
}

export interface LLMTestResult {
  success: boolean
  message: string
  provider?: string
  model?: string
  latency_ms?: number
}

export function getLlmConfig() {
  return request.get<LLMConfig>('/system/llm-config')
}

export function updateLlmConfig(data: Partial<LLMConfig>) {
  return request.put<LLMConfig>('/system/llm-config', data)
}

export function testLlmConfig() {
  return request.post<LLMTestResult>('/system/llm-config/test')
}

// ---------------- F11-03 水印 ----------------

export interface WatermarkConfig {
  enabled: boolean
  text: string
  opacity: number
  color: string
  font_size: number
  rotate: number
  position: string
}

export function getWatermark() {
  return request.get<WatermarkConfig>('/system/watermark')
}

export function getPublicWatermark() {
  return request.get<WatermarkConfig>('/system/watermark/public')
}

export function updateWatermark(data: Partial<WatermarkConfig>) {
  return request.put<WatermarkConfig>('/system/watermark', data)
}

// ---------------- F11-04 消息通知 ----------------

export interface NotificationConfig {
  enabled: boolean
  channels: string[]
  events: string[]
  recipients: string[]
}

export interface NotificationEvent {
  key: string
  label: string
}

export function getNotification() {
  return request.get<{ config: NotificationConfig; events: NotificationEvent[] }>('/system/notification')
}

export function updateNotification(data: Partial<NotificationConfig>) {
  return request.put<NotificationConfig>('/system/notification', data)
}

// ---------------- F11-02 阅卷界面偏好 ----------------

export interface PreferenceConfig {
  default_zoom: number
  image_fit: string
  keyboard_shortcuts: boolean
  auto_next: boolean
  show_ai_comment: boolean
  score_step: number
}

export function getPreferences() {
  return request.get<PreferenceConfig>('/system/preferences')
}

export function updatePreferences(data: Partial<PreferenceConfig>) {
  return request.put<PreferenceConfig>('/system/preferences', data)
}

// ---------------- F9-01 角色权限 ----------------

export interface RoleInfo {
  role: string
  is_super: boolean
  permissions: string[]
  overrides: Record<string, boolean>
}

export interface PermissionGroup {
  group: string
  items: [string, string][]
}

export function getRoles() {
  return request.get<{ roles: RoleInfo[]; catalog: PermissionGroup[] }>('/system/roles')
}

export function updateRolePermissions(role: string, permissions: string[]) {
  return request.put<{ role: string; permissions: string[] }>(`/system/roles/${role}`, { permissions })
}

// ---------------- F9-02 阅卷进度监控 ----------------

export interface ExamProgressSummary {
  exam_id: string
  exam_name: string
  subject: string
  grade: string
  status: string
  choice_total: number
  choice_graded: number
  subjective_total: number
  subjective_done: number
  arbitrating: number
  exception_pending: number
  overall_completion: number
}

export interface ExamProgressDetail {
  exam_id: string
  exam_name: string
  subject: string
  grade: string
  status: string
  overall_completion: number
  choice: {
    total: number
    graded: number
    exception: number
    reviewed: number
    correct: number
    correct_rate: number
    completion_rate: number
  }
  subjective: {
    total: number
    done: number
    arbitrating: number
    by_status: Record<string, number>
    completion_rate: number
  }
  exception: {
    total: number
    pending: number
    resolved: number
    by_status: Record<string, number>
    completion_rate: number
  }
  imports: {
    batch_count: number
    page_count: number
    processed_pages: number
  }
}

export function listMonitorExams(examStatus?: string) {
  return request.get<ExamProgressSummary[]>('/system/monitor/exams', {
    params: examStatus ? { exam_status: examStatus } : {},
  })
}

export function getMonitorExam(examId: string) {
  return request.get<ExamProgressDetail>(`/system/monitor/exams/${examId}`)
}

// ---------------- F9-03 审计日志 ----------------

export interface AuditLog {
  id: string
  user_id: string | null
  username: string | null
  role: string | null
  action: string
  method: string | null
  path: string | null
  resource_type: string | null
  status_code: number | null
  ip: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

export interface AuditLogQuery {
  user_id?: string
  role?: string
  action?: string
  resource_type?: string
  path?: string
  start?: string
  end?: string
  limit?: number
  offset?: number
}

export function listAuditLogs(params: AuditLogQuery) {
  return request.get<{ total: number; items: AuditLog[] }>('/system/audit-logs', { params })
}