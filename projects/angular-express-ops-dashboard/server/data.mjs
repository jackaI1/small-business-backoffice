export const stations = [
  { id: "north", name: "North gate", capacity: 180 },
  { id: "south", name: "South gate", capacity: 140 },
  { id: "concessions", name: "Concessions", capacity: 100 },
  { id: "information", name: "Information desk", capacity: 60 },
];
export const metadata = { from: "2026-10-26", to: "2026-11-01", stations };
// Fixed arithmetic makes each run reproducible. These are station-hour counts, not people.
export const records = Array.from({ length: 7 }, (_, day) => {
  const date = new Date(Date.UTC(2026, 9, 26 + day)).toISOString().slice(0, 10);
  return stations.flatMap((station, index) =>
    Array.from({ length: 12 }, (_, offset) => {
      const hour = offset + 12;
      const evening = hour >= 17 && hour <= 20 ? 0.38 : 0;
      let ratio =
        0.31 + ((day * 11 + offset * 7 + index * 13) % 29) / 100 + evening;
      if (day === 4 && hour === 18 && station.id === "north") ratio = 1.28;
      if (day === 2 && hour === 14 && station.id === "information")
        ratio = 0.12;
      const volume = Math.round(station.capacity * ratio);
      return {
        id: `${date}-${hour}-${station.id}`,
        date,
        hour,
        stationId: station.id,
        volume,
        capacity: station.capacity,
      };
    }),
  );
}).flat();
export const utilisation = (row) =>
  Math.round((row.volume / row.capacity) * 1000) / 10;
export const anomalyType = (row) =>
  utilisation(row) >= 95 ? "surge" : utilisation(row) < 25 ? "quiet" : null;
