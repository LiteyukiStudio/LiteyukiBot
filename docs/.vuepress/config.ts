import {defineUserConfig} from "vuepress";
import theme from "./theme.js";
import viteBundler from "@vuepress/bundler-vite";

export default defineUserConfig({
    base: "/",

    lang: "zh-CN",
    title: "LiteyukiBot",
    description: "An OneBot Standard ChatBot",
    head: [
// 设置 favor.ico，.vuepress/public 下
        [
            'link', {rel: 'icon', href: 'https://cdn.liteyuki.icu/favicon.ico'},

        ],
        [
            "meta",
            {
                name: "viewport",
                content: "width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no",
            },
        ]
    ],


    theme,
    // 和 PWA 一起启用
    // shouldPrefetch: false,
});