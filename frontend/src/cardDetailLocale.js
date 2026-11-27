const languages = ['ko', 'en', 'ja']

function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

// Authoritative fields can come from a reviewed correction or a linked printing.
// The server reports the resolved name and rules languages independently.
function editionField(card, lang, field, reportedLanguage, editions) {
  const value = text(card?.[field])
  if (value && reportedLanguage === lang) {
    return {
      value,
      basis: text(card[field + 'Basis']),
      reference: text(card[field + 'ReferenceUrl']),
    }
  }
  const byLanguage = text(card?.specs?.[editions]?.[lang])
  return {
    value: byLanguage,
    basis: byLanguage ? text(card.specs[field + 'Basis']?.[lang]) : null,
    reference: byLanguage ? text(card.specs.sources?.[lang]) : null,
  }
}

const labels = {
  type: ['종류', 'Card type', 'カード種類'], subtype: ['유형', 'Subtype', '分類'],
  attribute: ['속성', 'Attribute', '属性'], race: ['종족', 'Monster type', '種族'],
  level: ['레벨', 'Level', 'レベル'], rank: ['랭크', 'Rank', 'ランク'],
  link: ['링크', 'Link rating', 'リンク'], markers: ['링크 마커', 'Link arrows', 'リンクマーカー'],
  atk: ['공격력', 'ATK', '攻撃力'], def: ['수비력', 'DEF', '守備力'],
  scale: ['펜듈럼 스케일', 'Pendulum scale', 'ペンデュラムスケール'],
  hp: ['HP', 'HP', 'HP'], pokedex: ['전국도감 번호', 'Pokédex number', '全国図鑑番号'],
  energyType: ['타입', 'Type', 'タイプ'], retreat: ['후퇴 비용', 'Retreat cost', 'にげるためのエネルギー'],
  cost: ['코스트', 'Cost', 'コスト'], power: ['파워', 'Power', 'パワー'], color: ['색', 'Color', '色'],
  soul: ['소울', 'Soul', 'ソウル'], hit: ['히트', 'Hit', 'ヒット'], life: ['라이프', 'Life', 'ライフ'],
  energy: ['에너지', 'Energy', 'エネルギー'], might: ['위력', 'Might', '戦闘力'],
  runePower: ['힘', 'Power', 'ルーンのパワー'],
}

function terms(rows) {
  const words = new Map()
  for (const row of rows) for (const word of row) words.set(word.toLowerCase(), row)
  return words
}

const ygoType = terms([
  ['몬스터', 'Monster', 'モンスター'], ['마법', 'Spell', '魔法'], ['함정', 'Trap', '罠'], ['토큰', 'Token', 'トークン'],
])
const ygoAttribute = terms([
  ['빛', 'Light', '光'], ['어둠', 'Dark', '闇'], ['땅', 'Earth', '地'], ['물', 'Water', '水'],
  ['바람', 'Wind', '風'], ['화염', 'Fire', '炎'], ['신', 'Divine', '神'],
])
const ygoSubtype = terms([
  ['일반', 'Normal', '通常'], ['효과', 'Effect', '効果'], ['융합', 'Fusion', '融合'],
  ['의식', 'Ritual', '儀式'], ['싱크로', 'Synchro', 'シンクロ'], ['엑시즈', 'Xyz', 'エクシーズ'],
  ['링크', 'Link', 'リンク'], ['펜듈럼', 'Pendulum', 'ペンデュラム'], ['특수 소환', 'Special Summon', '特殊召喚'],
  ['튜너', 'Tuner', 'チューナー'], ['리버스', 'Flip', 'リバース'], ['지속', 'Continuous', '永続'],
  ['속공', 'Quick-Play', '速攻'], ['장착', 'Equip', '装備'], ['필드', 'Field', 'フィールド'],
  ['카운터', 'Counter', 'カウンター'], ['스피릿', 'Spirit', 'スピリット'], ['듀얼', 'Gemini', 'デュアル'],
  ['유니온', 'Union', 'ユニオン'], ['툰', 'Toon', 'トゥーン'],
])
const ygoRace = terms([
  ['마법사족', 'Spellcaster', '魔法使い族'], ['악마족', 'Fiend', '悪魔族'], ['전사족', 'Warrior', '戦士族'],
  ['드래곤족', 'Dragon', 'ドラゴン族'], ['기계족', 'Machine', '機械族'], ['물족', 'Aqua', '水族'],
  ['언데드족', 'Zombie', 'アンデット族'], ['천사족', 'Fairy', '天使族'], ['야수족', 'Beast', '獣族'],
  ['곤충족', 'Insect', '昆虫族'], ['식물족', 'Plant', '植物族'], ['사이버스족', 'Cyberse', 'サイバース族'],
  ['비행야수족', 'Winged Beast', '鳥獣族'], ['암석족', 'Rock', '岩石族'], ['야수전사족', 'Beast-Warrior', '獣戦士族'],
  ['공룡족', 'Dinosaur', '恐竜族'], ['사이킥족', 'Psychic', 'サイキック族'], ['환상마족', 'Illusion', '幻想魔族'],
  ['파충류족', 'Reptile', '爬虫類族'], ['어류족', 'Fish', '魚族'], ['번개족', 'Thunder', '雷族'],
  ['화염족', 'Pyro', '炎族'], ['해룡족', 'Sea Serpent', '海竜族'], ['환신야수족', 'Divine-Beast', '幻神獣族'],
  ['창조신족', 'Creator God', '創造神族'], ['환룡족', 'Wyrm', '幻竜族'],
])
const colors = terms([
  ['빨강', 'Red', '赤'], ['파랑', 'Blue', '青'], ['노랑', 'Yellow', '黄'], ['초록', 'Green', '緑'],
  ['보라', 'Purple', '紫'], ['검정', 'Black', '黒'], ['흰색', 'White', '白'],
])
const pokemonTypes = terms([
  ['풀', 'Grass', '草'], ['불꽃', 'Fire', '炎'], ['물', 'Water', '水'], ['번개', 'Lightning', '雷'],
  ['초', 'Psychic', '超'], ['격투', 'Fighting', '闘'], ['악', 'Darkness', '悪'], ['강철', 'Metal', '鋼'],
  ['드래곤', 'Dragon', 'ドラゴン'], ['페어리', 'Fairy', 'フェアリー'], ['무색', 'Colorless', '無色'],
])
const onepieceTypes = terms([
  ['리더', 'Leader', 'リーダー'], ['캐릭터', 'Character', 'キャラクター'], ['이벤트', 'Event', 'イベント'],
  ['스테이지', 'Stage', 'ステージ'], ['두웅!!', 'DON!!', 'ドン!!'],
])
const weissTypes = terms([
  ['캐릭터', 'Character', 'キャラ'], ['이벤트', 'Event', 'イベント'], ['클라이맥스', 'Climax', 'クライマックス'],
])
const nivelTypes = terms([
  ['유닛', 'Unit', 'ユニット'], ['스킬', 'Skill', 'スキル'],
  ['리더', 'Leader', 'リーダー'], ['아이템', 'Item', 'アイテム'],
])
const nivelAttributes = terms([
  ['화염', 'Flame', '火炎'], ['파도', 'Wave', '波'], ['대지', 'Earth', '大地'],
  ['번개', 'Lightning', '雷'], ['폭풍', 'Storm', '嵐'],
])
const arrows = {Top:'↑', Bottom:'↓', Left:'←', Right:'→', 'Top-Left':'↖', 'Top-Right':'↗', 'Bottom-Left':'↙', 'Bottom-Right':'↘'}

function numeric(value) {
  if (typeof value === 'number') return Number.isSafeInteger(value) && value >= 0 ? String(value) : null
  return typeof value === 'string' && /^\d{1,8}$/.test(value.trim()) ? value.trim() : null
}

function factsFor(card, lang) {
  const specs = card?.specs ?? {}
  const index = languages.indexOf(lang)
  const facts = []
  function add(key, value) {
    if (value) facts.push({ key, label: labels[key][index], value })
  }
  function word(dict, value) { return dict.get(text(value)?.toLowerCase())?.[index] }
  function list(dict, values) {
    if (!Array.isArray(values) || !values.length) return null
    const translated = values.map(value => word(dict, value))
    return translated.every(Boolean) ? translated.join(' / ') : null
  }
  switch (card?.gameCode) {
    case 'YUGIOH': {
      // YGOPRODeck encodes the class and subtypes together. Legacy imports keep them separate.
      const raw = text(specs.type) || ''
      const monster = raw.endsWith(' Monster')
      const kind = text(specs.k) || (monster ? 'Monster' : raw.replace(/ Card$/, ''))
      const subtypes = text(specs.sub)?.split(/\s*\/\s*/) || (monster ? raw.slice(0, -8).split(' ') : [specs.race])
      add('type', word(ygoType, kind))
      add('subtype', list(ygoSubtype, subtypes))
      add('attribute', word(ygoAttribute, specs.at || specs.attribute))
      add('race', word(ygoRace, specs.rc || specs.race))
      if (subtypes.some(sub => ['엑시즈', 'Xyz'].includes(sub))) add('rank', numeric(specs.lv ?? specs.level))
      else if (subtypes.some(sub => ['링크', 'Link'].includes(sub))) add('link', numeric(specs.linkval ?? specs.lv))
      else add('level', numeric(specs.lv ?? specs.level))
      add('scale', numeric(specs.ps ?? specs.scale))
      const markers = Array.isArray(specs.linkmarkers) ? specs.linkmarkers.map(key => arrows[key]) : []
      if (/^[↖↑↗←→↙↓↘]{1,8}$/.test(specs.mk)) add('markers', specs.mk)
      else if (markers.length && markers.every(value => typeof value === 'string')) add('markers', markers.join(''))
      add('atk', numeric(specs.atk) ?? (specs.atk === '?' ? '?' : null))
      add('def', numeric(specs.def) ?? (specs.def === '?' ? '?' : null))
      break
    }
    case 'POKEMON':
      add('hp', numeric(specs.hp))
      add('energyType', list(pokemonTypes, specs.types))
      add('retreat', numeric(specs.retreat))
      add('pokedex', numeric(specs.pokedex_number))
      break
    case 'WEISS':
      add('type', word(weissTypes, specs.type))
      add('color', word(colors, specs.color))
      for (const key of ['level', 'cost', 'power', 'soul']) add(key, numeric(specs[key]))
      break
    case 'NIVEL':
      add('type', word(nivelTypes, specs.type))
      add('attribute', word(nivelAttributes, specs.attribute))
      add('cost', numeric(specs['코스트']))
      add('power', numeric(specs['파워']))
      add('hit', numeric(specs['히트']))
      break
    case 'ONEPIECE':
      add('type', word(onepieceTypes, specs.type === 'don' ? 'DON!!' : specs.type))
      add('color', list(colors, specs.colors))
      for (const key of ['cost', 'power', 'life']) add(key, numeric(specs[key]))
      break
    case 'RIFTBOUND':
      add('energy', numeric(specs.energy))
      add('might', numeric(specs.might))
      add('runePower', numeric(specs.power))
      break
  }
  return facts
}

export function cardDetailLocale(card, lang) {
  const valid = languages.includes(lang)
  const title = valid && editionField(card, lang, 'name', card?.nameLanguage ?? card?.language, 'names')
  const rules = valid && editionField(card, lang, 'effect', card?.effectLanguage, 'texts')
  const hasTile = Array.isArray(card?.variants) && card.variants.some(v => v?.image?.language === lang && text(v.image.url))
  const hasImage = (card?.imageLanguage === lang && text(card?.imageUrl)) || hasTile || text(card?.specs?.images?.[lang])
  return {
    name: title?.value ?? null, effect: rules?.value ?? null,
    nameLanguage: title?.value ? lang : null, effectLanguage: rules?.value ? lang : null,
    nameBasis: title?.basis ?? null, effectBasis: rules?.basis ?? null,
    nameReferenceUrl: title?.reference ?? null, effectReferenceUrl: rules?.reference ?? null,
    imageLanguage: valid && hasImage ? lang : null, facts: valid ? factsFor(card, lang) : [],
  }
}
