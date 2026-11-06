import { Routes } from "@angular/router";
export const routes: Routes = [
  {
    path: "overview",
    loadComponent: () =>
      import("./overview.component").then((m) => m.OverviewComponent),
  },
  {
    path: "anomalies",
    loadComponent: () =>
      import("./anomalies.component").then((m) => m.AnomaliesComponent),
  },
  { path: "", pathMatch: "full", redirectTo: "overview" },
  { path: "**", redirectTo: "overview" },
];
