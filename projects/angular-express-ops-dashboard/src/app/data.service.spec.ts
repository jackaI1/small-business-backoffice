import { TestBed } from "@angular/core/testing";
import { provideHttpClient } from "@angular/common/http";
import {
  HttpTestingController,
  provideHttpClientTesting,
} from "@angular/common/http/testing";
import { Subject } from "rxjs";
import { DataService, DEFAULT_FILTERS } from "./data.service";
import { PanelState, Volume } from "../../shared/models";
const volume: Volume = {
  total: 20,
  peakHour: 12,
  hours: [{ hour: 12, volume: 20 }],
};
describe("DataService", () => {
  let service: DataService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(DataService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it("emits loading then ready and sends applied filters", () => {
    const states: PanelState<Volume>[] = [];
    service.volume(new Subject()).subscribe((state) => states.push(state));
    const request = http.expectOne((req) => req.url === "/api/volume");
    expect(states[0].status).toBe("loading");
    expect(request.request.params.get("from")).toBe(DEFAULT_FILTERS.from);
    request.flush(volume);
    expect(states[1].data).toEqual(volume);
  });
  it("recovers from an HTTP failure with a panel-specific retry", () => {
    const refresh = new Subject<void>();
    const statuses: string[] = [];
    service.volume(refresh).subscribe((state) => statuses.push(state.status));
    http
      .expectOne((req) => req.url === "/api/volume")
      .flush({}, { status: 503, statusText: "Unavailable" });
    refresh.next();
    http.expectOne((req) => req.url === "/api/volume").flush(volume);
    expect(statuses).toEqual(["loading", "error", "loading", "ready"]);
  });
  it("cancels an outdated request when the station changes", () => {
    const subscription = service.volume(new Subject()).subscribe();
    const old = http.expectOne((req) => req.url === "/api/volume");
    service.setFilters({ ...DEFAULT_FILTERS, station: "north" });
    expect(old.cancelled).toBeTrue();
    const current = http.expectOne(
      (req) => req.params.get("station") === "north",
    );
    current.flush(volume);
    subscription.unsubscribe();
  });
  it("shares one request across concurrent subscribers", () => {
    const stream = service.volume(new Subject());
    const first = stream.subscribe();
    const second = stream.subscribe();
    http.expectOne((req) => req.url === "/api/volume").flush(volume);
    first.unsubscribe();
    second.unsubscribe();
  });
  it("does not refetch when unchanged filters are applied", () => {
    const subscription = service.volume(new Subject()).subscribe();
    http.expectOne((req) => req.url === "/api/volume").flush(volume);
    service.setFilters({ ...DEFAULT_FILTERS });
    http.expectNone((req) => req.url === "/api/volume");
    subscription.unsubscribe();
  });
  it("unsubscribing releases in-flight requests", () => {
    const subscription = service.stations(new Subject()).subscribe();
    const request = http.expectOne((req) => req.url === "/api/stations");
    subscription.unsubscribe();
    expect(request.cancelled).toBeTrue();
  });
  it("keeps station and anomaly requests independent", () => {
    let stationState = "";
    let anomalyState = "";
    service
      .stations(new Subject())
      .subscribe((state) => (stationState = state.status));
    service
      .anomalies(new Subject())
      .subscribe((state) => (anomalyState = state.status));
    http
      .expectOne((req) => req.url === "/api/stations")
      .flush({}, { status: 500, statusText: "Failure" });
    http.expectOne((req) => req.url === "/api/anomalies").flush([]);
    expect(stationState).toBe("error");
    expect(anomalyState).toBe("ready");
  });
  it("exports a blob using the latest applied filters", () => {
    service.setFilters({ ...DEFAULT_FILTERS, station: "south" });
    service.exportCsv().subscribe((blob) => expect(blob.size).toBe(4));
    const request = http.expectOne((req) => req.url === "/api/export.csv");
    expect(request.request.responseType).toBe("blob");
    expect(request.request.params.get("station")).toBe("south");
    request.flush(new Blob(["test"]));
  });
});
