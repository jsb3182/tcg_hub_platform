export const sectionLabel = key => ({
  MAIN:'메인', EXTRA:'엑스트라', SIDE:'사이드', LEADER:'리더', LEGEND:'레전드', RUNE:'룬', BATTLEFIELD:'전장',
}[key] || key)
export const stateLabel = state => state === 'COMPLETE' ? '구성 완료' : '작성 중'
export const savedDate = value => new Intl.DateTimeFormat('ko-KR', {dateStyle:'short',timeStyle:'short'}).format(new Date(value))
