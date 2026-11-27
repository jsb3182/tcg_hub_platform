<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { locale, t } from '../i18n'
import { useSession } from '../stores/session'
import { saveDocument } from '../savePng'

const words={
  '내 일정':['My calendar','自分の予定'], '일정 제목':['Event title','予定名'], '시작':['Starts','開始'],
  '종료 (선택)':['Ends (optional)','終了（任意）'], '기기 알림':['Device reminder','端末の通知'],
  '알림 없음':['No reminder','通知なし'], '시작할 때':['At the start','開始時'], '15분 전':['15 minutes before','15分前'],
  '1시간 전':['1 hour before','1時間前'], '하루 전':['1 day before','1日前'], '일정 추가':['Add event','予定を追加'],
  '일정 저장':['Save event','予定を保存'], '캘린더로 내보내기':['Export to calendar','カレンダーに書き出す'],
  '로그인하면 내 일정과 알림을 등록할 수 있습니다.':['Sign in to save your events and reminders.','ログインすると、自分の予定と通知を登録できます。'],
  '등록된 일정이 없습니다.':['No events saved.','登録された予定はありません。'],
  '내보낸 ICS 파일을 기기 캘린더에서 가져오면 알림이 설정됩니다.':['Import the ICS file into your calendar to enable its reminder.','書き出したICSファイルを端末のカレンダーに読み込むと、通知を設定できます。'],
  '종료 시간을 시작 시간 이후로 입력하세요.':['Choose an end time after the start.','終了時刻は開始時刻より後にしてください。'],
  '일정을 저장했습니다.':['Event saved.','予定を保存しました。'],'일정을 삭제했습니다.':['Event deleted.','予定を削除しました。'],
  '파일 저장을 완료하지 못했습니다.':['The file was not saved.','ファイルを保存できませんでした。'],
  '이 일정을 삭제할까요?':['Delete this event?','この予定を削除しますか？'],
}
function label(key){return locale.value==='ko'?key:words[key]?.[locale.value==='en'?0:1]??t(key)}
const session=useSession(),route=useRoute()
const open=ref(route.hash==='#personal-calendar'), editing=ref(false), busy=ref(false), loading=ref(false)
const title=ref(''), start=ref(''), end=ref(''), reminder=ref(''), page=ref(0), revision=ref(0)
const events=ref([]), more=ref(false), error=ref(''), notice=ref(''), removing=ref(null)
const account=computed(()=>session.account?.email)
const next=computed(()=>route.fullPath.split('#')[0]+'#personal-calendar')
const choices=[['','알림 없음'],['0','시작할 때'],['15','15분 전'],['60','1시간 전'],['1440','하루 전']]
function date(value){return new Intl.DateTimeFormat(locale.value,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))}
watch(account,()=>{editing.value=false; title.value=start.value=end.value=reminder.value='';notice.value='';page.value=0})
watch([open,account,page,revision],async ([active,email,n],_,cleanup)=>{
  events.value=[]; more.value=false; error.value='';removing.value=null;loading.value=false
  if(!active || !email)return
  const controller=new AbortController();cleanup(()=>controller.abort());loading.value=true
  try{
    const result=await session.authenticatedRequest('/me/calendar?page='+n+'&size=10',{signal:controller.signal})
    if(!controller.signal.aborted){events.value=result.items;more.value=result.hasMore}
  }catch(e){if(!controller.signal.aborted)error.value=e.message}
  finally{if(!controller.signal.aborted)loading.value=false}
},{immediate:true})
async function action(work){
  if(busy.value || !account.value)return
  const email=account.value;error.value=notice.value='';busy.value=true
  try{await work(()=>account.value===email)}
  catch(e){if(account.value===email)error.value=e.message}
  finally{busy.value=false}
}
function create(){return action(async current=>{
  const from=new Date(start.value),until=end.value?new Date(end.value):null
  if(!Number.isFinite(from.getTime()) || (until && !(until>from))){error.value=label('종료 시간을 시작 시간 이후로 입력하세요.');return}
  await session.authenticatedRequest('/me/calendar',{method:'POST',body:{title:title.value.trim(),startsAt:from.toISOString(),
    endsAt:until?.toISOString()??null,reminderMinutes:reminder.value===''?null:Number(reminder.value)}})
  if(current()){editing.value=false;title.value=start.value=end.value=reminder.value='';notice.value=label('일정을 저장했습니다.');page.value=0;revision.value++}
})}
function remove(item){return action(async current=>{
  await session.authenticatedRequest('/me/calendar/'+item.id,{method:'DELETE'})
  if(current()){if(events.value.length===1&&page.value>0)page.value--;revision.value++;notice.value=label('일정을 삭제했습니다.')}
})}
function download(item){return action(async current=>{
  const blob=await session.authenticatedRequest('/me/calendar/'+item.id+'.ics',{calendarFile:true})
  if(current()){
    try{await saveDocument(blob,'TCG-'+item.id+'.ics')}
    catch{throw Error(label('파일 저장을 완료하지 못했습니다.'))}
  }
})}
</script>

<template>
  <details id="personal-calendar" class="personal-calendar" :open="open" @toggle="open=$event.target.open">
    <summary>{{ label('내 일정') }}</summary>
    <div v-if="open" class="calendar-body">
      <p v-if="!session.ready" role="status">{{ $t('불러오는 중…') }}</p>
      <template v-else-if="!account">
        <p>{{ label('로그인하면 내 일정과 알림을 등록할 수 있습니다.') }}</p>
        <RouterLink :to="{name:'login',query:{next}}">{{ $t('로그인') }}</RouterLink>
      </template>
      <template v-else>
        <button v-if="!editing" type="button" class="secondary" @click="editing=true">{{ label('일정 추가') }}</button>
        <form v-else @submit.prevent="create">
          <label>{{ label('일정 제목') }}<input v-model="title" type="text" required maxlength="160" autocomplete="off"></label>
          <div class="when">
            <label>{{ label('시작') }}<input v-model="start" type="datetime-local" required></label>
            <label>{{ label('종료 (선택)') }}<input v-model="end" type="datetime-local" :min="start || undefined"></label>
            <label>{{ label('기기 알림') }}<select v-model="reminder"><option v-for="[value,text] in choices" :key="value" :value="value">{{ label(text) }}</option></select></label>
          </div>
          <div class="buttons"><button class="primary" :disabled="busy || !title.trim()">{{ label('일정 저장') }}</button>
            <button class="secondary" type="button" :disabled="busy" @click="editing=false">{{ $t('취소') }}</button></div>
        </form>
        <p v-if="loading" role="status">{{ $t('불러오는 중…') }}</p>
        <p v-else-if="!events.length && !error">{{ label('등록된 일정이 없습니다.') }}</p>
        <ul v-else-if="events.length">
          <li v-for="item in events" :key="item.id">
            <strong>{{ item.title }}</strong>
            <span><time :datetime="item.startsAt">{{ date(item.startsAt) }}</time><template v-if="item.endsAt"> – <time :datetime="item.endsAt">{{ date(item.endsAt) }}</time></template></span>
            <span v-if="item.reminders.length">{{ label('기기 알림') }} · {{ item.reminders.map(date).join(', ') }}</span>
            <div v-if="removing===item.id" class="buttons"><span>{{ label('이 일정을 삭제할까요?') }}</span>
              <button type="button" class="secondary" :disabled="busy" @click="remove(item)">{{ $t('삭제') }}</button>
              <button type="button" class="text-button" @click="removing=null">{{ $t('취소') }}</button></div>
            <div v-else class="buttons"><button type="button" class="secondary" :disabled="busy" @click="download(item)">{{ label('캘린더로 내보내기') }}</button>
              <button type="button" class="text-button" :disabled="busy" @click="removing=item.id">{{ $t('삭제') }}</button></div>
          </li>
        </ul>
        <p v-if="events.some(e=>e.reminders.length)">{{ label('내보낸 ICS 파일을 기기 캘린더에서 가져오면 알림이 설정됩니다.') }}</p>
        <div v-if="page>0 || more" class="buttons">
          <button type="button" class="secondary" :disabled="page===0||busy" @click="page--">{{ $t('이전') }}</button>
          <button type="button" class="secondary" :disabled="!more||busy" @click="page++">{{ $t('다음') }}</button>
        </div>
        <p v-if="error" class="inline-error" role="alert">{{ error }} <button type="button" class="text-button" @click="revision++">{{ $t('다시 시도') }}</button></p>
        <p v-if="notice" role="status">{{ notice }}</p>
      </template>
    </div>
  </details>
</template>

<style scoped>
.personal-calendar { border-block:1px solid var(--bd);margin-block:1rem;scroll-margin-top:5rem }
summary { display:flex;align-items:center;justify-content:space-between;min-height:48px;cursor:pointer;font-weight:700 }
summary::after { content:'+';font-size:1.2rem;color:var(--mu) }
[open]>summary::after { content:'−' }
.calendar-body { padding-block:0 1rem;max-width:52rem }
.calendar-body>p { color:var(--mu);margin:.65rem 0 }
.calendar-body .inline-error { color:var(--wa) }
.calendar-body ul { padding:0;margin:.75rem 0;list-style:none }
.calendar-body li { display:grid;gap:.3rem;border-top:1px solid var(--bd);padding-block:.8rem;overflow-wrap:anywhere }
.when { display:grid;gap:.6rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,12rem),1fr)) }
.when label,.when input,.when select { min-width:0;max-width:100% }
.buttons { display:flex;flex-wrap:wrap;align-items:center;gap:.75rem }
.calendar-body button,.calendar-body a { min-height:44px }
.calendar-body a { display:inline-flex;align-items:center }
</style>
