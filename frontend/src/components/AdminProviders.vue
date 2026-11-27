<script setup>
import {onBeforeUnmount,onMounted,ref} from 'vue'
import {useSession} from '../stores/session'
import {bytes} from '../presentation'
import {pt} from '../pack'
const session=useSession(),data=ref(null),error=ref(''),busy=ref(false)
let controller
async function load(){
  controller?.abort();const abort=controller=new AbortController()
  error.value='';busy.value=true
  try{const result=await session.adminRequest('/providers',{signal:abort.signal});if(!abort.signal.aborted)data.value=result}
  catch(e){if(!abort.signal.aborted)error.value=e.message}
  finally{if(!abort.signal.aborted)busy.value=false}
}
onMounted(load);onBeforeUnmount(()=>controller?.abort())
</script>
<template>
  <details class="provider-status">
    <summary>{{ pt('공급자 연결 상태') }}</summary>
    <p v-if="error" role="alert">{{ error }} <button type="button" class="text-button" @click="load">{{ pt('다시 시도') }}</button></p>
    <p v-else-if="busy" role="status">{{ pt('불러오는 중…') }}</p>
    <template v-else-if="data"><dl>
      <div v-for="provider in data.providers" :key="provider.code"><dt>{{ provider.code }}</dt><dd>{{ pt(provider.requiresKey ? provider.configured?'키 설정됨':'키 미설정':'키 불필요') }}</dd></div>
      <div v-if="data.cacheBytes!=null"><dt>{{ pt('로컬 이미지 캐시') }}</dt><dd>{{ bytes(data.cacheBytes) }}</dd></div>
    </dl></template>
  </details>
</template>
<style scoped>.provider-status{border-block:1px solid var(--bd);margin:.8rem 0}.provider-status summary{cursor:pointer;min-height:44px;padding:.65rem 0}.provider-status dl{margin:0 0 1rem}.provider-status dl div{display:flex;justify-content:space-between;gap:10px;padding:4px 0}.provider-status dd{margin:0}</style>
