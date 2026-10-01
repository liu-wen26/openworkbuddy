import { downloadBlob } from './download'

// ---------------- F10-01 成绩明细 ----------------

export function exportGradeDetail(examId: string, examName = '成绩明细') {
  return downloadBlob(`/exports/exams/${examId}/grade-detail`, `${examName}_成绩明细.xlsx`)
}

// ---------------- F10-03 学情报表 ----------------

export function exportReport(examId: string, format: 'xlsx' | 'html' = 'xlsx', examName = '学情报表') {
  const ext = format === 'html' ? 'html' : 'xlsx'
  return downloadBlob(`/exports/exams/${examId}/report`, `${examName}_学情报表.${ext}`, { format })
}

// ---------------- F10-02 答卷/错题图片 ----------------

export interface AnswerImagesQuery {
  student_id?: string
  question_number?: string
  mark?: 'excellent' | 'typical_error' | 'blank'
}

export function exportAnswerImages(examId: string, params: AnswerImagesQuery = {}, examName = '答卷图片') {
  return downloadBlob(`/exports/exams/${examId}/answer-images`, `${examName}_答卷图片.zip`, params)
}