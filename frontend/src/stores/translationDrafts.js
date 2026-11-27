import {reactive,watch} from 'vue'
import {defineStore} from 'pinia'
import {useSession} from './session'

// Drafts survive SPA navigation only within the same administrator's session.
export const useTranslationDrafts=defineStore('translation-drafts',()=>{
  const session=useSession()
  const drafts=reactive(new Map())
  watch(()=>session.isAdmin?session.account?.email:null,()=>drafts.clear(),{flush:'sync'})
  function beforeUnload(event){event.preventDefault();event.returnValue=''}
  watch(()=>drafts.size>0,dirty=>{
    if(dirty)window.addEventListener('beforeunload',beforeUnload)
    else window.removeEventListener('beforeunload',beforeUnload)
  },{flush:'sync'})
  return {drafts}
})
