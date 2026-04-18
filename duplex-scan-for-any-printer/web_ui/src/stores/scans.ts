import { defineStore } from 'pinia'
import axios from 'axios'

export interface BotStatus {
  enabled: boolean
  connected: boolean
  pending_sessions: number
  authorized_users: number
  message: string
  channels?: Record<string, any>
}

export interface BotInfo {
  registered_chats: Record<string, number>  // user_id -> chat_id
  notify_chat_ids: string[]
}

export interface SessionStatus {
  current_session_id: string | null
  state: string
  mode: string
  image_count: number
  timeout_seconds: number
  message: string
}

export interface ActivityItem {
  id: string
  filename: string
  mode: string
  pages: number | null
  size_mb: number
  created: number
}

export const useScansStore = defineStore('scans', {
  state: () => ({
    scans: [] as Array<any>,
    activity: [] as ActivityItem[],
    isLoading: false,
    error: null as string | null,
    botStatus: null as BotStatus | null,
    botInfo: null as BotInfo | null,
    sessionStatus: null as SessionStatus | null,
  }),

  getters: {
    scanCount: (state: any) => state.scans.length,
    recentScans: (state: any) => state.scans.slice(0, 10),
    isBotEnabled: (state: any) => state.botStatus?.enabled ?? false,
    isBotConnected: (state: any) => state.botStatus?.connected ?? false,
    hasPendingSession: (state: any) => state.sessionStatus?.state === 'WAIT_CONFIRM',
  },

  actions: {
    async fetchScans() {
      this.isLoading = true
      this.error = null
      try {
        const response = await axios.get('/api/activity')
        this.activity = response.data.items ?? []
        this.scans = this.activity  // keep compat
      } catch (error: any) {
        this.error = error.message
        console.error('Failed to fetch activity:', error)
      } finally {
        this.isLoading = false
      }
    },

    async fetchBotStatus() {
      try {
        const response = await axios.get('/api/bot/status')
        this.botStatus = response.data
      } catch (error) {
        console.error('Failed to fetch bot status:', error)
      }
    },

    async fetchBotInfo() {
      try {
        const response = await axios.get('/api/bot/info')
        this.botInfo = response.data
      } catch (error) {
        console.error('Failed to fetch bot info:', error)
      }
    },

    async fetchSessionStatus() {
      try {
        const response = await axios.get('/api/session/status')
        this.sessionStatus = response.data
      } catch (error) {
        console.error('Failed to fetch session status:', error)
      }
    },

    async confirmSession(printRequested = false): Promise<{ ok: boolean; message?: string }> {
      try {
        const response = await axios.post(`/api/session/confirm?print_requested=${printRequested}`)
        await this.fetchSessionStatus()
        return response.data
      } catch (error: any) {
        return { ok: false, message: error.message }
      }
    },

    async rejectSession(): Promise<{ ok: boolean; message?: string }> {
      try {
        const response = await axios.post('/api/session/reject')
        await this.fetchSessionStatus()
        return response.data
      } catch (error: any) {
        return { ok: false, message: error.message }
      }
    },

    async deleteScan(filename: string) {
      try {
        await axios.delete(`/api/scan/${filename}`)
        this.scans = this.scans.filter((scan: any) => scan.filename !== filename)
      } catch (error) {
        console.error('Failed to delete scan:', error)
        throw error
      }
    },

    getScanByFilename(filename: string) {
      return this.scans.find((scan: any) => scan.filename === filename)
    },
  },
})
