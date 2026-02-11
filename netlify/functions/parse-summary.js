/**
 * ORT - Parse Summary (Netlify Function)
 * Generates AI summary of a road trip using Gemini Flash
 * Returns structured JSON: review (3 lines) + steps cards
 * Quota: 1/month per user (cached in Firestore per trip)
 */

import admin from 'firebase-admin';

// Init Firebase Admin
if (!admin.apps.length) {
  try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
      projectId: process.env.ORT_FB_PROJECTID
    });
  } catch (e) {
    admin.initializeApp({
      projectId: process.env.ORT_FB_PROJECTID
    });
  }
}
const db = admin.firestore();

const GEMINI_KEY = process.env.GEMINI_API_KEY;
const MONTHLY_LIMIT = parseInt(process.env.SUMMARY_MONTHLY_LIMIT || '1', 10);

// VIP list (unlimited)
const VIP = ['bWFyY3NvcmNpQGZyZWUuZnI=']; // base64

// ===== AUTH =====
async function verifyToken(authHeader) {
  if (!authHeader?.startsWith('Bearer ')) return null;
  try {
    return await admin.auth().verifyIdToken(authHeader.split('Bearer ')[1]);
  } catch { return null; }
}

// ===== QUOTA =====
async function checkQuota(uid, email) {
  if (email && VIP.includes(Buffer.from(email).toString('base64'))) {
    return { allowed: true, count: 0, limit: 9999, remaining: 9999 };
  }

  const ref = db.collection('users').doc(uid).collection('summary_usage');
  const now = new Date();
  const month = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;

  const monthRef = ref.doc(month);
  const monthDoc = await monthRef.get();
  let monthData = monthDoc.exists ? monthDoc.data() : { count: 0, month };

  if (monthData.count >= MONTHLY_LIMIT) {
    return {
      allowed: false,
      error: 'monthly_quota',
      count: monthData.count,
      limit: MONTHLY_LIMIT,
      remaining: 0
    };
  }

  monthData.count++;
  await monthRef.set(monthData);

  return {
    allowed: true,
    count: monthData.count,
    limit: MONTHLY_LIMIT,
    remaining: MONTHLY_LIMIT - monthData.count
  };
}

// ===== CACHE =====
async function getCachedSummary(uid, tripId) {
  try {
    const ref = db.collection('users').doc(uid).collection('trip_summaries').doc(tripId);
    const doc = await ref.get();
    if (doc.exists) return doc.data();
  } catch (e) {
    console.warn('Cache read error:', e.message);
  }
  return null;
}

async function saveSummary(uid, tripId, data) {
  try {
    const ref = db.collection('users').doc(uid).collection('trip_summaries').doc(tripId);
    await ref.set({
      ...data,
      tripId,
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    });
  } catch (e) {
    console.warn('Cache write error:', e.message);
  }
}

// ===== BUILD STEPS TEXT =====
function buildStepsText(steps) {
  let dayCounter = 0;
  return steps.map((step, idx) => {
    const nights = step.nights || 0;
    if (nights > 0) dayCounter++;
    const dayLabel = nights > 0 ? `Jour ${dayCounter}` : `Passage`;

    const visits = Array.isArray(step.visits)
      ? step.visits.map(v => typeof v === 'string' ? v : v.text).filter(Boolean)
      : [];
    const activities = Array.isArray(step.activities)
      ? step.activities.map(a => typeof a === 'string' ? a : a.text).filter(Boolean)
      : [];

    let text = `${dayLabel}: ${step.name || 'Étape ' + (idx+1)} (${nights} nuit${nights > 1 ? 's' : ''})`;
    if (visits.length) text += `\n  Visites: ${visits.join(' | ')}`;
    if (activities.length) text += `\n  Activités: ${activities.join(' | ')}`;
    if (step.description) text += `\n  Info: ${step.description}`;

    return text;
  }).join('\n');
}

// ===== PROMPT =====
function buildPrompt(title, stepsText, language) {
  const lang = language || 'fr';
  
  const instructions = {
    fr: `Tu es un expert en road trips. Analyse cet itinéraire et réponds UNIQUEMENT en JSON valide (pas de texte avant/après, pas de backticks).

Format JSON:
{
  "review": [
    "Points forts: ...",
    "Points faibles: ...",
    "Avis: pour qui, faut-il réduire/augmenter, conseil clé"
  ],
  "steps": [
    {
      "day": 1,
      "city": "NOM VILLE",
      "highlights": "Résumé des visites et activités en 1-2 phrases courtes. Mentionne les noms de lieux clés EN MAJUSCULES.",
      "next": "Direction + distance + temps (ex: Route côtière vers X, 120km, ~2h)"
    }
  ]
}

Règles:
- review: exactement 3 chaînes
- steps: une entrée par étape avec nuits > 0. Les passages (0 nuit) sont intégrés dans le "next" précédent
- highlights: condense TOUTES les visites/activités en 1-2 phrases vivantes, noms clés EN MAJUSCULES
- next: vide "" pour la dernière étape
- Concis, factuel, enthousiaste`,

    en: `You are a road trip expert. Analyze this itinerary and respond ONLY with valid JSON (no text before/after, no backticks).

JSON format:
{
  "review": [
    "Strengths: ...",
    "Weaknesses: ...",
    "Verdict: who is it for, shorten/extend, key tip"
  ],
  "steps": [
    {
      "day": 1,
      "city": "CITY NAME",
      "highlights": "Summary of visits and activities in 1-2 short sentences. Key place names IN CAPITALS.",
      "next": "Direction + distance + time (e.g.: Coastal road to X, 120km, ~2h)"
    }
  ]
}

Rules:
- review: exactly 3 strings
- steps: one entry per step with nights > 0. Pass-through stops (0 nights) merged into previous "next"
- highlights: condense ALL visits/activities into 1-2 vivid sentences, key names IN CAPITALS
- next: empty "" for last step
- Concise, factual, enthusiastic`,

    es: `Eres un experto en road trips. Responde SOLO con JSON válido.

Formato:
{
  "review": ["Puntos fuertes: ...","Puntos débiles: ...","Veredicto: ..."],
  "steps": [{"day":1,"city":"CIUDAD","highlights":"Resumen visitas 1-2 frases, nombres EN MAYÚSCULAS","next":"Dirección + distancia + tiempo"}]
}

Reglas: review=3 strings, steps=etapas con noches>0, passages en "next" anterior, highlights=1-2 frases vivas, next="" última etapa. Conciso, entusiasta.`,

    it: `Sei un esperto di road trip. Rispondi SOLO con JSON valido.

Formato:
{
  "review": ["Punti di forza: ...","Punti deboli: ...","Giudizio: ..."],
  "steps": [{"day":1,"city":"CITTÀ","highlights":"Riassunto visite 1-2 frasi, nomi IN MAIUSCOLO","next":"Direzione + distanza + tempo"}]
}

Regole: review=3 stringhe, steps=tappe con notti>0, passaggi nel "next" precedente, highlights=1-2 frasi vivaci, next="" ultima tappa. Conciso, entusiasta.`,

    pt: `Você é um especialista em road trips. Responda APENAS com JSON válido.

Formato:
{
  "review": ["Pontos fortes: ...","Pontos fracos: ...","Veredicto: ..."],
  "steps": [{"day":1,"city":"CIDADE","highlights":"Resumo visitas 1-2 frases, nomes EM MAIÚSCULAS","next":"Direção + distância + tempo"}]
}

Regras: review=3 strings, steps=etapas com noites>0, passagens no "next" anterior, highlights=1-2 frases vivas, next="" última etapa. Conciso, entusiasta.`,

    ar: `أنت خبير في رحلات الطريق. أجب فقط بـ JSON صالح.

التنسيق:
{
  "review": ["نقاط القوة: ...","نقاط الضعف: ...","الحكم: ..."],
  "steps": [{"day":1,"city":"المدينة","highlights":"ملخص الزيارات جملة أو جملتين","next":"الاتجاه + المسافة + الوقت"}]
}

القواعد: review=3 نصوص, steps=مراحل بليالي>0, highlights=جملة أو جملتين, next="" للأخيرة. موجز ومتحمس.`
  };

  const instr = instructions[lang] || instructions.en;
  return `${instr}\n\nItinéraire "${title}":\n${stepsText}`;
}

// ===== CALL GEMINI =====
async function callGemini(title, stepsText, language) {
  const prompt = buildPrompt(title, stepsText, language);

  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.6,
        maxOutputTokens: 3000,
        responseMimeType: 'application/json'
      }
    })
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error?.message || 'Gemini error');
  }

  const data = await res.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error('Empty Gemini response');

  const clean = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
  let parsed;
  try {
    parsed = JSON.parse(clean);
  } catch (e) {
    console.error('JSON parse error, raw:', text.substring(0, 500));
    throw new Error('Invalid AI response format');
  }

  if (!Array.isArray(parsed.review) || !Array.isArray(parsed.steps)) {
    throw new Error('Invalid AI response structure');
  }

  return parsed;
}

// ===== HANDLER =====
export default async (request, context) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  if (request.method === 'OPTIONS') {
    return new Response('', { status: 204, headers });
  }

  if (request.method !== 'POST') {
    return new Response(JSON.stringify({ success: false, error: 'Method not allowed' }), { status: 405, headers });
  }

  try {
    const { tripId, title, steps, language, cacheOnly } = await request.json();

    if (!tripId) {
      return new Response(JSON.stringify({ success: false, error: 'tripId required' }), { status: 400, headers });
    }
    if (!steps || !Array.isArray(steps) || steps.length === 0) {
      return new Response(JSON.stringify({ success: false, error: 'steps required' }), { status: 400, headers });
    }

    const user = await verifyToken(request.headers.get('authorization'));
    if (!user) {
      return new Response(JSON.stringify({ success: false, error: 'auth_required' }), { status: 401, headers });
    }

    // Cache first
    const cached = await getCachedSummary(user.uid, tripId);
    if (cached && cached.review && cached.steps) {
      console.log(`✅ Cache hit for trip ${tripId}`);
      return new Response(JSON.stringify({
        success: true,
        data: { review: cached.review, steps: cached.steps, fromCache: true }
      }), { status: 200, headers });
    }

    // cacheOnly mode = just check, don't generate
    if (cacheOnly) {
      return new Response(JSON.stringify({ success: false, error: 'no_cache' }), { status: 200, headers });
    }

    // Quota
    const quota = await checkQuota(user.uid, user.email);
    if (!quota.allowed) {
      return new Response(JSON.stringify({ success: false, error: quota.error, usage: quota }), { status: 429, headers });
    }

    if (!GEMINI_KEY) {
      return new Response(JSON.stringify({ success: false, error: 'AI not configured' }), { status: 500, headers });
    }

    const stepsText = buildStepsText(steps);
    const aiResult = await callGemini(title || 'Road Trip', stepsText, language || 'fr');

    await saveSummary(user.uid, tripId, aiResult);

    return new Response(JSON.stringify({
      success: true,
      data: { review: aiResult.review, steps: aiResult.steps, fromCache: false },
      usage: quota
    }), { status: 200, headers });

  } catch (e) {
    console.error('❌ Error:', e.message);
    return new Response(JSON.stringify({ success: false, error: e.message }), { status: 500, headers });
  }
};
