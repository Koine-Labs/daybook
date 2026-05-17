/**
 * JWT sign/verify using the jose library (Workers-compatible).
 */

import { SignJWT, jwtVerify } from "jose";
import type { JWTPayload } from "../types";

/** Sign an access token. */
export async function signAccessToken(
  payload: { sub: string; email: string; role: string },
  secret: string,
  ttlSeconds: number
): Promise<string> {
  const key = new TextEncoder().encode(secret);

  return new SignJWT({ email: payload.email, role: payload.role })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(payload.sub)
    .setIssuedAt()
    .setExpirationTime(`${ttlSeconds}s`)
    .setIssuer("lullaby")
    .sign(key);
}

/** Verify and decode an access token. Returns null if invalid/expired. */
export async function verifyAccessToken(
  token: string,
  secret: string
): Promise<JWTPayload | null> {
  try {
    const key = new TextEncoder().encode(secret);
    const { payload } = await jwtVerify(token, key, { issuer: "lullaby" });

    return {
      sub: payload.sub as string,
      email: payload.email as string,
      role: payload.role as string,
      iat: payload.iat as number,
      exp: payload.exp as number,
    };
  } catch {
    return null;
  }
}

/** Generate a random refresh token string. */
export function generateRefreshToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
