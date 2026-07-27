import { defineStore } from 'pinia'

import { getScenicSpots } from '@/api/scenic'
import { normalizeScenicSpots } from '@/utils/scenicCatalog'

export const useScenicStore = defineStore('scenic', {
  state: () => ({
    spots: [],
    loading: false,
    loaded: false
  }),
  getters: {
    getById: (state) => (id) => state.spots.find((spot) => spot.id === id) || null
  },
  actions: {
    async load(force = false) {
      if (this.loading || (this.loaded && !force)) return this.spots
      this.loading = true
      try {
        this.spots = normalizeScenicSpots(await getScenicSpots())
        this.loaded = true
        return this.spots
      } finally {
        this.loading = false
      }
    }
  }
})
