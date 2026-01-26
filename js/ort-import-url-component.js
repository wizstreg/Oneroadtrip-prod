/**
 * ORT - Import URL Component avec Fallback Modal
 * À intégrer dans les pages qui ont Firebase Auth
 */

// ==========================================
// HTML À AJOUTER DANS LA PAGE
// ==========================================
/*
<!-- Bouton déclencheur -->
<button id="btnImportUrl" class="btn">🔗 Importer depuis une URL</button>

<!-- Modal Import URL -->
<div id="importUrlModal" class="ort-modal">
  <div class="ort-modal-card">
    <button class="ort-modal-close" id="btnCloseUrlModal">×</button>
    <h3>🔗 Importer un itinéraire</h3>
    <p class="ort-hint">Collez l'URL d'un article de voyage (blog, guide...)</p>
    
    <input type="url" id="importUrlInput" 
           placeholder="https://www.exemple.com/road-trip-islande" 
           class="ort-input">
    
    <div id="importUrlStatus" class="ort-status"></div>
    
    <div class="ort-actions">
      <button id="btnCancelUrl" class="ort-btn outline">Annuler</button>
      <button id="btnConfirmUrl" class="ort-btn primary">
        <span class="btn-text">Importer</span>
        <span class="btn-loader" style="display:none">⏳</span>
      </button>
    </div>
    
    <div id="urlQuotaInfo" class="ort-quota"></div>
  </div>
</div>

<!-- Modal Fallback (s'ouvre si l'IA plante) -->
<div id="importFallbackModal" class="ort-modal">
  <div class="ort-modal-card fallback">
    <button class="ort-modal-close" id="btnCloseFallback">×</button>
    
    <div class="fallback-icon">🤖💨</div>
    <h3 id="fallbackTitle">Oups, l'IA a besoin d'une pause !</h3>
    
    <div class="fallback-explain" id="fallbackExplain">
      OneRoadTrip est <strong>100% gratuit</strong> et utilise des services d'IA gratuits avec des limites d'utilisation.
    </div>
    
    <div class="fallback-solution">
      <h4 id="fallbackSolutionTitle">Pas de panique ! Import manuel en 3 clics :</h4>
      <ol id="fallbackSteps">
        <li>Ouvrez la page de l'article</li>
        <li>Sélectionnez tout (<kbd>Ctrl</kbd>+<kbd>A</kbd>) et copiez (<kbd>Ctrl</kbd>+<kbd>C</kbd>)</li>
        <li>Collez dans notre outil d'import gratuit</li>
      </ol>
    </div>
    
    <div class="fallback-actions">
      <a id="fallbackOpenUrl" href="#" target="_blank" class="ort-btn outline">
        🔗 Ouvrir l'article
      </a>
      <a href="./import.html" class="ort-btn primary" id="fallbackGoImport">
        📋 Aller à l'import manuel
      </a>
    </div>
    
    <div class="fallback-error" id="fallbackErrorDetail"></div>
  </div>
</div>
*/

// ==========================================
// CSS À AJOUTER
// ==========================================
const ORT_IMPORT_URL_STYLES = `
<style id="ortImportUrlStyles">
/* Modal base */
.ort-modal {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.6);
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: 20px;
}
.ort-modal.active { display: flex; }

.ort-modal-card {
  position: relative;
  width: 100%;
  max-width: 480px;
  background: #fff;
  border-radius: 16px;
  padding: 28px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25);
  animation: ortSlideUp 0.3s ease;
}

@keyframes ortSlideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.ort-modal-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  border: none;
  background: #f1f5f9;
  border-radius: 50%;
  font-size: 20px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}
.ort-modal-close:hover {
  background: #e2e8f0;
  color: #334155;
}

.ort-modal-card h3 {
  margin: 0 0 8px;
  color: #113f7a;
  font-size: 20px;
}

.ort-hint {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 16px;
}

.ort-input {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 15px;
  transition: border-color 0.2s;
}
.ort-input:focus {
  outline: none;
  border-color: #113f7a;
}

.ort-status {
  display: none;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 14px;
}
.ort-status.loading { display: block; background: #fef3c7; color: #92400e; }
.ort-status.error { display: block; background: #fee2e2; color: #dc2626; }
.ort-status.success { display: block; background: #dcfce7; color: #166534; }

.ort-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 20px;
}

.ort-btn {
  padding: 12px 20px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ort-btn.outline {
  background: #fff;
  color: #113f7a;
  border: 2px solid #113f7a;
}
.ort-btn.outline:hover {
  background: #f0f4f8;
}

.ort-btn.primary {
  background: #113f7a;
  color: #fff;
  border: 2px solid #113f7a;
}
.ort-btn.primary:hover {
  background: #0d2f5e;
  border-color: #0d2f5e;
}

.ort-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ort-quota {
  margin-top: 16px;
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
}

/* === FALLBACK MODAL === */
.ort-modal-card.fallback {
  max-width: 520px;
  text-align: center;
}

.fallback-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.ort-modal-card.fallback h3 {
  color: #0369a1;
  font-size: 22px;
  margin-bottom: 16px;
}

.fallback-explain {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 14px;
  color: #0c4a6e;
  margin-bottom: 20px;
}

.fallback-solution {
  text-align: left;
  background: #f8fafc;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 20px;
}

.fallback-solution h4 {
  margin: 0 0 12px;
  font-size: 15px;
  color: #334155;
}

.fallback-solution ol {
  margin: 0;
  padding-left: 20px;
}

.fallback-solution li {
  font-size: 14px;
  color: #475569;
  margin-bottom: 8px;
  line-height: 1.5;
}

.fallback-solution kbd {
  background: #e2e8f0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: monospace;
}

.fallback-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.fallback-error {
  margin-top: 16px;
  font-size: 11px;
  color: #94a3b8;
  font-family: monospace;
}

/* Mobile */
@media (max-width: 540px) {
  .ort-modal-card {
    padding: 20px;
  }
  .ort-modal-card h3 {
    font-size: 18px;
    padding-right: 30px;
  }
  .ort-actions, .fallback-actions {
    flex-direction: column;
  }
  .ort-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
`;

// ==========================================
// I18N - Traductions
// ==========================================
const ORT_IMPORT_I18N = {
  fr: {
    // Modal principal
    title: "Importer un itinéraire",
    hint: "Collez l'URL d'un article de voyage (blog, guide...)",
    placeholder: "https://www.exemple.com/road-trip-islande",
    btnCancel: "Annuler",
    btnImport: "Importer",
    loading: "⏳ Analyse de la page en cours...",
    success: "✅ Itinéraire extrait ! Redirection...",
    quotaRemaining: "{n} imports restants ce mois",
    
    // Fallback modal
    fallbackTitle: "Oups, l'IA a besoin d'une pause !",
    fallbackExplain: "OneRoadTrip est <strong>100% gratuit</strong> et utilise des services d'IA gratuits avec des limites d'utilisation.",
    fallbackSolutionTitle: "Pas de panique ! Import manuel en 3 clics :",
    fallbackStep1: "Ouvrez la page de l'article",
    fallbackStep2: "Sélectionnez tout et copiez",
    fallbackStep3: "Collez dans notre outil d'import gratuit",
    fallbackBtnOpen: "🔗 Ouvrir l'article",
    fallbackBtnManual: "📋 Aller à l'import manuel",
    fallbackErrorPrefix: "Détail technique :"
  },
  en: {
    title: "Import an itinerary",
    hint: "Paste the URL of a travel article (blog, guide...)",
    placeholder: "https://www.example.com/iceland-road-trip",
    btnCancel: "Cancel",
    btnImport: "Import",
    loading: "⏳ Analyzing page...",
    success: "✅ Itinerary extracted! Redirecting...",
    quotaRemaining: "{n} imports left this month",
    
    fallbackTitle: "Oops, the AI needs a break!",
    fallbackExplain: "OneRoadTrip is <strong>100% free</strong> and uses free AI services with usage limits.",
    fallbackSolutionTitle: "No worries! Manual import in 3 clicks:",
    fallbackStep1: "Open the article page",
    fallbackStep2: "Select all and copy",
    fallbackStep3: "Paste into our free import tool",
    fallbackBtnOpen: "🔗 Open article",
    fallbackBtnManual: "📋 Go to manual import",
    fallbackErrorPrefix: "Technical detail:"
  },
  es: {
    title: "Importar un itinerario",
    hint: "Pega la URL de un artículo de viaje (blog, guía...)",
    placeholder: "https://www.ejemplo.com/road-trip-islandia",
    btnCancel: "Cancelar",
    btnImport: "Importar",
    loading: "⏳ Analizando página...",
    success: "✅ ¡Itinerario extraído! Redirigiendo...",
    quotaRemaining: "{n} importaciones restantes este mes",
    
    fallbackTitle: "¡Ups, la IA necesita un descanso!",
    fallbackExplain: "OneRoadTrip es <strong>100% gratuito</strong> y usa servicios de IA gratuitos con límites de uso.",
    fallbackSolutionTitle: "¡Sin problema! Importación manual en 3 clics:",
    fallbackStep1: "Abre la página del artículo",
    fallbackStep2: "Selecciona todo y copia",
    fallbackStep3: "Pega en nuestra herramienta de importación gratuita",
    fallbackBtnOpen: "🔗 Abrir artículo",
    fallbackBtnManual: "📋 Ir a importación manual",
    fallbackErrorPrefix: "Detalle técnico:"
  },
  it: {
    title: "Importa un itinerario",
    hint: "Incolla l'URL di un articolo di viaggio (blog, guida...)",
    placeholder: "https://www.esempio.com/road-trip-islanda",
    btnCancel: "Annulla",
    btnImport: "Importa",
    loading: "⏳ Analisi della pagina...",
    success: "✅ Itinerario estratto! Reindirizzamento...",
    quotaRemaining: "{n} importazioni rimaste questo mese",
    
    fallbackTitle: "Ops, l'IA ha bisogno di una pausa!",
    fallbackExplain: "OneRoadTrip è <strong>100% gratuito</strong> e utilizza servizi IA gratuiti con limiti di utilizzo.",
    fallbackSolutionTitle: "Niente panico! Importazione manuale in 3 clic:",
    fallbackStep1: "Apri la pagina dell'articolo",
    fallbackStep2: "Seleziona tutto e copia",
    fallbackStep3: "Incolla nel nostro strumento di importazione gratuito",
    fallbackBtnOpen: "🔗 Apri articolo",
    fallbackBtnManual: "📋 Vai all'importazione manuale",
    fallbackErrorPrefix: "Dettaglio tecnico:"
  },
  pt: {
    title: "Importar um itinerário",
    hint: "Cole a URL de um artigo de viagem (blog, guia...)",
    placeholder: "https://www.exemplo.com/road-trip-islandia",
    btnCancel: "Cancelar",
    btnImport: "Importar",
    loading: "⏳ Analisando página...",
    success: "✅ Itinerário extraído! Redirecionando...",
    quotaRemaining: "{n} importações restantes este mês",
    
    fallbackTitle: "Ops, a IA precisa de uma pausa!",
    fallbackExplain: "OneRoadTrip é <strong>100% gratuito</strong> e usa serviços de IA gratuitos com limites de uso.",
    fallbackSolutionTitle: "Sem problema! Importação manual em 3 cliques:",
    fallbackStep1: "Abra a página do artigo",
    fallbackStep2: "Selecione tudo e copie",
    fallbackStep3: "Cole em nossa ferramenta de importação gratuita",
    fallbackBtnOpen: "🔗 Abrir artigo",
    fallbackBtnManual: "📋 Ir para importação manual",
    fallbackErrorPrefix: "Detalhe técnico:"
  },
  ar: {
    title: "استيراد خط سير",
    hint: "الصق رابط مقال السفر (مدونة، دليل...)",
    placeholder: "https://www.exemple.com/road-trip",
    btnCancel: "إلغاء",
    btnImport: "استيراد",
    loading: "⏳ جاري تحليل الصفحة...",
    success: "✅ تم استخراج خط السير! جاري التحويل...",
    quotaRemaining: "{n} استيراد متبقي هذا الشهر",
    
    fallbackTitle: "عفواً، الذكاء الاصطناعي يحتاج استراحة!",
    fallbackExplain: "OneRoadTrip <strong>مجاني 100%</strong> ويستخدم خدمات ذكاء اصطناعي مجانية مع حدود استخدام.",
    fallbackSolutionTitle: "لا تقلق! استيراد يدوي في 3 نقرات:",
    fallbackStep1: "افتح صفحة المقال",
    fallbackStep2: "حدد الكل وانسخ",
    fallbackStep3: "الصق في أداة الاستيراد المجانية",
    fallbackBtnOpen: "🔗 فتح المقال",
    fallbackBtnManual: "📋 الذهاب للاستيراد اليدوي",
    fallbackErrorPrefix: "تفاصيل تقنية:"
  }
};

// ==========================================
// JAVASCRIPT - Logique du composant
// ==========================================
(function() {
  'use strict';
  
  // Injecter les styles si pas déjà présents
  if (!document.getElementById('ortImportUrlStyles')) {
    document.head.insertAdjacentHTML('beforeend', ORT_IMPORT_URL_STYLES);
  }
  
  // Attendre que le DOM soit prêt
  function init() {
    const modal = document.getElementById('importUrlModal');
    const fallbackModal = document.getElementById('importFallbackModal');
    
    if (!modal || !fallbackModal) {
      console.warn('[ORT Import URL] Modals not found in DOM');
      return;
    }
    
    const input = document.getElementById('importUrlInput');
    const status = document.getElementById('importUrlStatus');
    const btnOpen = document.getElementById('btnImportUrl');
    const btnCancel = document.getElementById('btnCancelUrl');
    const btnClose = document.getElementById('btnCloseUrlModal');
    const btnConfirm = document.getElementById('btnConfirmUrl');
    const btnText = btnConfirm?.querySelector('.btn-text');
    const btnLoader = btnConfirm?.querySelector('.btn-loader');
    const quotaInfo = document.getElementById('urlQuotaInfo');
    
    // Fallback elements
    const btnCloseFallback = document.getElementById('btnCloseFallback');
    const fallbackOpenUrl = document.getElementById('fallbackOpenUrl');
    const fallbackErrorDetail = document.getElementById('fallbackErrorDetail');
    
    // Get language
    const lang = document.documentElement.lang?.substring(0, 2) || 'fr';
    const t = ORT_IMPORT_I18N[lang] || ORT_IMPORT_I18N.en;
    
    // URL stockée pour le fallback
    let currentUrl = '';
    
    // === MODAL PRINCIPAL ===
    
    // Ouvrir
    btnOpen?.addEventListener('click', () => {
      openModal(modal);
      input.value = '';
      status.className = 'ort-status';
      status.textContent = '';
      input.focus();
    });
    
    // Fermer
    btnCancel?.addEventListener('click', () => closeModal(modal));
    btnClose?.addEventListener('click', () => closeModal(modal));
    modal?.addEventListener('click', (e) => {
      if (e.target === modal) closeModal(modal);
    });
    
    // Importer
    btnConfirm?.addEventListener('click', async () => {
      const url = input.value.trim();
      currentUrl = url;
      
      if (!url) {
        showStatus(status, 'Veuillez entrer une URL', 'error');
        return;
      }
      
      if (!url.startsWith('http')) {
        showStatus(status, 'URL invalide (doit commencer par http)', 'error');
        return;
      }
      
      // État loading
      setLoading(btnConfirm, btnText, btnLoader, true);
      showStatus(status, t.loading, 'loading');
      
      try {
        const result = await parseUrlToItinerary(url, lang);
        
        // Afficher quota restant
        if (result.usage && quotaInfo) {
          quotaInfo.textContent = t.quotaRemaining.replace('{n}', result.usage.remaining);
        }
        
        showStatus(status, t.success, 'success');
        
        // Sauvegarder et rediriger
        const itin = result.data.itins[0];
        const country = itin.itin_id?.split('::')[0] || 'XX';
        const key = `${country}_${slugify(itin.title || 'trip')}_${Date.now()}`;
        
        localStorage.setItem(`ORT_TEMP_TRIP_${key}_itins`, JSON.stringify(result.data));
        localStorage.setItem(`ORT_TEMP_TRIP_${key}_places`, JSON.stringify(result.places));
        
        setTimeout(() => {
          redirectAfterSuccess(key);
        }, 800);
        
      } catch (err) {
        // OUVRIR LA MODAL FALLBACK
        closeModal(modal);
        openFallbackModal(err.message, currentUrl, t);
        setLoading(btnConfirm, btnText, btnLoader, false);
      }
    });
    
    // === MODAL FALLBACK ===
    
    function openFallbackModal(errorMsg, url, translations) {
      // Mettre à jour les textes traduits
      const titleEl = document.getElementById('fallbackTitle');
      const explainEl = document.getElementById('fallbackExplain');
      const solutionTitleEl = document.getElementById('fallbackSolutionTitle');
      const stepsEl = document.getElementById('fallbackSteps');
      const btnManualEl = document.getElementById('fallbackGoImport');
      
      if (titleEl) titleEl.textContent = translations.fallbackTitle;
      if (explainEl) explainEl.innerHTML = translations.fallbackExplain;
      if (solutionTitleEl) solutionTitleEl.textContent = translations.fallbackSolutionTitle;
      if (stepsEl) {
        stepsEl.innerHTML = `
          <li>${translations.fallbackStep1}</li>
          <li>${translations.fallbackStep2} (<kbd>Ctrl</kbd>+<kbd>A</kbd>, <kbd>Ctrl</kbd>+<kbd>C</kbd>)</li>
          <li>${translations.fallbackStep3}</li>
        `;
      }
      if (fallbackOpenUrl) {
        fallbackOpenUrl.href = url;
        fallbackOpenUrl.textContent = translations.fallbackBtnOpen;
      }
      if (btnManualEl) btnManualEl.textContent = translations.fallbackBtnManual;
      if (fallbackErrorDetail) {
        fallbackErrorDetail.textContent = `${translations.fallbackErrorPrefix} ${errorMsg}`;
      }
      
      openModal(fallbackModal);
    }
    
    btnCloseFallback?.addEventListener('click', () => closeModal(fallbackModal));
    fallbackModal?.addEventListener('click', (e) => {
      if (e.target === fallbackModal) closeModal(fallbackModal);
    });
  }
  
  // === HELPERS ===
  
  function openModal(modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  
  function closeModal(modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
  
  function showStatus(el, msg, type) {
    el.textContent = msg;
    el.className = `ort-status ${type}`;
  }
  
  function setLoading(btn, textEl, loaderEl, loading) {
    btn.disabled = loading;
    if (textEl) textEl.style.display = loading ? 'none' : 'inline';
    if (loaderEl) loaderEl.style.display = loading ? 'inline' : 'none';
  }
  
  function slugify(text) {
    return text.toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .substring(0, 50);
  }
  
  // Redirection selon destination choisie
  function redirectAfterSuccess(key) {
    const dest = window._ortImportDestination || 'detail';
    if (dest === 'editor') {
      // Vers le carnet de voyage
      window.location.href = `./roadtrip-editor.html?from=temp&rtKey=${key}`;
    } else {
      // Vers RT Detail (défaut)
      window.location.href = `./roadtrip_detail.html?from=temp&rtKey=${key}`;
    }
  }
  
  async function parseUrlToItinerary(url, language) {
    const user = firebase.auth().currentUser;
    if (!user) throw new Error('Connexion requise');
    
    const token = await user.getIdToken();
    
    const res = await fetch('/.netlify/functions/parse-url', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ url, language })
    });
    
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    return data;
  }
  
  // Init quand DOM prêt
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  
  // Exposer pour usage externe
  window.ORT_ImportUrl = {
    open: (options = {}) => {
      // options.destination = 'detail' | 'editor' (défaut: 'detail')
      window._ortImportDestination = options.destination || 'detail';
      const modal = document.getElementById('importUrlModal');
      if (modal) openModal(modal);
    },
    close: () => {
      const modal = document.getElementById('importUrlModal');
      if (modal) closeModal(modal);
    }
  };
  
})();
