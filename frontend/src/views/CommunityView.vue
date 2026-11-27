<script setup>
import {computed,reactive,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {request} from '../api'
import {locale,gameName,t} from '../i18n'
import {useSession} from '../stores/session'

const route=useRoute(),router=useRouter(),session=useSession()
const boards={FREE:'자유게시판',SUGGESTION:'건의게시판',TRADE:'카드 거래'}
const types={SELL:'판매',BUY:'구매',EXCHANGE:'교환'},statuses={OPEN:'모집 중',RESERVED:'예약 중',CLOSED:'거래 완료'}
const board=computed(()=>Object.hasOwn(boards,route.query.board)?route.query.board:'FREE')
const id=computed(()=>route.params.id),page=ref(0),commentsPage=ref(0),reload=ref(0)
const list=ref(null),post=ref(null),comments=ref(null),error=ref(''),busy=ref(false),loading=ref(false)
const search=ref(''),trade=ref(''),stateFilter=ref(''),composing=ref(false),replyTo=ref(null),response=ref('')
const reporting=ref(null),reason=ref(''),notice=ref(''),writeError=ref('')
const cardSearch=ref(''),found=ref([]),lookupError=ref(''),looking=ref(false)
const draft=reactive({title:'',body:'',tradeType:'SELL',cards:[]})
const login=computed(()=>({name:'login',query:{next:route.fullPath}}))
function target(key,postId){
  return {name:'community',params:{id:postId||''},query:{board:key,...(route.query.lang?{lang:route.query.lang}:{})}}
}
function clearDraft(){Object.assign(draft,{title:'',body:'',tradeType:'SELL',cards:[]});cardSearch.value=''}
function formatDate(value){
  if (!value) return ''
  return new Intl.DateTimeFormat(locale.value,{year:'numeric',month:'short',day:'numeric'}).format(new Date(value))
}
function read(path,signal){return session.account?session.authenticatedRequest(path,{signal}):request(path,{signal})}
watch([board,id,()=>session.account?.email],()=>{
  page.value=0;commentsPage.value=0;composing.value=false;clearDraft();reporting.value=null;reason.value=''
  replyTo.value=null;response.value='';writeError.value='';notice.value='';search.value='';trade.value='';stateFilter.value=''
},{flush:'sync'})
watch([search,trade,stateFilter],()=>{page.value=0},{flush:'sync'})
watch([id,board,page,commentsPage,reload,()=>session.account?.email,search,trade,stateFilter],(_,__,cleanup)=>{
  const ctl=new AbortController();let timer
  cleanup(()=>{ctl.abort();clearTimeout(timer)})
  error.value='';loading.value=true
  if(id.value){list.value=null;if(String(post.value?.id)!==id.value)post.value=null;comments.value=null}
  else{list.value=null;post.value=null}
  timer=setTimeout(async()=>{
    try{
      if(id.value){
        const base='/community/posts/'+id.value
        const [current,replies]=await Promise.all([read(base,ctl.signal),read(base+'/comments?page='+commentsPage.value,ctl.signal)])
        if(!ctl.signal.aborted){post.value=current;comments.value=replies}
      }else{
        const query=new URLSearchParams({board:board.value,page:String(page.value),q:search.value.trim()})
        if(board.value==='TRADE'){
          if(trade.value)query.set('tradeType',trade.value)
          if(stateFilter.value)query.set('tradeStatus',stateFilter.value)
        }
        const result=await read('/community/posts?'+query,ctl.signal)
        if(!ctl.signal.aborted)list.value=result
      }
    }catch(e){if(!ctl.signal.aborted)error.value=e.message}
    finally{if(!ctl.signal.aborted)loading.value=false}
  },search.value?180:0)
},{immediate:true})
watch([cardSearch,composing,locale],([term,open],_,cleanup)=>{
  const ctl=new AbortController();let timer
  cleanup(()=>{ctl.abort();clearTimeout(timer)})
  found.value=[];lookupError.value='';looking.value=Boolean(term.trim()&&open)
  if(!looking.value)return
  timer=setTimeout(async()=>{
    try{
      const result=await request('/cards?'+new URLSearchParams({q:term.trim(),lang:locale.value,size:'8'}),{signal:ctl.signal})
      if(!ctl.signal.aborted)found.value=result.items
    }catch(e){if(!ctl.signal.aborted)lookupError.value=e.message}
    finally{if(!ctl.signal.aborted)looking.value=false}
  },220)
})
function addTag(card){if(draft.cards.length<12&&!draft.cards.some(c=>c.id===card.id))draft.cards.push(card);cardSearch.value=''}
async function mutate(action){
  if(busy.value)return
  busy.value=true;writeError.value='';notice.value=''
  try{await action()}catch(e){writeError.value=e.message}finally{busy.value=false}
}
function publish(){return mutate(async()=>{
  const created=await session.authenticatedRequest('/community/posts',{method:'POST',body:{
    board:board.value,title:draft.title.trim(),body:draft.body.trim(),cardIds:draft.cards.map(c=>c.id),
    ...(board.value==='TRADE'?{tradeType:draft.tradeType}:{})}})
  await router.push(target(board.value,created.id))
})}
function addComment(){return mutate(async()=>{
  await session.authenticatedRequest('/community/posts/'+id.value+'/comments',{method:'POST',body:{body:response.value.trim(),parentId:replyTo.value}})
  replyTo.value=null;response.value='';commentsPage.value=Math.floor((comments.value?.total||0)/(comments.value?.size||50))
  reload.value++;notice.value=t('댓글을 등록했습니다.')
})}
function tradeStatus(next){return mutate(async()=>{
  try {
    await session.authenticatedRequest('/community/posts/'+id.value+'/trade-status',{method:'PATCH',
      body:{tradeStatus:next,expectedTradeStatus:post.value.tradeStatus}})
  } finally { reload.value++ }
})}
function report(){return mutate(async()=>{
  await session.authenticatedRequest('/community/reports',{method:'POST',body:{...reporting.value,reason:reason.value.trim()}})
  reporting.value=null;reason.value='';notice.value=t('신고를 접수했습니다.')
})}
function openReport(target){reporting.value=target;reason.value='';writeError.value='';notice.value=''}
</script>
<template>
<section class="community">
  <header class="lib-heading"><h1>{{ $t('커뮤니티') }}</h1>
    <button v-if="!id && !composing && session.account" class="primary" @click="composing=true">{{ $t('글쓰기') }}</button>
    <RouterLink v-if="!id && !session.account" :to="login">{{ $t('로그인 후 글쓰기') }}</RouterLink>
  </header>
  <nav class="game-tabs" :aria-label="$t('게시판 선택')"><RouterLink v-for="(label,key) in boards" :key="key"
    :to="target(key)" :aria-current="(post?.board||board)===key?'page':undefined">{{ $t(label) }}</RouterLink></nav>
  <p v-if="error" role="alert">{{ error }} <button @click="reload++">{{ $t('다시 시도') }}</button></p>
  <p v-if="writeError" role="alert">{{ writeError }}</p><p v-if="notice" role="status">{{ notice }}</p>
  <template v-if="!id">
    <form v-if="composing && session.account" class="lib-panel form" @submit.prevent="publish">
      <h2>{{ $t(boards[board]) }} · {{ $t('글쓰기') }}</h2>
      <label v-if="board==='TRADE'">{{ $t('거래 방식') }}<select v-model="draft.tradeType"><option v-for="(v,k) in types" :key="k" :value="k">{{ $t(v) }}</option></select></label>
      <label>{{ $t('글 제목') }}<input v-model="draft.title" maxlength="120" required></label>
      <label>{{ $t('본문') }}<textarea v-model="draft.body" rows="6" maxlength="5000" required/></label>
      <label>{{ $t('도감 카드 태그') }}<input v-model="cardSearch" type="search" maxlength="120" :placeholder="$t('카드명 또는 번호')"></label>
      <div v-if="draft.cards.length" class="tags"><button v-for="c in draft.cards" :key="c.id" type="button"
        @click="draft.cards=draft.cards.filter(x=>x.id!==c.id)">{{ c.name }} ×</button></div>
      <div v-if="cardSearch.trim()" class="matches"><span v-if="lookupError" role="alert">{{ lookupError }}</span><span v-else-if="looking" role="status">{{ $t('불러오는 중…') }}</span>
        <button v-for="c in found" :key="c.id" type="button" :disabled="draft.cards.length>=12 || draft.cards.some(x=>x.id===c.id)" @click="addTag(c)">{{ gameName(c.gameCode) }} · {{ c.name }} · {{ c.number }}</button>
        <span v-if="!looking&&!lookupError&&!found.length">{{ $t('검색 결과가 없습니다.') }}</span></div>
      <div class="actions"><button class="secondary" type="button" @click="composing=false;clearDraft()">{{ $t('취소') }}</button>
        <button class="primary" :disabled="busy||!draft.title.trim()||!draft.body.trim()">{{ $t('등록') }}</button></div>
    </form>
    <div class="filters"><label>{{ $t('게시글 검색') }}<input type="search" v-model="search" maxlength="120"></label>
      <template v-if="board==='TRADE'"><label>{{ $t('거래 방식') }}<select v-model="trade"><option value="">{{ $t('전체') }}</option><option v-for="(v,k) in types" :value="k" :key="k">{{ $t(v) }}</option></select></label>
      <label>{{ $t('거래 상태') }}<select v-model="stateFilter"><option value="">{{ $t('전체') }}</option><option v-for="(v,k) in statuses" :value="k" :key="k">{{ $t(v) }}</option></select></label></template></div>
    <p v-if="loading" role="status">{{ $t('불러오는 중…') }}</p>
    <p v-else-if="list&&!list.total" class="state">{{ $t('표시할 게시글이 없습니다.') }}</p>
    <ul v-else-if="list" class="posts"><li v-for="p in list.items" :key="p.id"><RouterLink :to="target(p.board,p.id)">
      <small v-if="p.tradeType">{{ $t(types[p.tradeType]) }} · {{ $t(statuses[p.tradeStatus]) }}</small><strong>{{ p.title }}</strong>
      <span>{{ formatDate(p.createdAt) }} · {{ $t('댓글') }} {{ p.commentCount }}</span></RouterLink></li></ul>
    <nav v-if="list&&list.total>list.size" class="pagination"><button :disabled="!page" @click="page--">{{ $t('이전') }}</button><span>{{ page+1 }} / {{ Math.ceil(list.total/list.size) }}</span><button :disabled="(page+1)*list.size>=list.total" @click="page++">{{ $t('다음') }}</button></nav>
  </template>
  <template v-else>
    <RouterLink :to="target(post?.board||board)">← {{ $t('게시글 목록') }}</RouterLink>
    <p v-if="loading&&!post" role="status">{{ $t('불러오는 중…') }}</p>
    <article v-if="post" class="lib-panel detail"><small>{{ $t(boards[post.board]) }} · {{ formatDate(post.createdAt) }}</small><h2>{{ post.title }}</h2>
      <p v-if="post.tradeType">{{ $t(types[post.tradeType]) }} · {{ $t(statuses[post.tradeStatus]) }}</p>
      <p class="body">{{ post.body }}</p>
      <div v-if="post.cards?.length" class="tags"><RouterLink v-for="c in post.cards" :key="c.id" :to="{name:'card',params:{id:c.id},query:{lang:locale}}">{{ c.name }} · {{ c.number }}</RouterLink></div>
      <label v-if="post.mine && post.tradeType">{{ $t('거래 상태') }}<select :value="post.tradeStatus" :disabled="busy" @change="tradeStatus($event.target.value)"><option v-for="(v,k) in statuses" :value="k" :key="k">{{ $t(v) }}</option></select></label>
      <button v-if="session.account&&!post.mine" class="text-button" @click="openReport({postId:post.id})">{{ $t('신고') }}</button>
    </article>
    <section v-if="post && comments" class="replies"><h2>{{ $t('댓글') }} {{ comments.total }}</h2>
      <ol class="posts"><li v-for="c in comments.items" :key="c.id" :class="{nested:c.parentId}"><small v-if="c.parentId">↳ {{ $t('답글') }} #{{ c.parentId }}</small>
        <p class="body">{{ c.body }}</p><small>#{{ c.id }} · {{ formatDate(c.createdAt) }}</small>
        <button v-if="session.account&&!c.parentId" class="text-button" @click="replyTo=c.id">{{ $t('답글 쓰기') }}</button>
        <button v-if="session.account&&!c.mine" class="text-button" @click="openReport({commentId:c.id})">{{ $t('신고') }}</button></li></ol>
      <nav v-if="comments.total>comments.size" class="pagination"><button :disabled="!commentsPage" @click="commentsPage--">{{ $t('이전') }}</button><span>{{ commentsPage+1 }} / {{ Math.ceil(comments.total/comments.size) }}</span><button :disabled="(commentsPage+1)*comments.size>=comments.total" @click="commentsPage++">{{ $t('다음') }}</button></nav>
      <form v-if="session.account" class="form" @submit.prevent="addComment"><label>{{ $t(replyTo?'답글':'댓글') }} {{ replyTo?'#'+replyTo:'' }}<textarea v-model="response" maxlength="1200" required rows="2"/></label>
        <div class="actions"><button v-if="replyTo" class="secondary" type="button" @click="replyTo=null">{{ $t('취소') }}</button><button class="primary" :disabled="busy||!response.trim()">{{ $t('댓글 등록') }}</button></div></form>
      <RouterLink v-else :to="login">{{ $t('로그인 후 댓글 쓰기') }}</RouterLink>
    </section>
    <form v-if="reporting && session.account" class="lib-panel form" @submit.prevent="report"><label>{{ $t('신고 사유') }}<textarea v-model="reason" required maxlength="500" rows="3" autofocus/></label>
      <div class="actions"><button type="button" class="secondary" @click="reporting=null">{{ $t('취소') }}</button><button class="primary" :disabled="busy||!reason.trim()">{{ $t('신고 접수') }}</button></div></form>
  </template>
</section>
</template>
<style scoped>
.community{width:min(100%,52rem);margin-inline:auto;display:grid;gap:1rem;min-width:0}.community :is(h1,h2,p){margin-block:.35rem}.community h2{font-size:1.2rem}.community .game-tabs{display:flex;gap:1rem;border-bottom:1px solid var(--bd)}
.game-tabs a{padding:.65rem .15rem;color:var(--mu);text-decoration:none}.game-tabs a[aria-current]{border-bottom:2px solid var(--ac);color:var(--ac);font-weight:700}
.filters,.actions,.tags{display:flex;flex-wrap:wrap;gap:.6rem;align-items:end}.filters label:first-child{flex:1 1 13rem}.form,.detail,.matches,.replies{display:grid;gap:.75rem}
.community label{display:grid;gap:.3rem;font-size:.88rem}.community :is(input,select,textarea){max-width:100%;min-width:0;font:inherit;background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:6px;padding:.55rem}.community textarea{resize:vertical}
.actions{justify-content:end}.matches button,.tags :is(button,a){text-align:start;color:var(--ac);border:1px solid var(--bd);background:var(--sf);border-radius:6px;padding:.4rem .6rem}.posts{padding:0;list-style:none;margin:0}.posts li{border-top:1px solid var(--bd);padding:.8rem 0}.posts li>a{display:grid;gap:.25rem;text-decoration:none;color:var(--tx)}.posts :is(small,span),.detail small{font-size:.8rem;color:var(--mu)}
.community :is(.body,strong,h2,a){overflow-wrap:anywhere}.body{white-space:pre-wrap}.replies li.nested{padding-inline-start:1.25rem;border-inline-start:2px solid var(--bd)}.replies .text-button{margin-inline-start:.75rem}.replies{border-top:1px solid var(--bd);padding-block:1rem}
</style>
