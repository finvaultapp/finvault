// Thin fetch wrapper. Cookie session + X-FinVault header (the backend's CSRF check).
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(method, path, body, { form } = {}) {
  const opts = { method, credentials: 'same-origin', headers: { 'X-FinVault': '1' } }
  if (form) opts.body = form
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, opts)
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    let msg = data?.detail ?? res.statusText
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg.replace(/^Value error, /, '')).join(' ')
    if (res.status === 401 && path !== '/auth/login' && path !== '/auth/me') window.dispatchEvent(new Event('fv:signed-out'))
    throw new ApiError(msg, res.status)
  }
  return data
}

function safeJson(text) {
  try { return JSON.parse(text) } catch { return text }
}

export function qs(params) {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x))
    else u.append(k, v)
  }
  const s = u.toString()
  return s ? `?${s}` : ''
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  upload: (p, form) => request('POST', p, undefined, { form }),
}
