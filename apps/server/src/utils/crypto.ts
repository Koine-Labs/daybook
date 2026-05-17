/**
 * PBKDF2 password hashing via Web Crypto API (Workers-compatible, no native deps).
 */

const ITERATIONS = 100_000;
const KEY_LENGTH = 32; // bytes
const HASH_ALGO = "SHA-256";

/** Hash a password with a random salt. Returns "salt:hash" in hex. */
export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const key = await deriveKey(password, salt);
  const hash = await crypto.subtle.exportKey("raw", key) as ArrayBuffer;

  return `${toHex(salt)}:${toHex(new Uint8Array(hash))}`;
}

/** Verify a password against a "salt:hash" string. */
export async function verifyPassword(
  password: string,
  stored: string
): Promise<boolean> {
  const [saltHex, hashHex] = stored.split(":");
  if (!saltHex || !hashHex) return false;

  const salt = fromHex(saltHex);
  const key = await deriveKey(password, salt);
  const hash = await crypto.subtle.exportKey("raw", key) as ArrayBuffer;

  return toHex(new Uint8Array(hash)) === hashHex;
}

async function deriveKey(
  password: string,
  salt: Uint8Array
): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(password),
    "PBKDF2",
    false,
    ["deriveBits", "deriveKey"]
  );

  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: ITERATIONS, hash: HASH_ALGO },
    baseKey,
    { name: "HMAC", hash: HASH_ALGO, length: KEY_LENGTH * 8 },
    true,
    ["sign"]
  );
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

/** Hash a string with SHA-256 (for refresh token storage). */
export async function sha256(input: string): Promise<string> {
  const enc = new TextEncoder();
  const hash = await crypto.subtle.digest("SHA-256", enc.encode(input));
  return toHex(new Uint8Array(hash));
}
