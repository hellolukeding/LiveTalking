import axios from 'axios';

// 从环境变量获取 API 服务器地址
// 注意：Vite 要求环境变量以 VITE_ 开头才能暴露给前端
const API_HOST = import.meta.env.VITE_API_HOST || 'localhost';
const API_PORT = import.meta.env.VITE_API_PORT || '8010';
const BASE_URL = `http://${API_HOST}:${API_PORT}`;

console.log('[API] Using server:', BASE_URL);

const client = axios.create({
    baseURL: BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export default client;

// 导出配置供其他模块使用（如 WebRTC 连接）
export const API_CONFIG = {
    host: API_HOST,
    port: API_PORT,
    baseUrl: BASE_URL,
};

// 获取 API 基础 URL
export const getApiBaseUrl = () => BASE_URL;
