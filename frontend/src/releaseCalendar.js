export const productTypes={BOOSTER:'부스터 팩',STARTER:'스타터 덱',PROMO:'프로모션',ACCESSORY:'액세서리',SPECIAL:'특별 상품',UNKNOWN:'유형 미확인'}

export function selectedCodes(raw,options){
  const codes=new Set(typeof raw==='string' ? raw.split(',') : [])
  return options.filter(code=>codes.has(code))
}
export function toggledCode(value,code){
  const selected=value.includes(code) ? value.filter(item=>item!==code) : [...value,code]
  return selected.join(',')
}
export function releaseDistance(releaseDate,asOf){
  const remaining=(Date.parse(releaseDate+'T00:00:00Z')-Date.parse(asOf+'T00:00:00Z'))/86400000
  if(!Number.isInteger(remaining))return ''
  return remaining===0?'D-Day':remaining>0?'D−'+remaining:'D+'+Math.abs(remaining)
}
export function kstMonth(asOf){
  return /^\d{4}-\d{2}-\d{2}$/.test(asOf||'') ? asOf.slice(0,7) : new Date(Date.now()+9*3600000).toISOString().slice(0,7)
}
export function changeMonth(current,offset){
  const date=new Date(current+'-01T00:00:00Z')
  date.setUTCMonth(date.getUTCMonth()+offset)
  return date.toISOString().slice(0,7)
}
