import { expect, test } from "vitest";

import { formatDateTime } from "./ServiceDetailPage";

test("formate la date de dernière vérification pour l’utilisateur", () => {
  const formatted = formatDateTime("2026-07-15T12:34:00Z");

  expect(formatted).not.toContain("T12:34:00Z");
  expect(formatted).toMatch(/2026/);
  expect(formatDateTime(null)).toBe("Jamais");
  expect(formatDateTime("date-invalide")).toBe("Date inconnue");
});
