import {checkCropSource} from './cropSource'

export async function recognizeGridCapture(file,options,session,signal){
  await checkCropSource(file)
  const bitmap=await createImageBitmap(file),canvas=document.createElement('canvas')
  try{
    const ctx=canvas.getContext('2d')
    let cap=1800,blob
    do{
      const scale=Math.min(1,cap/Math.max(bitmap.width,bitmap.height))
      canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale))
      ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height)
      blob=await new Promise(ok=>canvas.toBlob(ok,'image/jpeg',.84));cap=Math.floor(cap*.75)
    }while(blob?.size>1048576 && cap>=480)
    if(!blob || blob.size>1048576)throw Error('이미지를 읽지 못했습니다.')
    const data=new FormData()
    data.append('file',blob,'deck.jpg')
    for(const [key,value] of Object.entries(options))data.append(key,String(value))
    const result=await session.authenticatedRequest('/decks/import-capture',{method:'POST',body:data,signal})
    if(!Array.isArray(result?.slots) || result.slots.length>120 || !result.width || !result.height)throw Error('카드 배열을 찾을 수 없습니다.')
    const thumb=document.createElement('canvas');thumb.width=64;thumb.height=91
    const pen=thumb.getContext('2d')
    return {rows:result.slots.map(slot=>{
      const candidates=(slot.candidates||[]).filter(c=>Number.isSafeInteger(c.cardId) && c.cardId>0)
      pen.clearRect(0,0,64,91)
      pen.drawImage(canvas,slot.left*canvas.width/result.width,slot.top*canvas.height/result.height,
        slot.width*canvas.width/result.width,slot.height*canvas.height/result.height,0,0,64,91)
      return {section:'MAIN',quantity:1,thumbnail:thumb.toDataURL('image/jpeg',.72),candidates,
        confidence:candidates.length && slot.needsReview===false?'high':candidates.length?'review':'unmatched'}
    })}
  }finally{bitmap.close();canvas.width=canvas.height=0}
}
