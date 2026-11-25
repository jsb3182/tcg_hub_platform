<script setup>
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { checkCropSource } from '../cropSource'

const props = defineProps({ disabled: Boolean })
const emit = defineEmits(['upload'])
const width = 300, height = 438
const source = shallowRef(null)
const canvas = ref(null), zoom = ref(1), horizontal = ref(50), vertical = ref(50)
const error = ref(''), loading = ref(false)
let generation = 0
let objectUrl = ''
function clearSource() {
  generation++
  source.value = null
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  objectUrl = ''
}
onBeforeUnmount(clearSource)
function center() {
  zoom.value = 1
  horizontal.value = vertical.value = 50
}
async function choose(event) {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  clearSource()
  const current = generation
  loading.value = true
  error.value = ''
  try {
    await checkCropSource(file)
    if (current !== generation) return
    const image = new Image()
    objectUrl = URL.createObjectURL(file)
    image.src = objectUrl
    try { await image.decode() } catch { throw new Error('이미지를 읽을 수 없습니다. 다른 파일을 선택해 주세요.') }
    if (current !== generation) return
    if (image.naturalWidth * image.naturalHeight > 12000000) throw new Error('1,200만 픽셀 이하 이미지를 선택해 주세요.')
    center()
    source.value = image
    await nextTick()
    draw()
  } catch (cause) {
    if (current === generation) {
      error.value = cause.message
      URL.revokeObjectURL(objectUrl)
      objectUrl = ''
    }
  } finally { if (current === generation) loading.value = false }
}
const crop = computed(() => {
  if (!source.value) return null
  const {naturalWidth: w, naturalHeight: h} = source.value
  const scale = Math.max(width / w, height / h) * zoom.value
  const cropWidth = width / scale, cropHeight = height / scale
  return {x:(w-cropWidth)*horizontal.value/100, y:(h-cropHeight)*vertical.value/100,
    width:cropWidth, height:cropHeight, moveX:w-cropWidth>0.5, moveY:h-cropHeight>0.5}
})
function draw() {
  if (!canvas.value || !crop.value) return
  const context = canvas.value.getContext('2d')
  context.fillStyle = '#181818'
  context.fillRect(0,0,width,height)
  context.imageSmoothingQuality = 'high'
  const frame = crop.value
  context.drawImage(source.value,frame.x,frame.y,frame.width,frame.height,0,0,width,height)
}
watch(crop,draw,{flush:'post'})
async function upload() {
  if (!source.value || props.disabled || loading.value) return
  const current = generation
  loading.value = true
  try {
    draw()
    const blob = await new Promise(resolve => canvas.value.toBlob(resolve,'image/png'))
    if (!blob) throw new Error('이미지를 저장하지 못했습니다. 다시 시도해 주세요.')
    if (current === generation) emit('upload',blob)
  } catch (cause) { error.value = cause.message }
  finally { if (current === generation) loading.value = false }
}
</script>
<template>
  <fieldset class="catalog-cropper" :disabled="disabled || loading">
    <label>원본 이미지<input type="file" accept=".jpg,.jpeg,.png,.webp" @change="choose" /></label>
    <small>JPG·PNG·WebP, 최대 8 MiB · 1,200만 픽셀</small>
    <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
    <div v-if="source" class="crop-grid">
      <canvas ref="canvas" :width="width" :height="height" aria-label="저장될 카드 이미지 미리보기"></canvas>
      <div><p>저장 영역 300 × 438 px</p>
        <label>확대 {{ Number(zoom).toFixed(1) }}배<input v-model.number="zoom" type="range" min="1" max="4" step="0.05" /></label>
        <label>가로 위치 {{ horizontal }}%<input v-model.number="horizontal" type="range" min="0" max="100" :disabled="!crop.moveX" /></label>
        <label>세로 위치 {{ vertical }}%<input v-model.number="vertical" type="range" min="0" max="100" :disabled="!crop.moveY" /></label>
        <div class="ops-actions"><button type="button" class="secondary" @click="center">위치 초기화</button>
          <button type="button" class="primary" @click="upload">자른 이미지 등록</button></div>
      </div>
    </div>
  </fieldset>
</template>
