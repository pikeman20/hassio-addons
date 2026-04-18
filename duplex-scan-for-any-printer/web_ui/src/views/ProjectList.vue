<template>
  <div class="min-h-screen bg-gray-50 p-8">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-2">📁 Scan Projects</h1>
        <p class="text-gray-600">Select a project to edit images and regenerate PDF</p>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading" class="flex items-center justify-center py-20">
        <div class="text-center">
          <div class="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p class="text-gray-600">Loading projects...</p>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else-if="projects.length === 0" class="text-center py-20">
        <svg class="w-24 h-24 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <h3 class="text-xl font-semibold text-gray-900 mb-2">No projects found</h3>
        <p class="text-gray-600 mb-4">Scan some documents first to create projects</p>
        <p class="text-sm text-gray-500">Run: <code class="bg-gray-100 px-2 py-1 rounded">python tests/test_main_scan_document.py</code></p>
      </div>

      <!-- Projects Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="project in projects"
          :key="project.id"
          class="bg-white rounded-lg shadow-md hover:shadow-xl transition-shadow cursor-pointer overflow-hidden group"
          @click="openProject(project)"
        >
          <!-- Thumbnail -->
          <div class="aspect-[3/4] bg-gray-100 overflow-hidden">
            <img
              :src="project.thumbnail"
              :alt="project.filename"
              class="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300"
            />
          </div>

          <!-- Info -->
          <div class="p-4">
            <h3 class="font-semibold text-gray-900 mb-2 truncate" :title="project.filename">
              {{ project.filename }}
            </h3>
            
            <!-- Metadata -->
            <div class="space-y-1 text-sm text-gray-600 mb-3">
              <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                  {{ project.mode }}
                </span>
                <span>{{ project.pages }} pages</span>
              </div>
              <div>📏 {{ project.size_mb }} MB</div>
              <div>📅 Created: {{ formatDate(project.created) }}</div>
              <div v-if="project.updated && project.updated !== project.created">✏️ Last edited: {{ formatDate(project.updated) }}</div>
              <div v-if="project.has_metadata" class="flex items-center gap-1 text-green-600">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                Has edit history
              </div>
            </div>

            <!-- Actions -->
            <div class="flex gap-2 mt-1">
              <button
                class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
                @click.stop="openProject(project)"
              >
                ✏️ Edit
              </button>
              <button
                class="px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-600 hover:text-white transition font-medium"
                :disabled="deletingId === project.id"
                @click.stop="deleteProject(project)"
                title="Delete project permanently"
              >
                <span v-if="deletingId === project.id">⏳</span>
                <span v-else>🗑️</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

type Project = {
  id: string
  filename: string
  thumbnail: string
  mode?: string
  pages?: number
  size_mb?: number
  created?: number
  updated?: number
  has_metadata?: boolean
}

const emit = defineEmits<{ (e: 'open-project', project: Project): void }>()

const projects = ref<Project[]>([])
const isLoading = ref(true)
const deletingId = ref<string | null>(null)

const loadProjects = async () => {
  isLoading.value = true
  try {
    const response = await axios.get('/api/projects')
    projects.value = response.data.projects as Project[]
  } catch (error) {
    console.error('Failed to load projects:', error)
  } finally {
    isLoading.value = false
  }
}

const openProject = (project: Project) => {
  emit('open-project', project)
}

const deleteProject = async (project: Project) => {
  if (!confirm(`Delete "${project.filename}" permanently?\nThis cannot be undone.`)) return
  deletingId.value = project.id
  try {
    await axios.delete(`/api/projects/${project.id}`)
    projects.value = projects.value.filter(p => p.id !== project.id)
  } catch (error) {
    console.error('Failed to delete project:', error)
    alert('Failed to delete project. See console for details.')
  } finally {
    deletingId.value = null
  }
}

const formatDate = (timestamp = 0) => {
  return new Date(timestamp * 1000).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadProjects()
})
</script>
