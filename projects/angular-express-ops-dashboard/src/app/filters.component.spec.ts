import { TestBed } from "@angular/core/testing";
import { provideHttpClient } from "@angular/common/http";
import {
  HttpTestingController,
  provideHttpClientTesting,
} from "@angular/common/http/testing";
import { ActivatedRoute, Router, convertToParamMap } from "@angular/router";
import { BehaviorSubject } from "rxjs";
import { FormControl, FormGroup } from "@angular/forms";
import { FiltersComponent, dateRangeValidator } from "./filters.component";
import { DataService, DEFAULT_FILTERS } from "./data.service";
describe("date range validation", () => {
  for (const [name, from, to, valid] of [
    ["inclusive day", "2026-10-30", "2026-10-30", true],
    ["31 days", "2026-10-01", "2026-10-31", true],
    ["32 days", "2026-10-01", "2026-11-01", false],
    ["reversed dates", "2026-11-01", "2026-10-01", false],
    ["impossible date", "2026-02-30", "2026-03-01", false],
    ["empty date", "", "2026-11-01", false],
  ] as const)
    it(`checks ${name}`, () => {
      const form = new FormGroup(
        { from: new FormControl(from), to: new FormControl(to) },
        { validators: dateRangeValidator },
      );
      expect(form.valid).toBe(valid);
    });
});
describe("FiltersComponent", () => {
  const params = new BehaviorSubject(convertToParamMap({}));
  let http: HttpTestingController;
  const navigate = jasmine.createSpy("navigate").and.resolveTo(true);
  beforeEach(() => {
    params.next(convertToParamMap({}));
    navigate.calls.reset();
    TestBed.configureTestingModule({
      imports: [FiltersComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigate } },
        { provide: ActivatedRoute, useValue: { queryParamMap: params } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function create() {
    const fixture = TestBed.createComponent(FiltersComponent);
    http.expectOne("/api/metadata").flush({ ...DEFAULT_FILTERS, stations: [] });
    fixture.detectChanges();
    return fixture;
  }
  it("restores valid filters from a shared URL", () => {
    params.next(
      convertToParamMap({
        station: "north",
        from: "2026-10-30",
        to: "2026-10-30",
      }),
    );
    const fixture = create();
    expect(fixture.componentInstance.form.controls.station.value).toBe("north");
    expect(TestBed.inject(DataService).filters.from).toBe("2026-10-30");
  });
  it("shows an invalid URL warning and uses safe defaults", () => {
    params.next(convertToParamMap({ station: "unknown" }));
    const fixture = create();
    expect(fixture.componentInstance.invalidLink()).toBeTrue();
    expect(TestBed.inject(DataService).filters).toEqual(DEFAULT_FILTERS);
    expect(fixture.nativeElement.textContent).toContain("Choose valid dates");
  });
  it("does not navigate for an invalid typed form", () => {
    const fixture = create();
    fixture.componentInstance.form.controls.to.setValue("2026-01-01");
    fixture.componentInstance.apply();
    expect(navigate).not.toHaveBeenCalled();
  });
  it("writes applied filters to the route", () => {
    const fixture = create();
    fixture.componentInstance.form.controls.station.setValue("south");
    fixture.componentInstance.apply();
    expect(navigate).toHaveBeenCalledWith([], {
      queryParams: { ...DEFAULT_FILTERS, station: "south" },
      queryParamsHandling: "merge",
    });
  });
  it("shows a metadata error and retries successfully", () => {
    const fixture = TestBed.createComponent(FiltersComponent);
    http
      .expectOne("/api/metadata")
      .flush({}, { status: 503, statusText: "Unavailable" });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Retry filter options");
    fixture.componentInstance.loadMetadata();
    http.expectOne("/api/metadata").flush({ ...DEFAULT_FILTERS, stations: [] });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("form")).toBeTruthy();
  });
  it("shows a recoverable CSV export error", () => {
    const fixture = create();
    fixture.componentInstance.exportCsv();
    http
      .expectOne((req) => req.url === "/api/export.csv")
      .flush(new Blob(), { status: 503, statusText: "Unavailable" });
    fixture.detectChanges();
    expect(fixture.componentInstance.exporting()).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain("CSV export failed");
  });
});
