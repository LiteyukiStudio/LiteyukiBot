import {ref} from "vue";

import {useData} from "vitepress";

const i18nData = {
    en: {
        online: 'Online',
        offline: 'Offline',
        total: 'Total',
        fetching: 'Fetching',
        stars: 'Stars',
        forks: 'Forks',
        issues: 'Issues',
        prs: 'Pull Requests',
        size: 'Size',
        plugins: 'Plugins',
        resources: 'Resources',
    },
    zh: {
        online: '在线',
        offline: '离线',
        total: '实例',
        fetching: '获取中',
        stars: '星星',
        forks: '叉子',
        issues: '开启议题',
        prs: '合并请求',
        size: '大小',
        plugins: '插件',
        resources: '主题资源',
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