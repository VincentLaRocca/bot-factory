// node test.mjs  — offline check of the worker against eBay's handshake
import assert from "node:assert";
import { createHash } from "node:crypto";
import worker from "./worker.js";

const env = { EBAY_VERIFICATION_TOKEN: "a".repeat(40), EBAY_DELETION_ENDPOINT: "https://ebay-deletion.x.workers.dev/ebay/account-deletion" };
const base = "https://ebay-deletion.x.workers.dev";

let r = await worker.fetch(new Request(`${base}/ebay/account-deletion?challenge_code=abc123`), env);
assert.equal(r.status, 200);
assert.match(r.headers.get("Content-Type"), /application\/json/);
const want = createHash("sha256").update("abc123" + env.EBAY_VERIFICATION_TOKEN + env.EBAY_DELETION_ENDPOINT).digest("hex");
assert.deepEqual(await r.json(), { challengeResponse: want });

r = await worker.fetch(new Request(`${base}/ebay/account-deletion`, { method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ metadata: { topic: "MARKETPLACE_ACCOUNT_DELETION" }, notification: { data: { username: "u", userId: "i" } } }) }), env);
assert.equal(r.status, 204);

r = await worker.fetch(new Request(`${base}/ebay/account-deletion`, { method: "POST", body: "not json" }), env);
assert.equal(r.status, 204);

r = await worker.fetch(new Request(`${base}/ebay/account-deletion?challenge_code=x`), {});
assert.equal(r.status, 400);
r = await worker.fetch(new Request(`${base}/other`), env);
assert.equal(r.status, 404);
r = await worker.fetch(new Request(`${base}/health`), env);
assert.equal(r.status, 200);
console.log("worker: all checks passed");
