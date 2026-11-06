import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { forkJoin, map } from 'rxjs';
import type { DailyTotals, Dashboard, Filters, LineTotals, Page, Run, Totals } from '../../../server/src/contracts';

@Injectable({ providedIn: 'root' })
export class OperationsApi {
  private readonly http = inject(HttpClient);
  load(filters: Filters, page: number) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) params = params.set(key, value);
    }
    return forkJoin({
      summary: this.http.get<Totals>('/api/summary', { params }),
      trends: this.http.get<{ data: DailyTotals[] }>('/api/trends', { params }),
      lines: this.http.get<{ data: LineTotals[] }>('/api/lines', { params }),
      runs: this.http.get<Page<Run>>('/api/runs', { params: params.set('page', page).set('pageSize', 10) }),
    }).pipe(map(result => ({ ...result, trends: result.trends.data, lines: result.lines.data }) satisfies Dashboard));
  }
}
