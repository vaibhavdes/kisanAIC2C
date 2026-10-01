// Indian cropping season used for planning, matching the API's current_season():
// kharif June–September, rabi October–February, summer (zaid) March–May.
export function currentSeason(today: Date = new Date()): "kharif" | "rabi" | "summer" {
  const month = today.getMonth() + 1;
  if (month >= 6 && month <= 9) return "kharif";
  if (month >= 10 || month <= 2) return "rabi";
  return "summer";
}
