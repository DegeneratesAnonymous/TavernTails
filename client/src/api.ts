const inferApiBase = () => {
  if (process.env.REACT_APP_API_URL && process.env.REACT_APP_API_URL.trim().length > 0) {
    return process.env.REACT_APP_API_URL.trim().replace(/\/$/, '')
  }
  if (typeof window !== 'undefined') {
    const origin = window.location.origin
    // If running on localhost (any port), map to backend port 8000 for dev
    try {
      const url = new URL(origin)
      if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') {
        return `${url.protocol}//${url.hostname}:8000`
      }
    } catch (e) {
      // fallback
      if (/localhost|127\.0\.0\.1/.test(origin)) return origin.replace(/:\d+$/,'') + ':8000'
    }
    return origin
  }
  return 'http://localhost:8000'
}

export const API_BASE = inferApiBase()

export const buildApiUrl = (path: string) => {
  if (!path.startsWith('/')) {
    return `${API_BASE}/${path}`
  }
  return `${API_BASE}${path}`
}

export const buildWsUrl = (path: string) => {
  const normalized = path.startsWith('/') ? path : `/${path}`
  const url = new URL(API_BASE)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${url.origin}${normalized}`
}

export async function apiFetch(path: string, opts: RequestInit = {}) {
  const headers: any = (opts.headers && typeof opts.headers === 'object') ? {...opts.headers} : {}
  // Default JSON content type when body is present.
  // IMPORTANT: Do not set Content-Type for FormData; the browser will add the multipart boundary.
  const isFormDataBody =
    typeof FormData !== 'undefined' &&
    typeof opts.body !== 'undefined' &&
    opts.body instanceof FormData
  if (opts.body && !isFormDataBody && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  const token = typeof window !== 'undefined' ? window.localStorage.getItem('access_token') : null
  if (token) headers['Authorization'] = `Bearer ${token}`
  const url = buildApiUrl(path)
  const merged: RequestInit = {...opts, headers}
  return fetch(url, merged)
}
