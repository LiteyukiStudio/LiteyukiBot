import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";

import { App } from "./App";
import { Toaster } from "@/components/ui/sonner";
import { LocaleProvider } from "@/i18n/locale";
import "./styles.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("WebUI root is unavailable.");
}

createRoot(root).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <LocaleProvider>
        <App />
        <Toaster />
      </LocaleProvider>
    </ThemeProvider>
  </StrictMode>,
);
