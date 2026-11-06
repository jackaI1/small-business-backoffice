import { Injectable, inject } from "@angular/core";
import { HttpClient, HttpParams } from "@angular/common/http";
import {
  BehaviorSubject,
  Observable,
  catchError,
  distinctUntilChanged,
  map,
  of,
  shareReplay,
  startWith,
  switchMap,
} from "rxjs";
import {
  Anomaly,
  Filters,
  Metadata,
  PanelState,
  StationPoint,
  Volume,
} from "../../shared/models";

export const DEFAULT_FILTERS: Filters = {
  from: "2026-10-26",
  to: "2026-11-01",
  station: "all",
};
@Injectable({ providedIn: "root" })
export class DataService {
  private readonly http = inject(HttpClient);
  private readonly filtersSubject = new BehaviorSubject<Filters>(
    DEFAULT_FILTERS,
  );
  readonly filters$ = this.filtersSubject
    .asObservable()
    .pipe(
      distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)),
    );
  get filters(): Filters {
    return this.filtersSubject.value;
  }
  setFilters(filters: Filters): void {
    this.filtersSubject.next(filters);
  }
  metadata(): Observable<Metadata> {
    return this.http.get<Metadata>("/api/metadata");
  }
  panel<T>(
    endpoint: string,
    refresh$: Observable<unknown>,
  ): Observable<PanelState<T>> {
    return this.filters$.pipe(
      switchMap((filters) =>
        refresh$.pipe(
          startWith(null),
          switchMap(() =>
            this.http
              .get<T>(`/api/${endpoint}`, {
                params: new HttpParams({ fromObject: { ...filters } }),
              })
              .pipe(
                map((data) => ({ status: "ready", data }) as PanelState<T>),
                catchError(() =>
                  of<PanelState<T>>({
                    status: "error",
                    message: "Could not load this panel. Try again.",
                  }),
                ),
                startWith<PanelState<T>>({ status: "loading" }),
              ),
          ),
        ),
      ),
      shareReplay({ bufferSize: 1, refCount: true }),
    );
  }
  volume(refresh$: Observable<unknown>): Observable<PanelState<Volume>> {
    return this.panel("volume", refresh$);
  }
  stations(
    refresh$: Observable<unknown>,
  ): Observable<PanelState<StationPoint[]>> {
    return this.panel("stations", refresh$);
  }
  anomalies(refresh$: Observable<unknown>): Observable<PanelState<Anomaly[]>> {
    return this.panel("anomalies", refresh$);
  }
  exportCsv(): Observable<Blob> {
    return this.http.get("/api/export.csv", {
      params: new HttpParams({ fromObject: { ...this.filters } }),
      responseType: "blob",
    });
  }
}
