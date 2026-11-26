import { locale, t } from './i18n'

const dates = Object.fromEntries(['ko','en','ja'].map(code=>[code,new Intl.DateTimeFormat(code, {
  timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',
})]))
const providers = { X:'X', TWITTER:'X', DC:'디시인사이드', DCINSIDE:'디시인사이드', COMMUNITY:'커뮤니티', OFFICIAL_NEWS:'공식 공지', CATALOG:'카드 도감' }
export function dateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : dates[locale.value].format(date) + ' KST'
}
export function providerName(value) {
  return value ? t(providers[value.toUpperCase()] || value) : ''
}
export function bytes(value) {
  if (!Number.isFinite(value) || value < 0) return t('측정값 없음')
  const gib=value>=1024**3
  return (value/(gib?1024**3:1024**2)).toLocaleString(locale.value,{maximumFractionDigits:1})+(gib?' GiB':' MiB')
}
