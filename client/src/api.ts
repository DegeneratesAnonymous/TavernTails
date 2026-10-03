const inferApiBase = () => {
  if (process.env.REACT_APP_API_URL && process.env.REACT_APP_API_URL.trim().length > 0) {
    return process.env.REACT_APP_API_URL.trim().replace(/\/$/, '')
  }
  if (typeof window !== 'undefined') {
    // When served behind Steward's /taverntails/ reverse proxy, API calls must
    // include that prefix so nginx can route them to the TavernTails port.
    if (window.location.pathname.startsWith('/taverntails')) {
      return window.location.origin + '/taverntails'
    }
    return window.location.origin
  }
  return 'http://localhost:8002'
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
  // Preserve the path prefix (e.g. /taverntails) so WebSocket connections
  // route through nginx correctly when proxied behind Steward.
  const basePath = url.pathname.replace(/\/$/, '')
  return `${url.origin}${basePath}${normalized}`
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
