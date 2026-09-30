import request from './request'
import { downloadBlob } from './download'

export interface ExamArchive {
  id: string
  exam_id: string
  exam_name: string
  status: string
  previous_status: string | null
  file_size: number
  original_paper_included: boolean
  snapshot: Record<string, unknown> | null
  created_by: string | null
  created_at: string
  restored_at: string | null
}

export function listArchives(includeRestored = true) {
  return request.get<ExamArchive[]>('/archives', { params: { include_restored: includeRestored } })
}

export function createArchive(examId: string) {
  return request.post<ExamArchive>(`/archives/exams/${examId}`)
}

export function restoreArchive(archiveId: string) {
  return request.post<ExamArchive>(`/archives/${archiveId}/restore`)
}

export function deleteArchive(archiveId: string) {
  return request.delete(`/archives/${archiveId}`)
}

export function downloadArchive(archiveId: string, examName = '归档包') {
  return downloadBlob(`/archives/${archiveId}/download`, `${examName}_归档.zip`)
}