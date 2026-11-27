<script setup>
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {useSession} from '../stores/session'
import {dateTime} from '../presentation'
import {pt} from '../pack'

const session=useSession(),open=ref(false),status=ref('OPEN'),page=ref(0),retry=ref(0)
const reports=ref([]),total=ref(0),loading=ref(false),saving=ref(false)
const candidate=ref(null),notice=ref(''),error=ref('')
const filters={OPEN:'검토 대기',RESOLVED:'숨김 처리',DISMISSED:'공개 유지'}
const size=20,pages=computed(()=>Math.max(1,Math.ceil(total.value/size)))
let alive=true
onBeforeUnmount(()=>{alive=false})
watch(status,()=>{page.value=0},{flush:'sync'})
watch([open,status,page,retry],async([visible,state,index],_,cleanup)=>{
  candidate.value=null;error.value=''
  if(!visible)return
  const controller=new AbortController();cleanup(()=>controller.abort())
  loading.value=true;reports.value=[]
  try{
    const result=await session.adminRequest('/community/reports?'+new URLSearchParams({status:state,page:index,size}),{signal:controller.signal})
    if(controller.signal.aborted)return
    total.value=result.total
    if(!result.items.length && index>0 && index>=pages.value){page.value=pages.value-1;return}
    reports.value=result.items
  }catch(e){if(!controller.signal.aborted)error.value=e.message}
  finally{if(!controller.signal.aborted)loading.value=false}
})
function choose(row,next){
  notice.value='';error.value='';candidate.value={id:row.id,next}
}
async function decide(){
  if(!candidate.value || saving.value)return
  const {id,next}=candidate.value
  saving.value=true;error.value=''
  try{
    await session.adminRequest('/community/reports/'+id,{method:'PATCH',body:{status:next}})
    if(alive){notice.value=next==='RESOLVED'?'신고 대상을 숨겼습니다.':'공개 상태를 유지했습니다.';retry.value++}
  }catch(e){if(alive)error.value=e.message}
  finally{if(alive)saving.value=false}
}
</script>
<template>
  <details class="community-reports" @toggle="open=$event.currentTarget.open">
    <summary>{{ pt('커뮤니티 신고') }}</summary>
    <template v-if="open">
      <div class="report-tools"><label>{{ pt('처리 상태') }} <select v-model="status" :disabled="saving" @change="notice=''"><option v-for="(label,key) in filters" :key="key" :value="key">{{ pt(label) }}</option></select></label>
        <button type="button" class="text-button" :disabled="loading||saving" @click="retry++">{{ pt('새로고침') }}</button></div>
      <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
      <p v-if="notice" role="status">{{ pt(notice) }}</p>
      <p v-if="loading" role="status">{{ pt('불러오는 중…') }}</p>
      <p v-else-if="!reports.length&&!error">{{ pt('해당 상태의 신고가 없습니다.') }}</p>
      <ul v-else class="report-list"><li v-for="row in reports" :key="row.id">
        <div class="report-meta">{{ pt(row.commentId?'댓글 신고':'게시글 신고') }} · <time :datetime="row.createdAt">{{ dateTime(row.createdAt) }}</time></div>
        <h3><RouterLink v-if="row.status!=='RESOLVED'||row.commentId" :to="{name:'community',params:{id:row.postId}}">{{ row.title }}</RouterLink><template v-else>{{ row.title }}</template></h3><p v-if="row.excerpt" class="report-excerpt">{{ row.excerpt }}</p>
        <p><strong>{{ pt('신고 사유') }}</strong> {{ row.reason }}</p>
        <template v-if="row.status==='OPEN'">
          <div v-if="candidate?.id===row.id" class="report-confirm">
            <p>{{ pt(candidate.next==='RESOLVED'?(row.commentId?'이 댓글과 답글을 숨길까요?':'이 게시글을 숨길까요?'):'공개 상태를 유지하고 신고를 종료할까요?') }}</p>
            <button type="button" class="primary" :disabled="saving" @click="decide">{{ pt('처리 확정') }}</button>
            <button type="button" class="secondary" :disabled="saving" @click="candidate=null">{{ pt('취소') }}</button>
          </div>
          <div v-else class="report-actions"><button type="button" class="secondary" :disabled="saving" @click="choose(row,'RESOLVED')">{{ pt('신고 대상 숨기기') }}</button>
            <button type="button" class="secondary" :disabled="saving" @click="choose(row,'DISMISSED')">{{ pt('공개 유지') }}</button></div>
        </template>
      </li></ul>
      <nav v-if="pages>1" class="pagination" :aria-label="pt('신고 페이지')">
        <button type="button" class="secondary" :disabled="loading||saving||!page" @click="page--">{{ pt('이전') }}</button><span>{{ page+1 }} / {{ pages }}</span>
        <button type="button" class="secondary" :disabled="loading||saving||page+1>=pages" @click="page++">{{ pt('다음') }}</button>
      </nav>
    </template>
  </details>
</template>
<style scoped>
.community-reports{border-block:1px solid var(--bd);margin:0 0 1.2rem}.community-reports summary{padding:.75rem 0;cursor:pointer;font-weight:650;min-height:44px}.report-tools,.report-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.report-tools{justify-content:space-between}.report-tools select{min-height:42px;background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:7px;padding-inline:.5rem}.report-list{padding:0;list-style:none}.report-list li{border-top:1px solid var(--bd);padding:.8rem 0;overflow-wrap:anywhere}.report-list h3,.report-list p{margin:.35rem 0}.report-meta,.report-excerpt{color:var(--mu);font-size:.85rem}.report-confirm button{margin:.2rem .4rem .15rem 0}
</style>
