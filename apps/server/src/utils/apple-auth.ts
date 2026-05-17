/**
 * Apple identity token validation via JWKS.
 * Validates tokens from Sign in with Apple using Apple's public keys.
 */

import { jwtVerify, createRemoteJWKSet } from "jose";

const APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys";
const APPLE_ISSUER = "https://appleid.apple.com";

interface AppleTokenPayload {
  sub: string; // Apple user ID (stable per app)
  email?: string;
  email_verified?: boolean;
  is_private_email?: boolean;
}

/** Verify an Apple identity token and return the user claims. */
export async function verifyAppleToken(
  identityToken: string,
  bundleId: string
): Promise<AppleTokenPayload> {
  const jwks = createRemoteJWKSet(new URL(APPLE_JWKS_URL));

  const { payload } = await jwtVerify(identityToken, jwks, {
    audience: bundleId,
    issuer: APPLE_ISSUER,
  });

  if (!payload.sub) {
    throw new Error("Apple token missing subject");
  }

  return {
    sub: payload.sub as string,
    email: payload.email as string | undefined,
    email_verified: payload.email_verified as boolean | undefined,
    is_private_email: payload.is_private_email as boolean | undefined,
  };
}
