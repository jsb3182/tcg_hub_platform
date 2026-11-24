const baseUrl = '/api/v1'

export class ApiError extends Error {
  constructor(status) {
    const descriptions = {
      400: '입력한 조건을 확인해 주세요.',
      401: '로그인이 필요합니다.',
      403: '이 작업에 필요한 권한이 없습니다.',
      404: '요청한 정보를 찾을 수 없습니다.',
      429: '요청이 많습니다. 잠시 뒤 다시 시도해 주세요.',
    }
    super(descriptions[status] || '서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.')
    this.status = status
  }
}

export async function request(path, options = {}) {
  const { signal, method = 'GET', body, token, privateRequest = false } = options
  const headers = { Accept: 'application/json' }
  if (privateRequest) headers['X-TCG-Request'] = '1'
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = 'Bearer ' + token
  let response
  try {
    response = await fetch(baseUrl + path, {
      method, headers, signal, body: body === undefined ? undefined : JSON.stringify(body),
      credentials: privateRequest ? 'same-origin' : 'omit',
      cache: privateRequest ? 'no-store' : 'default',
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(0)
  }
  if (!response.ok) throw new ApiError(response.status)
  if (response.status === 204) return null
  const text = await response.text()
  if (!text) return null
  try { return JSON.parse(text) } catch { throw new ApiError(502) }
}

export function mediaPath(rawPath) {
  if (typeof rawPath !== 'string' || !rawPath) return ''
  try {
    const url = new URL(rawPath, location.origin)
    return url.origin === location.origin && url.pathname.startsWith('/media/') ? url.href : ''
  } catch { return '' }
}
