// 文旅业务·景区配置（前端常量）。
// id 即数据作用域键 scenic_id（贯穿 路由参 → Ledger Props → 后端 WHERE scenic_id）。
// imagePath 指向 public/cultural-tourism/{id}.jpg；缺图时 UI 自动降级为渐变占位卡。
// platformList / 链接为占位示例，运营可按实际店铺主页替换。

// 各平台品牌色（用于入口徽标）
export const PLATFORM_BRANDS = {
  douyin: { name: '抖音', color: '#fe2c55' },
  ctrip: { name: '携程', color: '#2577e3' },
  meituan: { name: '美团', color: '#ffb000' },
  dianping: { name: '大众点评', color: '#ff6633' }
}

function P(key, url) {
  return { key, name: PLATFORM_BRANDS[key].name, color: PLATFORM_BRANDS[key].color, url }
}

// 各平台按景区名称的搜索入口（占位示例，运营可替换为实际店铺主页）
function platforms(name) {
  const q = encodeURIComponent(name)
  return [
    P('douyin', `https://www.douyin.com/search/${q}`),
    P('ctrip', `https://you.ctrip.com/searchsite/default/keyword.html?query=${q}`),
    P('meituan', `https://www.meituan.com/search/${q}`),
    P('dianping', `https://www.dianping.com/search/keyword/${q}`)
  ]
}

export const scenicSpots = [
  // id 即数据作用域键 scenic_id，保持不变（与已入库的核销台账绑定）；仅更新展示名称。
  { id: 'qihe', name: '泉城欧乐堡', imagePath: '/cultural-tourism/qihe.jpg', platformList: platforms('泉城欧乐堡') },
  { id: 'quanzhou', name: '泉州欧乐堡', imagePath: '/cultural-tourism/quanzhou.jpg', platformList: platforms('泉州欧乐堡') },
  { id: 'penglai', name: '福州欧乐堡', imagePath: '/cultural-tourism/penglai.jpg', platformList: platforms('福州欧乐堡') },
  { id: 'taishan', name: '遵义动物园', imagePath: '/cultural-tourism/taishan.jpg', platformList: platforms('遵义动物园') },
  { id: 'mengshan', name: '南阳森林野生动物世界', imagePath: '/cultural-tourism/mengshan.jpg', platformList: platforms('南阳森林野生动物世界') }
]

/** 按 id 取景区配置；未知 id 返回 null。 */
export function getScenicById(id) {
  return scenicSpots.find((s) => s.id === id) || null
}
