import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { Toaster } from "@/components/ui/sonner";
import "./styles.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("WebUI root is unavailable.");
}

createRoot(root).render(
  <StrictMode>
    <App />
    <Toaster />
  </StrictMode>,
);
