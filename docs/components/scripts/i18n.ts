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
        visitors: 'Visitor',
        size: 'Size',
        plugins: 'Plugins',
        resources: 'Resources',
        pluginStore: 'Plugin Store',
        pluginStoreDesc: 'Content from the LightSnow Plugin Store, LightSnow supports NoneBot through the lpnonebot plugin, and references some NoneBot plugins',
        liteyukiOnly: 'Liteyuki Only',
        search: 'Search',
        resourceStore: 'Resources Store',
    },
    zh: {
        stats: '统计信息',
        online: '在线',
        offline: '离线',
        total: '实例',
        fetching: '获取中',
        stars: '星标',
        forks: '分叉',
        issues: '开启议题',
        prs: '合并请求',
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
    }
}

let refData = {}

function getText(lang: string, key: string): string {
    lang = formatLang(lang);
    return i18nData[lang][key];
}

function formatLang(lang: string): string {
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
    return refData[key]
}