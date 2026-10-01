// eBay Marketplace Account Deletion endpoint as a Cloudflare Worker.
// Free tier, always on, stable https://<name>.<account>.workers.dev address:
// no domain, no tunnel, no dependence on the 5090 being awake.
//
//   GET  ?challenge_code=X  -> {"challengeResponse": hex(SHA-256(X + token + endpoint))}
//   POST (deletion notice)  -> 204. The hunter keeps no eBay user data
//                              (seller usernames are dropped at read time), so there is
//                              nothing to purge; the notice is acknowledged and counted.
//
// Secrets (set with wrangler, never in this file):
//   EBAY_VERIFICATION_TOKEN   32-80 chars, letters/digits/_/-
//   EBAY_DELETION_ENDPOINT    the exact URL registered with eBay, e.g.
//                             https://ebay-deletion.<account>.workers.dev/ebay/account-deletion

const PATH = "/ebay/account-deletion";

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return json(200, { status: "ok" });
    if (url.pathname !== PATH) return json(404, { status: "ERROR", message: "not found" });

    const token = env.EBAY_VERIFICATION_TOKEN || "";
    const endpoint = env.EBAY_DELETION_ENDPOINT || "";

    if (request.method === "GET") {
      const code = url.searchParams.get("challenge_code") || "";
      if (!code || !token || !endpoint) {
        return json(400, { status: "ERROR", message: "not configured or no challenge_code" });
      }
      return json(200, { challengeResponse: await sha256Hex(code + token + endpoint) });
    }

    if (request.method === "POST") {
      // Acknowledge fast, as eBay requires. Read the body only to confirm it's a deletion notice.
      try {
        const notice = await request.json();
        const topic = notice?.metadata?.topic || "";
        console.log(`eBay notice: ${topic || "unknown topic"}`); // no user ids logged
      } catch (_) {
        // a malformed body is still acknowledged; eBay retries otherwise
      }
      return new Response(null, { status: 204 });
    }

    return json(405, { status: "ERROR", message: "method not allowed" });
  },
};
