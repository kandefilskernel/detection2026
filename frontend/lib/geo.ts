/**
 * Référentiel géographique des 26 provinces de la RDC (chef-lieu et coordonnées approximatives).
 * Les opérateurs transmettent la province d'origine de la transaction, pas des coordonnées GPS :
 * chaque fraude est donc placée autour du chef-lieu de sa province.
 */
export type ProvinceGeo = { name: string; capital: string; lat: number; lng: number };

const PROVINCES: ProvinceGeo[] = [
  { name: "Kinshasa", capital: "Kinshasa", lat: -4.325, lng: 15.322 },
  { name: "Kongo-Central", capital: "Matadi", lat: -5.816, lng: 13.45 },
  { name: "Kwango", capital: "Kenge", lat: -4.806, lng: 16.9 },
  { name: "Kwilu", capital: "Bandundu", lat: -3.317, lng: 17.38 },
  { name: "Mai-Ndombe", capital: "Inongo", lat: -1.95, lng: 18.267 },
  { name: "Kasaï", capital: "Tshikapa", lat: -6.416, lng: 20.8 },
  { name: "Kasaï-Central", capital: "Kananga", lat: -5.896, lng: 22.417 },
  { name: "Kasaï-Oriental", capital: "Mbuji-Mayi", lat: -6.136, lng: 23.59 },
  { name: "Lomami", capital: "Kabinda", lat: -6.133, lng: 24.483 },
  { name: "Sankuru", capital: "Lusambo", lat: -4.97, lng: 23.44 },
  { name: "Maniema", capital: "Kindu", lat: -2.95, lng: 25.917 },
  { name: "Sud-Kivu", capital: "Bukavu", lat: -2.508, lng: 28.861 },
  { name: "Nord-Kivu", capital: "Goma", lat: -1.679, lng: 29.222 },
  { name: "Ituri", capital: "Bunia", lat: 1.567, lng: 30.25 },
  { name: "Haut-Uele", capital: "Isiro", lat: 2.767, lng: 27.617 },
  { name: "Bas-Uele", capital: "Buta", lat: 2.8, lng: 24.733 },
  { name: "Tshopo", capital: "Kisangani", lat: 0.515, lng: 25.191 },
  { name: "Tshuapa", capital: "Boende", lat: -0.217, lng: 20.867 },
  { name: "Mongala", capital: "Lisala", lat: 2.15, lng: 21.517 },
  { name: "Nord-Ubangi", capital: "Gbadolite", lat: 4.283, lng: 21.017 },
  { name: "Sud-Ubangi", capital: "Gemena", lat: 3.25, lng: 19.767 },
  { name: "Équateur", capital: "Mbandaka", lat: 0.048, lng: 18.26 },
  { name: "Haut-Lomami", capital: "Kamina", lat: -8.733, lng: 25.0 },
  { name: "Lualaba", capital: "Kolwezi", lat: -10.716, lng: 25.473 },
  { name: "Haut-Katanga", capital: "Lubumbashi", lat: -11.664, lng: 27.479 },
  { name: "Tanganyika", capital: "Kalemie", lat: -5.947, lng: 29.194 },
];

/** « Kasai-Oriental », « kasaï oriental », « KASAI_ORIENTAL » -> même clé. */
const norm = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[\s_]+/g, "-").trim();

const BY_KEY = new Map(PROVINCES.map((p) => [norm(p.name), p]));

export function provinceGeo(name: string | null | undefined): ProvinceGeo | undefined {
  return name ? BY_KEY.get(norm(name)) : undefined;
}

/** Cadrage de la carte (RDC entière). */
export const DRC_BOUNDS: [[number, number], [number, number]] = [[-13.5, 12.0], [5.5, 31.5]];

/**
 * Position d'affichage d'une fraude : autour du chef-lieu, décalée de façon déterministe
 * (même transaction -> même point) pour que les fraudes d'une même province ne se superposent pas.
 */
export function fraudPosition(geo: ProvinceGeo, transactionId: string, maxRadiusDeg = 0.3): [number, number] {
  let h = 2166136261;
  for (let i = 0; i < transactionId.length; i++) h = Math.imul(h ^ transactionId.charCodeAt(i), 16777619);
  const n = h >>> 0;
  const u = (n % 10007) / 10007;
  const v = (Math.floor(n / 10007) % 10007) / 10007;
  const r = maxRadiusDeg * Math.sqrt(u);           // répartition uniforme dans le disque
  const a = 2 * Math.PI * v;
  return [geo.lat + r * Math.sin(a), geo.lng + r * Math.cos(a)];
}
