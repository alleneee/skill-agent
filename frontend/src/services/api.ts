// 带配置的 Axios 实例
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 120000, // agents 执行超时 2 分钟
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 如有需要可在此添加鉴权 token
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // 全局错误处理
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

export default apiClient;
