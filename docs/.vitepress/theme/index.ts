import DefaultTheme from 'vitepress/theme'
import './custom.css'
import Home from './components/Home.vue'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('Home', Home)
  },
}
