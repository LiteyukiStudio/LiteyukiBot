import {defineUserConfig} from "vuepress";
import theme from "./theme.js";

export default defineUserConfig({
    base: "/",

    lang: "zh-CN",
    title: "LiteyukiBot",
    description: "An OneBot Standard ChatBot",
    head: [
// 设置 favor.ico，.vuepress/public 下
        [
            'link', {rel: 'icon', href: 'https://cdn.liteyuki.icu/favicon.ico'}
        ]
    ],

    theme,

    // 和 PWA 一起启用
    // shouldPrefetch: false,
});
