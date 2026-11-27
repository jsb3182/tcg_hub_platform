import {request} from './api'

// Resolve the original static site's fragment links against IDs on this installation.
let pending, expires=0
export function publicPacks() {
  if(!pending || Date.now()>=expires){
    expires=Date.now()+60000
    pending=request('/releases').catch(error=>{pending=null;throw error})
  }
  return pending
}

export function bookmarkedPack(rows,hash) {
  const key=hash.slice('#pack-'.length)
  return rows?.find(row=>row.gameCode==='YUGIOH' && row.metadata?.id===key)
}
