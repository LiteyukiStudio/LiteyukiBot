import {useData} from "vitepress";

const i18nData = {
    "zh": {
        online: '当前在线',
        offline: '离线',
        total: '全球实例',
        fetching: '获取中',
    },
    "en": {
        online: 'Online',
        offline: 'Offline',
        total: 'Total',
        fetching: 'Fetching',
    }
}

export default function getText(key: string): string {
    // 转换语言
    // zh-Hans -> zh
    // en-US -> en
    if (useData().site.value.lang.includes('-')) {
        return i18nData[useData().site.value.lang.split('-')[0]][key];
    }
    return i18nData[useData().site.value.lang][key];
}