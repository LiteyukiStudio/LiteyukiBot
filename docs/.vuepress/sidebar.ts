import {sidebar} from "vuepress-theme-hope";

export default sidebar({
    "/": [
        "",
        {
            text: "安装及部署",
            icon: "laptop-code",
            prefix: "deployment/",
            children: "structure",
        },
        {
            text: "使用及开发",
            icon: "book",
            prefix: "usage/",
            children: "structure",
        },
        {
            text: "资源及插件",
            icon: "store",
            prefix: "store/",
            children: "structure",
        },{
            text: "其他",
            icon: "question-circle",
            prefix: "other/",
            children: "structure",
        }
    ],
});
