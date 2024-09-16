import DefaultTheme from 'vitepress/theme'
import './liteyuki.scss'

import StatsBar from '../../components/StatsBar.vue'
import PluginStore from '../../components/PluginStore.vue'
import ResStore from '../../components/ResStore.vue'



export default {
    extends: DefaultTheme,
    enhanceApp({ app }) {
        app.component('StatsBar', StatsBar);
        app.component('PluginStore', PluginStore);
        app.component('ResStore', ResStore);
    },
    Layout: StatsBar
}