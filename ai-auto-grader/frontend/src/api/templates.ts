import request from './request'

export type RegionType = 'exam_number' | 'name' | 'choice' | 'subjective'

export interface TemplateRegion {
  id?: string
  template_id?: string
  page_index: number
  region_type: RegionType
  question_number?: string | null
  sub_question_number?: string | null
  max_score: number
  x: number
  y: number
  width: number
  height: number
  options_count: number
  allow_multiple: boolean
  partial_score_rules?: any
  knowledge_tags?: any
  config?: Record<string, any> | null
}

export interface Template {
  id: string
  name: string
  subject?: string | null
  paper_size: 'A3' | 'A4'
  duplex: boolean
  page_count: number
  margin_top: number
  margin_bottom: number
  margin_left: number
  margin_right: number
  title: string
  exam_number_digits: number
  exam_number_mode: 'omr' | 'ocr'
  class_prefix_enabled: boolean
  name_ocr_enabled: boolean
  tilt_threshold: number
  perspective_enabled: boolean
  deskew_enabled: boolean
  is_blank: boolean
  description?: string | null
  source_pdf_path?: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface TemplateDetail extends Template {
  regions: TemplateRegion[]
}

export interface TemplateForm {
  name: string
  subject?: string | null
  paper_size: 'A3' | 'A4'
  duplex: boolean
  page_count: number
  margin_top: number
  margin_bottom: number
  margin_left: number
  margin_right: number
  title: string
  exam_number_digits: number
  exam_number_mode: 'omr' | 'ocr'
  class_prefix_enabled: boolean
  name_ocr_enabled: boolean
  tilt_threshold: number
  perspective_enabled: boolean
  deskew_enabled: boolean
  description?: string | null
}

export interface ChoiceAnswer {
  id?: string
  template_id?: string
  exam_id?: string | null
  question_number: string
  correct_options: string
  score: number
  partial_score_rules?: any
}

export interface AIScoringConfig {
  id?: string
  template_id?: string
  exam_id?: string | null
  question_number: string
  standard_answer?: string | null
  scoring_points?: string[] | null
  deduction_notes?: string | null
  prompt_template?: string | null
  confidence_threshold: number
  score_tolerance: number
  enabled: boolean
}

export function getTemplates(keyword?: string) {
  return request.get<Template[]>('/templates', { params: keyword ? { keyword } : {} })
}

export function getTemplate(id: string) {
  return request.get<TemplateDetail>(`/templates/${id}`)
}

export function createTemplate(data: Partial<TemplateForm>) {
  return request.post<TemplateDetail>('/templates', data)
}

export function updateTemplate(id: string, data: Partial<TemplateForm>) {
  return request.put<TemplateDetail>(`/templates/${id}`, data)
}

export function deleteTemplate(id: string) {
  return request.delete(`/templates/${id}`)
}

export function copyTemplate(id: string, name?: string) {
  return request.post<TemplateDetail>(`/templates/${id}/copy`, { name })
}

export function replaceRegions(id: string, regions: TemplateRegion[]) {
  const payload = regions.map((r) => ({
    page_index: r.page_index,
    region_type: r.region_type,
    question_number: r.question_number ?? null,
    sub_question_number: r.sub_question_number ?? null,
    max_score: r.max_score ?? 0,
    x: r.x,
    y: r.y,
    width: r.width,
    height: r.height,
    options_count: r.options_count ?? 4,
    allow_multiple: r.allow_multiple ?? false,
    partial_score_rules: r.partial_score_rules ?? null,
    knowledge_tags: r.knowledge_tags ?? null,
    config: r.config ?? null,
  }))
  return request.put<TemplateRegion[]>(`/templates/${id}/regions`, payload)
}

export function getChoiceAnswers(id: string) {
  return request.get<ChoiceAnswer[]>(`/templates/${id}/choice-answers`)
}

export function replaceChoiceAnswers(id: string, answers: ChoiceAnswer[]) {
  const payload = {
    answers: answers.map((a) => ({
      question_number: a.question_number,
      correct_options: a.correct_options,
      score: a.score ?? 0,
      partial_score_rules: a.partial_score_rules ?? null,
    })),
  }
  return request.put<ChoiceAnswer[]>(`/templates/${id}/choice-answers`, payload)
}

export function getAIConfigs(id: string) {
  return request.get<AIScoringConfig[]>(`/templates/${id}/ai-configs`)
}

export function replaceAIConfigs(id: string, configs: AIScoringConfig[]) {
  const payload = {
    configs: configs.map((c) => ({
      question_number: c.question_number,
      standard_answer: c.standard_answer ?? null,
      scoring_points: c.scoring_points ?? null,
      deduction_notes: c.deduction_notes ?? null,
      prompt_template: c.prompt_template ?? null,
      confidence_threshold: c.confidence_threshold ?? 0.7,
      score_tolerance: c.score_tolerance ?? 0,
      enabled: c.enabled ?? true,
    })),
  }
  return request.put<AIScoringConfig[]>(`/templates/${id}/ai-configs`, payload)
}

export function exportTemplatePdf(id: string, watermark?: string) {
  return request.get(`/templates/${id}/export-pdf`, {
    params: watermark ? { watermark } : {},
    responseType: 'blob',
  })
}

export function backupTemplate(id: string) {
  return request.get(`/templates/${id}/backup`)
}

export function importTemplateBackup(payload: any) {
  return request.post<TemplateDetail>('/templates/import-backup', { payload })
}

export interface PrecheckIssue {
  level: 'error' | 'warning'
  code: string
  message: string
  page_index?: number | null
  region_index?: number | null
}

export interface PrecheckResult {
  passed: boolean
  error_count: number
  warning_count: number
  issues: PrecheckIssue[]
}

export function precheckTemplate(id: string) {
  return request.post<PrecheckResult>(`/templates/${id}/precheck`)
}