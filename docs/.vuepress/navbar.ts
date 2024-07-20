import {navbar} from "vuepress-theme-hope";

export default navbar([
    "/",
    {
        text: "安装及部署",
        link: "/deployment/",
        prefix: "deployment/",
    },
    {
        text: "使用及开发",
        link: "/usage/",
        prefix: "usage/",
    },
    {
        text: "资源及插件",
        link: "/store/resource",
        prefix: "store/",
    }
]);
