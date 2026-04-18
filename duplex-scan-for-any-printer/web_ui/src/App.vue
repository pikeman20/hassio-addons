<template>
  <div id="app" class="min-h-screen bg-gray-50">
    <!-- Header -->
    <header class="bg-white shadow-sm border-b border-gray-200">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <svg class="w-8 h-8 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <div>
              <h1 class="text-2xl font-bold text-gray-900">Scan Editor</h1>
              <p class="text-sm text-gray-500">Review and edit your scanned documents</p>
            </div>
          </div>
          
          <nav class="flex space-x-4">
            <button
              @click="currentView = 'dashboard'"
              :class="[
                'px-4 py-2 rounded-lg font-medium transition-colors',
                currentView === 'dashboard'
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              ]"
            >
              📊 Dashboard
            </button>
            <button
              @click="currentView = 'projects'"
              :class="[
                'px-4 py-2 rounded-lg font-medium transition-colors',
                currentView === 'projects'
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              ]"
            >
              📁 Projects
            </button>
            <button
              v-if="editorStore.currentScan"
              @click="currentView = 'editor'"
              :class="[
                'px-4 py-2 rounded-lg font-medium transition-colors',
                currentView === 'editor'
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              ]"
            >
              Editor
            </button>
          </nav>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <transition name="fade" mode="out-in">
        <Dashboard v-if="currentView === 'dashboard'" />
        <ProjectList v-else-if="currentView === 'projects'" @open-project="openProject" />
        <GalleryView v-else-if="currentView === 'gallery'" @open-editor="openEditor" />
        <EditorView v-else-if="currentView === 'editor'" @back="currentView = 'projects'" />
      </transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useEditorStore } from '@/stores/editor'
import ProjectList from '@/views/ProjectList.vue'
import GalleryView from '@/views/GalleryView.vue'
import EditorView from '@/views/EditorView.vue'
import Dashboard from '@/views/Dashboard.vue'

type Project = { filename: string }

const editorStore = useEditorStore()
const currentView = ref('dashboard') // Start with dashboard

const openProject = async (project: Project) => {
  await editorStore.loadScan(project.filename)
  currentView.value = 'editor'
}

const openEditor = async (filename: string) => {
  await editorStore.loadScan(filename)
  currentView.value = 'editor'
}
</script>

<style>
@import './assets/main.css';

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
