import { NextResponse, type NextRequest } from "next/server";

/** Barrière côté serveur : sans témoin de session, aucune page protégée n'est servie. */
export function middleware(req: NextRequest) {
  const logged = !!req.cookies.get("fraud-rdc-session")?.value;
  const { pathname } = req.nextUrl;
  if (pathname === "/login") {
    return logged ? NextResponse.redirect(new URL("/", req.url)) : NextResponse.next();
  }
  if (!logged) {
    const url = new URL("/login", req.url);
    if (pathname !== "/") url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!api|_next|.*\\..*).*)"] };
