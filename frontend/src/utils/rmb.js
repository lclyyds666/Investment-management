// 人民币金额转中文大写（用于审批单打印）

const DIGITS = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
const INT_UNITS = ['', '拾', '佰', '仟']
const SECTION_UNITS = ['', '万', '亿', '兆']

export function digitToRMB(amount) {
  let num = Number(amount)
  if (isNaN(num)) return ''
  if (num === 0) return '零元整'
  const negative = num < 0
  num = Math.abs(num)

  // 拆分整数与小数（角、分）
  const intPart = Math.floor(num)
  const decimal = Math.round((num - intPart) * 100)
  const jiao = Math.floor(decimal / 10)
  const fen = decimal % 10

  // 整数部分：按 4 位分节
  let intStr = ''
  if (intPart === 0) {
    intStr = '零'
  } else {
    const s = String(intPart)
    const sections = []
    for (let i = s.length; i > 0; i -= 4) {
      sections.unshift(s.substring(Math.max(0, i - 4), i))
    }
    sections.forEach((sec, idx) => {
      const secUnit = SECTION_UNITS[sections.length - 1 - idx]
      let secStr = ''
      let zero = false
      const len = sec.length
      for (let j = 0; j < len; j++) {
        const d = Number(sec[j])
        const unit = INT_UNITS[len - 1 - j]
        if (d === 0) {
          zero = true
        } else {
          if (zero) secStr += '零'
          zero = false
          secStr += DIGITS[d] + unit
        }
      }
      if (secStr) intStr += secStr + secUnit
      else if (idx < sections.length - 1 && intStr && !intStr.endsWith('零')) intStr += '零'
    })
  }

  let result = intStr + '元'
  if (jiao === 0 && fen === 0) {
    result += '整'
  } else {
    if (jiao > 0) result += DIGITS[jiao] + '角'
    else if (fen > 0) result += '零'
    if (fen > 0) result += DIGITS[fen] + '分'
  }
  return (negative ? '负' : '') + result
}
