import {sidebar} from "vuepress-theme-hope";

export default sidebar({
    "/": [
        "",
        {
            text: "项目部署",
            icon: "laptop-code",
            prefix: "deployment/",
            children: "structure",
        },
        {
            text: "使用手册",
            icon: "book",
            prefix: "usage/",
            children: "structure",
        },
        {
            text: "资源商店",
            icon: "store",
            prefix: "store/",
            link: "/store/",
            children: "structure",
        }
    ],
});
