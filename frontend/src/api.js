import { t } from './i18n'
const baseUrl = '/api/v1'

export class ApiError extends Error {
  constructor(status) {
    const descriptions = {
      400: '입력한 조건을 확인해 주세요.',
      401: '로그인이 필요합니다.',
      403: '이 작업에 필요한 권한이 없습니다.',
      404: '요청한 정보를 찾을 수 없습니다.',
      409: '다른 작업에서 상태를 변경했습니다. 최신 상태를 다시 확인해 주세요.',
      413: '파일 크기가 업로드 한도를 초과했습니다.',
      415: '지원하지 않는 이미지 형식입니다.',
      429: '요청이 많습니다. 잠시 뒤 다시 시도해 주세요.',
    }
    super(t(descriptions[status] || '서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.'))
    this.status = status
  }
}

export async function request(path, options = {}) {
  const { signal, method = 'GET', body, token, privateRequest = false } = options
  const multipart = body instanceof FormData
  const protectedAdmin = privateRequest && path.startsWith('/admin/')
  const headers = { Accept: 'application/json' }
  if (privateRequest) headers['X-TCG-Request'] = '1'
  if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = 'Bearer ' + token
  let response
  try {
    response = await fetch(path.startsWith('/admin/server/') ? '/api'+path : baseUrl + path, {
      method, headers, signal, body: multipart ? body : body === undefined ? undefined : JSON.stringify(body),
      credentials: privateRequest ? 'same-origin' : 'omit',
      cache: privateRequest ? 'no-store' : 'default',
      redirect: protectedAdmin ? 'manual' : 'follow',
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError(0)
  }
  // An Access challenge requires a top-level page visit to complete sign-in.
  if (protectedAdmin && response.type === 'opaqueredirect') throw new ApiError(403)
  if (!response.ok) {
    const error = new ApiError(response.status)
    if (response.status === 422) {
      const body = await response.json().catch(() => null)
      if (typeof body?.detail === 'string') error.message = body.detail
    }
    throw error
  }
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

export function sourceLink(rawUrl) {
  if (typeof rawUrl !== 'string' || !rawUrl) return ''
  try {
    const url = new URL(rawUrl)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}

export function artworkUrl(value) {
  const local = mediaPath(value)
  if (local) return local
  const external = sourceLink(value)
  return external.startsWith('https://') ? external : ''
}
