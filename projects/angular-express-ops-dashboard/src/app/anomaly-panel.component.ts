import { AsyncPipe, DecimalPipe } from "@angular/common";
import { Component, Input, inject } from "@angular/core";
import { FormControl, ReactiveFormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { Subject } from "rxjs";
import { Anomaly } from "../../shared/models";
import { DataService } from "./data.service";
import { PanelComponent } from "./panel.component";
@Component({
  selector: "app-anomaly-panel",
  standalone: true,
  imports: [
    AsyncPipe,
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    PanelComponent,
  ],
  template: ` <section
    class="panel anomaly-panel"
    aria-labelledby="anomalies-title"
  >
    <div class="panel-heading">
      <div>
        <h2 id="anomalies-title">
          {{ detailed ? "Anomaly review" : "Hours worth a closer look" }}
        </h2>
        <p>Surge: at least 95% utilisation. Quiet: below 25%.</p>
      </div>
      @if (!detailed) {
        <a routerLink="/anomalies" queryParamsHandling="preserve"
          >Review all anomalies</a
        >
      } @else {
        <label
          >Show<select [formControl]="type">
            <option value="all">All anomalies</option>
            <option value="surge">Surges</option>
            <option value="quiet">Quiet hours</option>
          </select></label
        >
      }
    </div>
    @let state = anomalies$ | async;
    <app-panel [state]="state" label="anomalies" (retry)="refresh.next()">
      @if (state?.data; as data) {
        <p class="count-note">
          {{ filtered(data).length }} matching anomalies{{
            detailed ? "" : " · showing up to 5 highest-pressure hours"
          }}
        </p>
        @if (filtered(data).length) {
          <div class="table-scroll">
            <table>
              <caption class="sr-only">
                Unusual station hours, highest utilisation first
              </caption>
              <thead>
                <tr>
                  <th scope="col">Station</th>
                  <th scope="col">Date / hour</th>
                  <th scope="col">Interactions</th>
                  <th scope="col">Utilisation</th>
                  <th scope="col">Flag</th>
                </tr>
              </thead>
              <tbody>
                @for (row of visible(data); track row.id) {
                  <tr>
                    <th scope="row">{{ row.station }}</th>
                    <td>
                      {{ row.date }}
                      <span class="muted">{{ row.hour }}:00</span>
                    </td>
                    <td>{{ row.volume | number }}</td>
                    <td>{{ row.utilisation | number: "1.1-1" }}%</td>
                    <td>
                      <span class="flag" [class.quiet]="row.type === 'quiet'">{{
                        row.type === "surge" ? "Surge" : "Quiet"
                      }}</span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="panel-message">No anomalies match these filters.</p>
        }
      }
    </app-panel>
  </section>`,
})
export class AnomalyPanelComponent {
  @Input() detailed = false;
  readonly refresh = new Subject<void>();
  readonly anomalies$ = inject(DataService).anomalies(this.refresh);
  readonly type = new FormControl<"all" | "surge" | "quiet">("all", {
    nonNullable: true,
  });
  filtered(rows: Anomaly[]): Anomaly[] {
    return rows.filter(
      (row) =>
        !this.detailed ||
        this.type.value === "all" ||
        row.type === this.type.value,
    );
  }
  visible(rows: Anomaly[]): Anomaly[] {
    return this.detailed
      ? this.filtered(rows)
      : this.filtered(rows).slice(0, 5);
  }
}
