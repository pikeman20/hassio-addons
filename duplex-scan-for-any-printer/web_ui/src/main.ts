import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import App from './App.vue'

// HA ingress serves the app under a dynamic subpath (e.g. /api/hassio_ingress/<token>/).
// Using relative baseURL ensures API calls resolve correctly through any proxy prefix.
axios.defaults.baseURL = './'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.mount('#app')
