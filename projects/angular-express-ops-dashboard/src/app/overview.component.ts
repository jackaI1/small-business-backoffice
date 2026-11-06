import { AsyncPipe, DecimalPipe } from "@angular/common";
import { Component, inject } from "@angular/core";
import { Subject } from "rxjs";
import { DataService } from "./data.service";
import { PanelComponent } from "./panel.component";
import { AnomalyPanelComponent } from "./anomaly-panel.component";
import { HourPoint } from "../../shared/models";
@Component({
  selector: "app-overview",
  standalone: true,
  imports: [AsyncPipe, DecimalPipe, PanelComponent, AnomalyPanelComponent],
  template: ` <div class="overview-grid">
    <section class="panel volume-panel" aria-labelledby="volume-title">
      <div class="panel-heading">
        <div>
          <h2 id="volume-title">Hourly volume</h2>
          <p>Interactions across the applied date range</p>
        </div>
        <span class="legend"><i></i>Interactions</span>
      </div>
      @let volume = volume$ | async;
      <app-panel
        [state]="volume"
        label="hourly volume"
        (retry)="volumeRefresh.next()"
      >
        @if (volume?.data; as data) {
          <div class="volume-summary">
            <div>
              <strong data-testid="total-volume">{{
                data.total | number
              }}</strong
              ><span>Total interactions</span>
            </div>
            <div>
              <strong>{{
                data.peakHour === null ? "No data" : time(data.peakHour)
              }}</strong
              ><span>Busiest hour</span>
            </div>
          </div>
          @if (data.total) {
            <ul class="hour-chart" aria-label="Hourly interaction volume">
              @for (point of data.hours; track point.hour) {
                <li [class.peak]="point.hour === data.peakHour">
                  <div class="bar-track">
                    <div
                      class="bar"
                      [style.height.%]="height(point.volume, data.hours)"
                      [attr.title]="
                        time(point.hour) + ': ' + point.volume + ' interactions'
                      "
                    >
                      <span>{{ point.volume | number }}</span>
                    </div>
                  </div>
                  <span class="hour-label">{{ point.hour }}</span
                  ><span class="sr-only"
                    >: {{ point.volume }} interactions</span
                  >
                </li>
              }
            </ul>
            <div class="chart-caption">
              <span>Hour of day</span><span>Peak hour highlighted</span>
            </div>
            <details>
              <summary>View hourly values</summary>
              <table>
                <caption class="sr-only">
                  Hourly interactions for applied filters
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Hour</th>
                    <th scope="col">Interactions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (point of data.hours; track point.hour) {
                    <tr>
                      <th scope="row">{{ time(point.hour) }}</th>
                      <td>{{ point.volume | number }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </details>
          } @else {
            <p class="panel-message">
              No interactions in this range. Choose dates within the sample
              week.
            </p>
          }
        }
      </app-panel>
    </section>
    <section class="panel station-panel" aria-labelledby="stations-title">
      <div class="panel-heading">
        <div>
          <h2 id="stations-title">Station utilisation</h2>
          <p>Demand compared with staffed capacity</p>
        </div>
      </div>
      @let stations = stations$ | async;
      <app-panel
        [state]="stations"
        label="station utilisation"
        (retry)="stationRefresh.next()"
      >
        @if (stations?.data; as data) {
          @for (station of data; track station.id) {
            <div class="station-row">
              <div class="station-label">
                <strong>{{ station.name }}</strong
                ><span>{{ station.utilisation | number: "1.1-1" }}%</span>
              </div>
              <div
                class="util-track"
                role="img"
                [attr.aria-label]="
                  station.name + ': ' + station.utilisation + '% utilisation'
                "
              >
                <div [style.width.%]="clamp(station.utilisation)"></div>
              </div>
              <p>
                {{ station.volume | number }} interactions /
                {{ station.capacityTotal | number }} capacity
              </p>
            </div>
          }
          @if (!data.length || !data[0].capacityTotal) {
            <p>No station activity in this range.</p>
          }
          <p class="definition">
            100% means demand matched the station's staffed hourly capacity.
            Higher values flag pressure on the shift.
          </p>
        }
      </app-panel>
    </section>
    <app-anomaly-panel class="anomaly-wide" />
  </div>`,
})
export class OverviewComponent {
  private readonly data = inject(DataService);
  readonly volumeRefresh = new Subject<void>();
  readonly stationRefresh = new Subject<void>();
  readonly volume$ = this.data.volume(this.volumeRefresh);
  readonly stations$ = this.data.stations(this.stationRefresh);
  time(hour: number): string {
    return `${hour}:00`;
  }
  height(value: number, hours: HourPoint[]): number {
    return (value / Math.max(1, ...hours.map((point) => point.volume))) * 100;
  }
  clamp(value: number): number {
    return Math.min(100, value);
  }
}
