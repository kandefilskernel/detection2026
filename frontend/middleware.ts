import { NextResponse, type NextRequest } from "next/server";

const PUBLIC = new Set(["/login", "/accueil"]);

/** Barrière côté serveur : sans témoin de session, aucune page protégée n'est servie.
 *  Visiteur non connecté : la racine mène à la page d'accueil, les autres pages à la connexion. */
export function middleware(req: NextRequest) {
  const logged = !!req.cookies.get("fraud-rdc-session")?.value;
  const { pathname } = req.nextUrl;
  if (pathname === "/login") {
    return logged ? NextResponse.redirect(new URL("/", req.url)) : NextResponse.next();
  }
  if (PUBLIC.has(pathname)) return NextResponse.next();
  if (!logged) {
    if (pathname === "/") return NextResponse.redirect(new URL("/accueil", req.url));
    const url = new URL("/login", req.url);
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!api|_next|.*\\..*).*)"] };
