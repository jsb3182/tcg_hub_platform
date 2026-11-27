import {riftEffectText} from './riftSymbols.js'
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
  stage:['진화 단계','Evolution stage','進化段階'],regulation:['레귤레이션 마크','Regulation mark','レギュレーションマーク'],
  domain:['영역','Domain','ドメイン'],printingNumber:['인쇄 번호','Printing number','収録番号'],
  traits:['특징','Traits','特徴'],counter:['카운터','Counter','カウンター'],
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

const pokemonClasses=terms([
  ['포켓몬','Pokémon','ポケモン'],['트레이너스','Trainer','トレーナーズ'],['에너지','Energy','エネルギー'],
  ['아이템','Item','グッズ'],['서포트','Supporter','サポート'],['서포터','Supporter','サポート'],['스타디움','Stadium','スタジアム'],
  ['기본 에너지','Basic Energy','基本エネルギー'],['특수 에너지','Special Energy','特殊エネルギー'],['포켓몬의 도구','Pokémon Tool','ポケモンのどうぐ'],
  ['복원','Restored','復元'],['레벨업','Level Up','レベルアップ'],['기본','Basic','たね'],['1진화','Stage 1','1進化'],['2진화','Stage 2','2進化'],
  ['M진화','Mega Evolution','M進化'],['V진화','V Evolution','V進化'],['BREAK진화','BREAK Evolution','BREAK進化'],
])
const riftTypes=terms([
  ['유닛','Unit','ユニット'],['전설','Legend','レジェンド'],['룬','Rune','ルーン'],['도구','Gear','装備'],
  ['주문','Spell','スペル'],['전장','Battlefield','バトルフィールド'],['토큰','Token','トークン'],
])
const riftDomains=terms([
  ['분노','Fury','Fury'],['평정','Calm','Calm'],['정신','Mind','Mind'],['신체','Body','Body'],['혼돈','Chaos','Chaos'],['질서','Order','Order'],
])
const traitTerms={
  YUGIOH:{type:ygoType,attribute:ygoAttribute,race:ygoRace},POKEMON:{type:pokemonClasses,stage:pokemonClasses,energyType:pokemonTypes},
  ONEPIECE:{type:onepieceTypes,color:colors},WEISS:{type:weissTypes,color:colors},
  NIVEL:{type:nivelTypes,attribute:nivelAttributes},RIFTBOUND:{type:riftTypes,domain:riftDomains},
}
export function traitLabel(game,key,lang){
  const field=game==='RIFTBOUND' && key==='power' ? 'runePower' : key
  return Object.prototype.hasOwnProperty.call(labels,field) ? labels[field][languages.indexOf(lang)] : null
}
export function traitValueLabel(game,key,raw,lang) {
  if(!traitLabel(game,key,lang) || (typeof raw!=='string' && typeof raw!=='number'))return null
  const value=String(raw).trim(),i=languages.indexOf(lang)
  if(!value)return null
  if(game==='ONEPIECE' && ['attribute','traits'].includes(key))
    return lang==='ko' && value.length<=160 && /[가-힣A-Za-z0-9]/u.test(value) && !/[<>\[\]\u0000-\u001f]/u.test(value) ? value : null
  if(key==='printingNumber')return /^[A-Za-z0-9][A-Za-z0-9 .★☆/#-]*$/.test(value)?value:null
  if(key==='regulation'){
    if(value.toLowerCase()==='none')return ['표기 없음','Unmarked','表記なし'][i]
    return /^[a-z]{1,3}$/i.test(value)?value.toUpperCase():null
  }
  const dict=traitTerms[game]?.[key]
  if(dict){
    const translated=dict.get((game==='ONEPIECE'&&value.toLowerCase()==='don'?'don!!':value.toLowerCase()))?.[i]
    if(translated)return translated
    if(lang==='ko' && /[가-힣]/.test(value) && !/[<>\[\]]/.test(value))return value
    if(lang==='en' && /^[a-zA-Z][a-zA-Z '!-]*$/.test(value))return value
    if(lang==='ja' && /[ぁ-ヿ]/.test(value) && !/[<>\[\]]/.test(value))return value
    return null
  }
  return numeric(value) ?? (value==='?'?'?':null)
}

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
      for(const [key,raw] of [['type',specs.card_type],['stage',specs.stage],['regulation',specs.regulation]])
        add(key,traitValueLabel('POKEMON',key,raw,lang))
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
    case 'ONEPIECE': {
      add('type', word(onepieceTypes, specs.type === 'don' ? 'DON!!' : specs.type))
      add('color', list(colors, specs.colors))
      const regional = lang==='ko' ? specs.regionalFacts?.ko : null
      const sameProduct = regional?.productCode && regional.productCode===specs.productCode
      if(regional) {
        add('attribute',traitValueLabel('ONEPIECE','attribute',regional.attribute,lang))
        if(Array.isArray(regional.traits)) {
          const traits=regional.traits.map(value=>traitValueLabel('ONEPIECE','traits',value,lang)).filter(Boolean)
          add('traits',traits.join(' · '))
        }
      }
      for (const key of ['cost', 'power', 'life','counter']) add(key, (sameProduct ? numeric(regional[key]) : null) ?? numeric(specs[key]))
      break
    }
    case 'RIFTBOUND':
      add('type',traitValueLabel('RIFTBOUND','type',specs.type,lang))
      add('domain',list(riftDomains,specs.domains))
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
  const effect=card?.gameCode==='RIFTBOUND'?riftEffectText(rules?.value,lang):rules?.value
  const hasTile = Array.isArray(card?.variants) && card.variants.some(v => v?.image?.language === lang && text(v.image.url))
  const hasImage = (card?.imageLanguage === lang && text(card?.imageUrl)) || hasTile || text(card?.specs?.images?.[lang])
  return {
    name: title?.value ?? null, effect: effect ?? null, symbolOriginal: effect!==rules?.value ? rules.value : null,
    nameLanguage: title?.value ? lang : null, effectLanguage: rules?.value ? lang : null,
    nameBasis: title?.basis ?? null, effectBasis: rules?.basis ?? null,
    nameReferenceUrl: title?.reference ?? null, effectReferenceUrl: rules?.reference ?? null,
    imageLanguage: valid && hasImage ? lang : null, facts: valid ? factsFor(card, lang) : [],
  }
}
