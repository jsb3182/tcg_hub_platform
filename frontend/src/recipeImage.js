import { artworkUrl, mediaPath } from './api'
import { locale, t } from './i18n'
import { sectionLabel } from './library'
import { recipeUiLabels } from './recipeUiLabels'
import { slots } from './recipeLayout'
import {cardArtworks,preferredArtwork} from './artwork'

export function rt(key){
  return locale.value==='ko' ? key : recipeUiLabels[key]?.[locale.value==='en'?0:1] ?? t(key)
}
function source(entry){
  const tile=entry.image
  const src=entry.variantId && tile ? null : entry.imageUrl
  const choice=preferredArtwork(cardArtworks(src,entry.imageLanguage,[{image:tile}],null,entry.imageBasis),locale.value)
  if(choice?.style)return {url:mediaPath(tile.url),tile}
  return {url:artworkUrl(choice?.src)}
}
function fitLabel(ctx,text,maxWidth){
  const chars=Array.from(String(text||''))
  if(ctx.measureText(chars.join('')).width<=maxWidth)return chars.join('')
  let lo=0,hi=chars.length
  while(lo<hi){
    const mid=Math.ceil((lo+hi)/2)
    if(ctx.measureText(chars.slice(0,mid).join('')+'…').width<=maxWidth)lo=mid
    else hi=mid-1
  }
  return chars.slice(0,lo).join('')+'…'
}
export async function drawRecipe({name,game,groups,excludeSide}){
  const sections=groups.filter(group=>group.total && !(excludeSide && group.section==='SIDE'))
  const total=sections.reduce((n,group)=>n+group.total,0)
  const grouped=total>240
  const cols=8, gap=8, width=960, pad=24, tileW=(width-pad*2-gap*(cols-1))/cols, tileH=Math.round(tileW*438/300), rowH=tileH+40
  const rows=sections.map(group=>({...group,slots:slots(group.entries,grouped?group.entries.length:group.total,grouped)}))
  const canvas=document.createElement('canvas')
  canvas.width=width;canvas.height=106+rows.reduce((n,g)=>n+48+Math.ceil(g.slots.length/cols)*rowH,0)+pad
  const ctx=canvas.getContext('2d')
  if(!ctx)throw new Error('canvas')
  const css=getComputedStyle(document.documentElement)
  const color=key=>css.getPropertyValue(key).trim()
  ctx.fillStyle=color('--sf');ctx.fillRect(0,0,canvas.width,canvas.height)
  ctx.textBaseline='top';ctx.fillStyle=color('--tx');ctx.font='bold 30px sans-serif'
  ctx.fillText(fitLabel(ctx,name,width-pad*2),pad,24)
  ctx.font='17px sans-serif';ctx.fillStyle=color('--mu')
  ctx.fillText([game,total+rt('장'),excludeSide?rt('사이드 제외'):'',grouped?rt('수량을 묶어 표시'):''].filter(Boolean).join(' · '),pad,68)
  const cache=new Map()
  const image=async url=>{
    if(!url)return null
    if(!cache.has(url)){
      const im=new Image();im.crossOrigin='anonymous';im.referrerPolicy='no-referrer';im.src=url
      cache.set(url,im.decode().then(()=>im).catch(()=>null))
    }
    return cache.get(url)
  }
  let y=104
  for(const group of rows){
    ctx.fillStyle=color('--bd');ctx.fillRect(pad,y,width-pad*2,1)
    ctx.fillStyle=color('--tx');ctx.font='bold 20px sans-serif';ctx.fillText(sectionLabel(group.section)+'  '+group.total+rt('장'),pad,y+9)
    y+=43
    for(const [i,{entry}] of group.slots.entries()){
      const x=pad+(i%cols)*(tileW+gap),top=y+Math.floor(i/cols)*rowH
      const art=source(entry), im=await image(art.url)
      if(im){
        if(art.tile){
          const w=im.naturalWidth/4,h=im.naturalHeight/3
          ctx.drawImage(im,art.tile.col*w,art.tile.row*h,w,h,x,top,tileW,tileH)
        }else{
          const ratio=Math.min(tileW/im.naturalWidth,tileH/im.naturalHeight)
          const w=im.naturalWidth*ratio,h=im.naturalHeight*ratio
          ctx.drawImage(im,x+(tileW-w)/2,top+(tileH-h)/2,w,h)
        }
      }else{
        ctx.fillStyle=color('--bg');ctx.fillRect(x,top,tileW,tileH)
        ctx.fillStyle=color('--mu');ctx.font='12px sans-serif'
        ctx.fillText(fitLabel(ctx,rt('이미지 없음'),tileW-8),x+4,top+tileH/2)
      }
      ctx.fillStyle=color('--tx');ctx.font='bold 13px sans-serif'
      ctx.fillText(fitLabel(ctx,entry.name,tileW),x,top+tileH+4)
      ctx.fillStyle=color('--mu');ctx.font='12px sans-serif'
      ctx.fillText(fitLabel(ctx,[grouped?'×'+entry.quantity:'',entry.number].filter(Boolean).join(' · '),tileW),x,top+tileH+20)
    }
    y+=Math.ceil(group.slots.length/cols)*rowH+5
  }
  return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('PNG')),'image/png'))
}
