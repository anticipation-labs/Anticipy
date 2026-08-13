// Dependency-free Twilio request signing for PocketBase's ES5 Goja runtime.
// Twilio signs: exact configured URL + sorted form key/value pairs, using
// HMAC-SHA1, then Base64.  This module is pure and is cross-checked in tests
// against Twilio's published vector and Python's standard hmac library.

function utf8Bytes(text) {
  const out = [];
  const s = String(text || "");
  for (let i = 0; i < s.length; i++) {
    let cp = s.charCodeAt(i);
    if (cp >= 0xd800 && cp <= 0xdbff && i + 1 < s.length) {
      const lo = s.charCodeAt(i + 1);
      if (lo >= 0xdc00 && lo <= 0xdfff) {
        cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
        i++;
      }
    }
    if (cp <= 0x7f) out.push(cp);
    else if (cp <= 0x7ff) {
      out.push(0xc0 | (cp >>> 6), 0x80 | (cp & 0x3f));
    } else if (cp <= 0xffff) {
      out.push(0xe0 | (cp >>> 12), 0x80 | ((cp >>> 6) & 0x3f), 0x80 | (cp & 0x3f));
    } else {
      out.push(0xf0 | (cp >>> 18), 0x80 | ((cp >>> 12) & 0x3f),
        0x80 | ((cp >>> 6) & 0x3f), 0x80 | (cp & 0x3f));
    }
  }
  return out;
}

function rol(value, bits) {
  return ((value << bits) | (value >>> (32 - bits))) >>> 0;
}

function sha1Bytes(input) {
  const bytes = input.slice();
  const bitLength = bytes.length * 8;
  bytes.push(0x80);
  while ((bytes.length % 64) !== 56) bytes.push(0);
  const high = Math.floor(bitLength / 0x100000000);
  const low = bitLength >>> 0;
  for (let shift = 24; shift >= 0; shift -= 8) bytes.push((high >>> shift) & 0xff);
  for (let shift = 24; shift >= 0; shift -= 8) bytes.push((low >>> shift) & 0xff);

  let h0 = 0x67452301;
  let h1 = 0xefcdab89;
  let h2 = 0x98badcfe;
  let h3 = 0x10325476;
  let h4 = 0xc3d2e1f0;
  const w = new Array(80);

  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let i = 0; i < 16; i++) {
      const p = offset + i * 4;
      w[i] = ((bytes[p] << 24) | (bytes[p + 1] << 16) |
        (bytes[p + 2] << 8) | bytes[p + 3]) >>> 0;
    }
    for (let i = 16; i < 80; i++) {
      w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    for (let i = 0; i < 80; i++) {
      let f, k;
      if (i < 20) { f = (b & c) | ((~b) & d); k = 0x5a827999; }
      else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const temp = (rol(a, 5) + (f >>> 0) + e + k + w[i]) >>> 0;
      e = d; d = c; c = rol(b, 30); b = a; a = temp;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
  }

  const out = [];
  for (const word of [h0, h1, h2, h3, h4]) {
    out.push((word >>> 24) & 0xff, (word >>> 16) & 0xff,
      (word >>> 8) & 0xff, word & 0xff);
  }
  return out;
}

function base64(bytes) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i];
    const hasB = i + 1 < bytes.length;
    const hasC = i + 2 < bytes.length;
    const b = hasB ? bytes[i + 1] : 0;
    const c = hasC ? bytes[i + 2] : 0;
    out += alphabet[a >>> 2];
    out += alphabet[((a & 3) << 4) | (b >>> 4)];
    out += hasB ? alphabet[((b & 15) << 2) | (c >>> 6)] : "=";
    out += hasC ? alphabet[c & 63] : "=";
  }
  return out;
}

function hmacSha1(keyText, messageText) {
  let key = utf8Bytes(keyText);
  if (key.length > 64) key = sha1Bytes(key);
  while (key.length < 64) key.push(0);
  const inner = [], outer = [];
  for (let i = 0; i < 64; i++) {
    inner.push(key[i] ^ 0x36);
    outer.push(key[i] ^ 0x5c);
  }
  return sha1Bytes(outer.concat(sha1Bytes(inner.concat(utf8Bytes(messageText)))));
}

function expectedSignature(authToken, url, params) {
  let payload = String(url || "");
  const keys = Object.keys(params || {}).sort();
  for (const key of keys) {
    const raw = params[key];
    const values = Array.isArray(raw) ? raw.slice().sort() : [raw];
    for (const value of values) payload += key + String(value == null ? "" : value);
  }
  return base64(hmacSha1(authToken, payload));
}

function constantTimeEqual(a, b) {
  const left = String(a || ""), right = String(b || "");
  let diff = left.length ^ right.length;
  const size = Math.max(left.length, right.length);
  for (let i = 0; i < size; i++) {
    diff |= (left.charCodeAt(i % Math.max(1, left.length)) || 0) ^
      (right.charCodeAt(i % Math.max(1, right.length)) || 0);
  }
  return diff === 0;
}

module.exports = {
  expectedSignature: expectedSignature,
  validate: function (authToken, url, params, supplied) {
    return constantTimeEqual(expectedSignature(authToken, url, params), supplied);
  },
};
