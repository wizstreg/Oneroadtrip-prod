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

// ===== PROMPT (Based on import.html, output in user's language) =====
function buildPrompt(language) {
  const langName = LANG_NAMES[language] || 'English';
  const langCode = language || 'en';
  
  return `You are a structured data extractor. Output ONLY valid JSON, no text, no Markdown.

🚨 SOURCE FIDELITY: The user chose this itinerary because they LIKE it.
- Extract ONLY places/activities explicitly mentioned in the source
- Keep the SAME number of days and stops
- Do NOT add places or activities not in the source
- You CAN and SHOULD enrich descriptions with verifiable facts (dates, dimensions, historical details)

Transform SOURCE content into JSON "itins" (SINGLE object). Follow this reference example:

{
  "itins": [{
    "itin_id": "FR::23::creuse-painters-valley",
    "language": "${langCode}",
    "created_at": "${new Date().toISOString().split('T')[0]}T12:00:00Z",
    "source_url": "",
    "dept_code": "23",
    "dept_name": "Creuse",
    "title": "Painters' Valley and Aubusson Tapestries",
    "subtitle": "Following Monet and the weavers through secret Creuse",
    "seo_keywords": ["Creuse painters valley", "Aubusson tapestry UNESCO", "Monet Fresselines"],
    "estimated_days_base": 2,
    "pacing_rules": {
      "factors": {"slow": 1.25, "standard": 1.0, "fast": 0.75},
      "merge_threshold": 0.85
    },
    "practical_context": {
      "best_months": ["May", "June", "September", "October"],
      "vehicle_type": "Standard car, winding but well-maintained roads",
      "group_type": "Couples, families, art and nature enthusiasts",
      "loop_type": "Loop La Souterraine ↔ Guéret",
      "total_km": 85,
      "daily_average_km": 43,
      "highlights": [
        "International City of Tapestry in Aubusson, UNESCO heritage",
        "Painters' Valley where Monet painted 23 canvases in 1889",
        "Medieval fortress of Crozant overlooking the confluence"
      ]
    },
    "ai_suggestions": {
      "nearby_gems": [
        "Abbaye de La Prée : abbaye cistercienne du XIIe siècle à 20 min, cadre paisible.",
        "Lac de Vassivière : plus grand lac artificiel du Limousin, baignade et art contemporain."
      ],
      "practical_tips": [
        "Privilégiez mai-juin pour les paysages verts sans la foule estivale.",
        "L'Espace Monet-Rollinat ferme entre 12h30 et 14h."
      ],
      "warnings": [
        "Routes sinueuses, attention aux virages serrés.",
        "Peu de stations-service après Guéret."
      ]
    },
    "days_plan": [
      {
        "day": 1,
        "slice": 1,
        "region_code": "FR-23",
        "suggested_days": 1.0,
        "night": {
          "place_id": "FR::fresselines",
          "coords": [46.3811, 1.6481]
        },
        "visits": [
          {
            "text": "Claude Monet stayed in Fresselines from March to May 1889 and painted 23 canvases there. Ten depict the confluence of the two Creuse rivers, nicknamed 'Les Eaux Semblantes'. This was his first true series on the same subject under different lights, a technique he later refined with the Haystacks and Cathedrals.",
            "place_id": "FR::fresselines",
            "coords": [46.3811, 1.6481],
            "visit_duration_min": 30
          },
          {
            "text": "The Monet-Rollinat Center, opened in 2018, displays reproductions of Monet's Creuse paintings and commemorates Maurice Rollinat, poet of Les Névroses who lived here for twenty years.",
            "place_id": "FR::fresselines::espace-monet-rollinat",
            "coords": [46.3815, 1.6485],
            "visit_duration_min": 75,
            "practical_info": {
              "hours": "April-November: Wed-Sun 10:30am-12:30pm/2pm-6pm",
              "duration": "1h to 1h30"
            }
          }
        ],
        "activities": [
          {
            "text": "The Painters' Trail (3 km) connects viewpoints immortalized by Monet. Reproductions of his paintings are installed at the exact spots where he set up his easel.",
            "place_id": "FR::fresselines::sentier-peintres",
            "coords": [46.3800, 1.6500],
            "activity_duration_min": 90,
            "practical_info": {
              "distance": "3 km",
              "duration": "1h30",
              "difficulty": "Easy"
            }
          }
        ],
        "to_next_leg": {
          "distance_km": 35,
          "drive_min": 45,
          "transport_mode": "car",
          "road_type": "Tarmac",
          "method": "heuristic"
        }
      }
    ]
  }]
}

📋 CRITICAL RULES:

1. SOURCE FIDELITY — Keep the exact places and structure from the source. Do NOT invent stops.
2. visits[] = places (monuments, museums, sites, viewpoints, waterfalls, landscapes)
3. activities[] = actions (hikes, kayaking, cycling, courses, walks, swimming)
4. ENRICH each visit/activity with verifiable facts (dates, dimensions, historical details)
5. suggested_days: 0.5 | 1.0 | 1.5 — beyond 1.5, split into multiple days
6. estimated_days_base = CEIL(sum of suggested_days)
7. to_next_leg on all days EXCEPT the last
8. coords = [lat, lon] of location — YOU provide these based on your knowledge
9. itin_id = CC::region::slug (CC = ISO2 country code)
10. slice = always 1

📋 COMPLETE ENRICHED FORMAT (REQUIRED):

11. subtitle = 1 SOBER tagline (no empty superlatives)
12. seo_keywords = 5-7 relevant SEO keywords  
13. COMPLETE practical_context: best_months, vehicle_type, group_type, loop_type, total_km, daily_average_km, highlights
14. practical_info on important activities (duration, difficulty, hours)
15. road_type REQUIRED in to_next_leg

💡 AI SUGGESTIONS (YOUR added value — MUST BE IN ${langName.toUpperCase()}):

"ai_suggestions": {
  "nearby_gems": ["2-4 places NEAR the route, not in source, worth a detour — with brief description"],
  "practical_tips": ["2-4 concrete useful tips based on your knowledge of the region"],
  "warnings": ["0-2 important cautions if relevant (road conditions, closures, safety)"]
}

⚠️ CRITICAL: ALL ai_suggestions content MUST be written in ${langName}, NOT in English!

═══════════════════════════════════════════════════════════
🚫 FORBIDDEN STYLE - AI POMPOUS EXPRESSIONS TO BAN
═══════════════════════════════════════════════════════════

❌ EMPTY VERBS AND CLICHÉS:
- "unfolds" / "déploie" (its roofs, its streets, its treasures...)
- "stands proudly/majestically" / "se dresse majestueusement"
- "invites" / "invite" (to travel, to contemplation...)
- "reveals" / "révèle" (its secrets, its mysteries...)
- "unveils" / "dévoile" (its charms, its hidden beauties...)
- "offers" / "offre" (a breathtaking panorama, an unparalleled view...)
- "bears witness to" / "témoigne de" (the grandeur, the splendor...)
- "plunges the visitor" / "plonge le visiteur"

❌ EMPTY ADJECTIVES AND SUPERLATIVES:
- "majestic", "breathtaking", "sumptuous", "grandiose"
- "must-see", "unmissable", "iconic", "incontournable", "emblématique"
- "picturesque", "authentic", "unique", "unparalleled"
- "un véritable", "une immersion totale", "un havre de paix"

✅ EXPECTED STYLE - FACTUAL AND DOCUMENTED:

GOOD: "Notre-Dame Church has the tallest bell tower in Creuse (60 meters). Built from the 11th to 13th century, it combines Romanesque and Gothic styles."
BAD: "Notre-Dame Church majestically raises its bell tower to the heavens, inviting visitors on a spiritual journey."

GOOD: "Monet stayed here from March to May 1889 and painted 23 canvases depicting the confluence."
BAD: "This picturesque village reveals the secrets of the Impressionist soul where Monet immortalized the magical light."

GOOD: "The fortress dates from the 12th century. From the ramparts, you can see the confluence below."
BAD: "The millennium-old fortress unfolds its romantic ramparts offering a breathtaking panorama."

GOLDEN RULE: Every sentence must contain VERIFIABLE INFORMATION (date, dimension, proper name, historical fact). No lyrical filler.

🚫 NEUTRALIZATION:
✅ KEEP: Museums, monuments, temples, parks, UNESCO sites, public markets
❌ REMOVE: Named businesses → "Rental agencies offer..." | People names → remove | Exact prices → omit

🌍 OUTPUT LANGUAGE: ALL texts MUST be written in ${langName}.
Set "language": "${langCode}" in the JSON.
Keep original proper nouns (Wat, Piazza, Playa, Fort, Cascade...).

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
      generationConfig: { temperature: 0.2, maxOutputTokens: 8192 }
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
          max_tokens: 8192
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
