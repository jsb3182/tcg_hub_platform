<script setup>
import { locale } from '../i18n'
import { ref, watch } from 'vue'
import { request } from '../api'
import LibraryThumbnail from './LibraryThumbnail.vue'
const props = defineProps({ game: { type: String, default: '' }, disabled: Boolean })
defineEmits(['pick'])
const query = ref(''), page = ref(0), items = ref([]), total = ref(0), loading = ref(false), error = ref(''), retry = ref(0)
watch([query, () => props.game], () => { page.value = 0 }, {flush:'sync'})
watch([query, page, () => props.game, retry, locale], (_, __, cleanup) => {
  const controller = new AbortController()
  loading.value = true
  error.value = ''
  const timer = setTimeout(async () => {
    const params = new URLSearchParams({ game: props.game, q:query.value.trim(), page:page.value, size:8, lang:locale.value })
    try {
      const result = await request('/cards?' + params, {signal:controller.signal})
      if (!controller.signal.aborted) { items.value = result.items; total.value = result.total }
    } catch (cause) { if (!controller.signal.aborted) error.value = cause.message }
    finally { if (!controller.signal.aborted) loading.value = false }
  }, query.value ? 180 : 0)
  cleanup(() => { clearTimeout(timer); controller.abort() })
}, {immediate:true})
</script>
<template>
  <section class="lib-panel" :aria-label="$t('도감에서 카드 추가')">
    <h2>{{ $t("도감에서 카드 추가") }}</h2>
    <label>{{ $t("카드 이름·번호") }}<input v-model="query" type="search" maxlength="120" :placeholder="$t('카드 검색')" /></label>
    <p v-if="loading" role="status">{{ $t("검색 중…") }}</p>
    <p v-else-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ $t("다시 시도") }}</button></p>
    <p v-else-if="!items.length">{{ $t("검색 결과가 없습니다.") }}</p>
    <ul v-else class="lib-list">
      <li v-for="card in items" :key="card.id">
        <div class="lib-print"><LibraryThumbnail :image="card.image" :src="card.imageUrl" /><div><strong :lang="card.language || locale">{{ card.name }}</strong><small>{{ [card.number,card.packName,card.rarity].filter(Boolean).join(' · ') }}</small></div></div>
        <button type="button" class="secondary" :aria-label="card.name + $t(' 추가')" :disabled="disabled" @click="$emit('pick',card,$event.currentTarget)">{{ $t("추가") }}</button>
      </li>
    </ul>
    <nav v-if="total > 8" class="pagination" :aria-label="$t('도감 검색 페이지')">
      <button class="secondary" :disabled="!page || loading" @click="page--">{{ $t("이전") }}</button>
      <span>{{ page + 1 }} / {{ Math.ceil(total / 8) }}</span>
      <button class="secondary" :disabled="(page+1)*8>=total || loading" @click="page++">{{ $t("다음") }}</button>
    </nav>
  </section>
</template>
