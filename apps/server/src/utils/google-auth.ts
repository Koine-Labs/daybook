/**
 * Google ID token validation via JWKS.
 * Validates tokens issued by accounts.google.com using Google's public keys.
 */

import { jwtVerify, createRemoteJWKSet } from "jose";

const GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs";
const GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"];

interface GoogleTokenPayload {
  sub: string; // Google user ID
  email: string;
  email_verified: boolean;
  name?: string;
  picture?: string;
}

/** Verify a Google ID token and return the user claims. */
export async function verifyGoogleToken(
  idToken: string,
  clientId: string
): Promise<GoogleTokenPayload> {
  const jwks = createRemoteJWKSet(new URL(GOOGLE_JWKS_URL));

  const { payload } = await jwtVerify(idToken, jwks, {
    audience: clientId,
    issuer: GOOGLE_ISSUERS,
  });

  if (!payload.email || !payload.sub) {
    throw new Error("Google token missing required claims");
  }

  if (!payload.email_verified) {
    throw new Error("Google email not verified");
  }

  return {
    sub: payload.sub as string,
    email: payload.email as string,
    email_verified: payload.email_verified as boolean,
    name: payload.name as string | undefined,
    picture: payload.picture as string | undefined,
  };
}
