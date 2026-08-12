/* ort-comments.js - Commentaires + alertes sur les pages itineraires
 * ------------------------------------------------------------------
 * Depend de : ORT_TRIP (itin, lang, title), window.ortEnsureFirebase()
 * Collections Firestore :
 *   ort_comments        : un document par commentaire
 *   ort_comment_counts  : un document par itineraire ET par langue { n: nombre }
 *   ort_alerts          : un document par signalement
 * Aucune lecture Firestore tant que le visiteur n'a pas bouge (anti-robots).
 */
(function () {
  'use strict';

  console.log('[ORT-CM] fichier charge');

  var host = document.getElementById('ortCommentsHost');
  if (!host) {
    console.warn('[ORT-CM] arret : conteneur #ortCommentsHost absent de la page');
    return;
  }

  // Les donnees viennent des attributs du conteneur ; ORT_TRIP sert de secours.
  var TRIP = window.ORT_TRIP || {};
  var ITIN  = host.getAttribute('data-itin')  || TRIP.itin  || '';
  var TITLE = host.getAttribute('data-title') || TRIP.title || document.title || '';
  var LANG  = (host.getAttribute('data-lang') || TRIP.lang || document.documentElement.lang || 'fr').slice(0, 2);

  if (!ITIN) {
    console.warn('[ORT-CM] arret : aucun identifiant d itineraire');
    return;
  }
  var ITIN_KEY = ITIN.replace(/::/g, '__').replace(/[^A-Za-z0-9_\-]/g, '_');
  var COUNT_KEY = ITIN_KEY + '__' + LANG;   // un compteur par langue

  /* ---------- Textes ---------- */
  var T = {
    fr: { title: 'Commentaires', none: 'Aucun commentaire pour le moment.', first: 'Soyez le premier a commenter.',
          write: 'Ecrire un commentaire', placeholder: 'Votre commentaire...', send: 'Envoyer', sending: 'Envoi...',
          sent: 'Merci, votre commentaire est publie.', login: 'Connectez-vous pour commenter', err: 'Envoi impossible, reessayez.',
          alertTitle: 'Signaler un probleme', alertPh: 'Que voulez-vous nous signaler ?', alertSent: 'Merci, signalement envoye.',
          alertBtn: 'Signaler', cancel: 'Annuler', empty: 'Ecrivez quelque chose avant d\u2019envoyer.', del: 'Supprimer' , readErr: 'Commentaires momentanement indisponibles.' , replyBy: 'Reponse de OneRoadTrip' , alertTip: 'Signaler une erreur' },
    en: { title: 'Comments', none: 'No comments yet.', first: 'Be the first to comment.',
          write: 'Write a comment', placeholder: 'Your comment...', send: 'Send', sending: 'Sending...',
          sent: 'Thanks, your comment is published.', login: 'Sign in to comment', err: 'Could not send, please retry.',
          alertTitle: 'Report a problem', alertPh: 'What would you like to report?', alertSent: 'Thanks, report sent.',
          alertBtn: 'Report', cancel: 'Cancel', empty: 'Please write something first.', del: 'Delete' , readErr: 'Comments temporarily unavailable.' , replyBy: 'Reply from OneRoadTrip' , alertTip: 'Report an error' },
    es: { title: 'Comentarios', none: 'Todavia no hay comentarios.', first: 'Se el primero en comentar.',
          write: 'Escribir un comentario', placeholder: 'Tu comentario...', send: 'Enviar', sending: 'Enviando...',
          sent: 'Gracias, tu comentario esta publicado.', login: 'Inicia sesion para comentar', err: 'No se pudo enviar, reintenta.',
          alertTitle: 'Informar de un problema', alertPh: 'Que quieres senalar?', alertSent: 'Gracias, aviso enviado.',
          alertBtn: 'Informar', cancel: 'Cancelar', empty: 'Escribe algo antes de enviar.', del: 'Borrar' , readErr: 'Comentarios no disponibles por ahora.' , replyBy: 'Respuesta de OneRoadTrip' , alertTip: 'Informar de un error' },
    it: { title: 'Commenti', none: 'Nessun commento per ora.', first: 'Sii il primo a commentare.',
          write: 'Scrivi un commento', placeholder: 'Il tuo commento...', send: 'Invia', sending: 'Invio...',
          sent: 'Grazie, il tuo commento e pubblicato.', login: 'Accedi per commentare', err: 'Invio non riuscito, riprova.',
          alertTitle: 'Segnala un problema', alertPh: 'Cosa vuoi segnalare?', alertSent: 'Grazie, segnalazione inviata.',
          alertBtn: 'Segnala', cancel: 'Annulla', empty: 'Scrivi qualcosa prima di inviare.', del: 'Elimina' , readErr: 'Commenti momentaneamente non disponibili.' , replyBy: 'Risposta di OneRoadTrip' , alertTip: 'Segnala un errore' },
    pt: { title: 'Comentarios', none: 'Ainda nao ha comentarios.', first: 'Seja o primeiro a comentar.',
          write: 'Escrever um comentario', placeholder: 'O seu comentario...', send: 'Enviar', sending: 'A enviar...',
          sent: 'Obrigado, o seu comentario esta publicado.', login: 'Inicie sessao para comentar', err: 'Nao foi possivel enviar, tente de novo.',
          alertTitle: 'Reportar um problema', alertPh: 'O que deseja reportar?', alertSent: 'Obrigado, reporte enviado.',
          alertBtn: 'Reportar', cancel: 'Cancelar', empty: 'Escreva algo antes de enviar.', del: 'Apagar' , readErr: 'Comentarios temporariamente indisponiveis.' , replyBy: 'Resposta da OneRoadTrip' , alertTip: 'Assinalar um erro' },
    de: { title: 'Kommentare', none: 'Noch keine Kommentare.', first: 'Schreiben Sie den ersten Kommentar.',
          write: 'Kommentar schreiben', placeholder: 'Ihr Kommentar...', send: 'Senden', sending: 'Wird gesendet...',
          sent: 'Danke, Ihr Kommentar ist veroffentlicht.', login: 'Zum Kommentieren anmelden', err: 'Senden fehlgeschlagen, bitte erneut versuchen.',
          alertTitle: 'Problem melden', alertPh: 'Was mochten Sie melden?', alertSent: 'Danke, Meldung gesendet.',
          alertBtn: 'Melden', cancel: 'Abbrechen', empty: 'Bitte zuerst etwas schreiben.', del: 'Loschen' , readErr: 'Kommentare vorubergehend nicht verfugbar.' , replyBy: 'Antwort von OneRoadTrip' , alertTip: 'Fehler melden' },
    nl: { title: 'Reacties', none: 'Nog geen reacties.', first: 'Wees de eerste die reageert.',
          write: 'Schrijf een reactie', placeholder: 'Uw reactie...', send: 'Versturen', sending: 'Versturen...',
          sent: 'Bedankt, uw reactie is geplaatst.', login: 'Log in om te reageren', err: 'Versturen mislukt, probeer opnieuw.',
          alertTitle: 'Probleem melden', alertPh: 'Wat wilt u melden?', alertSent: 'Bedankt, melding verstuurd.',
          alertBtn: 'Melden', cancel: 'Annuleren', empty: 'Schrijf eerst iets.', del: 'Verwijderen' , readErr: 'Reacties tijdelijk niet beschikbaar.' , replyBy: 'Antwoord van OneRoadTrip' , alertTip: 'Een fout melden' },
    ar: { title: '\u0627\u0644\u062a\u0639\u0644\u064a\u0642\u0627\u062a', none: '\u0644\u0627 \u062a\u0648\u062c\u062f \u062a\u0639\u0644\u064a\u0642\u0627\u062a \u0628\u0639\u062f.', first: '\u0643\u0646 \u0623\u0648\u0644 \u0645\u0646 \u064a\u0639\u0644\u0642.',
          write: '\u0627\u0643\u062a\u0628 \u062a\u0639\u0644\u064a\u0642\u064b\u0627', placeholder: '\u062a\u0639\u0644\u064a\u0642\u0643...', send: '\u0625\u0631\u0633\u0627\u0644', sending: '\u062c\u0627\u0631\u064d \u0627\u0644\u0625\u0631\u0633\u0627\u0644...',
          sent: '\u0634\u0643\u0631\u064b\u0627\u060c \u062a\u0645 \u0646\u0634\u0631 \u062a\u0639\u0644\u064a\u0642\u0643.', login: '\u0633\u062c\u0644 \u0627\u0644\u062f\u062e\u0648\u0644 \u0644\u0644\u062a\u0639\u0644\u064a\u0642', err: '\u062a\u0639\u0630\u0631 \u0627\u0644\u0625\u0631\u0633\u0627\u0644\u060c \u062d\u0627\u0648\u0644 \u0645\u062c\u062f\u062f\u064b\u0627.',
          alertTitle: '\u0627\u0644\u0625\u0628\u0644\u0627\u063a \u0639\u0646 \u0645\u0634\u0643\u0644\u0629', alertPh: '\u0645\u0627 \u0627\u0644\u0630\u064a \u062a\u0631\u064a\u062f \u0627\u0644\u0625\u0628\u0644\u0627\u063a \u0639\u0646\u0647\u061f', alertSent: '\u0634\u0643\u0631\u064b\u0627\u060c \u062a\u0645 \u0625\u0631\u0633\u0627\u0644 \u0627\u0644\u0628\u0644\u0627\u063a.',
          alertBtn: '\u0625\u0628\u0644\u0627\u063a', cancel: '\u0625\u0644\u063a\u0627\u0621', empty: '\u0627\u0643\u062a\u0628 \u0634\u064a\u0626\u064b\u0627 \u0642\u0628\u0644 \u0627\u0644\u0625\u0631\u0633\u0627\u0644.', del: '\u062d\u0630\u0641' , readErr: '\u0627\u0644\u062a\u0639\u0644\u064a\u0642\u0627\u062a \u063a\u064a\u0631 \u0645\u062a\u0627\u062d\u0629 \u062d\u0627\u0644\u064a\u064b\u0627.' , replyBy: '\u0631\u062f \u0645\u0646 OneRoadTrip' , alertTip: '\u0627\u0644\u0625\u0628\u0644\u0627\u063a \u0639\u0646 \u062e\u0637\u0623' }
  };
  var t = T[LANG] || T.en;

  /* ---------- Utilitaires ---------- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function el(tag, cls, html) {
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (html != null) d.innerHTML = html;
    return d;
  }
  function fbReady() {
    if (window.ortEnsureFirebase) return window.ortEnsureFirebase();
    if (window.firebase && window.firebase.firestore) return Promise.resolve();
    return Promise.reject(new Error('firebase absent'));
  }
  function currentUser() {
    try { return (window.firebase && firebase.auth && firebase.auth().currentUser) || null; } catch (e) { return null; }
  }
  function openLogin() {
    if (typeof OrtAuthModal !== 'undefined') {
      try {
        var m = new OrtAuthModal();
        Promise.resolve(m.init()).then(function () {
          m.mode = 'login';
          if (m.updateUI) m.updateUI();
          m.show();
        });
        return;
      } catch (e) { /* on retombe sur Google */ }
    }
    try {
      var p = new firebase.auth.GoogleAuthProvider();
      p.setCustomParameters({ prompt: 'select_account' });
      firebase.auth().signInWithPopup(p);
    } catch (e) { }
  }
  function fmtDate(ts) {
    try {
      var d = ts && ts.toDate ? ts.toDate() : new Date(ts);
      return d.toLocaleDateString(LANG, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) { return ''; }
  }

  /* ---------- Styles ---------- */
  var CSS = ''
    + '#ortCmBlk{margin:0;padding:0;font-family:inherit;width:100%}'
    + '#ortCmBlk .cm-head{display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none;background:#f2f6fb;border:1px solid #dbe6f2;border-radius:11px;padding:10px 14px;color:#113f7a;font-weight:700;font-size:.95rem}'
    + '#ortCmBlk .cm-head:hover{background:#e8f0f9}'
    + '#ortCmBlk .cm-arrow{display:inline-block;transition:transform .2s;font-size:.75rem}'
    + '#ortCmBlk.open .cm-arrow{transform:rotate(90deg)}'
    + '#ortCmBlk .cm-n{margin-left:auto;background:#113f7a;color:#fff;border-radius:999px;padding:1px 9px;font-size:.78rem;min-width:22px;text-align:center}'
    + '#ortCmBlk .cm-body{display:none;border:1px solid #dbe6f2;border-top:none;border-radius:0 0 11px 11px;padding:14px;background:#fff}'
    + '#ortCmBlk.open .cm-body{display:block}'
    + '#ortCmBlk.open .cm-head{border-radius:11px 11px 0 0}'
    + '#ortCmBlk .cm-item{padding:10px 0;border-bottom:1px solid #eef2f6}'
    + '#ortCmBlk .cm-item:last-child{border-bottom:none}'
    + '#ortCmBlk .cm-who{display:flex;align-items:center;gap:8px;margin-bottom:4px}'
    + '#ortCmBlk .cm-av{width:26px;height:26px;border-radius:50%;object-fit:cover;background:#dbe6f2;flex:none}'
    + '#ortCmBlk .cm-nm{font-weight:700;color:#113f7a;font-size:.88rem}'
    + '#ortCmBlk .cm-dt{color:#94a3b8;font-size:.76rem}'
    + '#ortCmBlk .cm-tx{margin:0;font-size:.9rem;line-height:1.55;color:#334155;white-space:pre-wrap;word-break:break-word}'
    + '#ortCmBlk .cm-rep{margin:7px 0 0 34px;padding:9px 12px;background:#f2f6fb;border-left:3px solid #113f7a;border-radius:0 9px 9px 0}'
    + '#ortCmBlk .cm-rep-w{font-weight:700;color:#113f7a;font-size:.8rem;margin-bottom:3px;display:flex;align-items:center;gap:6px}'
    + '#ortCmBlk .cm-rep-t{margin:0;font-size:.87rem;line-height:1.5;color:#334155;white-space:pre-wrap;word-break:break-word}'
    + '#ortCmBlk textarea{width:100%;min-height:76px;border:1px solid #d4e0ea;border-radius:9px;padding:9px 11px;font:inherit;font-size:.9rem;resize:vertical;box-sizing:border-box}'
    + '#ortCmBlk .cm-send,#ortAlBox .cm-send{margin-top:8px;background:#113f7a;color:#fff;border:none;border-radius:9px;padding:9px 18px;font-weight:700;font-size:.88rem;cursor:pointer}'
    + '#ortCmBlk .cm-send[disabled],#ortAlBox .cm-send[disabled]{opacity:.55;cursor:default}'
    + '#ortCmBlk .cm-msg{margin-top:7px;font-size:.84rem;color:#0a7d2c}'
    + '#ortCmBlk .cm-msg.ko{color:#b91c1c}'
    + '#ortCmBlk .cm-login{background:#fff;border:2px solid #113f7a;color:#113f7a;border-radius:9px;padding:9px 18px;font-weight:700;font-size:.88rem;cursor:pointer}'
    + '.ort-flag{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;margin-left:9px;width:23px;height:23px;border:1px solid #f0c9a8;background:#fff6ee;color:#c2410c;cursor:pointer;font-size:.85rem;font-weight:700;border-radius:50%;line-height:1;padding:0;flex:none}'
    + '.ort-flag:hover{background:#c2410c;color:#fff;border-color:#c2410c}'
    + '.ort-flag{position:relative}'
    + '.ort-flag::after{content:attr(data-tip);position:absolute;bottom:130%;left:50%;transform:translateX(-50%);background:#1e293b;color:#fff;font-size:.72rem;font-weight:600;white-space:nowrap;padding:5px 9px;border-radius:7px;opacity:0;pointer-events:none;transition:opacity .15s;z-index:50}'
    + '.ort-flag::before{content:"";position:absolute;bottom:118%;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top-color:#1e293b;opacity:0;pointer-events:none;transition:opacity .15s;z-index:50}'
    + '.ort-flag:hover::after,.ort-flag:focus::after,.ort-flag:hover::before,.ort-flag:focus::before{opacity:1}'
    + '.ort-flag-h1{width:30px;height:30px;font-size:1.05rem;margin-left:12px;background:rgba(255,255,255,.92);border-color:rgba(255,255,255,.7);box-shadow:0 2px 8px rgba(0,0,0,.35);vertical-align:middle}'
    + '@media(max-width:760px){.ort-flag::after,.ort-flag::before{display:none}.ort-flag-h1{width:25px;height:25px;font-size:.9rem;margin-left:8px}}'
    + '#ortAlOv{position:fixed;inset:0;background:rgba(8,15,30,.55);z-index:99990;display:flex;align-items:center;justify-content:center;padding:16px}'
    + '#ortAlBox{background:#fff;border-radius:14px;max-width:420px;width:100%;padding:20px;box-shadow:0 18px 50px rgba(0,0,0,.35)}'
    + '#ortAlBox h4{margin:0 0 4px;font-size:1rem;color:#113f7a}'
    + '#ortAlBox .al-tg{font-size:.82rem;color:#64748b;margin:0 0 12px;word-break:break-word}'
    + '#ortAlBox textarea{width:100%;min-height:96px;border:1px solid #d4e0ea;border-radius:9px;padding:9px 11px;font:inherit;font-size:.9rem;resize:vertical;box-sizing:border-box}'
    + '#ortAlBox .al-row{display:flex;gap:9px;align-items:center;margin-top:10px}'
    + '#ortAlBox .al-cancel{background:#fff;border:1px solid #d4e0ea;color:#475569;border-radius:9px;padding:9px 16px;font-size:.88rem;cursor:pointer}'
    + '#ortAlBox .al-msg{font-size:.84rem;color:#0a7d2c;margin-left:auto}'
    + '#ortAlBox .al-msg.ko{color:#b91c1c}'
    + '@media(max-width:760px){#ortCmBlk .cm-body{padding:10px}#ortCmBlk .cm-n{margin-left:4px}}';

  (function () {
    var s = document.createElement('style');
    s.textContent = CSS;
    document.head.appendChild(s);
  })();

  /* ---------- Bloc commentaires ---------- */
  var box = el('div', '');
  box.id = 'ortCmBlk';
  box.innerHTML =
    '<div class="cm-head" id="cmHead"><span class="cm-arrow">\u25b6</span>'
    + '<span>\uD83D\uDCAC ' + esc(t.title) + '</span>'
    + '<span class="cm-n" id="cmN" style="display:none">0</span></div>'
    + '<div class="cm-body" id="cmBody"><div id="cmList" style="color:#94a3b8;font-size:.88rem">\u2026</div>'
    + '<div id="cmForm" style="margin-top:12px"></div></div>';
  host.appendChild(box);
  console.log('[ORT-CM] bloc installe pour', ITIN_KEY);
  if (LANG === 'ar') box.setAttribute('dir', 'rtl');

  var listEl = box.querySelector('#cmList');
  var formEl = box.querySelector('#cmForm');
  var nEl = box.querySelector('#cmN');
  var loaded = false;

  box.querySelector('#cmHead').addEventListener('click', function () {
    var open = box.classList.toggle('open');
    if (open && !loaded) { loaded = true; loadComments(); }
  });

  /* Compteur : une seule lecture, et seulement si un humain a bouge */
  var counted = false;
  function loadCount() {
    if (counted) return;
    counted = true;
    var cached = null;
    try { cached = sessionStorage.getItem('ortCmN:' + COUNT_KEY); } catch (e) { }
    if (cached !== null) { showCount(parseInt(cached, 10) || 0); return; }
    fbReady().then(function () {
      return firebase.firestore().collection('ort_comment_counts').doc(COUNT_KEY).get();
    }).then(function (d) {
      var n = (d.exists && d.data().n) || 0;
      try { sessionStorage.setItem('ortCmN:' + COUNT_KEY, String(n)); } catch (e) { }
      showCount(n);
    }).catch(function () { });
  }
  function showCount(n) {
    if (n > 0) { nEl.textContent = n; nEl.style.display = ''; }
    else { nEl.style.display = 'none'; }
  }

  // Remet le compteur d'aplomb si quelqu'un a supprime des commentaires
  // directement dans la console Firestore. Necessite d'etre connecte.
  function syncCount(vrai) {
    if (!currentUser()) return;
    firebase.firestore().collection('ort_comment_counts').doc(COUNT_KEY)
      .set({ itin: ITIN, itinKey: ITIN_KEY, lang: LANG, title: TITLE, n: vrai }, { merge: true })
      .catch(function () { });
  }
  ['mousemove', 'scroll', 'touchstart', 'keydown'].forEach(function (ev) {
    window.addEventListener(ev, loadCount, { once: true, passive: true });
  });

  function loadComments() {
    fbReady().then(function () {
      // Pas de tri cote serveur : evite d'avoir a creer un index composite.
      return firebase.firestore().collection('ort_comments')
        .where('itinKey', '==', ITIN_KEY)
        .limit(200).get();
    }).then(function (snap) {
      listEl.innerHTML = '';
      var rows = [];
      snap.forEach(function (doc) {
        var c = doc.data();
        if ((c.lang || 'fr') === LANG) rows.push(c);   // une langue = ses commentaires
      });
      rows.sort(function (a, b) {
        var ta = a.ts && a.ts.toMillis ? a.ts.toMillis() : 0;
        var tb = b.ts && b.ts.toMillis ? b.ts.toMillis() : 0;
        return tb - ta;
      });
      if (!rows.length) {
        listEl.innerHTML = '<div style="color:#94a3b8;font-size:.88rem">' + esc(t.first) + '</div>';
        nEl.style.display = 'none';
        try { sessionStorage.setItem('ortCmN:' + COUNT_KEY, '0'); } catch (e) { }
        syncCount(0);
      } else {
        showCount(rows.length);
        try { sessionStorage.setItem('ortCmN:' + COUNT_KEY, String(rows.length)); } catch (e) { }
        syncCount(rows.length);
        rows.forEach(function (c) {
          var av = c.photo
            ? '<img class="cm-av" src="' + esc(c.photo) + '" alt="" referrerpolicy="no-referrer">'
            : '<span class="cm-av"></span>';
          var item = el('div', 'cm-item',
            '<div class="cm-who">' + av
            + '<span class="cm-nm">' + esc(c.name || '?') + '</span>'
            + '<span class="cm-dt">' + esc(fmtDate(c.ts)) + '</span></div>'
            + '<p class="cm-tx">' + esc(c.text || '') + '</p>'
            + (c.reply
                ? '<div class="cm-rep"><div class="cm-rep-w">\u21b3 ' + esc(t.replyBy) + '</div>'
                  + '<p class="cm-rep-t">' + esc(c.reply) + '</p></div>'
                : ''));
          listEl.appendChild(item);
        });
      }
      buildForm();
    }).catch(function (e) {
      console.warn('[ORT-CM] lecture impossible', e);
      listEl.innerHTML = '<div style="color:#b91c1c;font-size:.85rem">' + esc(t.readErr || t.err) + '</div>';
      buildForm();
    });
  }

  function buildForm() {
    fbReady().then(function () {
      firebase.auth().onAuthStateChanged(function (u) { renderForm(u); });
      renderForm(currentUser());
    }).catch(function () { renderForm(null); });
  }

  function renderForm(user) {
    formEl.innerHTML = '';
    if (!user) {
      var b = el('button', 'cm-login', esc(t.login));
      b.addEventListener('click', openLogin);
      formEl.appendChild(b);
      return;
    }
    var ta = el('textarea');
    ta.placeholder = t.placeholder;
    ta.maxLength = 1500;
    var btn = el('button', 'cm-send', esc(t.send));
    var msg = el('div', 'cm-msg');
    msg.style.display = 'none';
    formEl.appendChild(ta); formEl.appendChild(btn); formEl.appendChild(msg);

    btn.addEventListener('click', function () {
      var txt = ta.value.trim();
      if (!txt) { msg.className = 'cm-msg ko'; msg.textContent = t.empty; msg.style.display = ''; return; }
      btn.disabled = true; btn.textContent = t.sending;
      var db = firebase.firestore();
      db.collection('ort_comments').add({
        itin: ITIN, itinKey: ITIN_KEY, itinTitle: TITLE, lang: LANG,
        uid: user.uid, name: user.displayName || (user.email || '').split('@')[0] || '?',
        email: user.email || '', photo: user.photoURL || '',
        text: txt, ts: firebase.firestore.FieldValue.serverTimestamp()
      }).then(function () {
        return db.collection('ort_comment_counts').doc(COUNT_KEY).set({
          itin: ITIN, itinKey: ITIN_KEY, lang: LANG, title: TITLE,
          n: firebase.firestore.FieldValue.increment(1)
        }, { merge: true });
      }).then(function () {
        try { sessionStorage.removeItem('ortCmN:' + COUNT_KEY); } catch (e) { }
        msg.className = 'cm-msg'; msg.textContent = t.sent; msg.style.display = '';
        ta.value = '';
        btn.disabled = false; btn.textContent = t.send;
        loadComments();
      }).catch(function (e) {
        console.warn('[ORT-CM] envoi impossible', e);
        msg.className = 'cm-msg ko'; msg.textContent = t.err; msg.style.display = '';
        btn.disabled = false; btn.textContent = t.send;
      });
    });
  }

  /* ---------- Boutons d'alerte ---------- */
  // Bouton general, pose a cote du titre de l'itineraire.
  function addMainFlag() {
    var h1 = document.querySelector('.hr h1') || document.querySelector('h1');
    if (!h1 || h1.querySelector('.ort-flag')) return;
    var b = el('button', 'ort-flag ort-flag-h1', '!');
    b.type = 'button';
    b.title = t.alertTip;
    b.setAttribute('data-tip', t.alertTip);
    b.setAttribute('aria-label', t.alertTip);
    b.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      openAlert('general', TITLE, '', '');
    });
    h1.appendChild(b);
  }

  function addFlags(root) {
    // Un seul bouton par etape, pose a cote de son nom.
    root.querySelectorAll('.ds .dh h3').forEach(function (titre) {
      if (titre.querySelector('.ort-flag')) return;
      var b = el('button', 'ort-flag', '!');
      b.type = 'button';
      b.title = t.alertTip;
      b.setAttribute('data-tip', t.alertTip);
      b.setAttribute('aria-label', t.alertTip);
      b.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        var sec = titre.closest('.ds');
        var day = sec ? (sec.getAttribute('data-day') || '') : '';
        var nom = (titre.textContent || '').replace('!', '').trim().replace(/\s+/g, ' ').slice(0, 120);
        openAlert('etape', nom, day, '');
      });
      titre.appendChild(b);
    });
  }

  function openAlert(kind, label, day, extra) {
    if (document.getElementById('ortAlOv')) return;
    var ov = el('div'); ov.id = 'ortAlOv';
    var bx = el('div'); bx.id = 'ortAlBox';
    if (LANG === 'ar') bx.setAttribute('dir', 'rtl');
    bx.innerHTML = '<h4>\u26A0 ' + esc(t.alertTitle) + '</h4>'
      + '<p class="al-tg">' + esc(label || TITLE) + (day ? ' \u00b7 J' + esc(day) : '') + '</p>'
      + '<textarea id="alTx" placeholder="' + esc(t.alertPh) + '" maxlength="1200"></textarea>'
      + '<div class="al-row"><button class="cm-send" id="alGo">' + esc(t.send) + '</button>'
      + '<button class="al-cancel" id="alNo">' + esc(t.cancel) + '</button>'
      + '<span class="al-msg" id="alMsg"></span></div>';
    ov.appendChild(bx);
    document.body.appendChild(ov);

    ov.addEventListener('click', function (e) { if (e.target === ov) ov.remove(); });
    bx.querySelector('#alNo').addEventListener('click', function () { ov.remove(); });

    bx.querySelector('#alGo').addEventListener('click', function () {
      var ta = bx.querySelector('#alTx');
      var msg = bx.querySelector('#alMsg');
      var go = bx.querySelector('#alGo');
      var txt = ta.value.trim();
      if (!txt) { msg.className = 'al-msg ko'; msg.textContent = t.empty; return; }
      go.disabled = true; go.textContent = t.sending;
      fbReady().then(function () {
        var u = currentUser();
        return firebase.firestore().collection('ort_alerts').add({
          itin: ITIN, itinKey: ITIN_KEY, itinTitle: TITLE, lang: LANG,
          kind: kind, label: label || '', day: day || '', extra: extra || '',
          url: location.href, text: txt,
          uid: u ? u.uid : '', email: u ? (u.email || '') : '',
          name: u ? (u.displayName || '') : '',
          done: false, ts: firebase.firestore.FieldValue.serverTimestamp()
        });
      }).then(function () {
        msg.className = 'al-msg'; msg.textContent = t.alertSent;
        setTimeout(function () { ov.remove(); }, 1400);
      }).catch(function (e) {
        console.warn('[ORT-AL] envoi impossible', e);
        msg.className = 'al-msg ko'; msg.textContent = t.err;
        go.disabled = false; go.textContent = t.send;
      });
    });
  }

  function scan() {
    try { addMainFlag(); } catch (e) { }
    try { addFlags(document); } catch (e) { }
  }
  scan();
  setTimeout(scan, 1200);
  setTimeout(scan, 3500);
  var tp = document.getElementById('textPanel') || document.body;
  try {
    new MutationObserver(function () {
      clearTimeout(window.__ortFlagT);
      window.__ortFlagT = setTimeout(scan, 400);
    }).observe(tp, { childList: true, subtree: true });
  } catch (e) { }

  window.ortOpenAlert = openAlert;
})();
