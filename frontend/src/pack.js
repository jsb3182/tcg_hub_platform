import { locale, t } from './i18n'

const labels = {
  '카드명 표시':['Show card names','カード名を表示'],
  '뉴런 일러스트':['Neuron artwork','ニューロンのイラスト'],'저장한 그림':['Saved artwork','保存したイラスト'],
  '한국어':['Korean','韓国語'], '영어':['English','英語'], '일본어':['Japanese','日本語'],
  '카드명 언어':['Name language','カード名の言語'],'효과 언어':['Effect language','効果の言語'],
  '인쇄본 표기':['Printed name','収録版の表記'],'수집처 표기':['Source catalog name','収集元の表記'],
  '카드 참고 이미지':['Card reference image','カードの参考画像'],
  '번역 카드명':['Translated name','翻訳されたカード名'], '효과 출처':['Effect source','効果の出典'], '카드명 출처':['Name source','カード名の出典'],
  '한국어 카드명':['Korean name','韓国語名'],'영어 카드명':['English name','英語名'],'일본어 카드명':['Japanese name','日本語名'],
  '선택한 일러스트':['Selected artwork','選択したイラスト'],
  '카드명·효과 언어 보완':['Card name and effect translations','カード名・効果の言語補完'],
  '보완할 언어':['Language to edit','編集する言語'],'표기 근거':['Text basis','表記の根拠'],
  '같은 인쇄본 원문':['Text on this printing','同じ収録版の原文'],'확인한 번역':['Reviewed translation','確認した翻訳'],
  '확인한 원문 URL':['Source URL checked','確認した出典URL'],'확인한 원문 URL을 입력하세요.':['Enter the URL of the source you checked.','確認した出典のURLを入力してください。'],
  '언어 보완 저장':['Save language entry','言語補完を保存'],'언어 보완을 저장했습니다.':['Language entry saved.','言語補完を保存しました。'],
  '언어 보완을 지웠습니다.':['Language entry removed.','言語補完を削除しました。'],
  '다른 변경이 있습니다. 서버 값과 입력한 내용을 비교하세요.':['This entry changed. Compare the saved and edited text.','変更がありました。サーバーの内容と入力中の内容を確認してください。'],
  '현재 서버 값':['Currently saved','現在の保存内容'],'등록된 보완이 없습니다.':['No language entry is saved.','登録済みの補完はありません。'],
  '저장하면 이 언어의 보완 내용을 지웁니다.':['Saving removes the entry for this language.','保存するとこの言語の補完内容が削除されます。'],
  '이 언어 보완 지우기':['Remove this language entry','この言語の補完を削除'],'입력한 값으로 다시 저장':['Save my edit over this version','入力した内容で更新'],
  '서버 값 사용':['Use saved version','保存中の内容を使用'],'입력 취소':['Discard edit','入力を取消'],
  '검수한 번역 효과':['Reviewed effect translation','確認済みの効果翻訳'],
  '다른 인쇄의 참고 효과':['Reference effect from another printing','別の収録版を参考にした効果'],
  '확인한 인쇄본 효과':['Verified printed effect','確認済みの収録版の効果'],'인쇄본 원문에는 이 게임의 공식 사이트 URL을 입력하세요.':['Use the game’s official site for printed text.','収録版の原文には、このゲームの公式サイトのURLを入力してください。'],
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
