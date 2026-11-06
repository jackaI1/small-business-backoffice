import { Component } from "@angular/core";
import { RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { FiltersComponent } from "./filters.component";
@Component({
  selector: "app-root",
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, FiltersComponent],
  template: ` <a class="skip-link" href="#main">Skip to dashboard</a>
    <header class="masthead">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">▥</span>
        <div><strong>Shiftboard</strong><span>Venue operations</span></div>
      </div>
      <a class="production-link" href="/">Production overview</a
      ><span class="sample-tag">Synthetic venue data</span>
    </header>
    <div class="workspace">
      <nav aria-label="Main navigation">
        <a
          routerLink="/overview"
          queryParamsHandling="preserve"
          routerLinkActive="active"
          ariaCurrentWhenActive="page"
          >Shift overview</a
        ><a
          routerLink="/anomalies"
          queryParamsHandling="preserve"
          routerLinkActive="active"
          ariaCurrentWhenActive="page"
          >Anomaly review</a
        >
      </nav>
      <app-filters />
      <main id="main"><router-outlet /></main>
      <footer>
        Fictional venue. No visitor records. All times are venue local hours,
        12:00 to 23:00.
      </footer>
    </div>`,
})
export class AppComponent {}
