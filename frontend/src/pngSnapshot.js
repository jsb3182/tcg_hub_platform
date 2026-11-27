import { pt } from './pack'
import {mediaPath} from './api'

export async function pngSnapshot(source, title, subtitle, width) {
  const { toBlob } = await import('html-to-image')
  const stage=document.createElement('div')
  Object.assign(stage.style,{position:'absolute',left:'-10000px',top:'0',pointerEvents:'none'})
  stage.setAttribute('aria-hidden','true')
  const sheet=document.createElement('div')
  const colors=getComputedStyle(document.documentElement)
  Object.assign(sheet.style,{
    width:width+'px',padding:'16px',background:colors.getPropertyValue('--sf'),
    color:colors.getPropertyValue('--tx'),overflowWrap:'anywhere',
  })
  const heading=document.createElement('h2')
  heading.style.cssText='font-size:20px;margin:0 0 4px'
  heading.textContent=title
  const caption=document.createElement('p')
  caption.style.cssText='margin:0 0 15px;font-size:13px'
  caption.textContent=subtitle
  const content=source.cloneNode(true)
  for(const img of content.querySelectorAll('img')){
    img.removeAttribute('srcset')
    if(!mediaPath(img.getAttribute('src')))img.removeAttribute('src')
  }
  content.querySelectorAll('dialog,.variant-nav,.lib-actions,[data-png-skip]').forEach(el=>el.remove())
  content.querySelectorAll('[id]').forEach(el=>el.removeAttribute('id'))
  sheet.append(heading,caption,content)
  stage.append(sheet);document.body.append(stage)
  try {
    await document.fonts.ready
    await Promise.all([...content.querySelectorAll('img')].map(async img=>{
      try{
        const url=mediaPath(img.getAttribute('src'))
        if(!url)throw new Error('Missing local artwork')
        const original=new Image()
        original.src=url
        await original.decode()
        const copy=document.createElement('canvas')
        copy.width=Math.min(original.naturalWidth,Math.max(width,300))
        copy.height=Math.max(1,Math.round(copy.width*original.naturalHeight/original.naturalWidth))
        copy.getContext('2d').drawImage(original,0,0,copy.width,copy.height)
        img.loading='eager'; img.src=copy.toDataURL('image/png')
        await img.decode()
      }catch{
        const unavailable=document.createElement('span')
        unavailable.textContent=pt('이미지 저장 불가')
        unavailable.style.cssText='display:grid;place-items:center;aspect-ratio:300/438;border:1px solid currentColor;font-size:12px'
        img.replaceWith(unavailable)
      }
    }))
    return await toBlob(sheet,{pixelRatio:1,skipFonts:true,backgroundColor:colors.getPropertyValue('--sf').trim()})
  }finally{stage.remove()}
}
