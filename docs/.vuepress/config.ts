import {defineUserConfig} from "vuepress";
import theme from "./theme.js";
import viteBundler from "@vuepress/bundler-vite";

export default defineUserConfig({
    base: "/",

    locales: {
        "/": {
            // 设置正在使用的语言
            lang: "zh-CN",
        },
        "/en/": {
            // 设置正在使用的语言
            lang: "en-US",
        },
    },
    title: "LiteyukiBot 轻雪机器人",
    description: "LiteyukiBot | 轻雪机器人 | An OneBot Standard ChatBot | 一个OneBot标准的聊天机器人",
    head: [
// 设置 favor.ico，.vuepress/public 下
        ["script", {src: "/js/style.js", "type": "module"}],
        ["script", {src: "/js/get_data.js", "type": "module"}],
        ['link', {rel: 'icon', href: 'https://cdn.liteyuki.icu/favicon.ico'},],

        ['link', {rel: 'stylesheet', href: 'https://cdn.bootcdn.net/ajax/libs/firacode/6.2.0/fira_code.min.css'}],

        [
            "meta",
            {
                name: "viewport",
                content: "width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no",
            },
        ],
    ],

    theme,
    // 和 PWA 一起启用
    // shouldPrefetch: false,
});