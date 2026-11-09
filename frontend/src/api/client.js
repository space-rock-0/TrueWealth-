import axios from 'axios';

const client = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '/api', // Vite/nginx proxies handle the default path
    headers: {
        'Content-Type': 'application/json',
    },
    withCredentials: true,
});

client.interceptors.request.use((config) => {
    const method = (config.method || 'get').toLowerCase();
    if (!['get', 'head', 'options'].includes(method)) {
        const match = document.cookie.match(/(?:^|; )tw_csrf=([^;]*)/);
        if (match) config.headers['X-CSRF-Token'] = decodeURIComponent(match[1]);
    }
    return config;
});

export default client;
