import request from './request'

export type ChoiceStatus = 'scored' | 'exception' | 'reviewed'

export interface ChoiceResult {
  id: string
  exam_id: string
  student_id?: string
  page_id: string
  block_id: string
  region_id: string
  question_number: string
  recognized_options?: string
  correct_options?: string
  is_correct: boolean
  score: number
  max_score: number
  status: ChoiceStatus
  exception_type?: string
  confidence?: number
  fill_ratios?: number[]
  reviewed_by?: string
  reviewed_at?: string
  review_note?: string
  created_at: string
  updated_at?: string
  exam_number?: string
  student_name?: string
  class_name?: string
}

export interface ChoiceGradeResult {
  graded: number
  scored: number
  exception: number
  skipped: number
}

export interface ChoiceQuestionStat {
  question_number: string
  options_count: number
  allow_multiple: boolean
  max_score: number
  total: number
  graded: number
  correct: number
  exception: number
  correct_rate: number
  avg_score: number
  distribution: Record<string, number>
}

export interface ChoiceStatistics {
  overall: {
    total_questions: number
    total_results: number
    graded: number
    exception: number
    reviewed: number
    correct: number
    correct_rate: number
    avg_score: number
  }
  questions: ChoiceQuestionStat[]
}

export const CHOICE_EXCEPTION_LABELS: Record<string, string> = {
  choice_missing_fill: '未填涂',
  choice_multi_fill: '多涂',
  choice_ambiguous: '填涂模糊',
  choice_unreadable: '无法识别',
  choice_no_answer_key: '未配置答案',
}

export function gradeChoices(examId: string) {
  return request.post<ChoiceGradeResult>('/choices/grade', null, { params: { exam_id: examId } })
}

export function listChoiceResults(params: {
  exam_id: string
  status?: ChoiceStatus
  student_id?: string
  question_number?: string
}) {
  return request.get<ChoiceResult[]>('/choices/results', { params })
}

export function reviewChoiceResult(resultId: string, data: { options: string; note?: string }) {
  return request.post<ChoiceResult>(`/choices/results/${resultId}/review`, data)
}

export function getChoiceStatistics(examId: string) {
  return request.get<ChoiceStatistics>('/choices/statistics', { params: { exam_id: examId } })
}

export interface ChoiceAnswerItem {
  question_number: string
  options_count: number
  allow_multiple: boolean
  max_score: number
  correct_options: string
  score: number
  source: 'exam' | 'template' | 'none'
}

export interface ChoiceAnswerList {
  template_id: string
  items: ChoiceAnswerItem[]
}

export interface ChoiceAnswerSaveResult extends ChoiceAnswerList {
  grade?: ChoiceGradeResult
}

export function getChoiceAnswers(examId: string) {
  return request.get<ChoiceAnswerList>('/choices/answers', { params: { exam_id: examId } })
}

export function saveChoiceAnswers(
  examId: string,
  items: { question_number: string; correct_options: string; score?: number }[],
  regrade = true,
) {
  return request.put<ChoiceAnswerSaveResult>('/choices/answers', { items, regrade }, { params: { exam_id: examId } })
}