export interface Filters {
  from: string;
  to: string;
  station: string;
}
export interface Station {
  id: string;
  name: string;
  capacity: number;
}
export interface Metadata {
  from: string;
  to: string;
  stations: Station[];
}
export interface HourPoint {
  hour: number;
  volume: number;
}
export interface Volume {
  total: number;
  peakHour: number | null;
  hours: HourPoint[];
}
export interface StationPoint extends Station {
  volume: number;
  capacityTotal: number;
  utilisation: number;
}
export interface Anomaly {
  id: string;
  date: string;
  hour: number;
  station: string;
  stationId: string;
  volume: number;
  utilisation: number;
  type: "surge" | "quiet";
}
export interface PanelState<T> {
  status: "loading" | "ready" | "error";
  data?: T;
  message?: string;
}
