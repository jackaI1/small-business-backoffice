import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { App } from './app';

const totals = { runs: 12, planned: 1000, produced: 900, rejected: 18, good: 882, downtimeMinutes: 30, rejectionRate: 2 };
const run = { id: 1, date: '2026-10-01', line: 'alpha', shift: 'day', status: 'complete', planned: 100, produced: 90, rejected: 2, downtimeMinutes: 3 };

describe('operations dashboard', () => {
  let http: HttpTestingController;
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [App], providers: [provideHttpClient(), provideHttpClientTesting()] }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function requests() {
    return ['summary', 'trends', 'lines', 'runs'].map(route => http.expectOne(req => req.url === `/api/${route}`));
  }
  function complete(reqs: ReturnType<typeof requests>, empty = false, page = 1) {
    reqs[0].flush(empty ? { ...totals, runs: 0, planned: 0, produced: 0, rejected: 0, good: 0, downtimeMinutes: 0, rejectionRate: null } : totals);
    reqs[1].flush({ data: empty ? [] : [{ ...totals, date: '2026-10-01' }] });
    reqs[2].flush({ data: empty ? [] : [{ ...totals, line: 'alpha' }] });
    reqs[3].flush({ data: empty ? [] : [run], page, pageSize: 10, total: empty ? 0 : 12, totalPages: empty ? 0 : 2 });
  }
  it('loads and renders API totals, line comparison, daily trend and actual records', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Loading production runs');
    complete(requests());
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h1')?.textContent).toContain('Production overview');
    expect(el.textContent).toContain('882');
    expect(el.textContent).toContain('2%');
    expect(el.querySelectorAll('[data-testid="run-row"]')).toHaveLength(1);
    expect(el.querySelector('[data-testid="line-totals"]')?.textContent).toContain('Line A');
    expect(el.querySelector('[data-testid="daily-totals"]')?.textContent).toContain('2026-10-01');
    fixture.destroy();
  });
  it('requests the next page and resets to page one when filters are applied through the form', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges(); complete(requests()); await fixture.whenStable();
    fixture.nativeElement.querySelector('[data-testid="next"]').click();
    const next = requests();
    expect(next[3].request.params.get('page')).toBe('2');
    expect(next[3].request.params.get('pageSize')).toBe('10');
    complete(next, false, 2); await fixture.whenStable();
    const select = fixture.nativeElement.querySelector('select[name="line"]') as HTMLSelectElement;
    select.value = 'alpha'; select.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    const filtered = requests();
    for (const req of filtered) expect(req.request.params.get('line')).toBe('alpha');
    expect(filtered[3].request.params.get('page')).toBe('1');
    expect(filtered[0].request.params.has('page')).toBe(false);
    expect(filtered[0].request.params.has('from')).toBe(false);
    complete(filtered); await fixture.whenStable();
    fixture.destroy();
  });
  it('keeps the applied filters when moving between pages', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges(); complete(requests()); await fixture.whenStable();
    fixture.componentInstance.filters = { from: '2026-10-01', to: '2026-10-03', line: 'beta', status: 'delayed' };
    fixture.componentInstance.applyFilters();
    const filtered = requests(); complete(filtered); await fixture.whenStable();
    fixture.componentInstance.filters.line = 'alpha'; // editing the draft does not apply it
    fixture.nativeElement.querySelector('[data-testid="next"]').click();
    const next = requests();
    for (const req of next) {
      expect(req.request.params.get('line')).toBe('beta');
      expect(req.request.params.get('status')).toBe('delayed');
      expect(req.request.params.get('from')).toBe('2026-10-01');
      expect(req.request.params.get('to')).toBe('2026-10-03');
    }
    complete(next, false, 2); await fixture.whenStable(); fixture.destroy();
  });
  it('explains empty results and disables pagination', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges(); complete(requests(), true); await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('No runs match these filters');
    expect(fixture.nativeElement.textContent).toContain('No output');
    expect(fixture.nativeElement.querySelector('[data-testid="next"]').disabled).toBe(true);
    expect(fixture.nativeElement.querySelector('[data-testid="previous"]').disabled).toBe(true);
    fixture.destroy();
  });
  it.each([400, 429, 500])('shows recovery guidance for HTTP %s and retries successfully', async status => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const reqs = requests();
    reqs[0].flush({ error: { message: 'private implementation detail' } }, { status, statusText: 'Error' });
    await fixture.whenStable();
    const text = fixture.nativeElement.querySelector('[role="alert"]').textContent;
    expect(text).not.toContain('private implementation detail');
    expect(text).toContain(status === 429 ? 'one minute' : status === 400 ? 'filters' : 'server');
    fixture.nativeElement.querySelector('[data-testid="retry"]').click();
    complete(requests()); await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('882');
    fixture.destroy();
  });
  it('cancels an old load so stale data cannot replace the latest filter result', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges(); const old = requests();
    fixture.componentInstance.filters.line = 'gamma';
    fixture.componentInstance.applyFilters();
    expect(old.every(req => req.cancelled)).toBe(true);
    const latest = requests();
    expect(latest[0].request.params.get('line')).toBe('gamma');
    complete(latest, true); await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('No runs match these filters');
    fixture.destroy();
  });
});
