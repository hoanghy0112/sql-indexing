import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

// Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  register: (data: { username: string; email: string; password: string }) =>
    api.post('/auth/register', data),

  login: (data: { username: string; password: string }) =>
    api.post<{ access_token: string; token_type: string; expires_in: number }>(
      '/auth/login',
      data
    ),

  me: () => api.get('/auth/me'),

  refresh: () => api.post('/auth/refresh'),
}

// Connections API
export const connectionsApi = {
  list: () => api.get('/connections'),

  get: (id: number) => api.get(`/connections/${id}`),

  create: (data: {
    name: string
    description?: string
    host: string
    port: number
    database: string
    username: string
    password: string
    ssl_mode?: string
  }) => api.post('/connections', data),

  createFromUrl: (data: {
    name: string
    description?: string
    connection_url: string
  }) => api.post('/connections/from-url', data),

  update: (id: number, data: Partial<{
    name: string
    description: string
    host: string
    port: number
    database: string
    username: string
    password: string
    ssl_mode: string
  }>) => api.put(`/connections/${id}`, data),

  delete: (id: number) => api.delete(`/connections/${id}`),

  test: (id: number) => api.post(`/connections/${id}/test`),

  reanalyze: (id: number) => api.post(`/connections/${id}/reanalyze`),

  // Shares
  listShares: (id: number) => api.get(`/connections/${id}/shares`),

  addShare: (id: number, data: { user_id: number; can_edit: boolean }) =>
    api.post(`/connections/${id}/shares`, data),

  removeShare: (connectionId: number, userId: number) =>
    api.delete(`/connections/${connectionId}/shares/${userId}`),
}

// Intelligence API
export const intelligenceApi = {
  getInsights: (connectionId: number) =>
    api.get(`/intelligence/${connectionId}/insights`),

  getStats: (connectionId: number) =>
    api.get(`/intelligence/${connectionId}/stats`),

  updateInsight: (connectionId: number, insightId: number, data: {
    summary?: string
    insight_document?: string
  }) => api.put(`/intelligence/${connectionId}/insights/${insightId}`, data),
}

// Chat API
export const chatApi = {
  send: (connectionId: number, data: {
    question: string
    explain_mode?: boolean
    session_id?: number
  }) => api.post(`/chat/${connectionId}`, data),

  listSessions: (connectionId: number) =>
    api.get(`/chat/${connectionId}/sessions`),

  getSession: (connectionId: number, sessionId: number) =>
    api.get(`/chat/${connectionId}/sessions/${sessionId}`),

  deleteSession: (connectionId: number, sessionId: number) =>
    api.delete(`/chat/${connectionId}/sessions/${sessionId}`),
}

// System API
export const systemApi = {
  health: () => api.get('/system/health'),

  getConnectionStatus: (connectionId: number) =>
    api.get(`/system/connections/${connectionId}/status`),

  getSqlHistory: (connectionId: number, limit = 50, offset = 0) =>
    api.get(`/system/connections/${connectionId}/sql-history`, {
      params: { limit, offset },
    }),

  getStats: () => api.get('/system/stats'),
}

// Users API
export const usersApi = {
  search: (query: string) => api.get('/users/search', { params: { q: query } }),

  updateProfile: (data: { email?: string }) => api.put('/users/me', data),

  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post('/users/me/change-password', data),
}
