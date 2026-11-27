import { locale, t } from './i18n'
import {rarityBadges} from './cardRarity'
import {traitValueLabel} from './cardDetailLocale'

export function shortRarity(card){return rarityBadges(card,locale.value).map(r=>r.code || r.label).join(' · ')}

const labels = {
  '커뮤니티 신고':['Community reports','コミュニティの通報'],'처리 상태':['Review status','対応状況'],'검토 대기':['Awaiting review','審査待ち'],
  '숨김 처리':['Hidden','非公開にした通報'],'공개 유지':['Keep visible','公開を維持'],'신고 대상 숨기기':['Hide reported content','通報対象を非公開にする'],
  '게시글 신고':['Reported post','投稿への通報'],'댓글 신고':['Reported comment','コメントへの通報'],'신고 사유':['Report reason','通報理由'],
  '이 댓글과 답글을 숨길까요?':['Hide this comment and its replies?','このコメントと返信を非公開にしますか？'],
  '이 게시글을 숨길까요?':['Hide this post?','この投稿を非公開にしますか？'],
  '공개 상태를 유지하고 신고를 종료할까요?':['Close this report and keep the content visible?','公開を維持して通報を終了しますか？'],
  '처리 확정':['Confirm decision','対応を確定'],'신고 대상을 숨겼습니다.':['Reported content is now hidden.','通報対象を非公開にしました。'],
  '공개 상태를 유지했습니다.':['Content remains visible.','公開を維持しました。'],'해당 상태의 신고가 없습니다.':['No reports with this status.','この状態の通報はありません。'],'신고 페이지':['Report pages','通報のページ'],
  '확인한 카드':['Reviewed cards','確認済みのカード'],
  '빠른 이동':['Quick navigation','クイック移動'],'바인더·잡카통':['Binder','バインダー'],'필요·발매':['Needs / dates','不足・発売'],
  '금제·소식':['Limits / news','制限・ニュース'],'수록·지도':['Sets / map','収録・地図'],'금제 확인':['Check card restrictions','禁止・制限を確認'],
  '내 덱의 대회 제한 확인':['Check tournament limits for a deck','デッキの大会制限を確認'],
  '새 덱 추가':['Add a deck','新しいデッキを追加'],'한국어 이름 (필수)':['Korean name (required)','韓国語名（必須）'],
  '덱 레시피 캡처':['Deck recipe screenshot','デッキレシピの画像'],'캡처 형식':['Screenshot layout','画像のレイアウト'],
  '격자 지정':['Set a grid','マス目を指定'],'카드 영역':['Card area','カードの範囲'],'가로 칸':['Columns','列数'],'세로 칸':['Rows','行数'],
  '왼쪽 (%)':['Left (%)','左 (%)'],'오른쪽 (%)':['Right (%)','右 (%)'],'위 (%)':['Top (%)','上 (%)'],'아래 (%)':['Bottom (%)','下 (%)'],
  '120칸 이내로 카드 영역을 확인하세요.':['Check the frame and keep the grid to 120 slots.','範囲とマス目（120枠以内）を確認してください。'],
  '서버의 카드와 대조':['Match against local cards','サーバー内のカードと照合'],'이미지를 읽지 못했습니다.':['Could not read the image.','画像を読み込めませんでした。'],
  '덱은 저장됐습니다. 이미지를 다시 저장하세요.':['Deck saved. Retry saving the cover.','デッキを保存しました。カバーの保存を再試行してください。'],
  '만들기':['Create','作成'],'보유 배지 숨기기':['Hide collection badges','所持バッジを隠す'],'레어도 미기재':['Rarity unlisted','レアリティ未登録'],
  'PNG 저장을 요청했습니다.':['PNG download requested.','PNGの保存をリクエストしました。'],'대회 제한':['Tournament limit','大会制限'],
  '수록 팩 찾기':['Browse card sets','収録商品を探す'],'수록 수 미확인':['Size unconfirmed','収録数未確認'],'공개 카드':['Cataloged cards','公開カード'],
  '상품 전체 수록 수':['Announced set size','公表された収録数'],'수록 구성':['Set contents','収録内訳'],'수록 카드 정렬':['Sort set contents','収録カードの並び順'],
  '수록 순':['Set order','収録順'],'번호 순':['Card number','番号順'],'레어도 순':['Rarity','レアリティ順'],'이름 순':['Card name','名前順'],
  '최근 관측 시세':['Latest observed prices','最新の記録価格'],'번역의 원문':['Original text used for the translation','翻訳の原文'],
  '발매 연도':['Release year','発売年'],'모든 연도':['All years','すべての年'],'카드 특성':['Card attribute','カードの特性'],
  '특성 값':['Attribute value','特性の値'],'특성 선택':['Choose an attribute','特性を選択'],'필터를 불러오지 못했습니다.':['Could not load filter options.','絞り込み項目を読み込めませんでした。'],
  '수록 상품 첫 발매일':['First release of this set','収録商品の初回発売日'],'카드 상세 보기':['View card details','カード詳細を見る'],
  '상세':['Details','詳細'],'공식 카드 대조':['Official card record','公式カード情報'],
  '자동 번역':['Machine translation','自動翻訳'],'검수한 번역':['Reviewed translation','確認済みの翻訳'],
  '한국판 카드 정보':['Korean printing details','韓国版カード情報'],
  '선택한 한국판 특성':['Selected Korean printing trait','選択した韓国版の特徴'],
  '용어 사전 번역':['Glossary translation','用語辞書による翻訳'],'로컬 이미지 없음':['No locally stored image','ローカル画像なし'],
  '월간 달력':['Month calendar','月間カレンダー'],'타임라인':['Timeline','タイムライン'],
  '이전 달':['Previous month','前の月'],'다음 달':['Next month','次の月'],'이 달의 전체 일정':['All releases this month','今月の予定をすべて表示'],
  '종목·지역·상품 필터':['Games, regions and products','ゲーム・地域・商品で絞り込む'],'상품 유형':['Product type','商品種別'],
  '부스터 팩':['Booster pack','ブースターパック'],'스타터 덱':['Starter deck','スタートデッキ'],'프로모션':['Promotion','プロモーション'],
  '액세서리':['Accessory','アクセサリー'],'특별 상품':['Special product','特別商品'],'유형 미확인':['Type unconfirmed','種別未確認'],
  '필터 초기화':['Clear filters','絞り込みを解除'],'발매 일정 관리':['Manage releases','発売予定の管理'],
  '발매 일정 추가':['Add release','発売予定を追加'],'발매 일정 수정':['Edit release','発売予定を編集'],
  '상품명':['Product name','商品名'],'상품 코드':['Product code','商品コード'],'언어별 상품명':['Product names by language','言語別商品名'],
  '발매 정보 원문 URL을 확인하세요.':['Check the release source URL.','発売情報の出典URLを確認してください。'],'발매 일정을 저장했습니다.':['Release saved.','発売予定を保存しました。'],
  '다른 변경이 있습니다. 목록을 새로고침한 뒤 다시 선택하세요.':['This release changed. Refresh the list and select it again.','変更があります。一覧を更新して再選択してください。'],
  '저장하지 않은 변경을 취소할까요?':['Discard unsaved changes?','未保存の変更を破棄しますか？'],
  '연결할 팩 검색':['Find a set to link','関連付けるパックを検索'],'연결할 팩':['Linked set','関連パック'],'연결 없음':['No linked set','関連付けなし'],
  '공급자 연결 상태':['Provider configuration','提供元の接続設定'],'로컬 이미지 캐시':['Local image cache','ローカル画像キャッシュ'],
  '키 설정됨':['Key configured','キー設定済み'],'키 미설정':['Key missing','キー未設定'],'키 불필요':['No key required','キー不要'],
  '자동 번역의 원문':['Original used for machine translation','自動翻訳の原文'],
  '원문·출처':['Original text and sources','原文・出典'],
  '이 언어의 카드명 미등록':['No name in this language','この言語のカード名は未登録です'],
  '이 언어의 효과 텍스트 미등록':['No effect text in this language','この言語の効果テキストは未登録です'],
  '이 언어의 이미지 미등록':['No image in this language','この言語の画像は未登録です'],
  '카드명을 복사했습니다.':['Card name copied.','カード名をコピーしました。'],
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
  '나무위키 참고 문서':['NamuWiki references','ナムウィキの参考記事'],'나무위키 기여자':['NamuWiki contributors','ナムウィキの寄稿者'],
  '문서 판':['Revision','版'],'스냅샷':['Snapshot','スナップショット'],'나무위키 문서 열기':['Open NamuWiki article','ナムウィキの記事を開く'],
  '나무위키 참고 표기':['Name from NamuWiki','ナムウィキを参考にした表記'],'배포본':['Dataset snapshot','配布データ'],
  '나무위키 문서 기반 효과 요약':['Effect summary based on a NamuWiki article','ナムウィキの記事に基づく効果の要約'],
  '특징':['Traits','特徴'],'문서의 규칙 설명':['Rulings in this article','記事に記載された裁定'],'문서의 수록 정보':['Sets listed in this article','記事に記載された収録情報'],
  '발매 일정':['Release schedule','発売スケジュール'], '수록 카드':['Cards in this set','収録カード'],
  '모든 종목':['All games','すべてのゲーム'],'모든 지역':['All regions','すべての地域'],
  '발매 지역':['Release region','発売地域'],'지역 미확인':['Region unconfirmed','地域未確認'],
  '한국':['Korea','韓国'],'일본':['Japan','日本'],'북미':['North America','北米'],
  '영어판':['English edition','英語版'],'전 세계':['Worldwide','全世界'],'유럽':['Europe','欧州'],'중국':['China','中国'],
  'TCG판 (국가 미지정)':['TCG edition (country unspecified)','TCG版（国指定なし）'],
  '발매 정보 출처':['Release source','発売情報の出典'],'팩 도감':['Set catalog','パック図鑑'],
  '팩 상세':['Set details','商品詳細'],
  '발매 예정':['Upcoming','発売予定'],'지난 발매':['Past releases','発売済み'],'날짜 전체':['All dates','全期間'],
  '기준일':['As of','基準日'],'일정 보기':['Schedule view','スケジュール表示'],'일정':['Releases','発売情報'],
  '조건에 맞는 발매 일정이 없습니다.':['No release dates match these filters.','条件に合う発売情報はありません。'],
  '등록된 발매 예정 일정이 없습니다.':['No upcoming releases are listed.','発売予定はまだ登録されていません。'],
  '지역별 발매 일정':['Regional releases','地域別発売日'],
  '지역별 일정을 불러오지 못했습니다.':['Could not load regional releases.','地域別発売日を読み込めませんでした。'],
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
  '북미 일반 발매':['North America release','北米一般発売'],
  '북미 공인점 선행 발매':['North America OTS release','北米公認店先行発売'],
  '공식 상품 구성':['Publisher set size','公式商品収録枚数'],
  '공식 상품 안내':['Official product page','公式商品ページ'],
  '상품 출처':['Product sources','商品情報の出典'],
  '도감 등록 전':['No catalog entries yet','図鑑未登録'],
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
export const releaseRegions={KR:'한국',JP:'일본',NA:'북미',EN:'영어판',EU:'유럽',GLOBAL:'전 세계',CN:'중국',TCG:'TCG판 (국가 미지정)'}
export function regionName(code){return pt(releaseRegions[code] || '지역 미확인')}
export function releaseName(event){
  return event.names?.[locale.value] || event.name || event.code || event.productKey
}
export function packTitle(pack) {
  return locale.value !== 'ko' && pack.officialProduct ? pack.officialProduct.englishName : pt(pack.name)
}
export function facetValues(card, key) {
  if (key === 'rarity') return card.rarities?.length ? card.rarities : [card.rarity || unknown]
  return [card[key] || unknown]
}
export function facetLabel(key, value, game) {
  if (value===unknown) return pt({inclusion:'미분류',type:'종류 미확인',rarity:'레어도 미확인'}[key])
  if(game && key==='rarity')return shortRarity({gameCode:game,rarity:value})||value
  if(game && key==='type'){
    const kind=game==='YUGIOH' && / Monster$/.test(value)?'Monster':game==='YUGIOH'?String(value).replace(/ Card$/,''):value
    return traitValueLabel(game,'type',kind,locale.value)||pt('종류 미확인')
  }
  return pt(key==='inclusion' ? inclusions[value] || value : value)
}
export function countLabel(count) { return count.toLocaleString(locale.value)+t('장') }
