import { describe, expect, it } from 'vitest'
import { getScenicById, scenicSpots } from './scenic'

describe('scenic configuration', () => {
  it('registers Changsha Dongqu Kingdom as a ticket-only scenic spot', () => {
    const spot = getScenicById('changsha-dongqu')
    expect(spot).toMatchObject({
      id: 'changsha-dongqu',
      name: '长沙动趣王国',
      province: '湖南省',
      imagePath: '/scenic/changsha-dongqu.jpg',
      ticketEnabled: true,
      hotelEnabled: false
    })
    expect(spot.scenicPlatforms).toEqual([])
    expect(spot.ticketPlatforms.map(({ key }) => key)).toEqual(['douyin', 'ctrip', 'meituan'])
    expect(scenicSpots).toContainEqual(spot)
  })
})
