import { Component, EventEmitter, Input, Output } from "@angular/core";
import { PanelState } from "../../shared/models";
@Component({
  selector: "app-panel",
  standalone: true,
  template: ` @if (!state || state.status === "loading") {
      <div class="panel-message loading" role="status">
        Loading {{ label }}…
      </div>
    } @else if (state.status === "error") {
      <div class="panel-message" role="alert">
        <p>{{ state.message }}</p>
        <button class="secondary" type="button" (click)="retry.emit()">
          Retry {{ label }}
        </button>
      </div>
    } @else {
      <ng-content />
    }`,
})
export class PanelComponent {
  @Input({ required: true }) state: PanelState<unknown> | null = null;
  @Input({ required: true }) label = "";
  @Output() retry = new EventEmitter<void>();
}
