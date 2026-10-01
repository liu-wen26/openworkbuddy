import request from './request'

export type PrecheckStatus = 'active' | 'running' | 'cleared'
export type PrecheckPageStatus = 'pending' | 'processed' | 'exception'

export interface PrecheckSummary {
  pages: number
  samples: number
  provider?: string | null
  cut_blocks: number
  cut_failed: number
  cut_positioning: number
  exam_number_found: number
  exam_number_matched: number
  choice_total: number
  choice_scored: number
  choice_correct: number
  choice_exception: number
  subjective_total: number
  ai_scored: number
  ai_low_confidence: number
}

export interface PrecheckCutBlock {
  index: number
  region_type: string
  question_number?: string | null
  sub_question_number?: string | null
  group_key?: string | null
  region_count?: number
  grading?: boolean
  max_score: number
  options_count: number
  allow_multiple: boolean
  x: number
  y: number
  width: number
  height: number
  image_path?: string | null
  width_px: number
  height_px: number
  status: string
  message?: string | null
}

export interface PrecheckOMRItem {
  question_number?: string | null
  region_index: number
  options_count: number
  allow_multiple: boolean
  recognized_options: string
  correct_options: string
  is_correct: boolean
  score: number
  max_score: number
  confidence: number
  fill_ratios: number[]
  status: string
}

export interface PrecheckAIItem {
  question_number?: string | null
  region_index: number
  max_score: number
  ai_score?: number | null
  ai_comment?: string | null
  ai_confidence?: number | null
  ai_model?: string | null
  ai_provider?: string | null
  threshold: number
  low_confidence: boolean
  status: string
}

export interface PrecheckPage {
  id: string
  session_id: string
  source_type: string
  original_page_index?: number | null
  preprocessed_image_path?: string | null
  exam_number_ocr?: string | null
  tilt_angle?: number | null
  status: PrecheckPageStatus
  cut_result?: PrecheckCutBlock[] | null
  omr_result?: PrecheckOMRItem[] | null
  ai_result?: PrecheckAIItem[] | null
  created_at: string
}

export interface PrecheckSession {
  id: string
  exam_id: string
  status: PrecheckStatus
  sample_count: number
  page_count: number
  message?: string | null
  summary?: PrecheckSummary | null
  created_by?: string | null
  created_at: string
  cleared_at?: string | null
}

export interface PrecheckSessionDetail extends PrecheckSession {
  pages: PrecheckPage[]
}

export const PRECHECK_PAGE_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  processed: '已完成',
  exception: '存在异常',
}

export const PRECHECK_PAGE_STATUS_TYPES: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
  pending: 'info',
  processed: 'success',
  exception: 'warning',
}

export const OMR_STATUS_LABELS: Record<string, string> = {
  ok: '正常',
  blank: '漏涂',
  multi: '多涂',
  ambiguous: '模糊',
  unreadable: '无法识别',
  no_answer_key: '未配置答案',
}

export function openPrecheckSession(examId: string) {
  return request.post<PrecheckSession>('/precheck/sessions', { exam_id: examId })
}

export function listPrecheckSessions(examId: string) {
  return request.get<PrecheckSession[]>('/precheck/sessions', { params: { exam_id: examId } })
}

export function getPrecheckSession(sessionId: string) {
  return request.get<PrecheckSessionDetail>(`/precheck/sessions/${sessionId}`)
}

export function uploadPrecheckSamples(sessionId: string, files: File[]) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return request.post<{ session: PrecheckSession; added: number; pages: PrecheckPage[] }>(
    `/precheck/sessions/${sessionId}/samples`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 },
  )
}

export function runPrecheck(sessionId: string) {
  return request.post<PrecheckSession>(`/precheck/sessions/${sessionId}/run`)
}

export function clearPrecheckSession(sessionId: string) {
  return request.post<{
    session_id: string
    status: string
    cleared_pages: number
    cleared_samples: number
  }>(`/precheck/sessions/${sessionId}/clear`)
}

export async function getPrecheckPageImageUrl(pageId: string) {
  const res = await request.get(`/precheck/pages/${pageId}/image`, { responseType: 'blob' })
  return URL.createObjectURL(res.data)
}

export async function getPrecheckBlockImageUrl(pageId: string, blockIndex: number) {
  const res = await request.get(`/precheck/pages/${pageId}/blocks/${blockIndex}/image`, {
    responseType: 'blob',
  })
  return URL.createObjectURL(res.data)
}