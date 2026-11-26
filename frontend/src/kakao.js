let pending
export function loadKakao(key) {
  if(window.kakao?.maps?.Map)return Promise.resolve(window.kakao.maps)
  if(pending)return pending
  pending=new Promise((resolve,reject)=>{
    const script=document.createElement('script')
    const timer=setTimeout(fail,8000)
    function fail(){clearTimeout(timer);script.remove();pending=null;reject(new Error('Kakao Maps unavailable'))}
    script.onerror=fail
    script.onload=()=>{if(!window.kakao?.maps?.load)return fail()
      window.kakao.maps.load(()=>{clearTimeout(timer);resolve(window.kakao.maps)})}
    script.src='https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&appkey='+encodeURIComponent(key)
    script.async=true;document.head.append(script)
  })
  return pending
}
export function kakaoStores(api,element,onSelect) {
  const map=new api.Map(element,{center:new api.LatLng(36.2,127.85),level:13})
  const resize=new ResizeObserver(()=>map.relayout())
  resize.observe(element)
  let pins=[]
  function clear(){for(const [pin,click] of pins){api.event.removeListener(pin,'click',click);pin.setMap(null)}pins=[]}
  return {
    draw(stores,center) {
      clear()
      const bounds=new api.LatLngBounds()
      for(const store of stores){
        const position=new api.LatLng(store.lat,store.lon)
        const pin=new api.Marker({position,map,title:store.name}),click=()=>onSelect(store.id)
        api.event.addListener(pin,'click',click);pins.push([pin,click]);bounds.extend(position)
      }
      if(stores.length>1)map.setBounds(bounds)
      else if(stores.length===1)this.select(stores[0])
      else if(center)map.setCenter(new api.LatLng(center[1],center[0]))
    },
    select(store){map.setLevel(4);map.panTo(new api.LatLng(store.lat,store.lon))},
    center(){const pos=map.getCenter();return [pos.getLng(),pos.getLat()]},
    dispose(){clear();resize.disconnect()},
  }
}
