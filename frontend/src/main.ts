import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { startTheming } from './theme/theme'
import { takeToken } from './token'

takeToken()
// Before mounting, so the page is never drawn in the wrong theme first.
startTheming()

createApp(App).mount('#app')
