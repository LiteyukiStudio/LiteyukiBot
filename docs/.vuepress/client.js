import {defineClientConfig} from "vuepress/client";
import resourceStoreComp from "./components/res_store.vue";
import pluginStoreComp from "./components/plugin_store.vue";
//导入element-plus
import ElementPlus from 'element-plus';

export default defineClientConfig({
    enhance: ({app, router, siteData}) => {
        app.component("resourceStoreComp", resourceStoreComp);
        app.component("pluginStoreComp", pluginStoreComp);
        app.use(ElementPlus);

    },
});