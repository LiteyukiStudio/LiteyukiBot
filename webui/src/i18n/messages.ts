export const locales = ["en-US", "zh-CN"] as const;

export type Locale = (typeof locales)[number];

const enUS = {
  "app.name": "Liteyuki",
  "app.subtitle": "Local operations",
  "nav.overview": "Overview",
  "nav.events": "Events",
  "nav.topology": "Topology",
  "nav.runtimes": "Runtimes",
  "nav.plugins": "Plugins",
  "nav.functions": "Functions",
  "nav.configuration": "Configuration",
  "header.local": "Local instance",
  "header.language": "Language",
  "header.theme": "Theme",
  "health.unavailable": "Instance unavailable",
  "health.unavailableDetail": "Start an instance to view its current state.",
  "health.faults": "Unresolved faults",
  "overview.title": "Operational overview",
  "overview.ledger": "Event ledger",
  "overview.ledgerEmpty": "No event records are available.",
  "overview.runtimeHealth": "Runtime health",
  "overview.runtimeEmpty": "No runtime status is available.",
  "overview.evidence": "Recent evidence",
  "overview.evidenceEmpty": "No diagnostic evidence is available.",
  "workspace.emptyTitle": "No data available",
  "workspace.emptyDetail": "This view will show information when the local instance is running.",
  "theme.system": "System",
  "theme.light": "Light",
  "theme.dark": "Dark",
} satisfies Record<string, string>;

export type MessageKey = keyof typeof enUS;
export type Messages = Record<MessageKey, string>;

const zhCN: Messages = {
  "app.name": "Liteyuki",
  "app.subtitle": "本地运维",
  "nav.overview": "概览",
  "nav.events": "事件",
  "nav.topology": "拓扑",
  "nav.runtimes": "运行时",
  "nav.plugins": "插件",
  "nav.functions": "函数",
  "nav.configuration": "配置",
  "header.local": "本地实例",
  "header.language": "语言",
  "header.theme": "主题",
  "health.unavailable": "实例不可用",
  "health.unavailableDetail": "启动实例后可查看当前状态。",
  "health.faults": "未解决故障",
  "overview.title": "运行概览",
  "overview.ledger": "事件账本",
  "overview.ledgerEmpty": "暂无事件记录。",
  "overview.runtimeHealth": "运行时健康状态",
  "overview.runtimeEmpty": "暂无运行时状态。",
  "overview.evidence": "最近证据",
  "overview.evidenceEmpty": "暂无诊断证据。",
  "workspace.emptyTitle": "暂无数据",
  "workspace.emptyDetail": "本地实例运行后，此处将显示相关信息。",
  "theme.system": "跟随系统",
  "theme.light": "浅色",
  "theme.dark": "深色",
};

export const messages: Record<Locale, Messages> = {
  "en-US": enUS,
  "zh-CN": zhCN,
};

export function resolveLocale(value: string | null): Locale {
  return locales.includes(value as Locale) ? (value as Locale) : "en-US";
}
