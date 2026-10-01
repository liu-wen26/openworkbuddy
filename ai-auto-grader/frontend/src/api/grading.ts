import request from './request'

export type GradingMode = 'manual' | 'ai_assist' | 'double'
export type GradingStatus =
  | 'pending'
  | 'ai_scored'
  | 'graded'
  | 'graded_pending_second'
  | 'arbitrating'
  | 'arbitrated'
export type AnswerMark = 'none' | 'excellent' | 'typical_error' | 'blank'

export interface GradingTask {
  id: string
  exam_id: string
  student_id?: string | null
  page_id: string
  block_id: string
  region_id: string
  question_number?: string | null
  max_score: number

  grading_mode: GradingMode
  status: GradingStatus

  ai_score?: number | null
  ai_comment?: string | null
  ai_confidence?: number | null
  ai_model?: string | null
  ai_provider?: string | null
  ai_scored_at?: string | null

  first_score?: number | null
  first_comment?: string | null
  first_grader_id?: string | null
  first_graded_at?: string | null

  second_score?: number | null
  second_comment?: string | null
  second_grader_id?: string | null
  second_graded_at?: string | null

  final_score?: number | null
  arbiter_id?: string | null
  arbitrated_at?: string | null
  arbitration_note?: string | null

  mark: AnswerMark
  assigned_to?: string | null
  assigned_at?: string | null

  created_at: string
  updated_at?: string | null

  exam_number?: string | null
  student_name?: string | null
  class_name?: string | null
}

export interface GradingProgress {
  total: number
  done: number
  completion_rate: number
  by_status: Record<string, number>
  by_question: {
    question_number: string
    total: number
    graded: number
    arbitrating: number
    ai_scored: number
    max_score: number
  }[]
  ai_scored: number
  ai_pending_review: number
  ai_pending_rate: number
  finished_rate: number
}

export interface GradingLog {
  id: string
  exam_id: string
  block_id?: string | null
  result_id?: string | null
  action: string
  operator_id?: string | null
  operator_name?: string | null
  score_before?: number | null
  score_after?: number | null
  note?: string | null
  detail?: unknown
  created_at: string
}

export interface GradingDistributeResult {
  mode: GradingMode
  assigned: number
}

export interface GradingAIScoreResult {
  scored: number
  low_confidence: number
  skipped: number
  failed: number
  provider: string
}

export const GRADING_MODE_LABELS: Record<string, string> = {
  manual: '人工阅卷',
  ai_assist: 'AI 辅助阅卷',
  double: '双评模式',
}

export const GRADING_STATUS_LABELS: Record<string, string> = {
  pending: '待评分',
  ai_scored: 'AI 已评',
  graded: '已完成',
  graded_pending_second: '待二评',
  arbitrating: '待仲裁',
  arbitrated: '已仲裁',
}

export const GRADING_STATUS_TYPES: Record<string, 'success' | 'warning' | 'info' | 'primary' | 'danger'> = {
  pending: 'info',
  ai_scored: 'primary',
  graded: 'success',
  graded_pending_second: 'warning',
  arbitrating: 'danger',
  arbitrated: 'success',
}

export const ANSWER_MARK_LABELS: Record<string, string> = {
  none: '无标记',
  excellent: '优秀答卷',
  typical_error: '典型错误',
  blank: '空白作答',
}

export const GRADING_ACTION_LABELS: Record<string, string> = {
  distribute: '任务分发',
  ai_score: 'AI 预评',
  grade_first: '人工一评',
  grade_second: '人工二评',
  arbitrate: '仲裁终评',
}

export function distributeGrading(
  examId: string,
  data: { mode: GradingMode; assign_to?: string; question_numbers?: string[] },
) {
  return request.post<GradingDistributeResult>('/grading/distribute', data, { params: { exam_id: examId } })
}

export function runAIGrading(examId: string) {
  return request.post<GradingAIScoreResult>('/grading/ai-score', null, { params: { exam_id: examId } })
}

export function listGradingTasks(params: {
  exam_id: string
  status?: GradingStatus
  question_number?: string
  mine?: boolean
}) {
  return request.get<GradingTask[]>('/grading/tasks', { params })
}

export function gradeTask(
  resultId: string,
  data: { score: number; comment?: string; mark?: AnswerMark },
) {
  return request.post<GradingTask>(`/grading/tasks/${resultId}/grade`, data)
}

export function listArbitration(examId: string) {
  return request.get<GradingTask[]>('/grading/arbitration', { params: { exam_id: examId } })
}

export function arbitrateTask(resultId: string, data: { final_score: number; note?: string }) {
  return request.post<GradingTask>(`/grading/arbitration/${resultId}`, data)
}

export function getGradingProgress(examId: string) {
  return request.get<GradingProgress>('/grading/progress', { params: { exam_id: examId } })
}

export function listGradingLogs(examId: string, resultId?: string) {
  return request.get<GradingLog[]>('/grading/logs', {
    params: { exam_id: examId, result_id: resultId || undefined },
  })
}