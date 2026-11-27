import { strToU8,zipSync } from 'fflate'
import { t } from './i18n'
import { sectionLabel } from './library'
import { saveDocument } from './savePng'
const spreadsheet='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const ns='http://schemas.openxmlformats.org/'
function xml(s){return String(s??'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function xlsx(decks){
  const lines=[[t('덱 이름'),t('일본어 이름'),t('영어 이름'),t('게임'),t('구역'),t('카드명'),t('카드 번호'),t('수량'),t('일러스트')]]
  for(const deck of decks)for(const item of deck.entries.length?deck.entries:[{}]){
    lines.push([deck.name,deck.nameJa,deck.nameEn,deck.gameCode,item.section?sectionLabel(item.section):'',item.name,item.number,item.quantity,item.neuronArtwork??(item.illustration==null?'':item.illustration+1)])
  }
  const sheet=lines.map((row,i)=>'<row r="'+(i+1)+'">'+row.map((v,j)=>{
    const ref=String.fromCharCode(65+j)+(i+1)
    return typeof v==='number'?'<c r="'+ref+'"><v>'+v+'</v></c>':'<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+xml(v)+'</t></is></c>'
  }).join('')+'</row>').join('')
  const pkg='package/2006/relationships',doc='officeDocument/2006/relationships'
  const files={
    '[Content_Types].xml':'<Types xmlns="'+ns+'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    '_rels/.rels':'<Relationships xmlns="'+ns+pkg+'"><Relationship Id="rId1" Type="'+ns+doc+'/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    'xl/workbook.xml':'<workbook xmlns="'+ns+'spreadsheetml/2006/main" xmlns:r="'+ns+doc+'"><sheets><sheet name="TCG" sheetId="1" r:id="rId1"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':'<Relationships xmlns="'+ns+pkg+'"><Relationship Id="rId1" Type="'+ns+doc+'/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    'xl/worksheets/sheet1.xml':'<worksheet xmlns="'+ns+'spreadsheetml/2006/main"><sheetData>'+sheet+'</sheetData></worksheet>'
  }
  return new Blob([zipSync(Object.fromEntries(Object.entries(files).map(([k,v])=>[k,strToU8(v)])))],{type:spreadsheet})
}
export async function exportDecks(session,format,signal){
  const decks=[]
  let after=0
  do{
    const page=await session.authenticatedRequest('/me/decks/export?after='+after,{signal})
    decks.push(...page.items);after=page.next
  }while(after!=null)
  const blob=format==='xlsx'?xlsx(decks):new Blob([JSON.stringify({version:1,decks},null,2)],{type:'application/json'})
  await saveDocument(blob,'TCG-'+new Date().toISOString().slice(0,10)+'.'+format)
}
