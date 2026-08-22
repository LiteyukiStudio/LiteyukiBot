import * as React from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Applies the shared floating-surface treatment to a base card.
 * @param props - Base card properties and optional additional classes.
 * @returns A consistently styled card without introducing another nested container.
 */
export function SurfaceCard({ className, ...props }: React.ComponentProps<typeof Card>) {
  return <Card className={cn("webui-float-card py-0", className)} {...props} />;
}
