import request from './request'

export interface Exam {
  id: string
  name: string
  subject: string
  grade: string
  exam_type: string
  total_score: number
  pass_score?: number
  excellent_score?: number
  answer_card_template_id?: string
  original_paper_path?: string
  original_paper_uploaded_by?: string
  original_paper_uploaded_at?: string
  status: string
  grading_start_at?: string
  grading_end_at?: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface ExamForm {
  name: string
  subject: string
  grade: string
  exam_type: string
  total_score: number
  pass_score?: number
  excellent_score?: number
  answer_card_template_id?: string
  grading_start_at?: string
  grading_end_at?: string
}

export function getExams() {
  return request.get<Exam[]>('/exams')
}

export function getExam(id: string) {
  return request.get<Exam>(`/exams/${id}`)
}

export function createExam(data: ExamForm) {
  return request.post<Exam>('/exams', data)
}

export function updateExam(id: string, data: Partial<ExamForm>) {
  return request.put<Exam>(`/exams/${id}`, data)
}

export function deleteExam(id: string) {
  return request.delete(`/exams/${id}`)
}

export function copyExam(id: string) {
  return request.post<Exam>(`/exams/${id}/copy`)
}

export function lockExam(id: string) {
  return request.post<Exam>(`/exams/${id}/lock`)
}

export function unlockExam(id: string) {
  return request.post<Exam>(`/exams/${id}/unlock`)
}

export function uploadOriginalPaper(id: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post<Exam>(`/exams/${id}/original-paper`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function deleteOriginalPaper(id: string) {
  return request.delete<Exam>(`/exams/${id}/original-paper`)
}

export function importStudents(id: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post<{ total: number; success: number; failed: number; errors: string[] }>(
    `/exams/${id}/students/import`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
}

export function getExamStudents(id: string) {
  return request.get<Array<{
    id: string
    exam_id: string
    student_id: string
    exam_number: string
    name: string
    class_name?: string
    is_absent: boolean
    total_score?: number
  }>>(`/exams/${id}/students`)
}
