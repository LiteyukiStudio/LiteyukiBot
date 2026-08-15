import * as React from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function SurfaceCard({ className, ...props }: React.ComponentProps<typeof Card>) {
  return <Card className={cn("webui-float-card py-0", className)} {...props} />;
}
