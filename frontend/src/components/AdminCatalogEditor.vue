<script setup>
import { t as uiText, gameName } from '../i18n'

import { computed, ref, watch } from 'vue'
import { useSession } from '../stores/session'
import AdminPackSelect from './AdminPackSelect.vue'
const props = defineProps({kind:{type:String,required:true},item:Object,seed:Object,games:{type:Array,required:true},busy:Boolean,notice:String})
const emit = defineEmits(['saved','dirty','busy','reload','add-card','dismiss'])
const session = useSession()
const card = computed(()=>props.kind==='cards')
const readonly = computed(()=>props.item && (!props.item.editable || (card.value && props.item.status==='REJECTED')))
const form = ref({}), baseline = ref(''), error = ref(''), conflict = ref(false), sending = ref(false)
const locked = computed(()=>props.busy || sending.value)
watch([()=>props.item,()=>props.seed,()=>props.kind],()=>{
  const value=props.item || props.seed || {}
  form.value={
    gameCode:value.gameCode || '',name:value.name || '',code:value.code || '',releaseDate:value.releaseDate || '',
    releaseLabel:value.releaseLabel || '',originalName:value.originalName || '',number:value.number || '',
    rarity:value.rarity || '',effect:value.effect || '',packId:value.packId ?? null,packName:value.packName || '',
    status:value.status || 'PENDING',jsonText:JSON.stringify((card.value?value.specs:value.metadata) || {},null,2),
  }
  baseline.value=JSON.stringify(form.value);error.value='';conflict.value=false
},{immediate:true})
const dirty = computed(()=>JSON.stringify(form.value)!==baseline.value)
watch(dirty,flag=>emit('dirty',flag),{immediate:true,flush:'sync'})
function changeGame(e) {
  form.value.gameCode=e.target.value;form.value.packId=null;form.value.packName=''
}
function selectPack(id,name) { form.value.packId=id;form.value.packName=name }
const statusOnly=computed(()=>card.value && !!props.item && !props.item.editable && props.item.status !== 'REJECTED')
function metadataBody() {
  const f=form.value
  let details
  try {
    details=JSON.parse(f.jsonText)
    if (!details || Array.isArray(details) || typeof details!=='object') throw new Error()
  } catch { throw new Error(uiText("상세 데이터는 중괄호로 감싼 올바른 JSON 객체여야 합니다.")) }
  if (new TextEncoder().encode(JSON.stringify(details)).length>16384) throw new Error(uiText("JSON 데이터는 16 KiB 이하로 입력해 주세요."))
  if (!f.name.trim() || !f.gameCode) throw new Error(uiText("게임과 이름을 입력해 주세요."))
  const optional = str => str.trim() || null
  const body={gameCode:f.gameCode,name:f.name.trim(),releaseDate:f.releaseDate || null}
  if (card.value) Object.assign(body,{packId:f.packId,originalName:optional(f.originalName),number:optional(f.number),
    rarity:optional(f.rarity),effect:optional(f.effect),specs:details,status:f.status})
  else Object.assign(body,{code:optional(f.code),releaseLabel:optional(f.releaseLabel),metadata:details})
  if (props.item) body.version=props.item.version
  return body
}
async function save(onlyStatus=false) {
  if (locked.value || (readonly.value && !(onlyStatus && statusOnly.value))) return
  error.value=''
  const path='/catalog/'+props.kind+(props.item?'/'+props.item.id:'')+(onlyStatus?'/status':'')
  sending.value=true;emit('busy',true)
  try {
    const body=onlyStatus?{version:props.item.version,status:form.value.status}:metadataBody()
    const result=await session.adminRequest(path,{method:props.item?'PUT':'POST',body})
    emit('dirty',false);emit('saved',result)
  } catch (cause) {
    conflict.value=cause.status===409
    error.value=conflict.value?uiText("저장 중 다른 변경과 충돌했습니다. 입력한 내용은 이 화면에 남아 있습니다."):cause.message
  } finally { sending.value=false;emit('busy',false) }
}
</script>
<template>
  <section class="ops-card catalog-editor">
    <div class="ops-heading"><h3>{{ item?.name || (card?$t("새 카드"):$t("새 팩")) }}</h3>
      <button class="text-button" type="button" :disabled="locked" @click="$emit('dismiss')">{{ $t("목록으로") }}</button></div>
    <p v-if="readonly" class="muted">{{ item.editable?$t("반려된 카드입니다."):$t("수집·이관된 항목의 메타데이터입니다.") }} {{ $t("읽기 전용입니다.") }}</p>
    <form @submit.prevent="save(false)">
      <fieldset :disabled="!!readonly || locked"><div class="catalog-fields">
        <label>{{ $t("게임") }}<select required :value="form.gameCode" :disabled="!!item" @change="changeGame">
          <option value="" disabled>{{ $t("게임 선택") }}</option><option v-for="g in games" :value="g.code" :key="g.code">{{ gameName(g.code,g.name) }}</option>
        </select></label>
        <label>{{ card?$t("카드명"):$t("팩명") }}<input v-model="form.name" required maxlength="320" /></label>
        <template v-if="card">
          <label>{{ $t("원문 카드명") }}<input v-model="form.originalName" maxlength="320" /></label>
          <label>{{ $t("카드 번호") }}<input v-model="form.number" maxlength="128" /></label>
          <label>{{ $t("레어도") }}<input v-model="form.rarity" maxlength="128" /></label>
        </template>
        <template v-else>
          <label>{{ $t("팩 코드") }}<input v-model="form.code" maxlength="96" /></label>
          <label>{{ $t("발매일 표기") }}<input v-model="form.releaseLabel" maxlength="200" :placeholder="$t('예: 2026년 겨울 예정')" /></label>
        </template>
        <label>{{ $t("발매일") }}<input v-model="form.releaseDate" type="date" /></label>
      </div>
      <template v-if="card">
        <label v-if="readonly">{{ $t("수록 팩") }}<input :value="form.packName || $t('팩 없음')" readonly /></label>
        <AdminPackSelect v-else :game="form.gameCode" :pack-id="form.packId" :pack-name="form.packName" @select="selectPack" />
        <label>{{ $t("카드 효과") }}<textarea v-model="form.effect" rows="3" maxlength="8000"></textarea></label>
      </template>
      <label>{{ card?$t("게임별 상세 스펙 (JSON)"):$t("팩 메타데이터 (JSON)") }}
        <textarea class="catalog-json" v-model="form.jsonText" rows="4" spellcheck="false"></textarea></label>
      <label v-if="card && !statusOnly">{{ $t("공개 상태") }}<select v-model="form.status">
        <option value="PENDING">{{ $t("검수 대기 · 비공개") }}</option><option value="PUBLISHED">{{ $t("공개") }}</option>
        <option v-if="form.status==='REJECTED'" value="REJECTED">{{ $t("반려") }}</option>
      </select></label>
      <p v-else-if="!item" class="muted">{{ $t("저장한 팩은 도감의 팩 목록에 표시됩니다.") }}</p>
      <div v-if="!readonly" class="catalog-savebar">
        <button type="submit" class="primary" :disabled="conflict || (!!item && !dirty)">{{ sending?$t("저장 중…"):(card?$t("카드 저장"):$t("팩 저장")) }}</button>
        <span role="status" :class="dirty?'muted':'success-message'">{{ dirty?$t("저장되지 않은 변경"):notice }}</span>
      </div></fieldset>
    </form>
    <form v-if="statusOnly" @submit.prevent="save(true)">
      <label>{{ $t("공개 상태") }}<select v-model="form.status" :disabled="locked"><option value="PENDING">{{ $t("검수 대기 · 비공개") }}</option><option value="PUBLISHED">{{ $t("공개") }}</option></select></label>
      <div class="catalog-savebar"><button class="primary" :disabled="locked || conflict || form.status===item.status">{{ sending?$t("저장 중…"):$t("상태 저장") }}</button>
        <span role="status" :class="dirty?'muted':'success-message'">{{ dirty?$t("저장되지 않은 변경"):notice }}</span></div>
    </form>
    <p v-if="error" role="alert" class="inline-error">{{ error }}
      <button v-if="conflict" class="text-button" @click="$emit('reload')">{{ $t("서버의 최신 내용 열기") }}</button></p>
    <button v-if="!card && item" type="button" class="secondary" :disabled="locked" @click="$emit('add-card',item)">{{ $t("이 팩에 카드 추가") }}</button>
  </section>
</template>
