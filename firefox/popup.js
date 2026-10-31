browser.runtime.sendMessage({ type: "info" }).then(i => {
  document.getElementById("a").innerHTML = i.bridgeOk
    ? '<span class="ok">App PC connectée ✔</span>'
    : '<span class="ko">App PC non détectée</span> (dernier code connu utilisé)';
  document.getElementById("b").innerHTML = i.hasCode
    ? '<span class="ok">Code défini ✔</span>'
    : '<span class="ko">Aucun code : choisis-en un dans l\'app PC</span>';
});
