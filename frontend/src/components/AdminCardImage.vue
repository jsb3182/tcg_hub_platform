<script setup>
import { t as uiText } from '../i18n'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { mediaPath } from '../api'
import { useSession } from '../stores/session'
import CardCropper from './CardCropper.vue'

const props = defineProps({card:{type:Object,required:true},jobs:{type:Object,required:true}, disabled:Boolean})
const emit = defineEmits(['job','busy'])
const session = useSession()
const variants = ref([]), selected = ref(null), error = ref(''), loading = ref(false), sending = ref(false)
const statusError = ref(''), checking = ref(false)
const current = computed(() => variants.value.find(v => v.id === selected.value))
const job = computed(() => props.jobs[selected.value])
const statusLabels = { PENDING:uiText("시트 생성 대기"), DONE:uiText("시트 반영 완료"), FAILED:uiText("시트 생성 실패") }
let artController, statusController, timer, delay = 2000
let mounted = true

const tileStyle = computed(() => {
  const image = current.value?.image, url = mediaPath(image?.url)
  if (!url) return null
  return {backgroundImage:'url("'+url.replace(/"/g,'%22')+'")',
    aspectRatio:image.cellWidth+' / '+image.cellHeight,
    backgroundPosition:(image.col*100/3)+'% '+(image.row*50)+'%'}
})
async function loadImages() {
  artController?.abort()
  const controller = artController = new AbortController()
  loading.value = true
  error.value = ''
  try {
    const detail = await session.authenticatedRequest('/cards/'+props.card.id,{signal:controller.signal})
    if (controller.signal.aborted) return
    variants.value = detail.variants
    if (!variants.value.some(v => v.id === selected.value)) {
      selected.value = variants.value.find(v => v.id === props.card.variantId)?.id ?? variants.value[0]?.id ?? null
    }
  } catch (cause) { if (!controller.signal.aborted) error.value = cause.message }
  finally { if (!controller.signal.aborted) loading.value = false }
}
function stopPoll() {
  clearTimeout(timer)
  statusController?.abort()
  checking.value = false
}
function schedule() {
  clearTimeout(timer)
  if (job.value?.status === 'PENDING' && !document.hidden) timer = setTimeout(poll,delay)
}
async function poll() {
  if (!job.value || checking.value) return
  const id = job.value.id
  const controller = statusController = new AbortController()
  checking.value = true
  statusError.value = ''
  try {
    const fresh = await session.adminRequest('/media-jobs/'+id,{signal:controller.signal})
    if (controller.signal.aborted || selected.value !== fresh.variantId || job.value?.id !== id) return
    emit('job',fresh)
    if (fresh.status === 'DONE') await loadImages()
  } catch (cause) { if (!controller.signal.aborted) statusError.value = cause.message }
  finally {
    if (!controller.signal.aborted) {
      checking.value = false
      delay = Math.min(30000,delay*2)
      schedule()
    }
  }
}
function visibility() {
  if (document.hidden) clearTimeout(timer)
  else if (job.value?.status === 'PENDING') poll()
}
watch([selected,()=>job.value?.id,()=>job.value?.status], () => {
  stopPoll(); delay = 2000; statusError.value = ''
  schedule()
})
async function upload(blob) {
  if (!selected.value || sending.value || props.disabled || job.value?.status === 'PENDING') return
  const form = new FormData()
  form.append('file',blob,'crop.png')
  sending.value = true
  emit('busy',true)
  error.value = ''
  try {
    const result = await session.adminRequest('/variants/'+selected.value+'/image',{method:'POST',body:form})
    if (!mounted) return
    emit('job',result)
    if (result.status === 'DONE') await loadImages()
  } catch (cause) {
    if (mounted) error.value = cause.status === 409 ? uiText("카드가 공개 상태인지 확인한 뒤 다시 시도해 주세요.") : cause.message
  } finally { if (mounted) { sending.value = false; emit('busy',false) } }
}
onMounted(() => { loadImages(); document.addEventListener('visibilitychange',visibility) })
onBeforeUnmount(() => {
  mounted = false; artController?.abort(); stopPoll()
  emit('busy',false)
  document.removeEventListener('visibilitychange',visibility)
})
</script>
<template>
  <section class="ops-card catalog-image"><h3>{{ $t("카드 이미지") }}</h3>
    <p v-if="loading" role="status">{{ $t("일러스트를 불러오는 중입니다.") }}</p>
    <p v-if="error" role="alert" class="inline-error">{{ error }} <button class="text-button" @click="loadImages">{{ $t("다시 확인") }}</button></p>
    <label v-if="variants.length">{{ $t("일러스트 선택") }}
      <select v-model="selected" :disabled="sending"><option v-for="(v,i) in variants" :key="v.id" :value="v.id">{{ i+1 }}{{ $t("번") }}{{ v.rarity?' · '+v.rarity:'' }}</option></select>
    </label>
    <template v-if="current">
      <div v-if="tileStyle" class="current-art"><div class="catalog-tile" :style="tileStyle" role="img" :aria-label="card.name+$t(' 등록 이미지')"></div>
        <p>{{ $t("현재 등록 이미지") }}<br /><small>{{ $t("시트") }} {{ current.image.sheetId }} · {{ current.image.col+1 }}{{ $t("열") }} {{ current.image.row+1 }}{{ $t("행") }}</small></p></div>
      <p v-else class="muted">{{ $t("등록된 이미지가 없습니다.") }}</p>
      <CardCropper :key="selected" :disabled="disabled || sending || job?.status==='PENDING'" @upload="upload" />
      <p v-if="sending" role="status">{{ $t("자른 이미지를 전송하고 있습니다.") }}</p>
      <div v-if="job" class="catalog-job"><p role="status">{{ $t("작업 #") }}{{ job.id }} · {{ statusLabels[job.status] || job.status }}</p>
        <p v-if="job.error" class="inline-error">{{ job.error }}</p>
        <button v-if="job.status==='PENDING'" class="secondary" :disabled="checking" @click="poll">{{ $t("처리 상태 확인") }}</button>
      </div>
      <p v-if="statusError" role="alert" class="inline-error">{{ statusError }}</p>
    </template>
    <p v-else-if="!loading && !error">{{ $t("이미지를 연결할 일러스트가 없습니다.") }}</p>
  </section>
</template>
