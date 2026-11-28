const unownPrintings = new Map([
  ['https://api.tcgdex.net/v2/en/cards/exu-%21', { number: '!', page: 'https://pkmncards.com/card/unown-unseen-forces-uf-2/' }],
  ['https://api.tcgdex.net/v2/en/cards/exu-%253F', { number: '?', page: 'https://pkmncards.com/card/unown-unseen-forces-uf/' }]
])

// English gold finishes verified against the marketplace's product catalog and the OPTCG DON!! catalog.
const goldDonPrintings = new Map([
  ['DON:don_132', { pack:'EB-03', name:'DON!! Card (Boa Hancock) (Gold)',
    url:'https://www.tcgplayer.com/product/677571/one-piece-card-game-extra-booster-one-piece-heroines-edition-don-card-boa-hancock-gold' }],
  ['DON:don_169', { pack:'PRB-02', name:'DON!! Card (Rob Lucci) (Gold)',
    url:'https://www.tcgplayer.com/product/655121/one-piece-card-game-premium-booster-the-best-vol-2-don-card-rob-lucci-gold' }],
  ['DON:don_181', { pack:'EB-03', name:'DON!! Card (Uta) (Gold)',
    url:'https://www.tcgplayer.com/product/677567/one-piece-card-game-extra-booster-one-piece-heroines-edition-don-card-uta-gold' }],
  ['DON:don_185', { pack:'OP-16', name:'DON!! Card (Alternate Art) (Gold)',
    url:'https://www.tcgplayer.com/product/698314/one-piece-card-game-the-time-of-battle-don-card-alternate-art-gold' }]
])

export function printingSource(card) {
  if (!card) return null
  if (card.gameCode === 'POKEMON' && card.packName === 'Unseen Forces Unown Collection' && card.originalName === 'Unown') {
    const printing = unownPrintings.get(card.sourceUrl)
    const number = card.number === '%3F' ? '?' : card.number
    if (printing && number === printing.number) {
      return { url: printing.page, label: '영문 인쇄본', provider: 'PkmnCards', number: number + '/28' }
    }
  }
  if (card.gameCode === 'ONEPIECE' && card.sourceUrl === 'https://optcgapi.com/api/allDonCards/') {
    const printing = goldDonPrintings.get(card.number)
    if (printing && printing.name === card.originalName && printing.pack === card.productCode &&
        printing.pack === card.specs?.productCode && printing.name === card.specs?.names?.en) {
      return { url: printing.url, label: '영문 인쇄본', provider: 'TCGplayer' }
    }
  }
  if (card.gameCode === 'RIFTBOUND') {
    const evidence = card.specs?.editionEvidence?.en
    const code = evidence?.publicCode
    if (evidence?.basis === 'PUBLISHER_PRINTING' && evidence.source === 'https://playriftbound.com/en-us/card-gallery/' &&
        typeof code === 'string' && code.length <= 32 && /^[A-Za-z0-9]+-[A-Za-z0-9*]+(?:\/[0-9]+)?$/u.test(code) &&
        typeof card.number === 'string' && code.toLowerCase().replace('/', '-') === card.number.toLowerCase()) {
      return { url: evidence.source, label: 'Riot 영문 카드 갤러리', number: code }
    }
  }
  if (card.gameCode === 'WEISS' && typeof card.number === 'string' && card.number.length > 0 && card.number.length <= 128) {
    const value = card.specs?.publisherCardUrl
    if (typeof value !== 'string' || value.length > 768 ||
        !/^https:\/\/en\.ws-tcg\.com\/cardlist\/\?cardno=[^&#\s]+$/u.test(value)) return null
    try {
      if (new URL(value).searchParams.get('cardno') === card.number) {
        return { url: value, label: '발행사 영문 카드 페이지' }
      }
    } catch { return null }
  }
  return null
}
