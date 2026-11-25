// ============================================================
// OneRoadTrip - Installation de l'application (mode hors ligne)
// ------------------------------------------------------------
// Nov. 2026 : plus de bouton flottant sur les pages (genant sur
// telephone, et il aurait gene la carte hotel en bas de l'ecran).
// L'installation est expliquee en tete de l'aide (help-xx.html).
// Quand Chrome ou Edge proposent l'installation, le bouton de
// l'aide (#ortInstallHere) apparait et la lance. Sur iPhone,
// Apple n'autorise pas l'installation au clic : l'aide l'explique.
// ============================================================

(function() {
  'use strict';

  // Deja dans l'application installee : rien a faire.
  if ((window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
      window.navigator.standalone === true) {
    return;
  }

  var deferredPrompt = null;

  function zone() { return document.getElementById('ortInstallHere'); }
  function show() { var z = zone(); if (z && deferredPrompt) z.hidden = false; }
  function hide() { var z = zone(); if (z) z.hidden = true; }
  function whenReady(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  // Chrome / Edge : on garde la proposition d'installation pour le bouton de l'aide,
  // sans afficher leur propre bandeau en bas de l'ecran.
  window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault();
    deferredPrompt = e;
    whenReady(show);
  });

  window.addEventListener('appinstalled', function() {
    if (window.clarity) clarity('event', 'pwa_installee');
    deferredPrompt = null;
    hide();
  });

  document.addEventListener('click', function(e) {
    var btn = e.target && e.target.closest ? e.target.closest('#ortInstallHere button') : null;
    if (!btn) return;
    // La proposition a expire ou a deja servi : le bouton ne sert plus a rien.
    if (!deferredPrompt) { hide(); return; }
    if (window.clarity) clarity('event', 'pwa_clic_installer');
    var prompted = deferredPrompt;
    deferredPrompt = null; // consomme tout de suite : un 2e clic ne peut plus rien casser
    try {
      prompted.prompt();
      prompted.userChoice.then(function(choice) {
        if (window.clarity) clarity('event', 'pwa_choix_' + choice.outcome);
        hide();
      }).catch(function() { hide(); });
    } catch (err) {
      if (window.clarity) clarity('event', 'pwa_erreur_prompt');
      hide();
    }
  });
})();
