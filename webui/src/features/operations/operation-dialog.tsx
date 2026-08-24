import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useLocale } from "@/i18n/locale";
import type { JsonObject, WebUiOperation } from "@/models/api";
import { WebUiApi } from "@/services/webui-api";

type OperationDialogProps = {
  operation: WebUiOperation | null;
  close: () => void;
  api: WebUiApi;
  reload: () => Promise<void>;
  initialValues?: Record<string, string>;
};
const EMPTY_INITIAL_VALUES: Record<string, string> = {};

/**
 * Builds and submits a catalog-driven operation form.
 * @param props - Selected operation, API client, close command, and post-submit reload command.
 * @returns The operation dialog, or `null` when no operation is selected.
 * @remarks High-impact operations require the target to be typed verbatim; server-side authorization and schema
 * validation remain mandatory because this client check is only an interaction safeguard.
 */
export function OperationDialog({ operation, close, api, reload, initialValues = EMPTY_INITIAL_VALUES }: OperationDialogProps) {
  const { t } = useLocale();
  const [values, setValues] = useState<Record<string, string>>({});
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => { setValues(initialValues); setConfirmation(""); }, [initialValues, operation]);
  if (!operation) return null;

  const schema = operation.input_schema;
  const properties = schema.properties && typeof schema.properties === "object" && !Array.isArray(schema.properties) ? schema.properties as JsonObject : {};
  const required = Array.isArray(schema.required) ? schema.required.filter((field): field is string => typeof field === "string") : [];
  const fields = Object.entries(properties).filter(([, definition]) => typeof definition === "object" && definition !== null && !Array.isArray(definition));
  const targetField = operation.target_input_field;
  const target = targetField ? values[targetField] ?? "" : operation.target;
  const canSubmit = required.every((field) => values[field]?.trim()) && (!targetField || target.trim().length > 0) && (operation.impact !== "high" || confirmation === target);
  const submit = async () => {
    if (!canSubmit) return;
    setPending(true);
    try {
      await api.submit(operation, target, values, true);
      toast.success(t("webui.operation.queued"));
      close();
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : t("webui.operation.queued_failed"));
    } finally {
      setPending(false);
    }
  };

  return <Dialog open onOpenChange={(open) => !open && close()}><DialogContent><DialogHeader><DialogTitle>{operation.id}</DialogTitle><DialogDescription>{t("webui.operation.description")}</DialogDescription></DialogHeader><div className="grid gap-3">{fields.map(([field, definition]) => {
    const details = definition as JsonObject;
    const requiredField = required.includes(field);
    return <div key={field} className="grid gap-2"><label className="text-sm font-medium" htmlFor={`operation-${field}`}>{field}{requiredField && <span className="text-destructive"> *</span>}</label><Input id={`operation-${field}`} value={values[field] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))} placeholder={typeof details.description === "string" ? details.description : t("webui.operation.enter", { field })} />{field === targetField && operation.confirmation === "target" && <p className="text-xs text-muted-foreground">{t("webui.operation.confirm_hint")}</p>}</div>;
  })}{operation.impact === "high" && <div className="grid gap-2"><label className="text-sm font-medium" htmlFor="operation-confirmation">{t("webui.operation.confirm_target")}</label><Input id="operation-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder={t("webui.operation.confirm_placeholder")} /></div>}</div><DialogFooter><Button variant="outline" onClick={close}>{t("webui.action.cancel")}</Button><Button disabled={!canSubmit || pending} onClick={() => void submit()}>{pending ? t("webui.operation.queueing") : t("webui.operation.queue")}</Button></DialogFooter></DialogContent></Dialog>;
}
