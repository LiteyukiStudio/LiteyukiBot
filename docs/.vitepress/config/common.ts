// 共有配置项，导入index用

import { defineConfig } from "vitepress";
import { generateSidebar } from "vitepress-sidebar";
import { zh } from "./zh";
import { en } from "./en";

let defaultLocale = "zh";
const commonSidebarOptions = {
  collapsed: true,
  convertSameNameSubFileToGroupIndexPage: true,
  useTitleFromFrontmatter: true,
  useFolderTitleFromIndexFile: true,
  useFolderLinkFromIndexFile: true,
  includeFolderIndexFile: true,
  sortMenusByFrontmatterOrder: true,
  rootGroupText: "LITEYUKIBOT",
};

/**
 * Generate sidebar config
 * multiple languages and sections
 * @returns {any[]}
 */
function generateSidebarConfig(): any[] {
  let sections = ["dev", "store", "usage", "deploy"];
  let languages = ["zh", "en"];
  let ret = [];
  for (let language of languages) {
    for (let section of sections) {
      if (language === defaultLocale) {
        ret.push({
          basePath: `/${section}/`,
          scanStartPath: `${language}/${section}`,
          resolvePath: `/${section}/`,
          ...commonSidebarOptions,
        });
      } else {
        ret.push({
          basePath: `/${language}/${section}/`,
          scanStartPath: `${language}/${section}`,
          resolvePath: `/${language}/${section}/`,
          ...commonSidebarOptions,
        });
      }
    }
  }
  return ret;
}

export const common = defineConfig({
  head: [
    // 配置favicon.ico
    ["link", { rel: "icon", type: "image/x-icon", href: "favicon.ico" }],
    [
      "link",
      {
        rel: "stylesheet",
        href: "https://fonts.font.im/css?family=Cousine:400,400i,700,700i|Poppins:100,100i,200,200i,300,300i,400,400i,500,500i,600,600i,700,700i,800,800i,900,900i",
      },
    ],
    ["script", { src: "https://cdn.liteyuki.icu/js/liteyuki_footer.js" }],
  ],
  rewrites: {
    [`${defaultLocale}/:rest*`]: ":rest*",
  },
  cleanUrls: false,
  themeConfig: {
    logo: {
      light: "/liteyuki.svg",
      dark: "/liteyuki-dark.svg",
      alt: "LiteyukiBot Logo",
    },
    sidebar: generateSidebar([...generateSidebarConfig()]),
    socialLinks: [
      { icon: "github", link: "https://github.com/LiteyukiStudio/LiteyukiBot" },
      {
        icon: {
          svg: '<svg t="1725391346807" class="icon" viewBox="0 0 1025 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5067" width="256" height="256"><path d="M1004.692673 466.396616l-447.094409-447.073929c-25.743103-25.763582-67.501405-25.763582-93.264987 0l-103.873521 103.873521 78.171378 78.171378c12.533635-6.00058 26.562294-9.359266 41.389666-9.359266 53.02219 0 96.00928 42.98709 96.00928 96.00928 0 14.827372-3.358686 28.856031-9.359266 41.389666l127.97824 127.97824c12.533635-6.00058 26.562294-9.359266 41.389666-9.359266 53.02219 0 96.00928 42.98709 96.00928 96.00928s-42.98709 96.00928-96.00928 96.00928-96.00928-42.98709-96.00928-96.00928c0-14.827372 3.358686-28.856031 9.359266-41.389666l-127.97824-127.97824c-3.051489 1.454065-6.184898 2.744293-9.379746 3.870681l0 266.97461c37.273227 13.188988 63.99936 48.721433 63.99936 90.520695 0 53.02219-42.98709 96.00928-96.00928 96.00928s-96.00928-42.98709-96.00928-96.00928c0-41.799262 26.726133-77.331707 63.99936-90.520695l0-266.97461c-37.273227-13.188988-63.99936-48.721433-63.99936-90.520695 0-14.827372 3.358686-28.856031 9.359266-41.389666l-78.171378-78.171378-295.892081 295.871601c-25.743103 25.784062-25.743103 67.542365 0 93.285467l447.114889 447.073929c25.743103 25.743103 67.480925 25.743103 93.264987 0l445.00547-445.00547c25.763582-25.763582 25.763582-67.542365 0-93.285467z" fill="#a2d8f4" p-id="5068"></path></svg>',
        },
        link: "https://git.liteyuki.icu/bot/app",
      },
      {
        icon: {
          svg: '<svg t="1736700504329" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="14158" width="200" height="200"><path d="M944.355556 142.222222c-17.066667-22.755556-45.511111-34.133333-79.644445-34.133333-28.444444 0-68.266667 5.688889-108.088889 22.755555h-5.688889c17.066667 11.377778 34.133333 28.444444 51.2 39.822223 56.888889-17.066667 91.022222-11.377778 96.711111 0 11.377778 11.377778 5.688889 45.511111-22.755555 91.022222 11.377778 17.066667 17.066667 34.133333 28.444444 51.2 0 0 0 5.688889 5.688889 5.688889 22.755556-34.133333 34.133333-62.577778 45.511111-91.022222 11.377778-28.444444 5.688889-62.577778-11.377777-85.333334z" p-id="14159" fill="#a2d8f4"></path><path d="M267.377778 512a45.511111 45.511111 0 1 0 91.022222 0 45.511111 45.511111 0 1 0-91.022222 0Z" p-id="14160" fill="#a2d8f4"></path><path d="M625.777778 614.4c-113.777778 85.333333-227.555556 153.6-324.266667 193.422222-11.377778 5.688889-17.066667 5.688889-28.444444 11.377778 22.755556 17.066667 51.2 34.133333 79.644444 45.511111 51.2 22.755556 108.088889 34.133333 164.977778 34.133333s113.777778-11.377778 164.977778-34.133333c51.2-22.755556 96.711111-51.2 136.533333-91.022222 39.822222-39.822222 68.266667-85.333333 91.022222-130.844445 22.755556-51.2 34.133333-108.088889 34.133334-159.288888 0-51.2-11.377778-102.4-28.444445-153.6-5.688889 5.688889-11.377778 17.066667-17.066667 22.755555-68.266667 79.644444-164.977778 176.355556-273.066666 261.688889zM813.511111 187.733333c-5.688889-5.688889-11.377778-5.688889-11.377778-11.377777-17.066667-17.066667-34.133333-28.444444-51.2-39.822223-22.755556-11.377778-45.511111-28.444444-68.266666-34.133333-56.888889-28.444444-108.088889-39.822222-164.977778-39.822222s-113.777778 11.377778-164.977778 34.133333c-51.2 22.755556-96.711111 51.2-136.533333 91.022222-39.822222 34.133333-68.266667 79.644444-91.022222 130.844445-22.755556 51.2-34.133333 108.088889-34.133334 159.288889 0 51.2 11.377778 96.711111 22.755556 142.222222-22.755556 34.133333-39.822222 68.266667-51.2 96.711111-11.377778 39.822222-5.688889 68.266667 11.377778 91.022222 17.066667 22.755556 45.511111 34.133333 79.644444 34.133334h11.377778c28.444444 0 62.577778-11.377778 96.711111-22.755556-17.066667-11.377778-34.133333-28.444444-51.2-39.822222-51.2 11.377778-85.333333 11.377778-96.711111 0 0-17.066667 5.688889-45.511111 34.133333-96.711111 17.066667 34.133333 39.822222 62.577778 68.266667 91.022222h5.688889c17.066667-5.688889 39.822222-11.377778 62.577777-17.066667 91.022222-34.133333 204.8-102.4 307.2-187.733333 108.088889-85.333333 199.111111-170.666667 256-250.311111l34.133334-51.2c-22.755556-28.444444-39.822222-56.888889-68.266667-79.644445z m-500.622222 420.977778c-56.888889 0-102.4-45.511111-102.4-102.4s45.511111-102.4 102.4-102.4S409.6 455.111111 409.6 512c0 51.2-45.511111 96.711111-96.711111 96.711111z" p-id="14161" fill="#a2d8f4"></path></svg>',
        },
        link: "https://lab.liteyuki.icu/@LiteyukiBot",
      },
    ],
    search: {
      provider: "local",
      options: {
        locales: {
          root: {
            translations: {
              button: {
                buttonText: "搜索文档",
                buttonAriaLabel: "打开搜索框",
              },
              modal: {
                noResultsText: "没有找到搜索结果",
                resetButtonTitle: "清除查询条件",
                footer: {
                  selectText: "选择",
                  navigateText: "切换",
                },
              },
            },
          },
          en: {
            translations: {
              button: {
                buttonText: "Search",
                buttonAriaLabel: "Search",
              },
              modal: {
                noResultsText: "No results found",
                resetButtonTitle: "Reset search query",
                footer: {
                  selectText: "Select",
                  navigateText: "Navigate",
                },
              },
            },
          },
        },
      },
    },
  },
  sitemap: {
    hostname: "https://bot.liteyuki.icu",
  },
  lastUpdated: true,
  locales: {
    root: { label: "简体中文", ...zh },
    en: { label: "English", ...en },
  },
});
