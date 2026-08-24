import { BadgeCheck, CloudDownload, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PluginInfoGrid, formatPluginBytes } from "@/components/plugin-ui";
import { useLocale } from "@/i18n/locale";
import type { PluginPreview, WebUiOperation } from "@/models/api";

export function PluginPreviewDialog({
  preview,
  installOperation,
  close,
  install,
}: {
  preview: PluginPreview | null;
  installOperation: WebUiOperation | undefined;
  close: () => void;
  install: () => void;
}) {
  const { t } = useLocale();
  return <Dialog open={preview !== null} onOpenChange={(open) => !open && close()}>
    <DialogContent className="webui-plugin-preview-dialog">
      <DialogHeader><DialogTitle className="webui-plugin-dialog-title"><CloudDownload size={18} />{t("webui.plugins.preview_title")}</DialogTitle><DialogDescription>{t("webui.plugins.preview_description")}</DialogDescription></DialogHeader>
      {preview ? <PreviewContent preview={preview} /> : null}
      <DialogFooter><Button variant="outline" onClick={close}>{t("webui.action.cancel")}</Button><Button disabled={!installOperation} onClick={install}><CloudDownload size={15} />{t("webui.plugins.install")}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

function PreviewContent({ preview }: { preview: PluginPreview }) {
  const { t } = useLocale();
  return <div className="webui-plugin-preview-content">
    <PluginInfoGrid items={[
      { label: t("webui.plugins.target"), value: `${preview.selected_target.id} · ${preview.selected_target.kind}` },
      { label: t("webui.plugins.source"), value: `${preview.source.id} · ${preview.index_digest.slice(0, 12)}...` },
      { label: t("webui.plugins.publisher"), value: preview.bundle.publisher?.name ?? t("webui.plugins.unknown_publisher") },
      { label: t("webui.plugins.license"), value: preview.bundle.license?.expression ?? t("webui.plugins.unknown_license") },
      { label: t("webui.plugins.download"), value: formatPluginBytes(preview.download_bytes, preview.download_bytes_exact, t("webui.plugins.size_unavailable")) },
      { label: t("webui.plugins.closure"), value: String(preview.resolved_closure.length) },
    ]} />
    <div><p className="webui-plugin-label">{t("webui.plugins.capabilities")}</p><div className="webui-plugin-badge-row">{preview.requested_capabilities.map((capability) => <Badge key={capability} variant="secondary" className="font-mono text-[10px]">{capability}</Badge>)}</div></div>
    <div className="webui-plugin-security"><p><BadgeCheck size={14} className="text-emerald-600" />{t("webui.plugins.preview_metadata_only")}</p><p><ShieldCheck size={14} className="text-emerald-600" />{t("webui.plugins.preview_execution", { target: preview.selected_target.id })}</p></div>
  </div>;
}
