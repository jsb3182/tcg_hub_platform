export const playLanguages = { ko: '한국어', en: 'English', ja: '日本語' }
const languageKey = 'tcg.play.language'
const openingKey = game => 'tcg.play.opening.' + game
const supportedLanguage = code => typeof code === 'string' && Object.hasOwn(playLanguages, code)

function stored(key) {
  try { return sessionStorage.getItem(key) } catch { return null }
}
function remember(key, value) {
  try { sessionStorage.setItem(key, String(value)) } catch { /* Links still carry the language. */ }
}
export function practiceLanguage(code) {
  if (supportedLanguage(code)) return code
  const previous = stored(languageKey)
  return supportedLanguage(previous) ? previous : 'ko'
}
export function rememberPracticeLanguage(code) {
  if (supportedLanguage(code)) remember(languageKey, code)
}
export const validOpeningSize = size => Number.isInteger(size) && size >= 1 && size <= 10
export function practiceOpening(game) {
  const previous = Number(stored(openingKey(game)))
  return validOpeningSize(previous) ? previous : playGames[game].opening
}
export function rememberPracticeOpening(game, size) {
  if (validOpeningSize(size)) remember(openingKey(game), size)
}

export const playGames = {
  YUGIOH: {
    opening: 5,
    name: { ko: '유희왕', en: 'Yu-Gi-Oh!', ja: '遊戯王' },
    app: 'Master Duel',
    androidPackage: 'jp.konami.masterduel',
    urls: { ko: 'https://www.konami.com/yugioh/masterduel/asia/ko/',
      en: 'https://www.konami.com/yugioh/masterduel/asia/en/', ja: 'https://www.konami.com/yugioh/masterduel/jp/ja/' },
  },
  POKEMON: {
    opening: 7,
    name: { ko: '포켓몬', en: 'Pokémon', ja: 'ポケモン' },
    app: 'Pokémon TCG Pocket',
    androidPackage: 'jp.pokemon.pokemontcgp',
    urls: { ko: 'https://www.pokemonkorea.co.kr/pokemon_tcg_pocket/',
      en: 'https://tcgpocket.pokemon.com/en-us/', ja: 'https://www.pokemontcgpocket.com/ja/' },
  },
}

export const playText = {
  ko: { title: '플레이', game: '게임', official: '공식 사이트', about: '공식 앱에서 대전 언어를 설정할 수 있습니다.',
    practice: '내 덱 연습', choose: '저장한 덱 고르기', search: '카드 이름 또는 번호', find: '검색',
    add: '추가', remove: '한 장 빼기', pile: '남은 덱', hand: '손패', table: '테이블', discard: '버린 카드',
    selection: '연습할 카드', opening: '시작 손패 수', start: '섞고 시작', draw: '한 장 뽑기',
    place: '테이블에 놓기', drop: '버리기', back: '손으로 가져오기', end: '연습 끝내기', reset: '다시 섞기',
    empty: '카드가 없습니다.', noHits: '검색 결과가 없습니다.', loading: '불러오는 중…',
    fail: '카드를 불러올 수 없습니다.', retry: '다시 시도', login: '내 덱으로 연습하려면 로그인',
    deckError: '저장한 덱을 열 수 없습니다.', main: '메인 덱', fallback: '원문', limit: '연습 한도는 150장입니다.' },
  en: { title: 'Play', game: 'Game', official: 'Official site', about: 'Choose the battle language in the official app.',
    practice: 'Deck practice', choose: 'Choose a saved deck', search: 'Card name or number', find: 'Search',
    add: 'Add', remove: 'Remove one', pile: 'Draw pile', hand: 'Hand', table: 'Table', discard: 'Discard pile',
    selection: 'Practice cards', opening: 'Opening hand size', start: 'Shuffle and start', draw: 'Draw one',
    place: 'Place on table', drop: 'Discard', back: 'Return to hand', end: 'End practice', reset: 'Shuffle again',
    empty: 'No cards.', noHits: 'No cards found.', loading: 'Loading…', fail: 'Could not load cards.',
    retry: 'Try again', login: 'Sign in to practice with your deck', deckError: 'Could not open this deck.',
    main: 'Main deck', fallback: 'Original', limit: 'A practice deck can hold up to 150 cards.' },
  ja: { title: 'プレイ', game: 'ゲーム', official: '公式サイト', about: '対戦の言語は公式アプリで設定できます。',
    practice: 'デッキの練習', choose: '保存したデッキを選ぶ', search: 'カード名または番号', find: '検索',
    add: '追加', remove: '1枚減らす', pile: '山札', hand: '手札', table: 'テーブル', discard: '捨て札',
    selection: '練習用カード', opening: '最初の手札の枚数', start: 'シャッフルして開始', draw: '1枚引く',
    place: '場に出す', drop: '捨てる', back: '手札に戻す', end: '練習を終了', reset: '引き直す',
    empty: 'カードはありません。', noHits: 'カードが見つかりません。', loading: '読み込み中…',
    fail: 'カードを読み込めません。', retry: '再試行', login: 'マイデッキで練習するにはログイン',
    deckError: 'このデッキを開けません。', main: 'メインデッキ', fallback: '原文', limit: '練習デッキの上限は150枚です。' },
}

export function newRound(cards, opening) {
  const pile = cards.flatMap(({id, quantity}) => Array(quantity).fill(id))
  for (let i = pile.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const card = pile[i]
    pile[i] = pile[j]
    pile[j] = card
  }
  return { pile, hand: pile.splice(0, opening), table: [], discard: [] }
}
