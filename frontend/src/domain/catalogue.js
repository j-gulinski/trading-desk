import { formatSignedAmount, formatUnitPrice } from './formatting.js'
import { toNum } from './values.js'

export function catalogueFieldsOf(data) {
  return {
    ticketKind: data.ticket_kind ?? data.ticketKind ?? null,
    label: data.label ?? null,
  }
}

export function ticketKindOf(item) {
  return item?.ticketKind ?? item?.ticket_kind ?? item?.schema?.ticket_kind ?? null
}

export function assetClassLabel(assetClass, schemas) {
  return schemas?.[assetClass]?.label ?? String(assetClass ?? '').replaceAll('_', ' ')
}

export function classLabelOf(item, schemas) {
  if (item && typeof item === 'object') {
    return item.label ?? assetClassLabel(item.assetClass, schemas)
  }
  return assetClassLabel(item, schemas)
}

export function catalogueAssetClasses(schemas) {
  return Object.keys(schemas ?? {}).sort()
}

export function markForDisplay(item, value) {
  const price = toNum(value)
  if (ticketKindOf(item) !== 'bond' || price == null) return price
  const face = toNum(item.terms?.face_value ?? item.faceValue)
  return face != null && face > 0 ? price / face * 100 : price
}

export function formatMarkAmount(item, value) {
  const displayed = markForDisplay(item, value)
  if (ticketKindOf(item) === 'swap') return formatSignedAmount(displayed)
  return formatUnitPrice(displayed, item.assetClass)
}

export function sizeOf(item) {
  const kind = ticketKindOf(item)
  const terms = item.terms ?? {}
  if (kind === 'swap') return toNum(terms.notional)
  if (kind === 'bond') {
    const face = toNum(terms.face_value)
    const quantity = item.quantity ?? item.netQuantity ?? 1
    return face == null ? null : face * quantity
  }
  return item.quantity ?? item.netQuantity ?? null
}

export function sizeLabelOf(item) {
  switch (ticketKindOf(item)) {
    case 'swap':
      return 'Notional'
    case 'bond':
      return 'Face amount'
    default:
      return 'Quantity'
  }
}

export function valueLabelOf(item, prefix) {
  switch (ticketKindOf(item)) {
    case 'bond':
      return `${prefix} / 100 face`
    case 'swap':
      return `${prefix} NPV`
    case 'premium':
      return `${prefix} premium / contract`
    default:
      return item.assetClass === 'FX' ? `${prefix} rate` : `${prefix} price`
  }
}

export function positionValueLabelsOf(item) {
  switch (ticketKindOf(item)) {
    case 'swap':
      return ['ENTRY NPV', 'CURRENT NPV']
    case 'bond':
      return ['ENTRY / 100', 'CURRENT / 100']
    case 'premium':
      return ['ENTRY PREMIUM', 'MODEL PREMIUM']
    default:
      return item.assetClass === 'FX'
        ? ['AVG ENTRY RATE', 'MARK RATE']
        : ['AVG ENTRY', 'MARK']
  }
}

export function netSizeLabelOf(item) {
  switch (ticketKindOf(item)) {
    case 'swap':
      return 'NOTIONAL'
    case 'bond':
      return 'FACE'
    case 'premium':
      return 'NET CONTRACTS'
    default:
      if (item.assetClass === 'EQUITY') return 'NET SHARES'
      if (item.assetClass === 'FX') return 'NET NOTIONAL'
      return 'NET UNITS'
  }
}

export function priceDriverLabelOf(item) {
  switch (ticketKindOf(item)) {
    case 'bond':
      return 'Bond price move'
    case 'swap':
      return 'Model NPV move'
    case 'premium':
      return 'Premium move'
    default:
      if (item.assetClass === 'FX') return 'FX rate move'
      if (item.assetClass === 'EQUITY') return 'Share price move'
      return 'Spot price move'
  }
}
