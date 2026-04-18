import { defineStore } from 'pinia'
import axios from 'axios'

export const useEditorStore = defineStore('editor', {
  state: () => ({
    currentScan: null as string | null,
    currentPage: 0,
    totalPages: 0,
    activeTool: 'select' as string,
    isLoading: false,
    isDirty: false,
    previewWidth: 800,
    originalWidth: 0,
    apiBase: '/api' as string
  }),

  getters: {
    hasNext: (state: any) => state.currentPage < state.totalPages - 1,
    hasPrev: (state: any) => state.currentPage > 0,
    pageNumber: (state: any) => state.currentPage + 1,
    scaleFactor: (state: any) => (state.previewWidth ? state.originalWidth / state.previewWidth : 1)
  },

  actions: {
    async loadScan(filename: string) {
      this.isLoading = true
      try {
        const response = await axios.get(`${this.apiBase}/scan/${filename}/info`)
        this.currentScan = filename
        this.totalPages = response.data.pages
        this.originalWidth = response.data.width
        this.currentPage = 0
        this.isDirty = false
      } catch (error) {
        console.error('Failed to load scan:', error)
        throw error
      } finally {
        this.isLoading = false
      }
    },

    setTool(toolName: string) {
      this.activeTool = toolName
    },

    nextPage() {
      if (this.hasNext) {
        this.currentPage++
        return true
      }
      return false
    },

    prevPage() {
      if (this.hasPrev) {
        this.currentPage--
        return true
      }
      return false
    },

    goToPage(pageNum: number) {
      if (pageNum >= 0 && pageNum < this.totalPages) {
        this.currentPage = pageNum
        return true
      }
      return false
    },

    markDirty() {
      this.isDirty = true
    },

    markClean() {
      this.isDirty = false
    },

    getPageImageUrl(size = 'medium') {
      if (!this.currentScan) return null
      return `${this.apiBase}/scan/${this.currentScan}/page/${this.currentPage}?size=${size}`
    },

    async exportPDF(edits: any) {
      this.isLoading = true
      try {
        const response = await axios.post(`${this.apiBase}/edit`, {
          filename: this.currentScan,
          pages: edits,
          preview_width: this.previewWidth
        })

        this.markClean()
        return response.data
      } catch (error) {
        console.error('Failed to export PDF:', error)
        throw error
      } finally {
        this.isLoading = false
      }
    },

    getDownloadUrl(filename: string) {
      return `${this.apiBase}/download/${filename}`
    }
  }
})
