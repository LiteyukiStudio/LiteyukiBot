// 共有配置项，导入index用

import {defineConfig} from 'vitepress'
import {generateSidebar} from 'vitepress-sidebar';
import {zh} from "./zh";
import {en} from "./en";

let defaultLocale = 'zh';
const commonSidebarOptions = {
    collapsed: true,
    convertSameNameSubFileToGroupIndexPage: true,
    useTitleFromFrontmatter: true,
    useFolderTitleFromIndexFile: true,
    useFolderLinkFromIndexFile: true,
    includeFolderIndexFile: true,
    sortMenusByFrontmatterOrder: true,
    rootGroupText: 'LITEYUKIBOT',
}

/**
 * Generate sidebar config
 * multiple languages and sections
 * @returns {any[]}
 */
function generateSidebarConfig(): any[] {
    let sections = ["dev", "store", "usage", "deploy"]
    let languages = ['zh', 'en']
    let ret = []
    for (let language of languages) {
        for (let section of sections) {
            if (language === defaultLocale) {
                ret.push({
                    basePath: `/${section}/`,
                    scanStartPath: `${language}/${section}`,
                    resolvePath: `/${section}/`,
                    ...commonSidebarOptions
                })
            } else {
                ret.push({
                    basePath: `/${language}/${section}/`,
                    scanStartPath: `${language}/${section}`,
                    resolvePath: `/${language}/${section}/`,
                    ...commonSidebarOptions
                })
            }
        }
    }
    return ret
}

console.log(generateSidebarConfig())

export const common = defineConfig({
    head: [
        // 配置favicon.ico
        ['link', {rel: 'icon', type: 'image/x-icon', href: 'favicon.ico'}],
        ['link', {rel: 'stylesheet', href: 'https://fonts.font.im/css?family=Cousine:400,400i,700,700i|Poppins:100,100i,200,200i,300,300i,400,400i,500,500i,600,600i,700,700i,800,800i,900,900i'}],
    ],
    rewrites: {
        [`${defaultLocale}/:rest*`]: ":rest*",
    },
    themeConfig: {
        logo: {
            light: '/liteyuki.svg',
            dark: '/liteyuki-dark.svg',
            alt: 'LiteyukiBot Logo'
        },
        sidebar: generateSidebar(
            [
                ...generateSidebarConfig()
            ]
        ),
        socialLinks: [
            {icon: 'github', link: 'https://github.com/LiteyukiStudio/LiteyukiBot'},
            {
                icon: {
                    svg: '<svg t="1725391346807" class="icon" viewBox="0 0 1025 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5067" width="256" height="256"><path d="M1004.692673 466.396616l-447.094409-447.073929c-25.743103-25.763582-67.501405-25.763582-93.264987 0l-103.873521 103.873521 78.171378 78.171378c12.533635-6.00058 26.562294-9.359266 41.389666-9.359266 53.02219 0 96.00928 42.98709 96.00928 96.00928 0 14.827372-3.358686 28.856031-9.359266 41.389666l127.97824 127.97824c12.533635-6.00058 26.562294-9.359266 41.389666-9.359266 53.02219 0 96.00928 42.98709 96.00928 96.00928s-42.98709 96.00928-96.00928 96.00928-96.00928-42.98709-96.00928-96.00928c0-14.827372 3.358686-28.856031 9.359266-41.389666l-127.97824-127.97824c-3.051489 1.454065-6.184898 2.744293-9.379746 3.870681l0 266.97461c37.273227 13.188988 63.99936 48.721433 63.99936 90.520695 0 53.02219-42.98709 96.00928-96.00928 96.00928s-96.00928-42.98709-96.00928-96.00928c0-41.799262 26.726133-77.331707 63.99936-90.520695l0-266.97461c-37.273227-13.188988-63.99936-48.721433-63.99936-90.520695 0-14.827372 3.358686-28.856031 9.359266-41.389666l-78.171378-78.171378-295.892081 295.871601c-25.743103 25.784062-25.743103 67.542365 0 93.285467l447.114889 447.073929c25.743103 25.743103 67.480925 25.743103 93.264987 0l445.00547-445.00547c25.763582-25.763582 25.763582-67.542365 0-93.285467z" fill="#a2d8f4" p-id="5068"></path></svg>'
                },
                link: "https://git.liteyuki.icu/LiteyukiStudio/LiteyukiBot"
            }
        ],
        search: {
            provider: 'local',
            options: {
                locales: {
                    root: {
                        translations: {
                            button: {
                                buttonText: '搜索文档',
                                buttonAriaLabel: '打开搜索框',
                            },
                            modal: {
                                noResultsText: '没有找到搜索结果',
                                resetButtonTitle: '清除查询条件',
                                footer: {
                                    selectText: '选择',
                                    navigateText: '切换',
                                }
                            }
                        },
                    },
                    en: {
                        translations: {
                            button: {
                                buttonText: 'Search',
                                buttonAriaLabel: 'Search',
                            },
                            modal: {
                                noResultsText: 'No results found',
                                resetButtonTitle: 'Reset search query',
                                footer: {
                                    selectText: 'Select',
                                    navigateText: 'Navigate',
                                }
                            }
                        }
                    },
                }
            }
        }
    },
    sitemap: {
        hostname: 'https://bot.liteyuki.icu'
    },
    lastUpdated: true,
    locales: {
        root: {label: "简体中文", ...zh},
        en: {label: "English", ...en},
    },

})