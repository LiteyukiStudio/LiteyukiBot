import { defineClientConfig } from "vuepress/client";
import storeComp from "./components/store.vue";

export default defineClientConfig({
  enhance: ({ app, router, siteData }) => {
    app.component("storeComp", storeComp);
  },
});