export const locales = ["en-US", "zh-CN"] as const;

export type Locale = (typeof locales)[number];

const enUS = {
  "app.name": "Liteyuki",
  "app.subtitle": "Signal Ledger",
  "nav.overview": "Overview",
  "nav.events": "Events",
  "nav.topology": "Topology",
  "nav.runtimes": "Runtimes",
  "nav.plugins": "Plugins",
  "nav.configuration": "Configuration",
  "header.language": "Language",
  "header.theme": "Theme",
  "header.openMenu": "Open navigation",
  "theme.system": "System",
  "theme.light": "Light",
  "theme.dark": "Dark",
  "status.ready": "Ready",
  "status.runtimes": "{active} / {total} runtimes",
  "common.refresh": "Refresh",
} as const;

export type MessageKey = keyof typeof enUS;
export type Messages = Record<MessageKey, string>;

const zhCN: Messages = {
  "app.name": "Liteyuki",
  "app.subtitle": "信号账本",
  "nav.overview": "概览",
  "nav.events": "事件",
  "nav.topology": "拓扑",
  "nav.runtimes": "运行时",
  "nav.plugins": "插件",
  "nav.configuration": "配置",
  "header.language": "语言",
  "header.theme": "主题",
  "header.openMenu": "打开导航",
  "theme.system": "跟随系统",
  "theme.light": "浅色",
  "theme.dark": "深色",
  "status.ready": "就绪",
  "status.runtimes": "{active} / {total} 个运行时",
  "common.refresh": "刷新",
};

export const messages: Record<Locale, Messages> = { "en-US": enUS, "zh-CN": zhCN };

export function resolveLocale(value: string | null | undefined): Locale {
  if (value?.toLowerCase().startsWith("zh")) return "zh-CN";
  return "en-US";
}
