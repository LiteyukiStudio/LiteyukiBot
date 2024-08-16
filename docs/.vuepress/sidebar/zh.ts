import {sidebar} from "vuepress-theme-hope";

export const zhSidebarConfig = sidebar({
    "/": [
        "",
        {
            text: "安装及部署",
            icon: "laptop-code",
            prefix: "deploy/",
            children: "structure",
        },
        {
            text: "使用及功能",
            icon: "book",
            prefix: "usage/",
            children: "structure",
        },
        {
            text: "资源及插件",
            icon: "store",
            prefix: "store/",
            children: "structure",
        },
        {
            text: "开发及贡献",
            icon: "pen-nib",
            prefix: "dev/",
            children: "structure",
        }
    ],
});
