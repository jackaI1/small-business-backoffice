import { Component, DestroyRef, inject, signal } from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import {
  AbstractControl,
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from "@angular/forms";
import { ActivatedRoute, Router } from "@angular/router";
import { DataService, DEFAULT_FILTERS } from "./data.service";
import { Metadata } from "../../shared/models";

export function dateRangeValidator(
  control: AbstractControl,
): ValidationErrors | null {
  const { from, to } = control.value;
  const valid = (date: string) =>
    /^\d{4}-\d{2}-\d{2}$/.test(date) &&
    !Number.isNaN(Date.parse(date)) &&
    new Date(date).toISOString().slice(0, 10) === date;
  return valid(from) &&
    valid(to) &&
    from <= to &&
    Date.parse(to) - Date.parse(from) <= 30 * 86400000
    ? null
    : { dateRange: true };
}
@Component({
  selector: "app-filters",
  standalone: true,
  imports: [ReactiveFormsModule],
  template: ` <section class="filter-section" aria-label="Dashboard filters">
    <div class="page-intro">
      <div>
        <h1>Every hour tells a story.</h1>
        <p>
          Find the busy stations. Catch the unusual hours. Plan the next shift.
        </p>
      </div>
      <p class="dataset-note">
        Sample week<br /><strong>26 Oct to 1 Nov 2026</strong>
      </p>
    </div>
    @if (metadata(); as meta) {
      <form [formGroup]="form" (ngSubmit)="apply()" class="filter-bar">
        <label
          >From<input
            type="date"
            formControlName="from"
            required
            aria-describedby="filter-help"
        /></label>
        <label
          >To<input
            type="date"
            formControlName="to"
            required
            aria-describedby="filter-help"
        /></label>
        <label
          >Station<select formControlName="station">
            <option value="all">All stations</option>
            @for (station of meta.stations; track station.id) {
              <option [value]="station.id">{{ station.name }}</option>
            }
          </select></label
        >
        <button type="submit" [disabled]="form.invalid">Apply filters</button>
        <button
          type="button"
          class="secondary"
          (click)="exportCsv()"
          [disabled]="exporting()"
        >
          {{ exporting() ? "Preparing CSV…" : "Export CSV" }}
        </button>
      </form>
      <p id="filter-help" class="filter-help">
        Choose up to 31 days. Data is available from {{ meta.from }} to
        {{ meta.to }}. Export uses the applied filters.
      </p>
      @if (form.invalid || invalidLink()) {
        <p class="error-text" role="alert">
          Choose valid dates in order, covering no more than 31 days, and a
          listed station.
        </p>
      }
    } @else if (metadataError()) {
      <p role="alert">
        Could not load filter options.
        <button type="button" (click)="loadMetadata()">
          Retry filter options
        </button>
      </p>
    } @else {
      <p role="status">Loading filter options…</p>
    }
    @if (exportError()) {
      <p class="error-text" role="alert">
        CSV export failed. Try Export CSV again.
      </p>
    }
    @if (exported()) {
      <p role="status" class="filter-help">
        CSV downloaded for the applied filters.
      </p>
    }
  </section>`,
})
export class FiltersComponent {
  private readonly data = inject(DataService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly metadata = signal<Metadata | null>(null);
  readonly metadataError = signal(false);
  readonly exporting = signal(false);
  readonly exportError = signal(false);
  readonly exported = signal(false);
  readonly invalidLink = signal(false);
  readonly form = new FormGroup(
    {
      from: new FormControl(DEFAULT_FILTERS.from, {
        nonNullable: true,
        validators: [Validators.required],
      }),
      to: new FormControl(DEFAULT_FILTERS.to, {
        nonNullable: true,
        validators: [Validators.required],
      }),
      station: new FormControl("all", {
        nonNullable: true,
        validators: [
          Validators.pattern(/^(all|north|south|concessions|information)$/),
        ],
      }),
    },
    { validators: dateRangeValidator },
  );
  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.form.setValue({
        from: params.get("from") ?? DEFAULT_FILTERS.from,
        to: params.get("to") ?? DEFAULT_FILTERS.to,
        station: params.get("station") ?? "all",
      });
      this.invalidLink.set(this.form.invalid);
      this.data.setFilters(
        this.form.valid ? this.form.getRawValue() : DEFAULT_FILTERS,
      );
    });
    this.loadMetadata();
  }
  loadMetadata(): void {
    this.metadataError.set(false);
    this.data
      .metadata()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (value) => this.metadata.set(value),
        error: () => this.metadataError.set(true),
      });
  }
  apply(): void {
    if (this.form.invalid) return;
    this.invalidLink.set(false);
    this.exported.set(false);
    this.exportError.set(false);
    void this.router.navigate([], {
      queryParams: this.form.getRawValue(),
      queryParamsHandling: "merge",
    });
  }
  exportCsv(): void {
    this.exporting.set(true);
    this.exportError.set(false);
    this.exported.set(false);
    const applied = { ...this.data.filters };
    this.data
      .exportCsv()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement("a");
          anchor.href = url;
          anchor.download = `venue-${applied.from}-to-${applied.to}.csv`;
          anchor.click();
          setTimeout(() => URL.revokeObjectURL(url), 0);
          this.exporting.set(false);
          this.exported.set(true);
        },
        error: () => {
          this.exporting.set(false);
          this.exportError.set(true);
        },
      });
  }
}
