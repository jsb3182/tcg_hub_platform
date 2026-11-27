import { ref } from 'vue'
import { labels } from './labels'

export const languages = { ko: '한국어', en: 'English', ja: '日本語' }
export const supportedLanguage = value => typeof value === 'string' && Object.prototype.hasOwnProperty.call(languages, value)
const key = 'tcg.interface.language'

function initial() {
  try {
    for (const saved of [localStorage.getItem(key), localStorage.getItem('tcg.news.language'), sessionStorage.getItem('tcg.play.language')]) {
      if (supportedLanguage(saved)) return saved
    }
  } catch { /* The interface also works with storage disabled. */ }
  return 'ko'
}
export const locale = ref(initial())
export function selectLocale(value) {
  if (!supportedLanguage(value)) return
  locale.value = value
  document.documentElement.lang = value
  try { localStorage.setItem(key, value) } catch { /* URL links retain an explicit locale. */ }
}
export function t(source) {
  if (locale.value === 'ko') return source
  return labels[source]?.[locale.value === 'en' ? 0 : 1] ?? source
}
const games = {
  YUGIOH:['유희왕','Yu-Gi-Oh!','遊戯王'], POKEMON:['포켓몬 TCG','Pokémon TCG','ポケモンカードゲーム'],
  ONEPIECE:['원피스 카드 게임','ONE PIECE Card Game','ONE PIECEカードゲーム'], WEISS:['바이스 슈발츠','Weiß Schwarz','ヴァイスシュヴァルツ'],
  NIVEL:['니벨아레나','Nivel Arena','ニベルアレナ'], RIFTBOUND:['리프트바운드','Riftbound','リフトバウンド'],
}
export const gameCodes=Object.keys(games)
export function gameName(code,fallback=code) {
  return games[code]?.[locale.value==='en'?1:locale.value==='ja'?2:0] ?? fallback
}
const editionLabels = {ko:'한국어판',en:'영어판',ja:'일본어판'}
export function editionName(language) {
  return t(supportedLanguage(language) ? editionLabels[language] : '언어 미확인')
}
export function localizedCard(card) {
  const names=card?.specs?.names
  return card?.name || names?.[locale.value] || card?.originalName || t('이름 미정')
}
