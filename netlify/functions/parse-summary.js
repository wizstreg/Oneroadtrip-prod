/**
 * ORT - Parse Summary (Netlify Function)
 * AI: Gemini Flash → fallback OpenRouter (free text models)
 * 
 * Cache cascade:
 *   1. catalog_summaries/{catalogId}  — shared, language-agnostic
 *   2. trip_summaries/{tripId}        — per-trip fallback
 * 
 * Quota: users/{uid}/summary_usage/{month}
 */

import admin from 'firebase-admin';

if (!admin.apps.length) {
  try {
    const sa = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(sa), projectId: process.env.ORT_FB_PROJECTID });
  } catch (e) {
    admin.initializeApp({ projectId: process.env.ORT_FB_PROJECTID });
  }
}
const db = admin.firestore();

const GEMINI_KEY = process.env.GEMINI_API_KEY;
const OPENROUTER_KEY = process.env.OPENROUTER_API_KEY;
const MONTHLY_LIMIT = parseInt(process.env.SUMMARY_MONTHLY_LIMIT || '1', 10);
const VIP = ['bWFyY3NvcmNpQGZyZWUuZnI='];

// ===== HELPERS =====
function stripLangSuffix(itin) {
  if (!itin) return '';
  return itin.replace(/-(fr|en|es|it|pt|ar)$/i, '');
}

function sanitizeDocId(id) {
  return id.replace(/[\/\\]/g, '_').substring(0, 200);
}

// ===== AUTH =====
async function verifyToken(authHeader) {
  if (!authHeader?.startsWith('Bearer ')) return null;
  try { return await admin.auth().verifyIdToken(authHeader.split('Bearer ')[1]); }
  catch { return null; }
}

// ===== QUOTA =====
async function checkQuota(uid, email) {
  if (email && VIP.includes(Buffer.from(email).toString('base64'))) {
    return { allowed: true, count: 0, limit: 9999, remaining: 9999 };
  }
  const now = new Date();
  const month = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const ref = db.collection('users').doc(uid).collection('summary_usage').doc(month);
  const doc = await ref.get();
  let data = doc.exists ? doc.data() : { count: 0, month };
  if (data.count >= MONTHLY_LIMIT) {
    return { allowed: false, error: 'monthly_quota', count: data.count, limit: MONTHLY_LIMIT, remaining: 0 };
  }
  data.count++;
  await ref.set(data);
  return { allowed: true, count: data.count, limit: MONTHLY_LIMIT, remaining: MONTHLY_LIMIT - data.count };
}

// ===== CACHE CASCADE =====
async function findCachedSummary(catalogId, tripId) {
  if (catalogId) {
    try {
      const doc = await db.collection('catalog_summaries').doc(sanitizeDocId(catalogId)).get();
      if (doc.exists && doc.data().review && doc.data().steps) {
        console.log(`✅ Catalog cache hit: ${catalogId}`);
        return doc.data();
      }
    } catch (e) { console.warn('Catalog cache read:', e.message); }
  }
  if (tripId) {
    try {
      const doc = await db.collection('trip_summaries').doc(sanitizeDocId(tripId)).get();
      if (doc.exists && doc.data().review && doc.data().steps) {
        console.log(`✅ Trip cache hit: ${tripId}`);
        return doc.data();
      }
    } catch (e) { console.warn('Trip cache read:', e.message); }
  }
  return null;
}

async function saveSummary(catalogId, tripId, data, language, model) {
  const payload = { ...data, language, model, createdAt: admin.firestore.FieldValue.serverTimestamp() };
  if (catalogId) {
    try { await db.collection('catalog_summaries').doc(sanitizeDocId(catalogId)).set({ ...payload, catalogId }); }
    catch (e) { console.warn('Catalog save:', e.message); }
  }
  if (tripId && tripId !== catalogId) {
    try { await db.collection('trip_summaries').doc(sanitizeDocId(tripId)).set({ ...payload, tripId }); }
    catch (e) { console.warn('Trip save:', e.message); }
  }
}

// ===== BUILD STEPS TEXT =====
function buildStepsText(steps) {
  let day = 0;
  return steps.map((s, i) => {
    const n = s.nights || 0;
    if (n > 0) day++;
    const label = n > 0 ? `Jour ${day}` : 'Passage';
    const vis = (Array.isArray(s.visits) ? s.visits.map(v => typeof v === 'string' ? v : v.text).filter(Boolean) : []);
    const act = (Array.isArray(s.activities) ? s.activities.map(a => typeof a === 'string' ? a : a.text).filter(Boolean) : []);
    let t = `${label}: ${s.name || 'Étape '+(i+1)} (${n} nuit${n>1?'s':''})`;
    if (vis.length) t += `\n  Visites: ${vis.join(' | ')}`;
    if (act.length) t += `\n  Activités: ${act.join(' | ')}`;
    if (s.description) t += `\n  Info: ${s.description}`;
    return t;
  }).join('\n');
}

// ===== PROMPT =====
function buildPrompt(title, stepsText, lang) {
  const instr = {
    fr: `Tu es un expert en road trips. Réponds UNIQUEMENT en JSON valide (pas de texte avant/après, pas de backticks).
Format: {"review":["Points forts: ...","Points faibles: ...","Avis: pour qui, réduire/augmenter, conseil"],"steps":[{"day":1,"city":"NOM","highlights":"1-2 phrases, noms clés EN MAJUSCULES","next":"direction + distance + temps"}]}
Règles: review=3 chaînes, steps=étapes avec nuits>0, passages intégrés dans next précédent, next="" dernière étape. Concis, enthousiaste.`,
    en: `You are a road trip expert. Respond ONLY with valid JSON (no text before/after, no backticks).
Format: {"review":["Strengths: ...","Weaknesses: ...","Verdict: who, shorten/extend, tip"],"steps":[{"day":1,"city":"NAME","highlights":"1-2 sentences, key names IN CAPITALS","next":"direction + distance + time"}]}
Rules: review=3 strings, steps=stops with nights>0, pass-throughs in previous next, next="" last step. Concise, enthusiastic.`,
    es: `Experto en road trips. Responde SOLO con JSON válido (sin texto antes/después, sin backticks).
Formato: {"review":["Fuertes: ...","Débiles: ...","Veredicto: ..."],"steps":[{"day":1,"city":"CIUDAD","highlights":"1-2 frases, nombres EN MAYÚSCULAS","next":"dirección + distancia + tiempo"}]}
review=3, steps=etapas noches>0, next="" última. Conciso, entusiasta.`,
    it: `Esperto di road trip. Rispondi SOLO con JSON valido (nessun testo prima/dopo, nessun backtick).
Formato: {"review":["Forza: ...","Deboli: ...","Giudizio: ..."],"steps":[{"day":1,"city":"CITTÀ","highlights":"1-2 frasi, nomi IN MAIUSCOLO","next":"direzione + distanza + tempo"}]}
review=3, steps=tappe notti>0, next="" ultima. Conciso, entusiasta.`,
    pt: `Especialista em road trips. Responda APENAS com JSON válido (sem texto antes/depois, sem backticks).
Formato: {"review":["Fortes: ...","Fracos: ...","Veredicto: ..."],"steps":[{"day":1,"city":"CIDADE","highlights":"1-2 frases, nomes EM MAIÚSCULAS","next":"direção + distância + tempo"}]}
review=3, steps=etapas noites>0, next="" última. Conciso, entusiasta.`,
    ar: `خبير رحلات. أجب فقط بـ JSON صالح (بدون نص قبل/بعد، بدون backticks).
{"review":["القوة: ...","الضعف: ...","الحكم: ..."],"steps":[{"day":1,"city":"المدينة","highlights":"جملة أو جملتين","next":"اتجاه + مسافة + وقت"}]}
review=3, steps=مراحل بليالي>0, next="" الأخيرة.`
  };
  return `${instr[lang] || instr.en}\n\nItinéraire "${title}":\n${stepsText}`;
}

// ===== PARSE JSON RESPONSE =====
function parseAiJson(text) {
  const clean = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
  const parsed = JSON.parse(clean);
  if (!Array.isArray(parsed.review) || !Array.isArray(parsed.steps)) {
    throw new Error('Bad AI structure');
  }
  return parsed;
}

// ===== 1. GEMINI =====
async function callGemini(title, stepsText, language) {
  console.log('🤖 Trying Gemini Flash...');
  const prompt = buildPrompt(title, stepsText, language);

  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.6, maxOutputTokens: 3000, responseMimeType: 'application/json' }
      })
    });

    if (res.status === 429 || res.status >= 500) {
      console.warn(`⚠️ Gemini ${res.status} attempt ${attempt+1}`);
      if (attempt === 0) { await new Promise(r => setTimeout(r, 3000)); continue; }
      throw new Error(`Gemini ${res.status}`);
    }

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.error?.message || `Gemini HTTP ${res.status}`);
    }

    const data = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) throw new Error('Empty Gemini response');

    return { ...parseAiJson(text), model: 'gemini-2.0-flash' };
  }
  throw new Error('Gemini failed after retry');
}

// ===== 2. OPENROUTER FALLBACK =====
async function getOpenRouterTextModels() {
  const res = await fetch('https://openrouter.ai/api/v1/models', {
    headers: { 'Authorization': `Bearer ${OPENROUTER_KEY}` }
  });
  if (!res.ok) return [];
  const data = await res.json();

  // Free text models that handle JSON well
  const preferred = [
    'meta-llama/llama-3.1-8b-instruct:free',
    'meta-llama/llama-3.2-3b-instruct:free',
    'mistralai/mistral-7b-instruct:free',
    'google/gemma-2-9b-it:free',
    'qwen/qwen-2.5-7b-instruct:free'
  ];

  // Check which are actually available
  const available = data.data?.map(m => m.id) || [];
  const found = preferred.filter(m => available.includes(m));

  // If none of our preferred are available, grab any free model
  if (found.length === 0) {
    const freeModels = data.data
      ?.filter(m => m.id.includes(':free') && !m.id.includes('vision'))
      ?.map(m => m.id)
      ?.slice(0, 5) || [];
    console.log('📋 Free models found:', freeModels);
    return freeModels;
  }

  console.log('📋 Preferred models available:', found);
  return found;
}

async function callOpenRouter(title, stepsText, language) {
  console.log('📸 Fallback OpenRouter Text...');

  const models = await getOpenRouterTextModels();
  if (models.length === 0) throw new Error('Aucun modèle texte gratuit');

  const prompt = buildPrompt(title, stepsText, language);

  for (const model of models) {
    try {
      console.log('  Essai:', model);
      const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${OPENROUTER_KEY}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://oneroadtrip.co'
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.6,
          max_tokens: 3000
        })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        console.warn(`  ❌ ${model}:`, JSON.stringify(errData).substring(0, 200));
        continue;
      }

      const data = await res.json();
      const text = data.choices?.[0]?.message?.content?.trim();
      if (!text) { console.warn(`  ❌ ${model}: empty response`); continue; }

      try {
        const parsed = parseAiJson(text);
        console.log(`  ✅ Succès avec ${model}`);
        return { ...parsed, model };
      } catch (parseErr) {
        console.warn(`  ❌ ${model}: JSON parse failed:`, text.substring(0, 200));
        continue;
      }
    } catch (e) {
      console.warn(`  ❌ ${model}:`, e.message);
    }
  }
  throw new Error('Tous les modèles texte ont échoué');
}

// ===== MAIN AI CALL =====
async function generateSummary(title, stepsText, language) {
  // 1. Gemini
  if (GEMINI_KEY) {
    try {
      return await callGemini(title, stepsText, language);
    } catch (e) {
      console.warn('❌ Gemini échoué:', e.message);
    }
  }

  // 2. OpenRouter fallback
  if (OPENROUTER_KEY) {
    try {
      return await callOpenRouter(title, stepsText, language);
    } catch (e) {
      console.warn('❌ OpenRouter échoué:', e.message);
    }
  }

  throw new Error('Aucune API IA disponible');
}

// ===== HANDLER =====
export default async (request, context) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };
  if (request.method === 'OPTIONS') return new Response('', { status: 204, headers });
  if (request.method !== 'POST') return new Response(JSON.stringify({ success: false, error: 'Method not allowed' }), { status: 405, headers });

  try {
    const { tripId, catalogId: rawCatalogId, title, steps, language, cacheOnly } = await request.json();

    // Build language-agnostic catalogId
    let catalogId = null;
    if (rawCatalogId) {
      const parts = rawCatalogId.split('_');
      if (parts.length >= 2) {
        catalogId = parts[0] + '_' + stripLangSuffix(parts.slice(1).join('_'));
      } else {
        catalogId = stripLangSuffix(rawCatalogId);
      }
    }

    if (!catalogId && !tripId) {
      return new Response(JSON.stringify({ success: false, error: 'catalogId or tripId required' }), { status: 400, headers });
    }
    if (!steps || !Array.isArray(steps) || steps.length === 0) {
      return new Response(JSON.stringify({ success: false, error: 'steps required' }), { status: 400, headers });
    }

    // Auth
    const user = await verifyToken(request.headers.get('authorization'));
    if (!user) {
      return new Response(JSON.stringify({ success: false, error: 'auth_required' }), { status: 401, headers });
    }

    // 1) Cache cascade
    const cached = await findCachedSummary(catalogId, tripId);
    if (cached) {
      return new Response(JSON.stringify({
        success: true,
        data: { review: cached.review, steps: cached.steps, fromCache: true }
      }), { status: 200, headers });
    }

    // 2) cacheOnly
    if (cacheOnly) {
      return new Response(JSON.stringify({ success: false, error: 'no_cache' }), { status: 200, headers });
    }

    // 3) Quota
    const quota = await checkQuota(user.uid, user.email);
    if (!quota.allowed) {
      return new Response(JSON.stringify({ success: false, error: quota.error, usage: quota }), { status: 429, headers });
    }

    // 4) Generate: Gemini → OpenRouter
    const lang = language || 'fr';
    let aiResult;
    try {
      aiResult = await generateSummary(title || 'Road Trip', buildStepsText(steps), lang);
    } catch (aiErr) {
      console.error('❌ All AI failed:', aiErr.message);
      return new Response(JSON.stringify({
        success: false,
        error: 'ai_overloaded',
        message: aiErr.message,
        usage: quota
      }), { status: 503, headers });
    }

    // 5) Save to both caches
    await saveSummary(catalogId, tripId, { review: aiResult.review, steps: aiResult.steps }, lang, aiResult.model);

    return new Response(JSON.stringify({
      success: true,
      data: { review: aiResult.review, steps: aiResult.steps, fromCache: false },
      model: aiResult.model,
      usage: quota
    }), { status: 200, headers });

  } catch (e) {
    console.error('❌', e.message);
    return new Response(JSON.stringify({ success: false, error: e.message }), { status: 500, headers });
  }
};
