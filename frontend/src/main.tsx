import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "katex/dist/katex.min.css";
import "@fontsource-variable/noto-serif-sc";
import "@fontsource-variable/noto-sans-sc";
import "./style.css";
import "./editorial.css";
import { migrateBrandStorage } from "./brandMigration";
try { migrateBrandStorage(localStorage); } catch { /* Storage may be unavailable. */ }
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
