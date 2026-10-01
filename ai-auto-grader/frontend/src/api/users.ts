import request from './request'
import type { User } from './auth'

export interface UserCreateForm {
  username: string
  real_name: string
  password: string
  role: string
  email?: string
  phone?: string
}

export interface UserUpdateForm {
  real_name?: string
  role?: string
  email?: string
  phone?: string
  is_active?: boolean
  password?: string
}

export interface RoleOption {
  role: string
  label: string
}

export const ROLE_LABELS: Record<string, string> = {
  super_admin: '超级管理员',
  exam_admin: '教务管理员',
  group_leader: '教研组长',
  teacher: '阅卷教师',
}

export function listUsers() {
  return request.get<User[]>('/users')
}

export function listRoleOptions() {
  return request.get<RoleOption[]>('/users/roles')
}

export function createUser(data: UserCreateForm) {
  return request.post<User>('/users', data)
}

export function updateUser(id: string, data: UserUpdateForm) {
  return request.put<User>(`/users/${id}`, data)
}

export function deleteUser(id: string) {
  return request.delete(`/users/${id}`)
}