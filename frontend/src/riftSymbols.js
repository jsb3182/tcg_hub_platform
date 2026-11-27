// The names are paired English/Korean entries in Riot's Origins card gallery.
// Japanese uses the printed domain identifier with a Japanese rune label.
const runes={
  fury:['분노 룬','Fury Rune','Furyのルーン'],calm:['평정 룬','Calm Rune','Calmのルーン'],
  mind:['정신 룬','Mind Rune','Mindのルーン'],body:['신체 룬','Body Rune','Bodyのルーン'],
  chaos:['혼돈 룬','Chaos Rune','Chaosのルーン'],order:['질서 룬','Order Rune','Orderのルーン'],
}
const symbols={might:['위력','Might','戦闘力'],exhaust:['탈진','Exhaust','エグゾースト']}
const energy=['에너지','Energy','エネルギー']
export function riftEffectText(value,lang){
  const i=['ko','en','ja'].indexOf(lang)
  if(typeof value!=='string'||i<0||!value.includes(':rb_'))return value
  return value.replace(/:rb_([a-z0-9_]+):/g,(token,key)=>{
    const number=/^energy_([0-8]|12)$/.exec(key)
    const rune=/^rune_(fury|calm|mind|body|chaos|order)$/.exec(key)
    const label=number?energy[i]+' '+number[1]:rune?runes[rune[1]][i]:
      Object.prototype.hasOwnProperty.call(symbols,key)?symbols[key][i]:null
    return label?'['+label+']':token
  })
}
