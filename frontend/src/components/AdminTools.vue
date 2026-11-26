<script setup>
import { ref, watch } from 'vue'
import { useSession } from '../stores/session'
import { gameCodes, gameName, locale, t } from '../i18n'
import { dateTime } from '../presentation'
const props=defineProps({tab:{type:String,required:true}})
const session=useSession(), q=ref(''), search=ref(''), page=ref(0), status=ref('PUBLISHED')
const rows=ref([]), host=ref(null), busy=ref(false), loading=ref(false), error=ref(''), notice=ref(''), refresh=ref(0), hasNext=ref(false)
const edit=ref(null), event=ref(null)
const actions=[
 ['sync','지금 동기화'],['crawler/start','수집 시작'],['crawler/stop','수집 중지'],
 ['scheduler/pause','스케줄러 정지'],['scheduler/resume','스케줄러 재개'],['restart','서버 재시작'],['shutdown','서버 종료']
]
watch(()=>props.tab,()=>{q.value=search.value='';page.value=0;edit.value=event.value=null;notice.value=''})
watch([()=>props.tab,page,search,status,refresh,locale],async([tab],_,cleanup)=>{
 const ac=new AbortController();cleanup(()=>ac.abort());error.value='';rows.value=[];loading.value=true
 const query=new URLSearchParams({page:page.value,size:20,q:search.value,lang:locale.value})
 try{
  if(tab==='server'){
   const [state,log]=await Promise.all([session.adminRequest('/server/status',{signal:ac.signal}),session.adminRequest('/actions?'+query,{signal:ac.signal})])
   if(!ac.signal.aborted){host.value=state;rows.value=log;hasNext.value=log.length>=50}
  }else{
   if(tab==='posts')query.set('status',status.value)
   const result=await session.adminRequest('/'+tab+'?'+query,{signal:ac.signal})
   if(!ac.signal.aborted){rows.value=Array.isArray(result)?result:result.items;hasNext.value=Array.isArray(result)?result.length>=50:(page.value+1)*20<result.total}
  }
 }catch(e){if(!ac.signal.aborted)error.value=e.message}finally{if(!ac.signal.aborted)loading.value=false}
},{immediate:true})
async function write(path,method,body,confirmation){
 if(busy.value || (confirmation&&!window.confirm(confirmation)))return
 busy.value=true;error.value=notice.value=''
 try{await session.adminRequest(path,{method,body});edit.value=event.value=null;notice.value=t('요청을 처리했습니다.');refresh.value++}
 catch(e){error.value=e.message}finally{busy.value=false}
}
function editor(row){edit.value=row?{...row,gameCodes:[...(row.gameCodes||[])]}:{name:'',address:'',region:'',lat:null,lon:null,gameCodes:[],official:null,listed:false};event.value=null}
function saveStore(){const {id,name,address,region,lat,lon,gameCodes,official,listed,version}=edit.value
 return write('/stores'+(id?'/'+id:''),id?'PUT':'POST',{name,address,region,lat,lon,gameCodes,official,listed,version})}
function saveEvent(){const e=event.value
 return write('/stores/'+e.id+'/events','POST',{title:e.title,gameCode:e.gameCode,startsAt:new Date(e.startsAt).toISOString(),endsAt:e.endsAt?new Date(e.endsAt).toISOString():null})}
</script>
<template><section class="management">
 <form v-if="tab==='stores'||tab==='users'" class="actions" @submit.prevent="page=0;search=q.trim();refresh++"><label>{{tab==='users'?$t('이메일'):$t('매장명·지역')}}<input type="search" v-model="q" maxlength="100"></label><button class="secondary">{{ $t('검색') }}</button></form>
 <label v-if="tab==='posts'">{{ $t('공개 상태') }}<select v-model="status" @change="page=0"><option v-for="s in ['PUBLISHED','PENDING','REJECTED']" :key="s" :value="s">{{ $t(({PUBLISHED:'공개',PENDING:'검수 대기',REJECTED:'반려'})[s]) }}</option></select></label>
 <button v-if="tab==='stores'&&!edit" class="primary" @click="editor()">{{ $t('매장 등록') }}</button>
 <form v-if="edit&&tab==='stores'" class="panel ops-form" @submit.prevent="saveStore">
  <label>{{ $t('매장 이름') }}<input v-model.trim="edit.name" maxlength="160" required></label><label>{{ $t('주소') }}<input v-model.trim="edit.address" maxlength="300" required></label>
  <label>{{ $t('지역') }}<input v-model.trim="edit.region" required maxlength="60"></label><label>{{ $t('위도') }}<input v-model.number="edit.lat" type="number" min="-90" max="90" step="any" required></label><label>{{ $t('경도') }}<input v-model.number="edit.lon" type="number" min="-180" max="180" step="any" required></label>
  <fieldset><legend>{{ $t('취급 게임') }}</legend><label v-for="g in gameCodes" :key="g"><input type="checkbox" v-model="edit.gameCodes" :value="g">{{ gameName(g) }}</label></fieldset>
  <label>{{ $t('공인 매장') }}<select v-model="edit.official"><option :value="null">{{ $t('미확인') }}</option><option :value="true">{{ $t('예') }}</option><option :value="false">{{ $t('아니요') }}</option></select></label>
  <label><input type="checkbox" v-model="edit.listed">{{ $t('승인·공개') }}</label><div class="actions"><button class="primary" :disabled="busy">{{ $t('저장') }}</button><button class="secondary" type="button" @click="edit=null">{{ $t('취소') }}</button></div>
 </form>
 <form v-if="event" class="panel ops-form" @submit.prevent="saveEvent"><h3>{{ event.name }}</h3><label>{{ $t('대회 이름') }}<input v-model.trim="event.title" required maxlength="180"></label>
 <label>{{ $t('게임') }}<select v-model="event.gameCode" required><option disabled value="">{{ $t('게임 선택') }}</option><option v-for="g in gameCodes" :key="g" :value="g">{{gameName(g)}}</option></select></label>
 <label>{{ $t('시작 시각') }}<input type="datetime-local" v-model="event.startsAt" required></label><label>{{ $t('종료 시각') }}<input type="datetime-local" v-model="event.endsAt" :min="event.startsAt"></label><div class="actions"><button class="primary" :disabled="busy">{{ $t('저장') }}</button><button class="secondary" type="button" @click="event=null">{{ $t('취소') }}</button></div></form>
 <p v-if="error" role="alert" class="inline-error">{{ error }} <button class="text-button" @click="refresh++">{{ $t('다시 시도') }}</button></p><p v-if="notice" role="status">{{notice}}</p>
 <div v-if="tab==='server'&&host" class="panel"><dl><dt>DB</dt><dd>{{host.database}}</dd><dt>{{ $t('수집 워커') }}</dt><dd>{{ $t(host.crawlerEnabled?'수집 중':'일시정지') }}</dd><dt>{{ $t('스케줄러') }}</dt><dd>{{ $t(host.schedulerEnabled?'사용':'일시정지') }}</dd></dl>
 <div class="actions"><button v-for="[key,name] in actions" :key="key" class="secondary" :disabled="busy || (['restart','shutdown'].includes(key)&&!host.hostControlAvailable)" @click="write('/server/'+key,'POST',undefined,['restart','shutdown'].includes(key)?$t(name)+'?':'')">{{ $t(name) }}</button></div><h3>{{ $t('작업 기록') }}</h3></div>
 <p v-if="loading" role="status">{{ $t('목록을 불러오는 중입니다.') }}</p><p v-else-if="!rows.length&&!error">{{ $t('기록 없음') }}</p>
 <ul v-else class="admin-records"><li v-for="(row,i) in rows" :key="row.id||i">
  <template v-if="tab==='users'"><strong>{{row.email}}</strong><span>{{row.role}}</span><button class="secondary" :disabled="busy||session.account?.email===row.email" @click="write('/users/'+row.id+'/role','PUT',{role:row.role==='ROLE_ADMIN'?'ROLE_USER':'ROLE_ADMIN',expectedRole:row.role},$t('권한을 변경할까요?'))">{{ $t(row.role==='ROLE_ADMIN'?'일반 회원으로 변경':'관리자로 변경') }}</button></template>
  <template v-if="tab==='stores'"><div><strong>{{row.name}}</strong><small>{{row.address}} · {{ $t(row.listed?'공개':'비공개') }}</small></div><div class="actions"><button class="secondary" @click="editor(row)">{{ $t('편집') }}</button><button class="secondary" @click="edit=null;event={id:row.id,name:row.name,title:'',gameCode:'',startsAt:'',endsAt:''}">{{ $t('대회 등록') }}</button></div></template>
  <template v-if="tab==='posts'"><strong>{{row.title}}</strong><div class="actions" v-if="status==='PUBLISHED'"><button class="secondary" :disabled="busy" @click="write('/posts/'+row.id+'/visibility','POST',{hidden:!row.hidden,pinned:!!row.pinned})">{{ $t(row.hidden?'공개':'숨기기') }}</button><button class="secondary" :disabled="busy" @click="write('/posts/'+row.id+'/visibility','POST',{hidden:!!row.hidden,pinned:!row.pinned})">{{ $t(row.pinned?'고정 해제':'상단 고정') }}</button></div></template>
  <template v-if="tab==='server'"><strong>{{row.action}}</strong><small>{{row.targetId}} · {{dateTime(row.occurredAt)}}</small></template>
 </li></ul><nav class="pagination" v-if="page||hasNext"><button class="secondary" :disabled="!page" @click="page--">{{ $t('이전') }}</button><span>{{page+1}}</span><button class="secondary" :disabled="!hasNext" @click="page++">{{ $t('다음') }}</button></nav>
</section></template>
<style scoped>
.management{display:grid;gap:1rem}.management .actions,.admin-records li{display:flex;align-items:center;flex-wrap:wrap;gap:.6rem}.management input:not([type=checkbox]),.management select{padding:.55rem;background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:5px}.management label{display:grid;gap:.25rem}.ops-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr));gap:.8rem}.ops-form fieldset,.ops-form .actions{grid-column:1/-1}.ops-form fieldset label{display:inline-flex;margin:.3rem}.admin-records{list-style:none;padding:0;margin:0}.admin-records li{padding:.8rem 0;border-bottom:1px solid var(--bd);justify-content:space-between}.admin-records small{display:block;color:var(--mu)}.management dd{margin:0 0 .6rem}
</style>
