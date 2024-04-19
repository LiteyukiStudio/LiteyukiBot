import {navbar} from "vuepress-theme-hope";

export default navbar([
    "/",
    {
        text: "项目部署",
        link: "/deployment/",
        prefix: "deployment/",
    },
    {
        text: "使用手册",
        link: "/usage/",
        prefix: "usage/",
    },
    {
        text: "商店",
        link: "/store/resource",
        prefix: "store/",
    }
]);
