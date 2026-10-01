import request from './request'

export interface ScoreBin {
  label: string
  min: number
  max: number
  count: number
}

export interface ClassStat {
  class_name: string
  student_count: number
  appeared: number
  absent: number
  avg_score: number
  max_score: number
  min_score: number
  median_score: number
  pass_rate: number
  excellent_rate: number
  choice_rate?: number
  subjective_rate?: number
  question_count?: number
}

export interface ExamOverview {
  exam_id: string
  exam_name: string
  subject: string
  grade: string
  total_score: number
  pass_score: number
  excellent_score: number
  roster_count: number
  appeared_count: number
  absent_count: number
  absent_flag_count: number
  avg_score: number
  max_score: number
  min_score: number
  median_score: number
  score_std: number
  pass_rate: number
  excellent_rate: number
  distribution: ScoreBin[]
  classes: ClassStat[]
}

export interface ClassReport {
  exam_id: string
  total_score: number
  pass_score: number
  excellent_score: number
  classes: ClassStat[]
}

export interface CommonWrong {
  options: string
  count: number
}

export interface QuestionStat {
  question_number: string
  question_type: 'choice' | 'subjective'
  max_score: number
  total: number
  graded: number
  exception: number
  correct: number | null
  correct_rate: number | null
  avg_score: number
  score_rate: number
  difficulty: number
  discrimination: number
  option_distribution: Record<string, number> | null
  common_wrong: CommonWrong[] | null
  knowledge_tags: string[]
}

export interface QuestionReport {
  exam_id: string
  total_questions: number
  questions: QuestionStat[]
  high_error_questions: QuestionStat[]
}

export type MasteryLevel = 'mastered' | 'basic' | 'weak'

export interface KnowledgeTagStat {
  knowledge_tag: string
  question_numbers: string[]
  question_count: number
  avg_score_rate: number
  mastery_level: MasteryLevel
}

export interface KnowledgeReport {
  exam_id: string
  tag_count: number
  tags: KnowledgeTagStat[]
}

export interface AnalyticsStudent {
  student_id: string
  name: string
  exam_number: string
  class_name: string | null
  is_absent: boolean
  total_score: number
}

export interface StudentQuestionItem {
  question_number: string
  question_type: 'choice' | 'subjective'
  max_score: number
  score: number | null
  is_correct: boolean | null
  recognized_options: string | null
  correct_options: string | null
  mark: string | null
  knowledge_tags: string[]
}

export interface StudentReport {
  exam_id: string
  exam_name: string
  student_id: string
  student_name: string
  exam_number: string
  class_name: string
  is_absent: boolean
  total_score: number
  pass_score: number
  excellent_score: number
  score: number
  choice_score: number
  subjective_score: number
  rank_in_grade: number | null
  rank_in_class: number | null
  grade_student_count: number
  class_student_count: number
  passed: boolean
  excellent: boolean
  questions: StudentQuestionItem[]
  knowledge: { knowledge_tag: string; avg_score_rate: number; mastery_level: MasteryLevel }[]
  marks: {
    question_number: string | null
    mark: string
    score: number | null
    max_score: number
    block_id: string | null
    comment: string | null
  }[]
}

export interface ReviewMaterial {
  result_id: string
  block_id: string | null
  question_number: string | null
  student_id: string | null
  student_name: string | null
  class_name: string | null
  exam_number: string | null
  score: number | null
  max_score: number
  mark: string
  comment: string | null
  arbitration_note: string | null
}

export interface ReviewMaterials {
  exam_id: string
  excellent: ReviewMaterial[]
  typical_error: ReviewMaterial[]
  blank: ReviewMaterial[]
  high_error_questions: QuestionStat[]
  question_count: number
}

export const MASTERY_LABELS: Record<string, string> = {
  mastered: '已掌握',
  basic: '基本掌握',
  weak: '薄弱',
}

export const MASTERY_TYPES: Record<string, 'success' | 'warning' | 'danger'> = {
  mastered: 'success',
  basic: 'warning',
  weak: 'danger',
}

export const MARK_LABELS: Record<string, string> = {
  none: '无',
  excellent: '优秀',
  typical_error: '典型错误',
  blank: '空白',
}

export function getOverview(examId: string) {
  return request.get<ExamOverview>(`/analytics/exams/${examId}/overview`)
}

export function getClassReport(examId: string) {
  return request.get<ClassReport>(`/analytics/exams/${examId}/classes`)
}

export function getQuestionReport(examId: string) {
  return request.get<QuestionReport>(`/analytics/exams/${examId}/questions`)
}

export function getKnowledgeReport(examId: string) {
  return request.get<KnowledgeReport>(`/analytics/exams/${examId}/knowledge`)
}

export function listAnalyticsStudents(examId: string) {
  return request.get<AnalyticsStudent[]>(`/analytics/exams/${examId}/students`)
}

export function getStudentReport(examId: string, studentId: string) {
  return request.get<StudentReport>(`/analytics/exams/${examId}/students/${studentId}`)
}

export function getReviewMaterials(examId: string, limit = 30) {
  return request.get<ReviewMaterials>(`/analytics/exams/${examId}/review-materials`, {
    params: { limit },
  })
}

export function getOriginalPaperInfo(examId: string) {
  return request.get<{
    original_paper_path: string | null
    original_paper_uploaded_by: string | null
    original_paper_uploaded_at: string | null
  }>(`/exams/${examId}/original-paper`)
}

export async function getOriginalPaperPreviewUrl(examId: string) {
  const res = await request.get(`/exams/${examId}/original-paper/preview`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}