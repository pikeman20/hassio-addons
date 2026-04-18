import { createApp } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import App from './App.vue'

// HA ingress injects a <base href="..."> tag — document.baseURI picks it up automatically.
axios.defaults.baseURL = document.baseURI

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.mount('#app')
