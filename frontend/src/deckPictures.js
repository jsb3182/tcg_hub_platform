export function savedDeckPicture(value){
  return typeof value==='string' && value.startsWith('data:image/jpeg;base64,') ? value : ''
}

export async function prepareDeckPicture(file,slot) {
  if(!file || !['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>10*1024*1024) throw Error('image')
  const url=URL.createObjectURL(file)
  try {
    const image=new Image();image.src=url;await image.decode()
    if(image.naturalWidth*image.naturalHeight>32000000)throw Error('dimensions')
    const canvas=document.createElement('canvas')
    canvas.width=slot==='cover'?640:224;canvas.height=slot==='cover'?256:320
    const scale=Math.max(canvas.width/image.naturalWidth,canvas.height/image.naturalHeight)
    let x=(image.naturalWidth-canvas.width/scale)/2,y=(image.naturalHeight-canvas.height/scale)/2
    if(slot==='cover' && 'FaceDetector' in window){
      try{
        const [face]=await new window.FaceDetector({maxDetectedFaces:1,fastMode:true}).detect(image)
        if(face){
          const b=face.boundingBox
          x=Math.max(0,Math.min(2*x,b.x+b.width/2-canvas.width/(2*scale)))
          y=Math.max(0,Math.min(2*y,b.y+b.height/2-canvas.height/(2*scale)))
        }
      }catch{/* Center crop when face detection is unavailable. */}
    }
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height)
    ctx.drawImage(image,x,y,canvas.width/scale,canvas.height/scale,0,0,canvas.width,canvas.height)
    const result=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.84))
    if(!result)throw Error('encode')
    return new File([result],slot+'.jpg',{type:'image/jpeg'})
  }finally{URL.revokeObjectURL(url)}
}
export async function storeDeckPictures(session,id,pictures) {
  for(const [slot,image] of Object.entries(pictures)) {
    const body=new FormData();body.append('image',image)
    await session.authenticatedRequest('/me/decks/'+id+'/decoration/'+slot,{method:'POST',body})
    delete pictures[slot]
  }
}
