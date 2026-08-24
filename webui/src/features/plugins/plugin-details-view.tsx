import { useState } from "react";
import { ArrowLeft, Download, ExternalLink, Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PluginDetails } from "@/models/api";
import { useLocale } from "@/i18n/locale";

export function PluginDetailsView({ details, followed, toggleFollowed, close }: { details: PluginDetails; followed: boolean; toggleFollowed: () => Promise<void>; close: () => void }) {
  const { t } = useLocale();
  const [section, setSection] = useState<"description" | "changelog" | "versions">("description");
  const plugin = details.selected;
  return <div className="webui-plugin-detail-view">
    <div className="webui-plugin-detail-heading"><Button variant="ghost" size="sm" onClick={close}><ArrowLeft size={15} />{t("webui.action.back")}</Button><div className="min-w-0"><h2 className="webui-plugin-title">{plugin.display_name}</h2><p className="webui-plugin-muted">{plugin.bundle_id} · {plugin.version}</p></div><div className="webui-plugin-detail-actions"><Button size="icon" variant="outline" aria-label={t("webui.plugins.followed")} onClick={() => void toggleFollowed()}><Star size={16} fill={followed ? "currentColor" : "none"} /></Button>{plugin.repository ? <Button variant="outline" size="sm" asChild><a href={plugin.repository} target="_blank" rel="noreferrer"><ExternalLink size={15} />{t("webui.plugins.repository")}</a></Button> : null}</div></div>
    <nav className="webui-plugin-detail-tabs" aria-label={t("webui.plugins.detail_sections")}>{(["description", "changelog", "versions"] as const).map((item) => <Button key={item} variant={section === item ? "secondary" : "ghost"} onClick={() => setSection(item)}>{t(`webui.plugins.${item}`)}</Button>)}</nav>
    {section === "description" ? <div className="webui-plugin-detail-layout"><Card><CardHeader><CardTitle>{t("webui.plugins.description")}</CardTitle></CardHeader><CardContent className="grid gap-4"><p className="webui-plugin-detail-description">{plugin.description || plugin.summary || t("webui.plugins.no_summary")}</p><div className="webui-plugin-badge-row">{plugin.tags.map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>)}</div></CardContent></Card><Card><CardHeader><CardTitle>{t("webui.plugins.compatibility")}</CardTitle></CardHeader><CardContent className="grid gap-2">{plugin.compatibility.length ? plugin.compatibility.map((item) => <span key={item}>{item}</span>) : <span className="text-muted-foreground">{t("webui.plugins.compatibility_unknown")}</span>}</CardContent></Card></div> : null}
    {section === "changelog" ? <Card><CardHeader><CardTitle>{t("webui.plugins.changelog")}</CardTitle></CardHeader><CardContent>{plugin.changelog.length ? <ul className="webui-plugin-detail-list">{plugin.changelog.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="text-muted-foreground">{t("webui.plugins.changelog_empty")}</p>}</CardContent></Card> : null}
    {section === "versions" ? <Card><CardHeader><CardTitle>{t("webui.plugins.versions")}</CardTitle></CardHeader><CardContent className="webui-plugin-version-list">{details.versions.map((version) => <div className="webui-plugin-version-row" key={version.bundle_id}><span className="font-mono">{version.version}</span><span>{version.status}</span><span className="text-muted-foreground">{version.runtime_kinds.join(", ")}</span><Button variant="ghost" size="icon" aria-label={t("webui.plugins.download_version")}><Download size={15} /></Button></div>)}</CardContent></Card> : null}
  </div>;
}
