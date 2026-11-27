const extraKinds=[['융합',/fusion|융합|融合/i],['싱크로',/synchro|싱크로|シンクロ/i],
  ['엑시즈',/\bxyz\b|엑시즈|エクシーズ/i],['링크',/\blink\b|링크|リンク/i]]

export function groupRecipe(deck){
  return deck.rule.sections.map(({section})=>{
    const entries=deck.entries.filter(entry=>entry.section===section && copies(entry)>0)
    const counts=new Map()
    for(const entry of entries){
      for(const type of kinds(deck.gameCode,entry.type))counts.set(type,(counts.get(type)||0)+copies(entry))
    }
    return {section, entries, total:entries.reduce((n,e)=>n+copies(e),0), counts:[...counts]}
  })
}
export function copies(entry){return Math.max(0,Math.trunc(Number(entry.quantity))||0)}
function kinds(game,raw){
  if(!raw)return ['종류 미확인']
  if(game!=='YUGIOH')return [raw]
  const sub=extraKinds.find(([,match])=>match.test(raw))?.[0]
  if(sub)return ['몬스터',sub]
  if(/monster|몬스터|モンスター/i.test(raw))return ['몬스터']
  if(/\bspell\b|^마법(?:\s*카드|$)|^魔法/i.test(raw))return ['마법']
  if(/\btrap\b|^함정(?:\s*카드|$)|^罠/i.test(raw))return ['함정']
  return [raw]
}
export function slots(entries,limit,grouped=false){
  const result=[]
  for(const entry of entries){
    const n=Math.min(grouped ? 1 : copies(entry),limit-result.length)
    for(let index=0;index<n;index++)result.push({entry,index})
    if(result.length>=limit)break
  }
  return result
}
