// Read dimensions before decoding a small compressed file into a potentially much larger phone bitmap.
function jpegSize(bytes, view) {
  let index=2
  while (index+4<=bytes.length && bytes[index]===0xff) {
    while (bytes[index]===0xff) index++
    const marker=bytes[index++]
    if (marker===0xda || marker===0xd9 || index+2>bytes.length) return
    const length=view.getUint16(index)
    if (length<2 || index+length>bytes.length) return
    if (marker>=0xc0 && marker<=0xcf && ![0xc4,0xc8,0xcc].includes(marker) && length>=8) {
      return [view.getUint16(index+5),view.getUint16(index+3)]
    }
    index+=length
  }
}
function webpSize(bytes,view) {
  if (bytes.length<25) return
  const chunk=String.fromCharCode(...bytes.slice(12,16))
  if (chunk==='VP8X' && bytes.length>=30) {
    if ((bytes[20]&2)!==0) throw new Error('움직이는 WebP 대신 정지 이미지를 선택해 주세요.')
    const uint24=i=>bytes[i]+bytes[i+1]*256+bytes[i+2]*65536
    return [uint24(24)+1,uint24(27)+1]
  }
  if (chunk==='VP8 ' && bytes.length>=30 && bytes[23]===0x9d && bytes[24]===1 && bytes[25]===0x2a) {
    return [view.getUint16(26,true)&0x3fff,view.getUint16(28,true)&0x3fff]
  }
  if (chunk==='VP8L' && bytes[20]===0x2f) {
    const bits=view.getUint32(21,true)
    return [(bits&0x3fff)+1,((bits>>>14)&0x3fff)+1]
  }
}
export async function checkCropSource(file) {
  if (file.size>8*1024*1024) throw new Error('8 MiB 이하 파일을 선택해 주세요.')
  const buffer=await file.arrayBuffer(), view=new DataView(buffer), bytes=new Uint8Array(buffer)
  const suffix=file.name.split('.').pop().toLowerCase()
  let size
  if (suffix==='png' && bytes.length>=24 && [137,80,78,71,13,10,26,10].every((b,i)=>bytes[i]===b)
      && String.fromCharCode(...bytes.slice(12,16))==='IHDR') {
    size=[view.getUint32(16),view.getUint32(20)]
  } else if (['jpeg','jpg'].includes(suffix) && bytes[0]===255 && bytes[1]===216) {
    size=jpegSize(bytes,view)
  } else if (suffix==='webp' && String.fromCharCode(...bytes.slice(0,4))==='RIFF' &&
      String.fromCharCode(...bytes.slice(8,12))==='WEBP') size=webpSize(bytes,view)
  if (!size || !size[0] || !size[1]) throw new Error('형식을 확인할 수 없습니다. JPG, PNG 또는 WebP를 선택해 주세요.')
  if (size[0]*size[1]>12000000) throw new Error('1,200만 픽셀 이하 이미지를 선택해 주세요.')
}
