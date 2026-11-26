<script setup>
import { t as uiText, gameName } from '../i18n'

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useSession } from '../stores/session'
import { request } from '../api'
import AdminCatalogEditor from './AdminCatalogEditor.vue'
import AdminCardImage from './AdminCardImage.vue'
import '../styles/catalog-admin.css'

const props=defineProps({games:{type:Array,required:true}})
const emit=defineEmits(['editing'])
const session=useSession()
const kind=ref('cards'), game=ref(''), status=ref(''), search=ref(''), query=ref(''), page=ref(0), revision=ref(0)
const list=ref([]), total=ref(0), listBusy=ref(false), listError=ref(''), detailError=ref(''), notice=ref('')
const item=ref(null), seed=ref(null), editing=ref(false), loadingItem=ref(false), formDirty=ref(false)
const saving=ref(false), uploading=ref(false), editorElement=ref(null), listHeading=ref(null), jobs=ref({}), fallbackGames=ref([]), gamesError=ref('')
const busy=computed(()=>saving.value || uploading.value)
const games=computed(()=>props.games.length?props.games:fallbackGames.value)
const statusName=computed(()=>({PENDING:uiText("검수 대기"),PUBLISHED:uiText("공개"),REJECTED:uiText("반려")}))
const pageSize=15
let detailController, gameController
let mounted=true
function mayLeave() {
  if (busy.value) return false
  return !formDirty.value || window.confirm(uiText("저장하지 않은 편집 내용을 버리시겠습니까?"))
}
defineExpose({mayLeave})
onBeforeRouteLeave(mayLeave)
function beforeUnload(event) {
  if (formDirty.value || busy.value) { event.preventDefault();event.returnValue='' }
}
watch([formDirty,busy],([dirty,working])=>emit('editing',{dirty,busy:working}),{immediate:true})
async function loadGames() {
  if (props.games.length) return
  gameController?.abort()
  const c=gameController=new AbortController()
  gamesError.value=''
  try {
    const options=await request('/games',{signal:c.signal})
    if (!c.signal.aborted) fallbackGames.value=options
  }catch(cause){if(!c.signal.aborted)gamesError.value=cause.message}
}
function closeEditor() {
  detailController?.abort()
  item.value=null;seed.value=null;editing.value=false;loadingItem.value=false;formDirty.value=false
  detailError.value=''
}
async function dismiss() {
  if(!mayLeave())return
  closeEditor()
  await nextTick()
  listHeading.value?.focus()
}
function setKind(value) {
  if(kind.value===value || !mayLeave()) return
  closeEditor()
  search.value='';query.value='';status.value='';page.value=0;kind.value=value;notice.value=''
}
watch([game,status,query],()=>{page.value=0},{flush:'sync'})
watch([kind,game,status,query,page,revision],async(_,__,cleanup)=>{
  const c=new AbortController();cleanup(()=>c.abort())
  listBusy.value=true;listError.value='';list.value=[]
  const params=new URLSearchParams({q:query.value,page:page.value,size:pageSize})
  if(game.value)params.set('game',game.value)
  if(kind.value==='cards'&&status.value)params.set('status',status.value)
  try{
    const data=await session.adminRequest('/catalog/'+kind.value+'?'+params,{signal:c.signal})
    if(c.signal.aborted)return
    total.value=data.total
    if(page.value>0 && !data.items.length){page.value=Math.max(0,Math.ceil(data.total/pageSize)-1);return}
    list.value=data.items
  }catch(cause){if(!c.signal.aborted){listError.value=cause.message;total.value=0}}
  finally{if(!c.signal.aborted)listBusy.value=false}
},{immediate:true})
async function showEditor() {
  await nextTick()
  if(mounted && editorElement.value && matchMedia('(max-width: 799px)').matches) {
    editorElement.value.scrollIntoView({block:'start'})
    editorElement.value.focus({preventScroll:true})
  }
}
async function open(id) {
  if(!mayLeave())return
  detailController?.abort()
  const c=detailController=new AbortController()
  detailError.value='';notice.value='';loadingItem.value=true
  try{
    const data=await session.adminRequest('/catalog/'+kind.value+'/'+id,{signal:c.signal})
    if(c.signal.aborted)return
    item.value=data;seed.value=null;editing.value=true;formDirty.value=false
    await showEditor()
  }catch(cause){if(!c.signal.aborted)detailError.value=cause.message}
  finally{if(!c.signal.aborted)loadingItem.value=false}
}
function create(pack=null) {
  if(!mayLeave())return
  closeEditor()
  if(pack){kind.value='cards';game.value=pack.gameCode;search.value='';query.value='';status.value='';page.value=0}
  seed.value={gameCode:pack?.gameCode || game.value || games.value[0]?.code || '',packId:pack?.id,packName:pack?.name}
  editing.value=true;notice.value=''
  showEditor()
}
function saved(value){
  item.value=value;seed.value=null;formDirty.value=false;notice.value=kind.value==='cards'?uiText("카드를 저장했습니다."):uiText("팩을 저장했습니다.")
  revision.value++
}
function rememberJob(job) { jobs.value={...jobs.value,[job.variantId]:job} }
onMounted(()=>{loadGames();window.addEventListener('beforeunload',beforeUnload)})
onBeforeUnmount(()=>{
  mounted=false;detailController?.abort();gameController?.abort()
  emit('editing',{dirty:false,busy:false})
  window.removeEventListener('beforeunload',beforeUnload)
})
</script>
<template>
  <p v-if="gamesError && !games.length" role="alert" class="inline-error">{{ gamesError }} <button class="text-button" @click="loadGames">{{ $t("게임 목록 다시 불러오기") }}</button></p>
  <div class="catalog-toolbar">
    <div class="catalog-kinds" role="group" :aria-label="$t('편집할 자료')">
      <button type="button" class="secondary" :aria-pressed="kind==='cards'" :disabled="busy" @click="setKind('cards')">{{ $t("카드 관리") }}</button>
      <button type="button" class="secondary" :aria-pressed="kind==='packs'" :disabled="busy" @click="setKind('packs')">{{ $t("팩 관리") }}</button>
    </div>
    <button type="button" class="primary" :disabled="busy || !games.length" @click="create()">{{ $t("새") }} {{ kind==='cards'?$t("카드"):$t("팩") }} {{ $t("추가") }}</button>
  </div>
  <div class="admin-catalog-layout" :class="{'has-editor':editing}">
    <section class="ops-card admin-catalog-list"><h3 ref="listHeading" tabindex="-1">{{ kind==='cards'?$t("카드"):$t("팩") }} {{ $t("찾기") }}</h3>
      <form @submit.prevent="query=search.trim();revision++">
        <div class="catalog-fields"><label>{{ $t("게임 필터") }}<select v-model="game"><option value="">{{ $t("전체 게임") }}</option><option v-for="g in games" :key="g.code" :value="g.code">{{ gameName(g.code,g.name) }}</option></select></label>
          <label v-if="kind==='cards'">{{ $t("상태 필터") }}<select v-model="status"><option value="">{{ $t("모든 상태") }}</option><option v-for="(title,key) in statusName" :key="key" :value="key">{{ title }}</option></select></label></div>
        <label>{{ kind==='cards'?$t("카드 이름·번호"):$t("팩 이름·코드") }}<input v-model="search" maxlength="120" type="search" /></label>
        <div class="ops-actions"><button class="secondary">{{ $t("검색") }}</button><button type="button" class="text-button" @click="revision++">{{ $t("목록 새로고침") }}</button></div>
      </form>
      <p v-if="listBusy" role="status">{{ $t("목록을 불러오는 중입니다.") }}</p>
      <p v-else-if="listError" role="alert" class="inline-error">{{ listError }}</p>
      <p v-else-if="!list.length" class="muted">{{ $t("조건에 맞는") }} {{ kind==='cards'?$t("카드가"):$t("팩이") }} {{ $t("없습니다.") }}</p>
      <template v-else>
        <p class="update-time">{{ total.toLocaleString('ko-KR') }}{{ $t("건") }}</p>
        <ul><li v-for="row in list" :key="row.id">
          <button type="button" :disabled="busy" :aria-pressed="item?.id===row.id" @click="open(row.id)">
            <strong>{{ row.name }}</strong><small>{{ [gameName(row.gameCode),row.number || row.code,row.rarity,kind==='cards'?statusName[row.status]:null].filter(Boolean).join(' · ') }}</small>
          </button>
        </li></ul>
        <nav v-if="total>pageSize" class="pagination" :aria-label="$t('도감 관리 목록 페이지')">
          <button type="button" class="secondary" :disabled="!page" @click="page--">{{ $t("이전") }}</button><span>{{ page+1 }} / {{ Math.ceil(total/pageSize) }}</span>
          <button type="button" class="secondary" :disabled="(page+1)*pageSize>=total" @click="page++">{{ $t("다음") }}</button>
        </nav>
      </template>
    </section>
    <div ref="editorElement" class="catalog-detail" tabindex="-1">
      <p v-if="detailError" class="inline-error" role="alert">{{ detailError }}</p>
      <p v-if="loadingItem" role="status">{{ $t("상세 정보를 불러오는 중입니다.") }}</p>
      <template v-if="editing">
        <AdminCatalogEditor :kind="kind" :item="item" :seed="seed" :games="games" :busy="busy || loadingItem" :notice="notice"
          @saved="saved" @dirty="formDirty=$event" @busy="saving=$event" @dismiss="dismiss" @reload="open(item.id)" @add-card="create" />
        <AdminCardImage v-if="kind==='cards' && item?.status==='PUBLISHED'" :key="item.id" :card="item" :jobs="jobs" :disabled="saving || loadingItem" @job="rememberJob" @busy="uploading=$event" />
        <p v-else-if="kind==='cards' && (!item || item.status==='PENDING')" class="muted">{{ $t("카드를 공개 상태로 저장하면 이미지를 등록할 수 있습니다.") }}</p>
      </template>
      <p v-else-if="!loadingItem && !detailError" class="state">{{ $t("목록에서 항목을 선택하거나 새로 추가해 주세요.") }}</p>
    </div>
  </div>
</template>
