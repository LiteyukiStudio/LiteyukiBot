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
    },
    zh: {
        online: '在线',
        offline: '离线',
        total: '实例',
        fetching: '获取中',
        stars: '星星',
        forks: '叉子',
        issues: '议题',
        prs: '合并',
    }
}

let refData = {}

function getText(lang: string, key: string): string {
    lang = formatLang(lang);
    return i18nData[key][key];
}

function formatLang(lang: string): string {
    if (lang.includes('-')) {
        return lang.split('-')[0];
    }
    return lang;
}

export function updateRef() {
    const lang = useData().site.value.lang;
    for (let key in refData) {
        refData[key].value = getText(lang, key);
    }
}

export function getTextRef(key: string): any {
    const lang = formatLang(useData().site.value.lang);
    refData[key] = ref(i18nData[lang][key]);
    return refData[key]
}