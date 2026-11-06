import { Component } from "@angular/core";
import { AnomalyPanelComponent } from "./anomaly-panel.component";
@Component({
  selector: "app-anomalies",
  standalone: true,
  imports: [AnomalyPanelComponent],
  template: `<p class="review-intro">
      Use these flags to decide where to review staffing. A flag is a prompt to
      investigate, not proof of a problem.
    </p>
    <app-anomaly-panel [detailed]="true" />`,
})
export class AnomaliesComponent {}
