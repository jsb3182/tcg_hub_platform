import {t,locale} from './i18n'
export const sectionLabel = key => t(({
  CHAMPION:'챔피언', MAIN:'메인', DON:'DON!!', EXTRA:'엑스트라', SIDE:'사이드', LEADER:'리더', LEGEND:'레전드', RUNE:'룬', BATTLEFIELD:'전장',
}[key] || key))
export const stateLabel = state => t(state === 'COMPLETE' ? '구성 완료' : '작성 중')
export const savedDate = value => new Intl.DateTimeFormat(locale.value, {dateStyle:'short',timeStyle:'short'}).format(new Date(value))
