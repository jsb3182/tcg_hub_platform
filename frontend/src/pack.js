import { locale, t } from './i18n'

const labels = {
  '다른 인쇄의 참고 카드명':['Reference name from another printing','別の収録版を参考にしたカード名'],
  '참고 인쇄본':['Reference printing','参照した収録版'], '기존 도감 표기':['Name from the original catalog','既存図鑑での表記'],
  '기존 도감 원문':['Original-language name from the catalog','既存図鑑の原文名'],
  '나무위키에서 검색':['Search NamuWiki','ナムウィキで検索'],
  '발매 일정':['Release schedule','発売スケジュール'], '수록 카드':['Cards in this set','収録カード'],
  '신규':['New','新規'], '재록':['Reprints','再録'], '신규 일러스트':['New artwork','新規イラスト'],
  '미분류':['Unclassified','未分類'], '종류 미확인':['Type unknown','種類不明'], '레어도 미확인':['Rarity unknown','レアリティ不明'],
  '카드 배열':['Card gallery','カード一覧'], '수록 구분':['Printing','収録区分'], '카드 종류':['Card type','カードの種類'],
  '팩에서 검색':['Search this set','この商品内を検索'], '카드명·번호·효과':['Name, number or effect','カード名・番号・効果'],
  '배열 필터':['Gallery filters','一覧の絞り込み'], '필터 지우기':['Clear filters','絞り込みを解除'],
  '배열 PNG 저장':['Save gallery PNG','一覧をPNGで保存'], '이 페이지 PNG 저장':['Save this page as PNG','このページをPNGで保存'],
  '카드 정보 PNG':['Save card details as PNG','カード情報をPNGで保存'], '이미지 가로 폭':['Image width','画像の幅'],
  '이미지 없음':['No image','画像なし'], '검색 결과가 없습니다.':['No matching cards.','一致するカードがありません。'],
  '이미지 저장 불가':['Image unavailable for export','画像を保存できません'],
  '수록 카드가 아직 없습니다.':['No cards have been listed yet.','収録カードはまだ登録されていません。'],
  '일본 발매':['Japan release','日本発売'], '한국 발매':['Korea release','韓国発売'],
  '수록 상품':['Product','収録商品'], '종류':['Type','種類'], '몬스터':['Monster','モンスター'], '마법':['Spell','魔法'], '함정':['Trap','罠'],
  '남은 카드 불러오기':['Load remaining cards','残りのカードを読み込む'], '카드 불러오는 중…':['Loading cards…','カードを読み込み中…'],
  '페이지':['Page','ページ'], '카드 목록':['Card list','カードリスト'], '이미지 저장':['Save image','画像を保存'],
  '이미지 만들기':['Create image','画像を作成'], 'PNG 파일 다운로드':['Download PNG','PNGをダウンロード'],
  '이미지 미리보기':['Preview image','画像をプレビュー'],
  '이미지를 저장할 수 있습니다.':['Your image is ready to save.','画像を保存できます。'],
  '길게 누르거나 다운로드하세요.':['Press and hold the image or download it.','画像を長押しするか、ダウンロードしてください。'],
}
export function pt(key) {
  return locale.value==='ko' ? key : labels[key]?.[locale.value==='en'?0:1] ?? t(key)
}
export const inclusions = {NEW:'신규',REPRINT:'재록',NEW_ART:'신규 일러스트'}
export const unknown = '__unknown__'
export function facetValues(card, key) {
  if (key === 'rarity') return card.rarities?.length ? card.rarities : [card.rarity || unknown]
  return [card[key] || unknown]
}
export function facetLabel(key, value) {
  if (value===unknown) return pt({inclusion:'미분류',type:'종류 미확인',rarity:'레어도 미확인'}[key])
  return pt(key==='inclusion' ? inclusions[value] || value : value)
}
export function countLabel(count) { return count.toLocaleString(locale.value)+t('장') }
