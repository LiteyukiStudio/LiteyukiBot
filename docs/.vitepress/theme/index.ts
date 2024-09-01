import DefaultTheme from 'vitepress/theme'
import './liteyuki.css'

import StatsBar from '../../components/StatsBar.vue'



export default {
    extends: DefaultTheme,
    Layout: StatsBar
}