import {request} from './api'

export async function localizedCards(ids,game,lang,signal){
  const byId=new Map()
  const unique=[...new Set(ids)]
  for(let i=0;i<unique.length;i+=100){
    const params=new URLSearchParams({ids:unique.slice(i,i+100).join(','),game,lang,size:100})
    const {items}=await request('/cards?'+params,{signal})
    for(const card of items)byId.set(card.id,card)
  }
  return byId
}
export function nameFields(card){
  return {name:card.name,language:card.language,nameBasis:card.nameBasis,nameReferenceUrl:card.nameReferenceUrl}
}
