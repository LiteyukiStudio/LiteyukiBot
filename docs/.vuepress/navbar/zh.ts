
import {navbar} from "vuepress-theme-hope";

export const zhNavbarConfig = navbar([
    "/",
    {
        text: "安装及部署",
        link: "/deploy/",
        prefix: "deploy/",
    },
    {
        text: "使用及功能",
        link: "/usage/",
        prefix: "usage/",
    },
    {
        text: "资源及插件",
        link: "/store/",
        prefix: "store/",
    },
    {
        text: "开发及贡献",
        link: "/dev/",
        prefix: "dev/",
    },
]);
