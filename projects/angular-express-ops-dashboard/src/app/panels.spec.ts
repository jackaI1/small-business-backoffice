import { TestBed } from "@angular/core/testing";
import { Component } from "@angular/core";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";
import { PanelComponent } from "./panel.component";
import { OverviewComponent } from "./overview.component";
import { AnomalyPanelComponent } from "./anomaly-panel.component";
import { DataService } from "./data.service";
@Component({
  standalone: true,
  imports: [PanelComponent],
  template: `<app-panel [state]="state" label="sample" (retry)="retried = true"
    ><p>Panel data</p></app-panel
  >`,
})
class HostComponent {
  state: { status: "loading" | "ready" | "error"; message?: string } = {
    status: "loading",
  };
  retried = false;
}
describe("PanelComponent", () => {
  it("announces loading and hides stale content", () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector('[role="status"]').textContent,
    ).toContain("Loading sample");
    expect(fixture.nativeElement.textContent).not.toContain("Panel data");
  });
  it("announces an error and emits a retry", () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.componentInstance.state = {
      status: "error",
      message: "Try again.",
    };
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeTruthy();
    fixture.nativeElement.querySelector("button").click();
    expect(fixture.componentInstance.retried).toBeTrue();
  });
  it("projects ready data", () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.componentInstance.state = { status: "ready" };
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Panel data");
  });
});
const rows = [
  {
    id: "1",
    date: "2026-10-30",
    hour: 18,
    station: "North gate",
    stationId: "north",
    volume: 230,
    utilisation: 127.8,
    type: "surge" as const,
  },
  {
    id: "2",
    date: "2026-10-28",
    hour: 14,
    station: "Information desk",
    stationId: "information",
    volume: 7,
    utilisation: 11.7,
    type: "quiet" as const,
  },
];
const data = {
  volume: () =>
    of({
      status: "ready",
      data: { total: 230, peakHour: 18, hours: [{ hour: 18, volume: 230 }] },
    }),
  stations: () =>
    of({
      status: "ready",
      data: [
        {
          id: "north",
          name: "North gate",
          capacity: 180,
          volume: 230,
          capacityTotal: 180,
          utilisation: 127.8,
        },
      ],
    }),
  anomalies: () => of({ status: "ready", data: rows }),
};
describe("dashboard panels", () => {
  beforeEach(() =>
    TestBed.configureTestingModule({
      providers: [{ provide: DataService, useValue: data }, provideRouter([])],
    }),
  );
  it("renders totals, hourly bars, and station capacity", () => {
    const fixture = TestBed.createComponent(OverviewComponent);
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector('[data-testid="total-volume"]')
        .textContent,
    ).toBe("230");
    expect(
      fixture.nativeElement.querySelectorAll(".hour-chart li").length,
    ).toBe(1);
    expect(fixture.nativeElement.textContent).toContain("127.8%");
    expect(fixture.componentInstance.clamp(127.8)).toBe(100);
  });
  it("offers quiet-hour filtering on the review page", () => {
    const fixture = TestBed.createComponent(AnomalyPanelComponent);
    fixture.componentInstance.detailed = true;
    fixture.detectChanges();
    fixture.componentInstance.type.setValue("quiet");
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll("tbody tr").length).toBe(1);
    expect(fixture.nativeElement.querySelector("tbody").textContent).toContain(
      "Information desk",
    );
  });
  it("limits overview anomalies to five highest-pressure hours", () => {
    const fixture = TestBed.createComponent(AnomalyPanelComponent);
    expect(
      fixture.componentInstance.visible(
        Array.from({ length: 9 }, () => rows[0]),
      ).length,
    ).toBe(5);
  });
});
