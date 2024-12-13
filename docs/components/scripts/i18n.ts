import {ref} from "vue";

import {useData} from "vitepress";

const i18nData = {
    en: {
        stats: 'Stats',
        online: 'Online',
        offline: 'Offline',
        total: 'Total',
        fetching: 'Fetching',
        stars: 'Stars',
        forks: 'Forks',
        issues: 'Issues',
        prs: 'Pull Requests',
        visitors: 'Visitors',
        size: 'Size',
        plugins: 'Plugins',
        resources: 'Resources',
        pluginStore: 'Plugin Store',
        pluginStoreDesc: 'Content from the LightSnow Plugin Store, LightSnow supports NoneBot through the lpnonebot plugin, and references some NoneBot plugins',
        liteyukiOnly: 'Liteyuki Only',
        search: 'Search',
        resourceStore: 'Resources Store',
        thx_contributors: 'Thanks the following contributors!',
        easterEgg: 'Congratulations on finding the Easter egg!',

        publishPlugin: 'Publish Plugin',
        publishRes: 'Publish Resource',
        closeButtonText: 'Close',
        submitButtonText: 'Submit',

        resName: 'Name',
        resDesc: 'Description',
        resAuthor: 'Author',
        resLink: 'Download Link',
        resHomepage: 'Homepage',

        resNameText: 'Example: Kawaii Style Theme',
        resDescText: 'Example: A kawaii style and color theme',
        resAuthorText: 'Usually the github username, Example: yanyongyu',
        resLinkText: 'Direct download link, usually zip package link',
        resHomepageText: 'Optional, can be the name of the git platform repository"',
    },
    zh: {
        stats: '统计信息',
        online: '在线',
        offline: '离线',
        total: '实例',
        fetching: '获取中',
        stars: '星星',
        forks: '分叉',
        issues: '议题',
        prs: '拉取请求',
        visitors: '访客',
        size: '大小',
        plugins: '插件',
        resources: '主题资源',
        store: '商店',
        pluginStore: '插件商店',
        pluginStoreDesc: '内容来自轻雪插件商店，轻雪通过lpnonebot插件对NoneBot实现支持，引用了部分NoneBot插件',
        liteyukiOnly: '仅轻雪',
        search: '搜索',
        resourceStore: '资源商店',
        thx_contributors: '感谢以下贡献者！',
        easterEgg: '恭喜你发现了彩蛋！',

        publishPlugin: '发布插件',
        publishRes: '发布资源',
        closeButtonText: '关闭',
        submitButtonText: '提交',

        resName: '名称',
        resDesc: '描述',
        resAuthor: '作者',
        resLink: '下载链接',
        resHomepage: '主页',

        resNameText: '示例：可爱风格主题',
        resDescText: '示例：一个可爱风格和配色的主题',
        resAuthorText: '通常为github用户名，示例：yanyongyu',
        resLinkText: '直接下载链接，通常为zip包链接',
        resHomepageText: '可选，可为git平台仓库名',
    }
}

let refData = {}

function getText(lang: string, key: string): string {
    lang = formatLang(lang);
    return i18nData[lang][key];
}

export  function formatLang(lang: string): string {
    if (lang.includes('-')) {
        return lang.split('-')[0];
    }
    return lang;
}

export function updateRefData() {
    const lang = formatLang(useData().site.value.lang);
    for (let key in refData) {
        refData[key].value = getText(lang, key);
    }
}

export function getTextRef(key: string): any {
    const lang = formatLang(useData().site.value.lang);
    refData[key] = getText(lang, key);
    return refData[key] || key;
}
