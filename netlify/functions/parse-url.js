/**
 * ORT - Parse URL (Netlify Function)
 * Fetch URL content, parse via Gemini Flash (+ OpenRouter fallback)
 * Returns itinerary JSON in user's language
 * Quotas: 5/jour, 30/mois par user
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
const OPENROUTER_KEY = process.env.OPENROUTER_API_KEY;

const DAILY_LIMIT = parseInt(process.env.URL_PARSE_DAILY_LIMIT || '5', 10);
const MONTHLY_LIMIT = parseInt(process.env.URL_PARSE_MONTHLY_LIMIT || '30', 10);

// ===== LANGUAGE MAPPING =====
const LANG_NAMES = {
  fr: 'French',
  en: 'English',
  es: 'Spanish',
  it: 'Italian',
  pt: 'Portuguese',
  ar: 'Arabic',
  de: 'German'
};

const MONTH_NAMES = {
  fr: ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  es: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
  it: ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'],
  pt: ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],
  ar: ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'],
  de: ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
};

// ===== PROMPT (English base, output in user's language) =====
function buildPrompt(language) {
  const langName = LANG_NAMES[language] || 'English';
  const langCode = language || 'en';
  
  return `You are a structured data extractor. Produce ONLY valid JSON, no text, no Markdown.

🚨 CRITICAL: STRICT FIDELITY TO SOURCE
The user chose this itinerary because they LIKE it. Your job is to STRUCTURE it, NOT to rewrite or improve it.

⛔ ABSOLUTELY FORBIDDEN:
- DO NOT invent places, visits, or activities not mentioned in the source
- DO NOT add days or stops not in the original itinerary
- DO NOT change the itinerary order unless geographically absurd

✅ YOU MUST:
- Extract ONLY places/activities explicitly mentioned in the source
- Preserve the original tone and writing style
- Translate to target language while keeping the author's voice
- Complete technical fields (coords, place_id, region_code) that the source cannot provide

✅ YOU CAN (and should):
- Write a SHORT DESCRIPTIVE SENTENCE for each visit/activity, not just the place name
- If source says "Lac Genin" → write "Le lac Genin, surnommé le petit Canada, offre un cadre paisible en pleine forêt."
- Add FACTUAL descriptions based on your knowledge (what the place IS), this is NOT invention
- Estimate total_km and daily_average_km based on the route
- Suggest best_months based on your knowledge of the region's climate

Transform the SOURCE content into JSON "itins" (ONE object). Follow this example:

{
  "itins": [{
    "itin_id": "LA::north::luang-prabang-vang-vieng",
    "language": "${langCode}",
    "created_at": "${new Date().toISOString().split('T')[0]}T12:00:00Z",
    "source_url": "",
    "dept_code": "LP",
    "dept_name": "Luang Prabang",
    "title": "Temples and karsts of Northern Laos",
    "subtitle": "From golden temples to turquoise lagoons",
    "estimated_days_base": 2,
    "practical_context": {
      "best_months": ["May", "June", "September"],
      "vehicle_type": "Car or scooter",
      "group_type": "Couple, friends",
      "loop_type": "Luang Prabang ↔ Vang Vieng",
      "total_km": 460,
      "daily_average_km": 230,
      "highlights": [
        "Tak bat monks procession at dawn",
        "Kuang Si turquoise waterfalls",
        "Karst landscapes and caves",
        "Mekong river navigation"
      ]
    },
    "ai_suggestions": {
      "nearby_gems": [
        "Pak Ou Caves: Sacred caves with thousands of Buddha statues, 2h boat ride from Luang Prabang",
        "Nong Khiaw: Stunning limestone cliffs and peaceful riverside village, worth a 3h detour north"
      ],
      "practical_tips": [
        "Carry cash - ATMs are rare outside main towns and often empty",
        "Book Kuang Si early morning to avoid tour groups arriving at 10am",
        "Rent a scooter in Vang Vieng for flexibility between lagoons and caves"
      ],
      "warnings": [
        "Rainy season (Jul-Sep): some dirt roads to caves become impassable"
      ]
    },
    "pacing_rules": {
      "factors": {"slow": 1.25, "standard": 1.0, "fast": 0.75},
      "merge_threshold": 0.85
    },
    "days_plan": [
      {
        "day": 1,
        "slice": 1,
        "region_code": "LA-LP",
        "suggested_days": 1.5,
        "night": {
          "place_id": "LA::luang_prabang",
          "coords": [19.8856, 102.1347]
        },
        "visits": [
          {"text": "Wat Xieng Thong spreads its sweeping roofs in pure Lao style."},
          {"text": "Climb the 328 steps of Mount Phousi to overlook the peninsula."},
          {"text": "The Royal Palace now houses the national museum with the Phra Bang."},
          {"text": "Wat Mai features a gilded porch carved with Ramayana scenes."},
          {"text": "Wat Visoun, the oldest temple (1513), holds a large wooden Buddha."}
        ],
        "activities": [
          {"text": "Rise at dawn to witness tak bat, the silent monks procession.", "practical_info": {"best_time": "5:30-6:30am", "tip": "Stay quiet, no flash"}},
          {"text": "The night market takes over Sisavangvong Road from 5pm."},
          {"text": "Local cooking schools teach Lao classics.", "practical_info": {"duration": "3h"}}
        ],
        "to_next_leg": {
          "distance_km": 230,
          "drive_min": 270,
          "transport_mode": "car",
          "road_type": "Winding tarmac",
          "method": "heuristic"
        }
      }
    ]
  }]
}

📋 STRUCTURE RULES:

⚠️ CRITICAL - VISITS AND ACTIVITIES MUST BE COMPLETE SENTENCES:
   
1. visits[] = places mentioned in source — MUST BE A DESCRIPTIVE SENTENCE (1-2 lines)
   ❌ WRONG: {"text": "Lac Genin à Charix"}
   ❌ WRONG: {"text": "Cascade de Glandieu"}
   ❌ WRONG: {"text": "Pérouges"}
   ✅ CORRECT: {"text": "Le lac Genin, surnommé le petit Canada jurassien, déploie ses eaux émeraude au cœur d'une forêt de sapins centenaires."}
   ✅ CORRECT: {"text": "La cascade de Glandieu dévale 60 mètres de falaise calcaire dans un cadre sauvage et préservé."}
   ✅ CORRECT: {"text": "Pérouges, cité médiévale classée parmi les plus beaux villages de France, a conservé ses ruelles pavées et ses maisons à colombages du XVe siècle."}
   
2. activities[] = actions mentioned in source — MUST BE A DESCRIPTIVE SENTENCE
   ❌ WRONG: {"text": "Randonnée"}
   ❌ WRONG: {"text": "Randonnée de 4 à 6 heures aller/retour."}
   ✅ CORRECT: {"text": "Une randonnée de 4 à 6 heures aller-retour mène au sommet du Crêt de la Neige (1720m), point culminant du Jura, offrant un panorama sur les Alpes et le Mont-Blanc."}

3. Keep the EXACT number of days/stops from the source — do NOT add or remove
4. suggested_days: 0.5 | 1.0 | 1.5 based on source's time indications
5. estimated_days_base = number of days in the source itinerary
6. to_next_leg on all days EXCEPT the last (estimate distance based on your geographic knowledge)
7. coords = [lat, lon] — YOU provide this (lookup the real coordinates)
8. itin_id = CC::region::slug (CC = ISO2 country code)
9. region_code = CC-XX (regional code)
10. slice = always 1

⚠️ MANDATORY CALCULATIONS:
11. total_km = SUM of all to_next_leg.distance_km — MUST NOT be null
12. daily_average_km = total_km / estimated_days_base — MUST NOT be null
13. best_months = ARRAY of best months based on your knowledge of the region's climate — MUST NOT be empty
    Example for Jura/Ain region: ["mai", "juin", "septembre", "octobre"]

📋 OPTIONAL ENRICHMENT (only if source provides specific info):
14. subtitle = extract or adapt from source intro (or write a catchy one-liner)
15. practical_context.highlights = extract key points FROM the source text
16. practical_info = add to activities IF source gives duration, difficulty, tips
17. road_type = add in to_next_leg if source mentions road conditions

💡 AI SUGGESTIONS — YOUR ADDED VALUE (MUST BE IN ${langName.toUpperCase()}):
Add an "ai_suggestions" object with YOUR recommendations based on your knowledge of the region.

⚠️ CRITICAL: ALL ai_suggestions content MUST be written in ${langName}, NOT in English!

Example for French:
"ai_suggestions": {
  "nearby_gems": [
    "Abbaye d'Ambronay : Impressionnante abbaye bénédictine avec une architecture remarquable, à quelques minutes de Meximieux.",
    "Grottes du Cerdon : Grottes préhistoriques avec visites guidées et activités aventure, une expérience souterraine unique."
  ],
  "practical_tips": [
    "Privilégiez les intersaisons (printemps, automne) pour éviter la foule et profiter d'une météo agréable.",
    "Emportez des chaussures de randonnée confortables pour explorer les sites naturels.",
    "Vérifiez les horaires d'ouverture à l'avance, notamment pour le Fort l'Écluse."
  ],
  "warnings": [
    "Certaines routes de montagne sont étroites et sinueuses, prudence requise.",
    "Les abords des cascades peuvent être glissants, surtout après la pluie."
  ]
}

Rules:
- nearby_gems: 2-4 places NEAR the route, not in source, worth a detour — IN ${langName.toUpperCase()}
- practical_tips: 2-4 concrete tips from your knowledge — IN ${langName.toUpperCase()}
- warnings: 0-2 cautions if relevant — IN ${langName.toUpperCase()}
- Keep each item to 1-2 sentences max

✍️ WRITING STYLE — MATCH THE SOURCE:
- If source is enthusiastic, be enthusiastic
- If source is factual and concise, stay factual and concise
- If source uses "you/your", keep that personal tone
- If source is descriptive, preserve that richness
- Translate but PRESERVE the author's voice and style

🚫 NEUTRALIZATION (apply only these):
- Remove specific business names → use generic terms
- Remove specific people names (unless historical figures)
- Remove prices (they change)
- Remove recent dates

🚫 FORBIDDEN: 
- Inventing content not in the source
- Adding visits/activities to "fill" days
- Changing the itinerary structure

🌍 OUTPUT LANGUAGE: ALL texts (title, subtitle, visits, activities, highlights, practical_context) MUST be written in ${langName}. Keep original proper nouns (Wat, Piazza, Playa...).
Set "language": "${langCode}" in the JSON.

⚠️ FINAL CHECKLIST — VERIFY BEFORE OUTPUT:
□ ALL visits have DESCRIPTIVE SENTENCES (not just place names)
□ ALL activities have DESCRIPTIVE SENTENCES  
□ best_months is NOT empty — suggest based on region climate
□ total_km is calculated (sum of all distances)
□ daily_average_km is calculated
□ ai_suggestions is written in ${langName.toUpperCase()}, NOT English
□ All text content is in ${langName}

SOURCE:
`;
}

// ===== AUTH =====
async function verifyToken(authHeader) {
  if (!authHeader?.startsWith('Bearer ')) return null;
  try {
    return await admin.auth().verifyIdToken(authHeader.split('Bearer ')[1]);
  } catch { return null; }
}

// ===== QUOTA =====
const VIP = ['bWFyY3NvcmNpQGZyZWUuZnI=']; // base64

async function checkQuota(uid, email) {
  // VIP bypass
  if (email && VIP.includes(Buffer.from(email).toString('base64'))) {
    return { allowed: true, count: 0, limit: 9999, remaining: 9999 };
  }
  
  const ref = db.collection('users').doc(uid).collection('url_parse_usage');
  const now = new Date();
  const month = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const today = now.toISOString().split('T')[0];
  
  const monthRef = ref.doc(month);
  const dayRef = ref.doc(today);
  
  const [monthDoc, dayDoc] = await Promise.all([monthRef.get(), dayRef.get()]);
  
  let monthData = monthDoc.exists ? monthDoc.data() : { count: 0 };
  let dayData = dayDoc.exists ? dayDoc.data() : { count: 0 };

  if (monthData.count >= MONTHLY_LIMIT) {
    return { allowed: false, error: 'Monthly quota reached', count: monthData.count, limit: MONTHLY_LIMIT, remaining: 0 };
  }
  if (dayData.count >= DAILY_LIMIT) {
    return { allowed: false, error: 'Daily quota reached', count: monthData.count, limit: MONTHLY_LIMIT, remaining: MONTHLY_LIMIT - monthData.count };
  }

  // Increment
  await Promise.all([
    monthRef.set({ count: (monthData.count || 0) + 1, month }),
    dayRef.set({ count: (dayData.count || 0) + 1, date: today })
  ]);

  return { allowed: true, count: monthData.count + 1, limit: MONTHLY_LIMIT, remaining: MONTHLY_LIMIT - monthData.count - 1 };
}

// ===== FETCH URL =====
async function fetchUrlContent(url) {
  console.log('🌐 Fetching URL:', url);
  
  const res = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.5'
    },
    redirect: 'follow'
  });
  
  if (!res.ok) {
    throw new Error(`Failed to fetch URL: ${res.status} ${res.statusText}`);
  }
  
  const html = await res.text();
  return cleanHtmlToText(html);
}

// ===== CLEAN HTML =====
function cleanHtmlToText(html) {
  let text = html;
  
  // Remove scripts, styles, comments
  text = text.replace(/<script[\s\S]*?<\/script>/gi, '');
  text = text.replace(/<style[\s\S]*?<\/style>/gi, '');
  text = text.replace(/<!--[\s\S]*?-->/g, '');
  text = text.replace(/<noscript[\s\S]*?<\/noscript>/gi, '');
  text = text.replace(/<header[\s\S]*?<\/header>/gi, '');
  text = text.replace(/<footer[\s\S]*?<\/footer>/gi, '');
  text = text.replace(/<nav[\s\S]*?<\/nav>/gi, '');
  text = text.replace(/<aside[\s\S]*?<\/aside>/gi, '');
  
  // Replace common block elements with newlines
  text = text.replace(/<\/?(p|div|br|h[1-6]|li|tr)[^>]*>/gi, '\n');
  
  // Remove all remaining HTML tags
  text = text.replace(/<[^>]+>/g, ' ');
  
  // Decode HTML entities
  text = text.replace(/&nbsp;/g, ' ')
             .replace(/&amp;/g, '&')
             .replace(/&lt;/g, '<')
             .replace(/&gt;/g, '>')
             .replace(/&quot;/g, '"')
             .replace(/&#39;/g, "'")
             .replace(/&#x27;/g, "'")
             .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(n));
  
  // Clean whitespace
  text = text.replace(/\s+/g, ' ');
  text = text.replace(/\n\s*\n/g, '\n');
  text = text.trim();
  
  // Limit length (Gemini context)
  if (text.length > 30000) {
    text = text.substring(0, 30000) + '... [truncated]';
  }
  
  return text;
}

// ===== GEMINI =====
async function callGemini(content, language) {
  console.log('🔄 Calling Gemini Flash...');
  
  const prompt = buildPrompt(language);
  
  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt + '\n\n' + content }] }],
      generationConfig: { temperature: 0.2, maxOutputTokens: 4096 }
    })
  });
  
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error?.message || 'Gemini error');
  }
  
  const data = await res.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error('Empty Gemini response');
  
  return { text, model: 'Gemini Flash' };
}

// ===== OPENROUTER FALLBACK =====
async function getOpenRouterFreeModels() {
  const res = await fetch('https://openrouter.ai/api/v1/models', {
    headers: { 'Authorization': `Bearer ${OPENROUTER_KEY}` }
  });
  if (!res.ok) return [];
  const data = await res.json();
  
  return data.data
    .filter(m => m.pricing && parseFloat(m.pricing.prompt) === 0 && parseFloat(m.pricing.completion) === 0)
    .filter(m => m.context_length >= 16000) // Need decent context
    .map(m => m.id)
    .slice(0, 5);
}

async function callOpenRouter(content, language) {
  console.log('🔄 Fallback to OpenRouter...');
  
  const freeModels = await getOpenRouterFreeModels();
  console.log('📋 Free models:', freeModels);
  
  if (freeModels.length === 0) throw new Error('No free models available');
  
  const prompt = buildPrompt(language);
  
  for (const model of freeModels) {
    try {
      console.log('🔄 Trying', model);
      const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${OPENROUTER_KEY}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://oneroadtrip.co'
        },
        body: JSON.stringify({
          model: model,
          messages: [
            { role: 'system', content: prompt },
            { role: 'user', content: content }
          ],
          temperature: 0.2,
          max_tokens: 4096
        })
      });

      if (!res.ok) continue;

      const data = await res.json();
      const text = data.choices?.[0]?.message?.content?.trim();
      if (text) {
        console.log('✅ Success with:', model);
        return { text, model };
      }
    } catch (e) {
      console.warn('❌', model, e.message);
    }
  }
  
  throw new Error('All models failed');
}

// ===== PARSE URL =====
async function parseUrl(url, language) {
  // 1. Fetch content
  const content = await fetchUrlContent(url);
  
  if (content.length < 100) {
    throw new Error('Page content too short or empty');
  }
  
  // 2. Gemini
  if (GEMINI_KEY) {
    try {
      return await callGemini(content, language);
    } catch (e) {
      console.warn('❌ Gemini failed:', e.message);
    }
  }
  
  // 3. OpenRouter fallback
  if (OPENROUTER_KEY) {
    return await callOpenRouter(content, language);
  }
  
  throw new Error('No API configured');
}

// ===== CLEAN JSON =====
function cleanJSON(text) {
  let c = text.trim();
  if (c.startsWith('```json')) c = c.slice(7);
  if (c.startsWith('```')) c = c.slice(3);
  if (c.endsWith('```')) c = c.slice(0, -3);
  return c.trim();
}

// ===== VALIDATE & ENHANCE =====
function validateAndEnhance(data, sourceUrl) {
  if (!data.itins || !Array.isArray(data.itins) || data.itins.length === 0) {
    throw new Error('Missing or empty "itins" array');
  }
  
  const itin = data.itins[0];
  
  // Add source_url
  itin.source_url = sourceUrl;
  
  // Ensure required fields
  if (!itin.itin_id) {
    const cc = itin.country || 'XX';
    const slug = (itin.title || 'trip').toLowerCase().replace(/[^a-z0-9]+/g, '-').substring(0, 30);
    itin.itin_id = `${cc}::imported::${slug}`;
  }
  
  if (!itin.created_at) {
    itin.created_at = new Date().toISOString();
  }
  
  if (!itin.pacing_rules) {
    itin.pacing_rules = {
      factors: { slow: 1.25, standard: 1.0, fast: 0.75 },
      merge_threshold: 0.85
    };
  }
  
  // Validate days_plan
  if (!itin.days_plan || !Array.isArray(itin.days_plan)) {
    throw new Error('Missing days_plan array');
  }
  
  itin.days_plan.forEach((day, idx) => {
    if (!day.day) day.day = idx + 1;
    if (!day.slice) day.slice = 1;
    if (!day.suggested_days) day.suggested_days = 1;
    if (!day.visits) day.visits = [];
    if (!day.activities) day.activities = [];
  });
  
  // Calculate estimated_days_base if missing
  if (!itin.estimated_days_base) {
    const total = itin.days_plan.reduce((sum, d) => sum + (d.suggested_days || 1), 0);
    itin.estimated_days_base = Math.ceil(total);
  }
  
  return data;
}

// ===== GENERATE PLACES =====
function generatePlacesFromItin(data) {
  const places = [];
  const seen = new Set();
  
  data.itins.forEach(itin => {
    itin.days_plan?.forEach(day => {
      if (day.night?.place_id && !seen.has(day.night.place_id)) {
        seen.add(day.night.place_id);
        const [cc, slug] = day.night.place_id.split('::');
        places.push({
          place_id: day.night.place_id,
          name: slug?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Unknown',
          coords: day.night.coords || [0, 0],
          country: cc || 'XX',
          region_code: day.region_code || `${cc}-00`
        });
      }
    });
  });
  
  return { places };
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
    const { url, language } = await request.json();
    
    // Validate URL
    if (!url) {
      return new Response(JSON.stringify({ success: false, error: 'URL required' }), { status: 400, headers });
    }
    
    let parsedUrl;
    try {
      parsedUrl = new URL(url);
      if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
        throw new Error('Invalid protocol');
      }
    } catch {
      return new Response(JSON.stringify({ success: false, error: 'Invalid URL format' }), { status: 400, headers });
    }

    // Auth
    const user = await verifyToken(request.headers.get('authorization'));
    if (!user) {
      return new Response(JSON.stringify({ success: false, error: 'Authentication required' }), { status: 401, headers });
    }

    // Quota
    const quota = await checkQuota(user.uid, user.email);
    if (!quota.allowed) {
      return new Response(JSON.stringify({ success: false, error: quota.error, usage: quota }), { status: 429, headers });
    }

    // Parse URL
    const result = await parseUrl(url, language || 'en');
    const data = JSON.parse(cleanJSON(result.text));
    
    // Validate and enhance
    const enhanced = validateAndEnhance(data, url);
    
    // Generate places
    const places = generatePlacesFromItin(enhanced);

    return new Response(JSON.stringify({
      success: true,
      data: enhanced,
      places: places,
      usage: quota,
      _meta: { model: result.model, source_url: url }
    }), { status: 200, headers });

  } catch (e) {
    console.error('❌ Error:', e.message);
    return new Response(JSON.stringify({ success: false, error: e.message }), { status: 500, headers });
  }
};
