/* BassaAI Translator - Shared JS utilities */
const API = '';

function getToken() {
    return localStorage.getItem('bassa_token');
}

function setToken(token) {
    localStorage.setItem('bassa_token', token);
}

function clearToken() {
    localStorage.removeItem('bassa_token');
    localStorage.removeItem('bassa_user');
}

function getUser() {
    const u = localStorage.getItem('bassa_user');
    return u ? JSON.parse(u) : null;
}

function setUser(user) {
    localStorage.setItem('bassa_user', JSON.stringify(user));
}

async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const resp = await fetch(API + url, { ...options, headers });
    if (resp.status === 401) {
        clearToken();
    }
    return resp;
}

function showToast(message, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

async function checkAuth() {
    const token = getToken();
    if (!token) return null;
    try {
        const resp = await apiFetch('/api/auth/me');
        if (resp.ok) {
            const user = await resp.json();
            setUser(user);
            return user;
        }
    } catch {}
    clearToken();
    return null;
}

function logout() {
    clearToken();
    window.location.href = '/';
}
