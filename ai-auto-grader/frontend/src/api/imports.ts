import request from './request'

export type ImportType = 'pdf' | 'image'
export type BatchStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface ImportBatch {
  id: string
  exam_id: string
  import_type: ImportType
  status: BatchStatus
  total_files: number
  total_pages: number
  processed_pages: number
  source: string
  message?: string | null
  created_by: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface ImportProgress {
  batch_id: string
  status: BatchStatus
  total_pages: number
  processed_pages: number
  percent: number
  exception_count: number
  message?: string | null
}

export interface ImportedPage {
  id: string
  batch_id: string
  exam_id: string
  source_type: string
  original_file_path: string
  original_page_index?: number | null
  preprocessed_image_path?: string | null
  student_id?: string | null
  exam_number_ocr?: string | null
  tilt_angle?: number | null
  perspective_corrected: boolean
  status: string
  created_at: string
  student_name?: string | null
  class_name?: string | null
}

export interface AnswerBlock {
  id: string
  page_id: string
  exam_id: string
  student_id?: string | null
  region_id: string
  question_number?: string | null
  block_type: string
  image_path?: string | null
  x: number
  y: number
  width: number
  height: number
  status: string
}

export interface ExamExceptionItem {
  id: string
  exam_id: string
  page_id?: string | null
  block_id?: string | null
  exception_type: string
  source: string
  status: string
  description?: string | null
  snapshot_path?: string | null
  resolved_by?: string | null
  resolved_at?: string | null
  resolution_action?: string | null
  resolution_note?: string | null
  created_at: string
  exam_number_ocr?: string | null
  student_name?: string | null
}

export const EXCEPTION_TYPE_LABELS: Record<string, string> = {
  exam_number_not_found: '考号未识别（请检查填涂或手动输入）',
  exam_number_not_match: '考号不在花名册（请确认考生信息）',
  tilt_exceed: '倾斜超限',
  perspective_exceed: '透视矫正超限',
  cut_failed: '题块切割失败',
  choice_multi: '选择题多涂',
  choice_blank: '选择题漏涂',
  choice_fuzzy: '选择题填涂模糊',
  ai_low_confidence: 'AI低置信度',
  manual_review: '人工标记复核',
}

// ---------------- 批次 ----------------

export function createImportBatch(data: { exam_id: string; import_type: ImportType; source?: string }) {
  return request.post<ImportBatch>('/imports/batches', data)
}

export function listImportBatches(params: { exam_id: string; status?: string }) {
  return request.get<ImportBatch[]>('/imports/batches', { params })
}

export function getImportBatch(batchId: string) {
  return request.get<ImportBatch>(`/imports/batches/${batchId}`)
}

export function deleteImportBatch(batchId: string) {
  return request.delete(`/imports/batches/${batchId}`)
}

export function uploadSourceFiles(batchId: string, files: File[], autoProcess = true) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return request.post(`/imports/batches/${batchId}/files`, form, {
    params: { auto_process: autoProcess },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  })
}

export function getImportProgress(batchId: string) {
  return request.get<ImportProgress>(`/imports/batches/${batchId}/progress`)
}

export function processImportBatch(batchId: string) {
  return request.post<ImportProgress>(`/imports/batches/${batchId}/process`)
}

// ---------------- 分片上传 / 断点续传 ----------------

export interface ChunkUploadStatus {
  upload_id: string
  filename: string
  total_size: number
  chunk_size: number
  total_chunks: number
  received: number[]
  completed: boolean
}

export function initChunkUpload(
  batchId: string,
  data: { filename: string; total_size: number; chunk_size?: number },
) {
  return request.post<ChunkUploadStatus>(`/imports/batches/${batchId}/uploads`, data)
}

export function getChunkUploadStatus(batchId: string, uploadId: string) {
  return request.get<ChunkUploadStatus>(`/imports/batches/${batchId}/uploads/${uploadId}`)
}

export function uploadChunk(batchId: string, uploadId: string, index: number, blob: Blob) {
  return request.put<ChunkUploadStatus>(
    `/imports/batches/${batchId}/uploads/${uploadId}`,
    blob,
    {
      params: { index },
      headers: { 'Content-Type': 'application/octet-stream' },
      timeout: 120000,
    },
  )
}

export function completeChunkUpload(batchId: string, uploadId: string, autoProcess = true) {
  return request.post<{ batch: ImportBatch; pages: ImportedPage[]; mode: string }>(
    `/imports/batches/${batchId}/uploads/${uploadId}/complete`,
    null,
    { params: { auto_process: autoProcess }, timeout: 120000 },
  )
}

// ---------------- 答卷页与题块 ----------------

export function listBatchPages(batchId: string) {
  return request.get<ImportedPage[]>(`/imports/batches/${batchId}/pages`)
}

export function listPages(params: { exam_id: string; batch_id?: string; status?: string }) {
  return request.get<ImportedPage[]>('/imports/pages', { params })
}

export function getPage(pageId: string) {
  return request.get<ImportedPage>(`/imports/pages/${pageId}`)
}

export function listPageBlocks(pageId: string) {
  return request.get<AnswerBlock[]>(`/imports/pages/${pageId}/blocks`)
}

export function setPageExamNumber(pageId: string, examNumber: string) {
  return request.post<ImportedPage>(`/imports/pages/${pageId}/exam-number`, { exam_number: examNumber })
}

export function recutPage(pageId: string, perspectivePoints?: number[][]) {
  return request.post<ImportedPage>(`/imports/pages/${pageId}/recut`, {
    perspective_points: perspectivePoints ?? null,
  })
}

export async function getPageImageUrl(pageId: string) {
  const res = await request.get(`/imports/pages/${pageId}/image`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}

export async function getPageOriginalUrl(pageId: string) {
  const res = await request.get(`/imports/pages/${pageId}/original`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}

export async function getPageSourceImageUrl(pageId: string) {
  const res = await request.get(`/imports/pages/${pageId}/source-image`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}

export async function getBlockImageUrl(blockId: string) {
  const res = await request.get(`/imports/blocks/${blockId}/image`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}

// ---------------- 异常中心 ----------------

export function getExceptionSummary(examId: string) {
  return request.get<{
    exam_id: string
    total: number
    by_status: Record<string, number>
    by_type: Record<string, Record<string, number>>
  }>('/imports/exceptions/summary', { params: { exam_id: examId } })
}

export function listExceptions(params: {
  exam_id: string
  status?: string
  exception_type?: string
  batch_id?: string
}) {
  return request.get<ExamExceptionItem[]>('/imports/exceptions', { params })
}

export function updateException(
  id: string,
  data: { status: string; resolution_action?: string; resolution_note?: string },
) {
  return request.put<ExamExceptionItem>(`/imports/exceptions/${id}`, data)
}

export async function getExceptionSnapshotUrl(id: string) {
  const res = await request.get(`/imports/exceptions/${id}/snapshot`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}