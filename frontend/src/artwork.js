import { artworkUrl, mediaPath } from './api'

export function cardArtworks(src, directLanguage, variants, failedUrl) {
  const choices = []
  const url = artworkUrl(src)
  if (url && url !== failedUrl) choices.push({ key:'direct', src:url, language:directLanguage })

  for (const [position,variant] of variants.entries()) {
    const tile = variant.image
    const sheet = mediaPath(tile?.url)
    if (!sheet || !Number.isInteger(tile.col) || tile.col < 0 || tile.col > 3 ||
        !Number.isInteger(tile.row) || tile.row < 0 || tile.row > 2) {
      // Direct publisher art can represent the first variant even before an atlas is available.
      if (position===0 && choices[0]?.src) choices[0].rarity = variant.rarity
      else if (variant.id!=null) choices.push({key:variant.id, rarity:variant.rarity})
      continue
    }
    choices.push({
      key:variant.id, rarity:variant.rarity, language:tile.language,
      style:{
        backgroundImage:'url("' + sheet.replace(/"/g, '%22') + '")',
        backgroundPosition:(tile.col * 100 / 3) + '% ' + (tile.row * 50) + '%',
        aspectRatio:tile.cellWidth > 0 && tile.cellHeight > 0 ? tile.cellWidth + ' / ' + tile.cellHeight : '300 / 438',
      },
    })
  }
  return choices
}

export function preferredArtwork(choices, language) {
  return choices.find(art => art.language === language) ?? choices.find(art => art.src || art.style) ?? choices[0]
}
