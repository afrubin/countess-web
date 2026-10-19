import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { takeToken } from './token'

takeToken()

createApp(App).mount('#app')
