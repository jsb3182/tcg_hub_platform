// Public card details contain only the article matches accepted for this card's ID.
// A search URL or an arbitrary link in a translation record is not an article match.
export function namuArticleUrl(value) {
  if (typeof value !== 'string' || !value.startsWith('https://') || /[\\\u0000-\u001f\u007f]/u.test(value)) return ''
  try {
    const url=new URL(value)
    if (url.origin!=='https://namu.wiki' || url.username || url.password || !url.pathname.startsWith('/w/')) return ''
    const title=decodeURIComponent(url.pathname.slice(3))
    return title.trim() && !/[\u0000-\u001f\u007f]/u.test(title) ? url.href : ''
  } catch {return ''}
}

function verifiedPrintingUrl(game,value){
  try{
    const u=new URL(value)
    if(u.username || u.password || u.protocol!=='https:' || u.port)return ''
    if(game==='POKEMON' && u.hostname==='pokemoncard.co.kr' && /^\/cards\/detail\/[A-Za-z0-9]+$/.test(u.pathname))return u.href
    if(game==='YUGIOH' && u.hostname==='www.db.yugioh-card.com' && u.pathname==='/yugiohdb/card_search.action' && /^\d+$/.test(u.searchParams.get('cid') || ''))return u.href
  }catch{/* Older entries may not have a verification URL. */}
  return ''
}

export function cardWikiReferences(specs, game) {
  if (!Array.isArray(specs?.wikiReferences)) return []
  const rows=[], seen=new Set()
  for (const item of specs.wikiReferences) {
    const url=namuArticleUrl(item?.url)
    const title=typeof item?.title==='string' ? item.title.trim() : ''
    if (!url || !title || item.language!=='ko') continue
    const revision=(typeof item.revision==='string' || Number.isSafeInteger(item.revision)) ? String(item.revision).trim() : ''
    const snapshotDate=/^\d{4}-\d{2}-\d{2}$/.test(item.snapshotDate) ? item.snapshotDate : ''
    const key=JSON.stringify([url,revision,snapshotDate])
    if (seen.has(key)) continue
    seen.add(key)
    // The provenance link identifies a particular distribution revision, independent of the article revision.
    const snapshotUrl=typeof item.snapshotUrl==='string' &&
      /^https:\/\/huggingface\.co\/datasets\/Bingsu\/namuwiki_20210301_filtered\/tree\/[0-9a-f]{40}\/?$/u.test(item.snapshotUrl)
      ? item.snapshotUrl : ''
    const facts=Object.entries(item.facts && typeof item.facts==='object' ? item.facts : {}).filter(([code,value])=>
      ['atk','def','level','rank','link','hp','cost','power','life','soul','hit','energy','might','attribute','race','type','color','printingNumber'].includes(code)
      && (typeof value==='string' || Number.isFinite(value)))
    const details={}
    for(const field of ['traits','rulings','packs']){
      const values=item.details?.[field]
      if(Array.isArray(values))details[field]=[...new Set(values.filter(s=>typeof s==='string' && s.trim()))]
    }
    const textKo=typeof item.textKo==='string'?item.textKo.trim():''
    rows.push({key,title,url,language:item.language,revision,snapshotDate,snapshotUrl,facts,details,textKo,verificationUrl:verifiedPrintingUrl(game,item.verificationUrl)})
  }
  return rows
}
