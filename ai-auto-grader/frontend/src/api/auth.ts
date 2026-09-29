import request from './request'

export interface LoginForm {
  username: string
  password: string
}

export interface User {
  id: string
  username: string
  real_name: string
  role: string
  email?: string
  phone?: string
  is_active: boolean
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: User
}

export function login(data: LoginForm) {
  return request.post<LoginResult>('/auth/login', data)
}

export function getMe() {
  return request.get<User>('/auth/me')
}
