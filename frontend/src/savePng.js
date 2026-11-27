// The WebView reads only the pending PNG in small chunks. Android owns the destination picker.
export function savePng(blob,filename) {
  if(blob?.type!=='image/png')throw Error('PNG')
  return saveDocument(blob,filename)
}
export async function saveDocument(blob,filename) {
  const kind={'image/png':'png','application/json':'json','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'xlsx','text/calendar':'ics'}[blob?.type]
  if(!(blob instanceof Blob)||!kind||!blob.size)throw Error('file')
  const name=(filename||'TCG').replace(/[<>:"/\\|?*\u0000-\u001f]/g,'_').replace(/\.(png|json|xlsx|ics)$/i,'').slice(0,80)+'.'+kind
  if (!navigator.userAgent.includes('TCGHubPng/1')) {
    const url=URL.createObjectURL(blob)
    const link=document.createElement('a')
    link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove()
    setTimeout(()=>URL.revokeObjectURL(url),120000)
    return
  }
  if (blob.size>16*1024*1024 || window.__tcgPngRead) throw Error('PNG')
  const key=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('')
  const encoded=await new Promise((resolve,reject)=>{
    const reader=new FileReader()
    reader.onload=()=>resolve(reader.result.slice(reader.result.indexOf(',')+1))
    reader.onerror=()=>reject(reader.error)
    reader.readAsDataURL(blob)
  })
  return new Promise((resolve,reject)=>{
    function finish(ok) {
      clearTimeout(timer);delete window.__tcgPngRead;delete window.__tcgPngDone
      if(ok)resolve();else reject(Error('PNG'))
    }
    window.__tcgPngRead=(token,offset)=>token===key && Number.isSafeInteger(offset) && offset>=0 ? encoded.slice(offset,offset+49152) : null
    window.__tcgPngDone=(token,ok)=>{if(token===key)finish(ok)}
    const timer=setTimeout(()=>finish(false),300000)
    location.href='tcghub-save://'+kind+'/'+key+'?size='+blob.size+'&name='+encodeURIComponent(name)
  })
}
