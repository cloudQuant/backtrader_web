import axios from 'axios'
import type { AxiosInstance, AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

// 创建axios实例
const api: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error: AxiosError) => {
    const status = error.response?.status
    const data = error.response?.data as { detail?: string }
    
    if (status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      ElMessage.error('登录已过期，请重新登录')
    } else if (status === 403) {
      ElMessage.error('没有权限访问')
    } else if (status === 404) {
      ElMessage.error('资源不存在')
    } else if (status === 500) {
      ElMessage.error('服务器错误')
    } else {
      ElMessage.error(data?.detail || '请求失败')
    }
    
    return Promise.reject(error)
  }
)

export default api
