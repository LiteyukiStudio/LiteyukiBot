export const locales = ["en-US", "zh-CN"] as const;

export type Locale = (typeof locales)[number];

const enUS = {
  "app.name": "Liteyuki", "app.subtitle": "Signal Ledger", "app.local": "Local instance",
  "nav.overview": "Overview", "nav.events": "Events", "nav.topology": "Topology", "nav.runtimes": "Runtimes", "nav.plugins": "Plugins", "nav.functions": "Functions", "nav.configuration": "Configuration",
  "header.language": "Language", "header.theme": "Theme", "header.accent": "Accent color", "header.openMenu": "Open navigation",
  "theme.system": "System", "theme.light": "Light", "theme.dark": "Dark", "accent.blue": "Blue", "accent.lilac": "Lilac", "accent.teal": "Teal",
  "status.healthy": "Healthy", "status.attention": "Attention", "status.critical": "Critical", "status.neutral": "Neutral", "status.running": "Running", "status.stopped": "Stopped", "status.recovering": "Recovering", "status.enabled": "Enabled", "status.disabled": "Disabled", "status.ready": "Ready",
  "overview.title": "Operational overview", "overview.summary": "Local operation state", "overview.runtime": "Runtime health", "overview.ledger": "Event ledger", "overview.evidence": "Recent evidence", "overview.allEvents": "View events", "overview.openOperation": "New operation", "overview.activeRuntimes": "Active runtimes", "overview.enabledPlugins": "Enabled plugins", "overview.eventRate": "Event rate", "overview.faults": "Unresolved faults",
  "events.title": "Events", "events.summary": "Ordered runtime and action trace", "events.filter": "Filter events", "events.filterPlaceholder": "Filter by source or trace", "events.category": "Category", "events.all": "All records", "events.trace": "Trace", "events.source": "Source", "events.time": "Time", "events.empty": "No matching event records", "events.detail": "Event detail", "events.viewTrace": "View trace",
  "topology.title": "Topology", "topology.summary": "Resolved local ownership graph", "topology.kernel": "Kernel", "topology.runtime": "Runtime", "topology.plugin": "Plugin", "topology.route": "Event route", "topology.noRoutes": "No configured event routes",
  "runtimes.title": "Runtimes", "runtimes.summary": "Supervised protocol hosts", "runtimes.runtime": "Runtime", "runtimes.kind": "Kind", "runtimes.uptime": "Uptime", "runtimes.protocol": "Protocol", "runtimes.capabilities": "Capabilities", "runtimes.activity": "Activity", "runtimes.detail": "Runtime detail", "runtimes.actions": "Runtime actions",
  "plugins.title": "Plugins", "plugins.summary": "Installed native extensions", "plugins.plugin": "Plugin", "plugins.version": "Version", "plugins.capabilities": "Capabilities", "plugins.detail": "Plugin detail", "plugins.surface": "Contributed surface", "plugins.noSurface": "This plugin does not contribute a surface.", "plugins.operations": "Plugin operations",
  "functions.title": "Functions", "functions.summary": "Indexed function resources", "functions.function": "Function", "functions.source": "Source", "functions.handlers": "Handlers", "functions.diagnostics": "Diagnostics", "functions.detail": "Function detail", "functions.readOnly": "Source is available for inspection only.", "functions.runCheck": "Run controlled check",
  "configuration.title": "Configuration", "configuration.summary": "Read-only instance settings", "configuration.version": "Configuration version", "configuration.webui": "WebUI service", "configuration.data": "Data directory", "configuration.mode": "Mode", "configuration.review": "Configuration changes remain in the local configuration file.",
  "setup.title": "Set up the local instance", "setup.summary": "A runtime or plugin source is required before operational data can be collected.", "setup.runtime": "Runtime", "setup.pluginSource": "Plugin source", "setup.create": "Create local instance", "setup.skip": "View empty workspace", "setup.ready": "Configuration is ready for the first runtime.",
  "operation.title": "Submit operation", "operation.summary": "Operations are recorded before the daemon executes them.", "operation.target": "Target", "operation.confirm": "Confirm target", "operation.confirmHint": "Enter the target identifier to continue.", "operation.cancel": "Cancel", "operation.submit": "Queue operation", "operation.queued": "Operation queued", "operation.queuedDetail": "The operation has been added to the local ledger.", "operation.highImpact": "High impact", "operation.standard": "Standard", "operation.close": "Close operation panel",
  "drawer.close": "Close detail", "detail.id": "Record", "detail.status": "Status", "detail.trace": "Trace", "detail.source": "Source", "detail.evidence": "Evidence", "detail.noEvidence": "No additional diagnostic evidence is available.",
  "common.open": "Open", "common.close": "Close", "common.back": "Back", "common.refresh": "Refresh", "common.notAvailable": "Not available", "common.updated": "Updated", "common.action": "Action", "common.state": "State", "common.name": "Name", "common.none": "None",
} satisfies Record<string, string>;

export type MessageKey = keyof typeof enUS;
export type Messages = Record<MessageKey, string>;

const zhCN: Messages = {
  "app.name": "Liteyuki", "app.subtitle": "信号账本", "app.local": "本地实例",
  "nav.overview": "概览", "nav.events": "事件", "nav.topology": "拓扑", "nav.runtimes": "运行时", "nav.plugins": "插件", "nav.functions": "函数", "nav.configuration": "配置",
  "header.language": "语言", "header.theme": "主题", "header.accent": "强调色", "header.openMenu": "打开导航",
  "theme.system": "跟随系统", "theme.light": "浅色", "theme.dark": "深色", "accent.blue": "蓝色", "accent.lilac": "薰衣草", "accent.teal": "青色",
  "status.healthy": "健康", "status.attention": "需关注", "status.critical": "严重", "status.neutral": "中性", "status.running": "运行中", "status.stopped": "已停止", "status.recovering": "恢复中", "status.enabled": "已启用", "status.disabled": "已禁用", "status.ready": "就绪",
  "overview.title": "运行概览", "overview.summary": "本地运行状态", "overview.runtime": "运行时健康状态", "overview.ledger": "事件账本", "overview.evidence": "最近证据", "overview.allEvents": "查看事件", "overview.openOperation": "新建操作", "overview.activeRuntimes": "活跃运行时", "overview.enabledPlugins": "已启用插件", "overview.eventRate": "事件速率", "overview.faults": "未解决故障",
  "events.title": "事件", "events.summary": "有序的运行时与 Action 追踪", "events.filter": "筛选事件", "events.filterPlaceholder": "按来源或追踪筛选", "events.category": "类别", "events.all": "全部记录", "events.trace": "追踪", "events.source": "来源", "events.time": "时间", "events.empty": "没有匹配的事件记录", "events.detail": "事件详情", "events.viewTrace": "查看追踪",
  "topology.title": "拓扑", "topology.summary": "已解析的本地所有权图", "topology.kernel": "内核", "topology.runtime": "运行时", "topology.plugin": "插件", "topology.route": "事件路由", "topology.noRoutes": "没有已配置的事件路由",
  "runtimes.title": "运行时", "runtimes.summary": "受监管的协议宿主", "runtimes.runtime": "运行时", "runtimes.kind": "类型", "runtimes.uptime": "运行时长", "runtimes.protocol": "协议", "runtimes.capabilities": "能力", "runtimes.activity": "活动", "runtimes.detail": "运行时详情", "runtimes.actions": "运行时操作",
  "plugins.title": "插件", "plugins.summary": "已安装的原生扩展", "plugins.plugin": "插件", "plugins.version": "版本", "plugins.capabilities": "能力", "plugins.detail": "插件详情", "plugins.surface": "贡献页面", "plugins.noSurface": "此插件未贡献页面。", "plugins.operations": "插件操作",
  "functions.title": "函数", "functions.summary": "已索引的函数资源", "functions.function": "函数", "functions.source": "来源", "functions.handlers": "处理器", "functions.diagnostics": "诊断", "functions.detail": "函数详情", "functions.readOnly": "源码仅可用于查看。", "functions.runCheck": "运行受控检查",
  "configuration.title": "配置", "configuration.summary": "只读实例设置", "configuration.version": "配置版本", "configuration.webui": "WebUI 服务", "configuration.data": "数据目录", "configuration.mode": "模式", "configuration.review": "配置更改仍在本地配置文件中完成。",
  "setup.title": "设置本地实例", "setup.summary": "收集运行数据前需要添加运行时或插件来源。", "setup.runtime": "运行时", "setup.pluginSource": "插件来源", "setup.create": "创建本地实例", "setup.skip": "查看空工作台", "setup.ready": "配置已准备好供首个运行时使用。",
  "operation.title": "提交操作", "operation.summary": "操作会在 daemon 执行前被记录。", "operation.target": "目标", "operation.confirm": "确认目标", "operation.confirmHint": "输入目标标识以继续。", "operation.cancel": "取消", "operation.submit": "加入操作队列", "operation.queued": "操作已排队", "operation.queuedDetail": "操作已加入本地账本。", "operation.highImpact": "高影响", "operation.standard": "常规", "operation.close": "关闭操作面板",
  "drawer.close": "关闭详情", "detail.id": "记录", "detail.status": "状态", "detail.trace": "追踪", "detail.source": "来源", "detail.evidence": "证据", "detail.noEvidence": "没有其他诊断证据。",
  "common.open": "打开", "common.close": "关闭", "common.back": "返回", "common.refresh": "刷新", "common.notAvailable": "不可用", "common.updated": "已更新", "common.action": "操作", "common.state": "状态", "common.name": "名称", "common.none": "无",
};

export const messages: Record<Locale, Messages> = { "en-US": enUS, "zh-CN": zhCN };

export function resolveLocale(value: string | null): Locale {
  return locales.includes(value as Locale) ? (value as Locale) : "en-US";
}
