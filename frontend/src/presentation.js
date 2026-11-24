const seoulTime = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const providers = { X: 'X', TWITTER: 'X', DC: '디시인사이드', DCINSIDE: '디시인사이드', COMMUNITY: '커뮤니티', OFFICIAL_NEWS: '공식 공지', CATALOG: '카드 도감' }

export function dateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : seoulTime.format(date) + ' KST'
}

export function providerName(value) {
  return value ? (providers[value.toUpperCase()] || value) : ''
}

export function bytes(value) {
  if (!Number.isFinite(value) || value < 0) return '측정값 없음'
  if (value >= 1024 ** 3) return (value / 1024 ** 3).toLocaleString('ko-KR', {maximumFractionDigits: 1}) + ' GiB'
  return (value / 1024 ** 2).toLocaleString('ko-KR', {maximumFractionDigits: 1}) + ' MiB'
}
