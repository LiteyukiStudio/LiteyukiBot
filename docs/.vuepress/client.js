import {defineClientConfig} from "vuepress/client";

import resourceStoreComp from "./components/ResStore.vue";
import pluginStoreComp from "./components/PluginStore.vue";
import dashComp from "./components/Dash.vue";
import homeComp from "./components/Home.vue";


import ElementPlus from 'element-plus';


export default defineClientConfig({
    enhance: ({app, router, siteData}) => {
        app.component("homeComp", homeComp);
        app.component("dashComp", dashComp);
        app.component("resourceStoreComp", resourceStoreComp);
        app.component("pluginStoreComp", pluginStoreComp);
        app.use(ElementPlus);
    },
});