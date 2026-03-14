import axios from 'axios';

// 从环境变量获取 API 服务器地址
// 注意：Vite 要求环境变量以 VITE_ 开头才能暴露给前端
const API_HOST = import.meta.env.VITE_API_HOST || '192.168.1.132';
const API_PORT = import.meta.env.VITE_API_PORT || '8011';
const BASE_URL = `http://${API_HOST}:${API_PORT}`;

console.log('[API] Using server:', BASE_URL);
console.log('[API] Environment check:', {
    VITE_API_HOST: import.meta.env.VITE_API_HOST,
    VITE_API_PORT: import.meta.env.VITE_API_PORT,
    resolvedHost: API_HOST,
    resolvedPort: API_PORT,
    resolvedUrl: BASE_URL
});

const client = axios.create({
    baseURL: BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 30000, // 30 秒超时
});

// 添加请求拦截器
client.interceptors.request.use(
    (config) => {
        console.log('[API] Request:', {
            method: config.method,
            url: config.url,
            baseURL: config.baseURL,
            fullURL: `${config.baseURL}/${config.url}`,
        });
        return config;
    },
    (error) => {
        console.error('[API] Request error:', error);
        return Promise.reject(error);
    }
);

// 添加响应拦截器
client.interceptors.response.use(
    (response) => {
        console.log('[API] Response:', {
            status: response.status,
            url: response.config.url,
        });
        return response;
    },
    (error) => {
        console.error('[API] Response error:', {
            message: error.message,
            status: error.response?.status,
            statusText: error.response?.statusText,
            data: error.response?.data,
            url: error.config?.url,
            baseURL: error.config?.baseURL,
        });

        // 如果是网络错误或连接超时
        if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
            console.error('[API] Request timeout. Please check if the server is running at:', BASE_URL);
        }

        // 如果是连接被拒绝
        if (error.message.includes('Network Error') || error.code === 'ERR_NETWORK') {
            console.error('[API] Network error. Please check if the server is running at:', BASE_URL);
            console.error('[API] If you are using the desktop app, make sure the LiveTalking server is accessible.');
        }

        return Promise.reject(error);
    }
);

export default client;

// 导出配置供其他模块使用（如 WebRTC 连接）
export const API_CONFIG = {
    host: API_HOST,
    port: API_PORT,
    baseUrl: BASE_URL,
};

// 获取 API 基础 URL
export const getApiBaseUrl = () => BASE_URL;
