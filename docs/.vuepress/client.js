import {defineClientConfig} from "vuepress/client";
import { defineEChartsConfig } from "vuepress-plugin-md-enhance/client";

import resourceStoreComp from "./components/ResStore.vue";
import pluginStoreComp from "./components/PluginStore.vue";
import dashComp from "./components/Dash.vue";
import homeComp from "./components/Home.vue";
import geoComp from "./components/Geo.vue";

// import ElementPlus from 'element-plus';

defineEChartsConfig({
  options: {
    // 全局 ECharts 配置
  },
  setup: async () => {
    // ECharts 设置
    // 例如: await import("echarts-wordcloud")
  },
});


export default defineClientConfig({
    enhance: ({app, router, siteData}) => {
        app.component("homeComp", homeComp);
        app.component("dashComp", dashComp);
        app.component("resourceStoreComp", resourceStoreComp);
        app.component("pluginStoreComp", pluginStoreComp);
        app.component("geoComp", geoComp);
        // app.use(ElementPlus);
    },
});