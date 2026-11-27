<script setup>
import {computed,reactive,ref,watch} from 'vue'
import {onBeforeRouteLeave} from 'vue-router'
import {request,sourceLink} from '../api'
import {gameCodes,gameName} from '../i18n'
import {pt,regionName,releaseRegions} from '../pack'
import {productTypes} from '../releaseCalendar'
import {useSession} from '../stores/session'

const session=useSession(),game=ref(''),query=ref(''),search=ref(''),page=ref(0),tick=ref(0),size=20
const rows=ref([]),total=ref(0),busy=ref(false),listError=ref(''),saving=ref(false),error=ref(''),message=ref('')
const editor=ref(false),selected=ref(null),baseline=ref(''),packFilter=ref(''),packs=ref([]),packsFailed=ref(false)
const conflict=ref(null)
const blank=()=>({gameCode:'YUGIOH',region:'KR',code:'',name:'',ko:'',en:'',ja:'',releaseDate:'',sourceUrl:'',catalogPackId:'',productType:'UNKNOWN'})
const form=reactive(blank())
const dirty=computed(()=>editor.value && JSON.stringify(form)!==baseline.value)
const emit=defineEmits(['busy'])
watch(saving,v=>emit('busy',v))
function mayLeave(){return !saving.value && (!dirty.value || window.confirm(pt('저장하지 않은 변경을 취소할까요?')))}
defineExpose({mayLeave})
onBeforeRouteLeave(()=>mayLeave())
watch([game,search,page,tick],async([g,q,n],_,clean)=>{
  const abort=new AbortController();clean(()=>abort.abort());busy.value=true;listError.value=''
  try{
    const result=await session.adminRequest('/releases?'+new URLSearchParams({game:g,q,page:n,size}),{signal:abort.signal})
    if(!abort.signal.aborted){rows.value=result.items;total.value=result.total}
  }catch(e){if(!abort.signal.aborted)listError.value=e.message}
  finally{if(!abort.signal.aborted)busy.value=false}
},{immediate:true})
watch([editor,()=>form.gameCode],async([open,g],_,clean)=>{
  const abort=new AbortController();clean(()=>abort.abort());packs.value=[];packFilter.value='';packsFailed.value=false
  if(!open)return
  try{const data=await request('/packs?'+new URLSearchParams({game:g}),{signal:abort.signal});if(!abort.signal.aborted)packs.value=data}
  catch{if(!abort.signal.aborted)packsFailed.value=true}
})
const matching=computed(()=>{
  const q=packFilter.value.trim().toLocaleLowerCase(),filtered=packs.value.filter(p=>!q || [p.name,p.code].some(v=>v?.toLocaleLowerCase().includes(q))).slice(0,100)
  const old=packs.value.find(p=>String(p.id)===form.catalogPackId)
  if(old && !filtered.includes(old))filtered.unshift(old)
  return filtered
})
function edit(row){
  if(!mayLeave())return
  editor.value=true;selected.value=row||null;error.value='';message.value='';conflict.value=null
  Object.assign(form,blank(),row?{gameCode:row.gameCode,region:row.region,code:row.code||'',name:row.name,
    ko:row.names?.ko||'',en:row.names?.en||'',ja:row.names?.ja||'',releaseDate:row.releaseDate,sourceUrl:row.sourceUrl,
    catalogPackId:row.catalogPackId==null?'':String(row.catalogPackId),productType:row.productType||'UNKNOWN'}:{gameCode:game.value||'YUGIOH'})
  baseline.value=JSON.stringify(form)
}
function close(){if(mayLeave()){editor.value=false;error.value=''}}
async function save(){
  if(saving.value || conflict.value)return
  error.value='';message.value=''
  const url=sourceLink(form.sourceUrl.trim())
  if(!url){error.value=pt('발매 정보 원문 URL을 확인하세요.');return}
  const body={gameCode:form.gameCode,region:form.region,code:form.code.trim()||null,name:form.name.trim(),
    names:Object.fromEntries(['ko','en','ja'].filter(lang=>form[lang].trim()).map(lang=>[lang,form[lang].trim()])),
    releaseDate:form.releaseDate,sourceUrl:url,catalogPackId:form.catalogPackId?Number(form.catalogPackId):null,productType:form.productType}
  if(selected.value)body.version=selected.value.version
  saving.value=true
  try{
    const saved=await session.adminRequest('/releases'+(selected.value?'/'+selected.value.id:''),{method:selected.value?'PUT':'POST',body})
    selected.value=saved;baseline.value=JSON.stringify(form);editor.value=false;message.value=pt('발매 일정을 저장했습니다.');tick.value++
  }catch(e){
    if(e.status===409 && selected.value){
      error.value=pt('다른 변경이 있습니다. 서버 값과 입력한 내용을 비교하세요.')
      try{conflict.value=await session.adminRequest('/releases/'+selected.value.id)}
      catch{error.value=pt('다른 변경이 있습니다. 목록을 새로고침한 뒤 다시 선택하세요.');tick.value++}
    }else error.value=e.message
  }
  finally{saving.value=false}
}
</script>
<template>
<section class="admin-releases">
  <form class="release-tools" role="search" @submit.prevent="page=0;search=query.trim();tick++">
    <label>{{ pt('게임') }}<select v-model="game" @change="page=0"><option value="">{{ pt('모든 종목') }}</option><option v-for="g in gameCodes" :key="g" :value="g">{{ gameName(g) }}</option></select></label>
    <label>{{ pt('팩 검색') }}<input v-model="query" type="search" maxlength="100"></label>
    <button class="secondary">{{ $t('검색') }}</button><button type="button" @click="edit(null)">{{ pt('발매 일정 추가') }}</button>
  </form>
  <p v-if="message" role="status" class="success-message">{{ message }}</p>
  <form v-if="editor" class="release-editor" @submit.prevent="save">
    <h3>{{ pt(selected?'발매 일정 수정':'발매 일정 추가') }}</h3>
    <fieldset :disabled="saving">
      <label>{{ pt('게임') }}<select v-model="form.gameCode" :aria-label="pt('게임')" :disabled="!!selected" @change="form.catalogPackId=''"><option v-for="g in gameCodes" :key="g" :value="g">{{ gameName(g) }}</option></select></label>
      <label>{{ pt('발매 지역') }}<select v-model="form.region" :disabled="!!selected"><option v-for="(_,r) in releaseRegions" :key="r" :value="r">{{ regionName(r) }}</option></select></label>
      <label>{{ pt('상품명') }}<input v-model="form.name" maxlength="320" required></label>
      <label>{{ pt('상품 코드') }}<input v-model="form.code" maxlength="96"></label>
      <label>{{ $t('발매일') }}<input v-model="form.releaseDate" type="date" required></label>
      <label>{{ pt('상품 유형') }}<select v-model="form.productType"><option v-for="(label,p) in productTypes" :key="p" :value="p">{{ pt(label) }}</option></select></label>
      <label class="span">{{ pt('발매 정보 출처') }}<input v-model="form.sourceUrl" type="url" maxlength="2048" required></label>
      <details class="span"><summary>{{ pt('언어별 상품명') }}</summary><label v-for="(name,l) in {ko:'한국어',en:'English',ja:'日本語'}" :key="l">{{ name }}<input v-model="form[l]" :lang="l" maxlength="320"></label></details>
      <label>{{ pt('연결할 팩 검색') }}<input v-model="packFilter" type="search"></label>
      <label>{{ pt('연결할 팩') }}<select v-model="form.catalogPackId"><option value="">{{ pt('연결 없음') }}</option>
        <option v-if="form.catalogPackId && !matching.some(p=>String(p.id)===form.catalogPackId)" :value="form.catalogPackId">#{{ form.catalogPackId }}</option>
        <option v-for="p in matching" :key="p.id" :value="String(p.id)">{{ [p.code,p.name].filter(Boolean).join(' · ') }}</option></select></label>
      <p v-if="packsFailed" class="inline-error span" role="status">{{ $t('팩 목록') }}{{ $t('을 불러오지 못했습니다.') }}</p>
      <p v-if="error" role="alert" class="inline-error span">{{ error }}</p>
      <section v-if="conflict" class="span">
        <h4>{{ pt('현재 서버 값') }}</h4>
        <p>{{ [conflict.name,conflict.code,conflict.releaseDate,productTypes[conflict.productType] && pt(productTypes[conflict.productType])].filter(Boolean).join(' · ') }}</p>
        <p v-for="(name,lang) in conflict.names" :key="lang" :lang="lang">{{ name }}</p>
        <p v-if="conflict.catalogPackId">{{ pt('연결할 팩') }} #{{ conflict.catalogPackId }}</p>
        <a v-if="sourceLink(conflict.sourceUrl)" :href="sourceLink(conflict.sourceUrl)" rel="noopener noreferrer" target="_blank">{{ conflict.sourceUrl }}</a>
        <div><button type="button" class="secondary" @click="selected=conflict;conflict=null;save()">{{ pt('입력한 값으로 다시 저장') }}</button></div>
      </section>
      <div class="span"><button type="submit" :disabled="!!conflict">{{ $t('저장') }}</button> <button class="secondary" type="button" @click="close">{{ $t('닫기') }}</button></div>
    </fieldset>
  </form>
  <p v-if="listError" role="alert">{{ listError }} <button type="button" class="text-button" @click="tick++">{{ pt('다시 시도') }}</button></p>
  <p v-else-if="busy" role="status">{{ pt('불러오는 중…') }}</p>
  <ul v-else-if="rows.length"><li v-for="r in rows" :key="r.id"><button class="text-button" @click="edit(r)">{{ r.name }}</button><small>{{ [gameName(r.gameCode),regionName(r.region),r.releaseDate].join(' · ') }}</small></li></ul>
  <p v-else>{{ pt('조건에 맞는 발매 일정이 없습니다.') }}</p>
  <nav v-if="total>size" class="pagination"><button class="secondary" :disabled="!page" @click="page--">{{ pt('이전') }}</button><span>{{ page+1 }}/{{ Math.ceil(total/size) }}</span><button class="secondary" :disabled="(page+1)*size>=total" @click="page++">{{ pt('다음') }}</button></nav>
</section>
</template>
<style scoped>
.release-tools,.release-editor fieldset{display:flex;align-items:end;gap:.65rem;flex-wrap:wrap}.admin-releases label{display:grid;min-width:0;gap:3px;font-size:.88rem}
.admin-releases :is(input,select){width:100%;min-width:0;min-height:42px;background:var(--sf);border:1px solid var(--bd);border-radius:5px;color:var(--tx);padding:.4rem}
.release-editor{margin:1.3rem 0;border-block:1px solid var(--bd);padding:1rem 0}.release-editor h3{margin:0 0 .6rem}.release-editor fieldset{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));padding:0;margin:0;border:0}.span{grid-column:1/-1}.release-editor summary{cursor:pointer;min-height:36px}.release-editor details label{margin:.3rem 0}
.admin-releases ul{list-style:none;padding:0}.admin-releases li{padding:.4rem 0;border-bottom:1px solid var(--bd)}.admin-releases li button{min-height:36px;text-align:start}.admin-releases li small{display:block;color:var(--mu)}.release-tools>label{flex:1 1 9rem}
</style>
