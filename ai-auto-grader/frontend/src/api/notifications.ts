import request from './request'

export type NotificationLevel = 'info' | 'success' | 'warning' | 'danger'

export interface NotificationItem {
  id: string
  event: string
  title: string
  content?: string | null
  level: NotificationLevel
  link?: string | null
  meta?: Record<string, unknown> | null
  is_read: boolean
  created_at: string
  read_at?: string | null
}

export interface NotificationListResult {
  total: number
  unread: number
  items: NotificationItem[]
}

export function listNotifications(params?: { unread_only?: boolean; limit?: number; offset?: number }) {
  return request.get<NotificationListResult>('/notifications', { params })
}

export function getUnreadCount() {
  return request.get<{ unread: number }>('/notifications/unread-count')
}

export function markNotificationRead(id: string) {
  return request.post<NotificationItem>(`/notifications/${id}/read`)
}

export function markAllNotificationsRead() {
  return request.post<{ updated: number }>('/notifications/read-all')
}

export function deleteNotification(id: string) {
  return request.delete(`/notifications/${id}`)
}