import {sidebar} from "vuepress-theme-hope";

export const enSidebarConfig = sidebar({
    "/en/": [
        "",
        {
            text: "Install & Deploy",
            icon: "laptop-code",
            prefix: "deploy/",
            children: "structure",
        },
        {
            text: "Usage & Features",
            icon: "book",
            prefix: "usage/",
            children: "structure",
        },
        {
            text: "Resources & Plugins",
            icon: "store",
            prefix: "store/",
            children: "structure",
        },
        {
            text: "Development & Contribution",
            icon: "pen-nib",
            prefix: "dev/",
            children: "structure",
        }
    ],
});
