/**
 * 阶段 9：实时推送 WebSocket 组合式函数。
 *
 * 全应用共享单一连接（模块级单例），组件通过 on/off 注册事件处理器，
 * 按消息 type 分发。连接断开后自动重连并恢复已订阅 topic。
 */
import { ref } from 'vue'
import Cookies from 'js-cookie'

export interface RealtimeMessage {
  topic?: string
  type: string
  data: Record<string, unknown>
  ts?: string
}

type Handler = (data: Record<string, unknown>, message: RealtimeMessage) => void

const connected = ref(false)
const connecting = ref(false)

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let manualClose = false
let retry = 0

const handlers = new Map<string, Set<Handler>>()
const topics = new Set<string>()

function buildWsUrl(token: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string) || '/api/v1'
  let prefix: string
  if (base.startsWith('http')) {
    prefix = base.replace(/^http/, 'ws')
  } else {
    prefix = `${window.location.origin.replace(/^http/, 'ws')}${base}`
  }
  return `${prefix.replace(/\/$/, '')}/ws?token=${encodeURIComponent(token)}`
}

function scheduleReconnect() {
  if (manualClose || reconnectTimer) return
  const delay = Math.min(1000 * 2 ** retry, 15000)
  retry += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, delay)
}

function dispatch(message: RealtimeMessage) {
  const set = handlers.get(message.type)
  if (set) {
    set.forEach((handler) => {
      try {
        handler(message.data, message)
      } catch {
        // 单个处理器异常不应影响其它订阅者
      }
    })
  }
}

export function connect() {
  if (socket || connecting.value) return
  const token = Cookies.get('access_token')
  if (!token) return

  connecting.value = true
  manualClose = false
  try {
    socket = new WebSocket(buildWsUrl(token))
  } catch {
    connecting.value = false
    scheduleReconnect()
    return
  }

  socket.onopen = () => {
    connected.value = true
    connecting.value = false
    retry = 0
    // 恢复历史订阅
    topics.forEach((topic) => {
      socket?.send(JSON.stringify({ action: 'subscribe', topic }))
    })
  }

  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data) as RealtimeMessage
      dispatch(message)
    } catch {
      // 忽略无法解析的消息
    }
  }

  socket.onclose = () => {
    socket = null
    connected.value = false
    connecting.value = false
    scheduleReconnect()
  }

  socket.onerror = () => {
    socket?.close()
  }
}

export function disconnect() {
  manualClose = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  socket?.close()
  socket = null
  connected.value = false
  connecting.value = false
}

export function subscribe(topic: string) {
  if (!topic || topics.has(topic)) return
  topics.add(topic)
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'subscribe', topic }))
  } else {
    connect()
  }
}

export function unsubscribe(topic: string) {
  if (!topics.has(topic)) return
  topics.delete(topic)
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'unsubscribe', topic }))
  }
}

export function on(type: string, handler: Handler): () => void {
  if (!handlers.has(type)) handlers.set(type, new Set())
  handlers.get(type)!.add(handler)
  return () => off(type, handler)
}

export function off(type: string, handler: Handler) {
  handlers.get(type)?.delete(handler)
}

export function useRealtime() {
  return { connected, connecting, connect, disconnect, subscribe, unsubscribe, on, off }
}