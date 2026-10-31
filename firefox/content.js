// AntiScroll - détecte chaque nouvelle vidéo "courte" et demande le code.
(() => {
  const host = location.hostname;

  // Est-on dans un fil de vidéos courtes ? Renvoie une clé si l'URL identifie la vidéo.
  function feedInfo() {
    const p = location.pathname;
    if (host.includes("youtube.com")) {
      return p.startsWith("/shorts/") ? { feed: true, urlKey: p } : { feed: false };
    }
    if (host.includes("instagram.com")) {
      if (/^\/(reels?|reel)\//.test(p)) return { feed: true, urlKey: p.length > 8 ? p : null };
      return { feed: false };
    }
    if (host.includes("tiktok.com")) {
      if (/^\/(messages|upload|setting|login|signup)/.test(p)) return { feed: false };
      return { feed: true, urlKey: /\/video\/\d+/.test(p) ? p : null };
    }
    if (host.includes("snapchat.com")) {
      return p.startsWith("/spotlight") ? { feed: true, urlKey: null } : { feed: false };
    }
    if (host.includes("facebook.com")) {
      return /^\/(reel|reels)\//.test(p) ? { feed: true, urlKey: p } : { feed: false };
    }
    return { feed: false };
  }

  // Identifiant stable pour chaque balise <video>
  const ids = new WeakMap();
  let nextId = 1;
  const vid = v => { if (!ids.has(v)) ids.set(v, nextId++); return ids.get(v); };

  // La vidéo principale visible à l'écran
  function activeVideo() {
    let best = null, bestArea = 0;
    for (const v of document.querySelectorAll("video")) {
      const r = v.getBoundingClientRect();
      const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
      const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
      const area = w * h;
      if (area > bestArea && h > innerHeight * 0.35) { best = v; bestArea = area; }
    }
    return best;
  }

  let lastOk = null;      // clé de la dernière vidéo débloquée
  let blocking = false;
  let overlay = null;

  function pauseAll() {
    for (const v of document.querySelectorAll("video")) { try { v.pause(); } catch (e) {} }
  }

  // Si le site relance la vidéo pendant le blocage, on remet en pause
  document.addEventListener("play", e => {
    if (blocking && e.target.tagName === "VIDEO") e.target.pause();
  }, true);

  // Empêche les raccourcis du site (flèches, j/k, molette) pendant le blocage
  window.addEventListener("keydown", e => {
    if (blocking && !(overlay && overlay.contains(e.target))) {
      e.stopImmediatePropagation(); e.preventDefault();
    }
  }, true);

  function showOverlay(key) {
    blocking = true;
    pauseAll();
    if (overlay) overlay.remove();
    overlay = document.createElement("div");
    overlay.setAttribute("style", [
      "position:fixed", "inset:0", "z-index:2147483647", "background:#000",
      "display:flex", "align-items:center", "justify-content:center",
      "font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif", "padding:16px"
    ].join(";"));
    // Fond noir opaque + carte blanche/cyan au centre
    overlay.innerHTML = `
      <div style="background:#fff;color:#0f172a;border-radius:22px;border:2px solid #06b6d4;
                  box-shadow:0 20px 60px rgba(6,182,212,.25);padding:30px 28px 22px;
                  width:100%;max-width:400px;box-sizing:border-box;
                  display:flex;flex-direction:column;align-items:center;gap:12px;text-align:center">
        <div style="font-size:13px;font-weight:700;color:#0891b2;letter-spacing:.04em">AntiScroll</div>
        <div style="font-size:26px;font-weight:800;line-height:1.2">Encore une vidéo ?</div>
        <div style="color:#64748b;font-size:15px;line-height:1.45">
          Tape ton code pour voir <b style="color:#0f172a">cette</b> vidéo. Il sera redemandé à la suivante.</div>
        <input type="password" placeholder="Code" autocomplete="off"
          style="font-size:20px;padding:12px 14px;border-radius:12px;border:2px solid #dbe7ec;
                 background:#f4f9fb;color:#0f172a;text-align:center;width:100%;box-sizing:border-box;
                 outline:none;margin-top:4px">
        <button data-a="ok" style="font-size:16px;font-weight:700;padding:12px 18px;border-radius:12px;
          border:0;background:#06b6d4;color:#fff;cursor:pointer;width:100%">Débloquer</button>
        <button data-a="leave" style="font-size:14px;padding:8px 18px;border-radius:10px;border:0;
          background:transparent;color:#64748b;cursor:pointer;text-decoration:underline">Partir</button>
        <div data-m style="color:#ef4444;font-size:14px;min-height:18px"></div>
      </div>`;
    document.documentElement.appendChild(overlay);
    const input = overlay.querySelector("input");
    const msg = overlay.querySelector("[data-m]");
    overlay.addEventListener("wheel", e => e.preventDefault(), { passive: false });
    overlay.addEventListener("touchmove", e => e.preventDefault(), { passive: false });

    async function submit() {
      const code = input.value; input.value = "";
      const r = await browser.runtime.sendMessage({ type: "verify", code });
      if (r && r.ok) {
        lastOk = key; blocking = false; overlay.remove(); overlay = null;
        const v = activeVideo(); if (v) v.play().catch(() => {});
      } else msg.textContent = "Code incorrect";
    }
    input.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") submit(); });
    overlay.querySelector('[data-a="ok"]').onclick = submit;
    overlay.querySelector('[data-a="leave"]').onclick = () => {
      location.href = host.includes("youtube.com") ? "https://www.youtube.com/feed/subscriptions" : "about:blank";
    };
    input.addEventListener("focus", () => { input.style.borderColor = "#06b6d4"; });
    input.addEventListener("blur", () => { input.style.borderColor = "#dbe7ec"; });
    const okBtn = overlay.querySelector('[data-a="ok"]');
    okBtn.addEventListener("mouseenter", () => { okBtn.style.background = "#0891b2"; });
    okBtn.addEventListener("mouseleave", () => { okBtn.style.background = "#06b6d4"; });
    setTimeout(() => input.focus(), 50);
  }

  function check() {
    const info = feedInfo();
    if (!info.feed) {
      if (overlay) { overlay.remove(); overlay = null; blocking = false; }
      return;
    }
    const v = activeVideo();
    if (!v && !info.urlKey) return;
    const key = info.urlKey || ("v" + vid(v) + "|" + (v.currentSrc || "").split("?")[0].slice(0, 120));
    if (key !== lastOk && !blocking) showOverlay(key);
    else if (blocking) pauseAll();
  }

  setInterval(check, 400);
})();
