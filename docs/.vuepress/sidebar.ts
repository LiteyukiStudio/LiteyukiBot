import { sidebar } from "vuepress-theme-hope";

export default sidebar({
  "/": [
    "",
    {
      text: "项目部署",
      icon: "laptop-code",
      prefix: "deployment/",
      link: "deployment/",
      children: "structure",
    },
    {
      text: "使用手册",
      icon: "laptop-code",
      prefix: "usage/",
      link: "usage/",
      children: "structure",
    },
  ],
});
