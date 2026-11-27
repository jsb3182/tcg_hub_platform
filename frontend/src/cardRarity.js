// The same abbreviation can mean different things across games (e.g. SR).
// The original Korean pack catalog uses several short codes for one printing.
const ygo = {
  N:['노말','Common','ノーマル'], R:['레어','Rare','レア'], SR:['슈퍼 레어','Super Rare','スーパーレア'],
  UR:['울트라 레어','Ultra Rare','ウルトラレア'], UL:['얼티미트 레어','Ultimate Rare','アルティメットレア'],
  CR:['컬렉터즈 레어',"Collector's Rare",'コレクターズレア'], SE:['시크릿 레어','Secret Rare','シークレットレア'],
  EXSE:['엑스트라 시크릿 레어','Extra Secret Rare','エクストラシークレットレア'],
  '20thSE':['20th 시크릿 레어','20th Secret Rare','20thシークレットレア'],
  '10000SE':['10000 시크릿 레어','10000 Secret Rare','10000シークレットレア'],
  PSE:['프리즈마틱 시크릿 레어','Prismatic Secret Rare','プリズマティックシークレットレア'],
  QCSE:['쿼터 센추리 시크릿 레어','Quarter Century Secret Rare','クォーターセンチュリーシークレットレア'],
  HR:['홀로그래픽 레어','Holographic Rare','ホログラフィックレア'], GR:['골드 레어','Gold Rare','ゴールドレア'],
  GSE:['골드 시크릿 레어','Gold Secret Rare','ゴールドシークレットレア'], GMR:['그랜드마스터','Grandmaster','グランドマスター'],
  P:['패러렐(노말)','Parallel Common','ノーマルパラレル'], 'P+SR':['패러렐(슈퍼 레어)','Parallel Super Rare','スーパーパラレル'],
  'P+UR':['패러렐(울트라 레어)','Parallel Ultra Rare','ウルトラパラレル'], 'P+SE':['패러렐(시크릿 레어)','Parallel Secret Rare','シークレットパラレル'],
  M:['밀레니엄','Millennium Rare','ミレニアムレア'], 'M+GR':['밀레니엄 골드 레어','Millennium Gold Rare','ミレニアムゴールドレア'],
  STAR:['스타라이트 레어','Starlight Rare','スターライトレア'],
}
const finishes = {
  red:['레드 ', 'Red ', 'レッド'], MangaMono:['흑백 ', 'Monochrome ', 'モノクロ'],
  MangaColor:['컬러 ', 'Color ', 'カラー'], of:['오버프레임 ', 'Overframe ', 'オーバーフレーム'],
}
for (const code of ['redSE','MangaMonoUR','MangaMonoSE','MangaColorUR','MangaColorSE','ofUR','ofSE','ofPSE','ofSTAR']) {
  const prefix=Object.keys(finishes).find(p=>code.startsWith(p))
  ygo[code]=ygo[code.slice(prefix.length)].map((label,i)=>finishes[prefix][i]+label)
}
const shared = [
  ['커먼','Common','コモン'], ['언커먼','Uncommon','アンコモン'], ['레어','Rare','レア'],
  ['슈퍼 레어','Super Rare','スーパーレア'], ['시크릿 레어','Secret Rare','シークレットレア'],
  ['울트라 레어','Ultra Rare','ウルトラレア'], ['더블 레어','Double Rare','ダブルレア'],
  ['트리플 레어','Triple Rare','トリプルレア'], ['프로모','Promo','プロモ'],
  ['일러스트 레어','Illustration Rare','イラストレア'], ['하이퍼 레어','Hyper Rare','ハイパーレア'],
]
const terms = new Map(shared.flatMap(names=>names.map(name=>[name.toLowerCase(),names])))
const ygoTerms = new Map(Object.entries(ygo).flatMap(([code,names])=>[code,...names].map(name=>[name.toLowerCase(),code])))

export function rarityBadges(card, lang) {
  const i=['ko','en','ja'].indexOf(lang)
  if (!card || i<0) return []
  const values=[card.rarity,...(card.variants||[]).map(v=>v.rarity)].filter(v=>typeof v==='string' && v.trim())
  const badges=new Map()
  for (const value of values) {
    const raw=value.trim(),parts=raw.split(/\s+/)
    const isYgo=card.gameCode==='YUGIOH'
    const entries=isYgo && parts.every(k=>Object.prototype.hasOwnProperty.call(ygo,k)) ? parts : [raw]
    for (const entry of entries) {
      const key=entry.toLowerCase()
      const code=isYgo && ygoTerms.get(key)
      if (code) badges.set(code,{code,label:ygo[code][i]})
      else if (terms.has(key)) {
        const label=terms.get(key)[i]
        badges.set(label,{code:'',label})
      } else if (/^[A-Z0-9★☆+/-]{1,12}$/.test(entry)) badges.set(entry,{code:entry,label:''})
      else if (entry!=='?' && card.specs?.language===lang) badges.set(entry,{code:'',label:entry})
    }
  }
  return [...badges.values()]
}
