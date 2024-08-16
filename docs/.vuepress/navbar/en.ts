import {navbar} from "vuepress-theme-hope";

export const enNavbarConfig = navbar([
    "/en/",
    {
        text: "Deploy",
        link: "/en/deploy/",
        prefix: "deploy/",
    },
    {
        text: "Usage",
        link: "/en/usage/",
        prefix: "usage/",
    },
    {
        text: "Extensions",
        link: "/en/store/",
        prefix: "store/",
    },
    {
        text: "Contribute",
        link: "/en/dev/",
        prefix: "dev/",
    },
]);
