import {defineClientConfig} from "vuepress/client";
import resourceStoreComp from "./components/ResStore.vue";
import pluginStoreComp from "./components/PluginStore.vue";
//导入element-plus
import ElementPlus from 'element-plus';

export default defineClientConfig({
    enhance: ({app, router, siteData}) => {
        app.component("resourceStoreComp", resourceStoreComp);
        app.component("pluginStoreComp", pluginStoreComp);
        app.use(ElementPlus);
    },
});