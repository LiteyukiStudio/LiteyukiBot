import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";

import { App } from "@/app/App";
import { Toaster } from "@/components/ui/sonner";
import { LocaleProvider } from "@/i18n/locale";
import { ThemeControllerProvider } from "@/themes/theme-controller";
import "./styles.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("WebUI root is unavailable.");
}

createRoot(root).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <ThemeControllerProvider>
        <LocaleProvider>
          <App />
          <Toaster />
        </LocaleProvider>
      </ThemeControllerProvider>
    </ThemeProvider>
  </StrictMode>,
);
