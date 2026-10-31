// AntiScroll - script d'arrière-plan.
// Récupère le code (sous forme chiffrée) depuis l'app PC et vérifie les
// codes tapés. Marche même si l'app PC est fermée (dernier code connu).
const BRIDGE = "http://127.0.0.1:47811";

async function refresh() {
  try {
    const r = await fetch(BRIDGE + "/status", { cache: "no-store" });
    const s = await r.json();
    await browser.storage.local.set({ unlock: s.unlock || null, bridgeOk: true, lastSeen: Date.now() });
  } catch (e) {
    await browser.storage.local.set({ bridgeOk: false });
  }
}

function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

async function pbkdf2Hex(code, saltHex, iter) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(code),
    "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: hexToBytes(saltHex), iterations: iter }, key, 256);
  return [...new Uint8Array(bits)].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function verify(code) {
  const { unlock } = await browser.storage.local.get("unlock");
  if (!unlock) return true; // aucun code choisi
  const h = await pbkdf2Hex(code, unlock.salt, unlock.iter || 150000);
  return h === unlock.hash;
}

browser.runtime.onMessage.addListener(async (msg) => {
  if (msg.type === "verify") return { ok: await verify(msg.code || "") };
  if (msg.type === "info") {
    await refresh();
    const s = await browser.storage.local.get(["unlock", "bridgeOk"]);
    return { hasCode: !!s.unlock, bridgeOk: !!s.bridgeOk };
  }
});

refresh();
setInterval(refresh, 30000);
