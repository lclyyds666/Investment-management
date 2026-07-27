import assert from 'node:assert/strict'
import test from 'node:test'

import {
  enabledLedgerModules,
  normalizeScenicSpots
} from '../src/utils/scenicCatalog.js'

test('欧乐堡景区目录保持正常显示', () => {
  const spots = normalizeScenicSpots([{
    id: 'quanzhou-ouleb',
    name: '泉州欧乐堡',
    image: '/scenic/quanzhou-ouleb.jpg',
    ticket_enabled: true,
    hotel_enabled: true
  }])

  assert.equal(spots.length, 1)
  assert.equal(spots[0].name, '泉州欧乐堡')
  assert.equal(spots[0].image, '/scenic/quanzhou-ouleb.jpg')
})

test('接口新增景区后无需静态前端定义即可进入目录', () => {
  const spots = normalizeScenicSpots([{
    id: 'test-config-001',
    name: '测试景区',
    image: '',
    ticket_enabled: true,
    hotel_enabled: false
  }])

  assert.deepEqual(spots.map((spot) => spot.id), ['test-config-001'])
})

test('门票和酒店模块严格按照景区开关展示', () => {
  assert.deepEqual(enabledLedgerModules({ ticket_enabled: true, hotel_enabled: false }), ['ticket'])
  assert.deepEqual(enabledLedgerModules({ ticket_enabled: false, hotel_enabled: true }), ['hotel'])
  assert.deepEqual(enabledLedgerModules({ ticket_enabled: true, hotel_enabled: true }), ['ticket', 'hotel'])
  assert.deepEqual(enabledLedgerModules({ ticket_enabled: false, hotel_enabled: false }), [])
})
