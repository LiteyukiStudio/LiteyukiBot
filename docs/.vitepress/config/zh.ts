import {defineConfig} from 'vitepress'
import {ThemeConfig} from "./utils";

export const zh = defineConfig({
    lang: "zh-Hans",
    title: "轻雪机器人",
    description: "一个综合性的机器人应用及管理框架",
    themeConfig: {
        nav: [
            {text: '部署', link: '/deploy/install'},
            {text: '使用', link: '/usage/basic'},
            {text: '扩展', link: '/store/resource'},
            {text: '开发', link: '/dev/guide'},
        ],
        docFooter: {
            prev: '上一页',
            next: '下一页'
        },
        editLink: ThemeConfig.getEditLink(
            '在 GitHub 上编辑此页',
        ),
        footer: {
            message: '网站部署在 <a href="https://meli.liteyuki.icu" target="_blank">Liteyukiflare Meli</a> 由 <a href="https://cdn.liteyuki.icu" target="_blank">Liteyukiflare CDN</a> 提供加速服务<br>文档由 <a href="https://vitepress.dev/">VitePress</a> 构建 | API引用由 <a href="https://github.com/LiteyukiStudio/litedoc">litedoc</a> 生成',
            copyright: ThemeConfig.copyright
        },
        outline: ThemeConfig.getOutLine("页面内容"),

        langMenuLabel: '语言',
        returnToTopLabel: '返回顶部',
        sidebarMenuLabel: '菜单',
        darkModeSwitchLabel: '主题',
        lightModeSwitchTitle: '轻色模式',
        darkModeSwitchTitle: '深色模式',
    },
})