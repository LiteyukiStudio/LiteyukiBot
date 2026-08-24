import { Bug, CircleCheck, CircleX, Info, LoaderCircle, PanelLeft, PanelsTopLeft, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";
import type { WebUiLayout } from "@/models/api";

import { SurfaceCard } from "@/components/surface-card";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/i18n/locale";

const states = [
  ["success", CircleCheck],
  ["error", CircleX],
  ["info", Info],
  ["warning", TriangleAlert],
] as const;

export function DeveloperView({ layout, changeLayout, duration, changeDuration }: { layout: WebUiLayout; changeLayout: (layout: WebUiLayout) => void; duration: number; changeDuration: (duration: number) => void }) {
  const { t } = useLocale();
  const [type, setType] = useState("success");
  const [durationText, setDurationText] = useState(String(duration));
  const [message, setMessage] = useState("");
  const labels = { success: t("webui.developer.toast_success"), error: t("webui.developer.toast_error"), info: t("webui.developer.toast_info"), warning: t("webui.developer.toast_warning") };
  const showToast = (state = type) => {
    const text = message || t("webui.developer.toast_message", { state: labels[state as keyof typeof labels] ?? state });
    const options = { duration };
    if (state === "success") toast.success(text, options);
    else if (state === "error") toast.error(text, options);
    else if (state === "warning") toast.warning(text, options);
    else toast.info(text, options);
  };
  const showLoading = () => {
    const id = toast.loading(message || t("webui.developer.toast_loading_message"));
    window.setTimeout(() => toast.success(t("webui.developer.toast_message", { state: labels.success }), { id, duration }), 1200);
  };
  const controls = <div className="webui-developer-controls">
    <label>Type<select value={type} onChange={(event) => setType(event.target.value)}>{Object.keys(labels).map((state) => <option value={state} key={state}>{labels[state as keyof typeof labels]}</option>)}</select></label>
    <label>Duration<select value={durationText} onChange={(event) => { setDurationText(event.target.value); changeDuration(Number(event.target.value)); }}><option value="1500">1500 ms</option><option value="3000">3000 ms</option><option value="6000">6000 ms</option></select></label>
    <label className="webui-developer-message">Message<input value={message} onChange={(event) => setMessage(event.target.value)} placeholder={t("webui.developer.toast_message", { state: labels[type as keyof typeof labels] })} /></label>
  </div>;
  const toastButtons = <div className="flex flex-wrap gap-2">{states.map(([state, Icon]) => <Button key={state} variant="outline" onClick={() => showToast(state)}><Icon size={15} />{labels[state]}</Button>)}<Button variant="outline" onClick={showLoading}><LoaderCircle size={15} />{t("webui.developer.toast_loading")}</Button></div>;

  return <div className="webui-developer-view">
    <header className="webui-plugin-header"><div><h2 className="webui-plugin-title"><Bug size={20} className="text-primary" />{t("webui.developer.title")}</h2></div></header>
    <div className="webui-developer-layout-switch" role="group"><Button variant={layout === "sidebar" ? "secondary" : "outline"} size="sm" onClick={() => changeLayout("sidebar")}><PanelLeft size={15} />Sidebar</Button><Button variant={layout === "inline" ? "secondary" : "outline"} size="sm" onClick={() => changeLayout("inline")}><PanelsTopLeft size={15} />Inline</Button><Button variant={layout === "main-sidebar" ? "secondary" : "outline"} size="sm" onClick={() => changeLayout("main-sidebar")}><PanelLeft size={15} />Main sidebar</Button></div>
    {layout === "sidebar" ? <div className="webui-developer-sidebar-layout"><nav className="webui-developer-subnav"><Button variant="ghost" className="webui-sidebar-control webui-developer-sidebar-select justify-start" data-active="true">{t("webui.developer.toast_section")}</Button></nav><SurfaceCard><CardHeader><CardTitle className="text-sm font-semibold">{t("webui.developer.toast_section")}</CardTitle></CardHeader><CardContent className="grid gap-4">{controls}{toastButtons}</CardContent></SurfaceCard></div> : <SurfaceCard><CardHeader><CardTitle className="text-sm font-semibold">{t("webui.developer.toast_section")}</CardTitle></CardHeader><CardContent className="grid gap-4">{controls}{toastButtons}</CardContent></SurfaceCard>}
  </div>;
}
