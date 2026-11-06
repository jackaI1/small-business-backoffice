import { Component, computed, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { OperationsApi } from './operations-api';
import type { Dashboard, Filters } from '../../../server/src/contracts';

type DraftFilters = { from: string; to: string; line: string; status: string };
@Component({
  selector: 'app-root', imports: [DecimalPipe, FormsModule],
  templateUrl: './app.html', styleUrl: './app.css',
})
export class App implements OnInit, OnDestroy {
  private readonly api = inject(OperationsApi);
  private subscription?: Subscription;
  private appliedFilters: Filters = {};
  filters: DraftFilters = { from: '', to: '', line: '', status: '' };
  readonly dashboard = signal<Dashboard | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly chartMax = computed(() => Math.max(1, ...this.dashboard()?.lines.map(line => line.produced) ?? []));
  readonly lineNames: Record<string, string> = { alpha: 'Line A', beta: 'Line B', gamma: 'Line C' };
  ngOnInit() { this.load(1); }
  ngOnDestroy() { this.subscription?.unsubscribe(); }
  applyFilters() {
    this.appliedFilters = Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value !== '')) as Filters;
    this.load(1);
  }
  resetFilters() {
    this.filters = { from: '', to: '', line: '', status: '' };
    this.applyFilters();
  }
  changePage(delta: number) {
    const result = this.dashboard()?.runs;
    if (this.loading() || !result) return;
    const page = result.page + delta;
    if (page >= 1 && page <= result.totalPages) this.load(page);
  }
  retry() { this.load(1); }
  private load(page: number) {
    this.subscription?.unsubscribe();
    this.loading.set(true);
    this.error.set('');
    this.dashboard.set(null);
    this.subscription = this.api.load(this.appliedFilters, page).subscribe({
      next: dashboard => { this.dashboard.set(dashboard); this.loading.set(false); },
      error: (error: HttpErrorResponse) => {
        this.error.set(error.status === 429
          ? 'Too many requests. Wait one minute, then try again.'
          : error.status === 400
            ? 'Check the filters. Use valid dates and put the start date before the end date.'
            : 'Could not reach the server. Check that it is running, then try again.');
        this.loading.set(false);
      },
    });
  }
}
